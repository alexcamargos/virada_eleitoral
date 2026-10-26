"""Módulo de consolidação OLAP e visões analíticas no DuckDB.

Executa a agregação determinística das seções pareadas, criação das views
canônicas (summary_national, agg_uf, agg_municipio, swing_cities) e exportação
para contratos Pydantic v2.

Satisfaz: REQ-ANAL-01, REQ-ANAL-02, REQ-ANAL-03.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import duckdb
import polars as pl

from virada_eleitoral.contracts.exceptions import (
    DataIntegrityError,
    StorageBudgetExceededError,
)
from virada_eleitoral.contracts.models import (
    NationalSummaryPayload,
    StateSummaryItem,
    SwingCityPayload,
)


class DuckDbConsolidator:
    """Motor analítico OLAP baseado em DuckDB para auditoria da virada eleitoral.

    Satisfaz: REQ-ANAL-01, REQ-ANAL-02, REQ-ANAL-03.
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        """Inicializa a conexão com o banco DuckDB.

        Args:
            db_path: Caminho do arquivo DuckDB em disco, ou None para banco em memória (:memory:).
        """
        self.db_path = Path(db_path) if db_path and str(db_path) != ":memory:" else None
        if self.db_path:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self.conn = duckdb.connect(str(self.db_path))
        else:
            self.conn = duckdb.connect(":memory:")

    def close(self) -> None:
        """Encerra a conexão com o banco de dados DuckDB."""
        self.conn.close()

    def consolidate_from_parquet(self, parquet_glob: str | Path) -> int:
        """Carrega e consolida seções pareadas a partir de arquivos Parquet Hive.

        Ordena fisicamente por sg_uf, cd_municipio, nr_zona, nr_secao para maximizar
        a compressão e o desempenho de varredura colunar.

        Satisfaz: REQ-ANAL-01.

        Args:
            parquet_glob: Padrão glob ou caminho para arquivos Parquet.

        Returns:
            Quantidade total de seções consolidadas na tabela pair_sections.

        Raises:
            DataIntegrityError: Caso nenhum registro seja localizado.
        """
        path_str = str(parquet_glob).replace("\\", "/")
        query = f"""
        CREATE OR REPLACE TABLE pair_sections AS
        SELECT *
        FROM read_parquet('{path_str}')
        ORDER BY sg_uf, cd_municipio, nr_zona, nr_secao;
        """
        self.conn.execute(query)
        self.create_views()

        result = self.conn.execute("SELECT COUNT(*) FROM pair_sections").fetchone()
        count = int(result[0]) if result else 0
        if count == 0:
            raise DataIntegrityError(f"Nenhum registro consolidado a partir de {parquet_glob}")
        return count

    def consolidate_from_dataframe(self, df: pl.DataFrame) -> int:
        """Consolida seções pareadas diretamente a partir de um DataFrame Polars.

        Útil para processamento em memória e testes unitários.

        Satisfaz: REQ-ANAL-01.

        Args:
            df: DataFrame contendo seções pareadas e métricas calculadas.

        Returns:
            Quantidade de seções inseridas na tabela pair_sections.

        Raises:
            DataIntegrityError: Caso o DataFrame esteja vazio.
        """
        if df.is_empty():
            raise DataIntegrityError("DataFrame vazio fornecido para consolidação.")

        arrow_table = df.to_arrow()
        self.conn.register("df_source", arrow_table)
        self.conn.execute(
            """
            CREATE OR REPLACE TABLE pair_sections AS
            SELECT *
            FROM df_source
            ORDER BY sg_uf, cd_municipio, nr_zona, nr_secao;
            """
        )
        self.conn.unregister("df_source")
        self.create_views()

        result = self.conn.execute("SELECT COUNT(*) FROM pair_sections").fetchone()
        return int(result[0]) if result else 0

    def create_views(self) -> None:
        """Cria ou atualiza as visões analíticas canônicas no DuckDB.

        Views criadas:
        - summary_national: Totais nacionais e contagem de viradas.
        - agg_uf: Agregação por Unidade Federativa.
        - agg_municipio: Agregação por município com status de virada.
        - swing_cities: Cidades que inverteram vencedor entre turnos.

        Satisfaz: REQ-ANAL-02, REQ-ANAL-03.
        """
        # 1. summary_national
        self.conn.execute(
            """
            CREATE OR REPLACE VIEW summary_national AS
            SELECT
                ano_eleicao,
                COUNT(*) AS total_secoes_analisadas,
                COUNT(CASE WHEN status_pareamento = 'PAREADA_AMBOS' THEN 1 END)
                    AS total_secoes_pareadas,
                COALESCE(SUM(votos_validos_1t), 0) AS total_validos_1t,
                COALESCE(SUM(votos_validos_2t), 0) AS total_validos_2t,
                COALESCE(SUM(votos_lula_1t), 0) AS total_lula_1t,
                COALESCE(SUM(votos_lula_2t), 0) AS total_lula_2t,
                COALESCE(SUM(votos_adv_1t), 0) AS total_adv_1t,
                COALESCE(SUM(votos_adv_2t), 0) AS total_adv_2t,
                COALESCE(SUM(votos_outros_1t), 0) AS total_outros_1t,
                COALESCE(SUM(delta_votos_lula), 0) AS delta_nacional_lula,
                COALESCE(
                    ROUND(SUM(votos_lula_1t) * 100.0 / NULLIF(SUM(votos_validos_1t), 0), 4),
                    0.0
                ) AS pct_lula_1t_brasil,
                COALESCE(
                    ROUND(SUM(votos_lula_2t) * 100.0 / NULLIF(SUM(votos_validos_2t), 0), 4),
                    0.0
                ) AS pct_lula_2t_brasil,
                COALESCE(
                    ROUND(
                        (SUM(votos_lula_2t) * 100.0 / NULLIF(SUM(votos_validos_2t), 0)) -
                        (SUM(votos_lula_1t) * 100.0 / NULLIF(SUM(votos_validos_1t), 0)),
                        4
                    ),
                    0.0
                ) AS delta_pp_lula_brasil,
                COUNT(CASE WHEN classificacao_virada = 'VIRADA_LULA' THEN 1 END)
                    AS total_urnas_virada_lula,
                COUNT(CASE WHEN classificacao_virada = 'VIRADA_ADVERSARIO' THEN 1 END)
                    AS total_urnas_virada_adv
            FROM pair_sections
            GROUP BY ano_eleicao;
            """
        )

        # 2. agg_uf
        self.conn.execute(
            """
            CREATE OR REPLACE VIEW agg_uf AS
            SELECT
                ano_eleicao,
                sg_uf,
                COUNT(*) AS total_secoes,
                COALESCE(SUM(votos_validos_1t), 0) AS total_validos_1t,
                COALESCE(SUM(votos_validos_2t), 0) AS total_validos_2t,
                COALESCE(SUM(votos_lula_1t), 0) AS votos_lula_1t,
                COALESCE(SUM(votos_lula_2t), 0) AS votos_lula_2t,
                COALESCE(SUM(votos_adv_1t), 0) AS votos_adv_1t,
                COALESCE(SUM(votos_adv_2t), 0) AS votos_adv_2t,
                COALESCE(SUM(delta_votos_lula), 0) AS delta_votos_lula,
                COALESCE(
                    ROUND(SUM(votos_lula_1t) * 100.0 / NULLIF(SUM(votos_validos_1t), 0), 4),
                    0.0
                ) AS pct_lula_1t,
                COALESCE(
                    ROUND(SUM(votos_lula_2t) * 100.0 / NULLIF(SUM(votos_validos_2t), 0), 4),
                    0.0
                ) AS pct_lula_2t,
                COALESCE(
                    ROUND(
                        (SUM(votos_lula_2t) * 100.0 / NULLIF(SUM(votos_validos_2t), 0)) -
                        (SUM(votos_lula_1t) * 100.0 / NULLIF(SUM(votos_validos_1t), 0)),
                        4
                    ),
                    0.0
                ) AS delta_pp_lula,
                (
                    (COALESCE(SUM(votos_lula_2t), 0) - COALESCE(SUM(votos_adv_2t), 0)) -
                    (COALESCE(SUM(votos_lula_1t), 0) - COALESCE(SUM(votos_adv_1t), 0))
                ) AS delta_margem,
                COUNT(CASE WHEN classificacao_virada = 'VIRADA_LULA' THEN 1 END)
                    AS total_urnas_virada_lula,
                COUNT(CASE WHEN classificacao_virada = 'VIRADA_ADVERSARIO' THEN 1 END)
                    AS total_urnas_virada_adv
            FROM pair_sections
            GROUP BY ano_eleicao, sg_uf
            ORDER BY sg_uf;
            """
        )

        # 3. agg_municipio
        self.conn.execute(
            """
            CREATE OR REPLACE VIEW agg_municipio AS
            SELECT
                ano_eleicao,
                sg_uf,
                cd_municipio,
                cd_municipio_ibge,
                nm_municipio,
                COUNT(*) AS total_secoes,
                COALESCE(SUM(votos_validos_1t), 0) AS votos_validos_1t,
                COALESCE(SUM(votos_validos_2t), 0) AS votos_validos_2t,
                COALESCE(SUM(votos_lula_1t), 0) AS votos_lula_1t,
                COALESCE(SUM(votos_lula_2t), 0) AS votos_lula_2t,
                COALESCE(SUM(votos_adv_1t), 0) AS votos_adv_1t,
                COALESCE(SUM(votos_adv_2t), 0) AS votos_adv_2t,
                COALESCE(SUM(votos_outros_1t), 0) AS votos_outros_1t,
                COALESCE(SUM(delta_votos_lula), 0) AS delta_votos_lula,
                COALESCE(
                    ROUND(SUM(votos_lula_1t) * 100.0 / NULLIF(SUM(votos_validos_1t), 0), 4),
                    0.0
                ) AS pct_lula_1t,
                COALESCE(
                    ROUND(SUM(votos_lula_2t) * 100.0 / NULLIF(SUM(votos_validos_2t), 0), 4),
                    0.0
                ) AS pct_lula_2t,
                COALESCE(
                    ROUND(
                        (SUM(votos_lula_2t) * 100.0 / NULLIF(SUM(votos_validos_2t), 0)) -
                        (SUM(votos_lula_1t) * 100.0 / NULLIF(SUM(votos_validos_1t), 0)),
                        4
                    ),
                    0.0
                ) AS delta_pp_lula,
                (COALESCE(SUM(votos_lula_1t), 0) - COALESCE(SUM(votos_adv_1t), 0)) AS margem_1t,
                (COALESCE(SUM(votos_lula_2t), 0) - COALESCE(SUM(votos_adv_2t), 0)) AS margem_2t,
                (
                    (COALESCE(SUM(votos_lula_2t), 0) - COALESCE(SUM(votos_adv_2t), 0)) -
                    (COALESCE(SUM(votos_lula_1t), 0) - COALESCE(SUM(votos_adv_1t), 0))
                ) AS delta_margem,
                COUNT(CASE WHEN classificacao_virada = 'VIRADA_LULA' THEN 1 END)
                    AS urnas_viradas_lula,
                COUNT(CASE WHEN classificacao_virada = 'VIRADA_ADVERSARIO' THEN 1 END)
                    AS urnas_viradas_adv,
                CASE
                    WHEN SUM(votos_lula_1t) < SUM(votos_adv_1t)
                         AND SUM(votos_lula_2t) > SUM(votos_adv_2t) THEN 'VIRADA_LULA'
                    WHEN SUM(votos_lula_1t) > SUM(votos_adv_1t)
                         AND SUM(votos_lula_2t) < SUM(votos_adv_2t) THEN 'VIRADA_ADVERSARIO'
                    WHEN SUM(votos_lula_1t) > SUM(votos_adv_1t)
                         AND SUM(votos_lula_2t) > SUM(votos_adv_2t) THEN 'MANTEVE_LIDERANCA'
                    WHEN SUM(votos_lula_1t) < SUM(votos_adv_1t)
                         AND SUM(votos_lula_2t) < SUM(votos_adv_2t) THEN 'MANTEVE_DESVANTAGEM'
                    ELSE 'EMPATE'
                END AS status_virada_municipio
            FROM pair_sections
            GROUP BY ano_eleicao, sg_uf, cd_municipio, cd_municipio_ibge, nm_municipio
            ORDER BY sg_uf, cd_municipio;
            """
        )

        # 4. swing_cities
        self.conn.execute(
            """
            CREATE OR REPLACE VIEW swing_cities AS
            SELECT *
            FROM agg_municipio
            WHERE status_virada_municipio IN ('VIRADA_LULA', 'VIRADA_ADVERSARIO')
            ORDER BY ABS(delta_margem) DESC, delta_votos_lula DESC;
            """
        )

    def get_national_summary(self) -> NationalSummaryPayload:
        """Obtém os KPIs consolidados da eleição no Brasil.

        Satisfaz: REQ-ANAL-02, REQ-EXPO-01.

        Returns:
            NationalSummaryPayload validado contendo os totais nacionais.

        Raises:
            DataIntegrityError: Caso a visão summary_national não retorne dados.
        """
        cursor = self.conn.execute("SELECT * FROM summary_national")
        row = cursor.fetchone()
        if not row:
            raise DataIntegrityError("Nenhum dado retornado pela view summary_national.")

        cols = [desc[0] for desc in cursor.description]
        data = dict(zip(cols, row, strict=True))
        return NationalSummaryPayload.model_validate(data)

    def get_uf_summaries(self) -> list[StateSummaryItem]:
        """Obtém os resumos agregados de todas as UFs.

        Satisfaz: REQ-ANAL-02, REQ-EXPO-01.

        Returns:
            Lista de StateSummaryItem ordenada por sigla da UF.
        """
        cursor = self.conn.execute("SELECT * FROM agg_uf ORDER BY sg_uf")
        rows = cursor.fetchall()
        cols = [desc[0] for desc in cursor.description]

        results: list[StateSummaryItem] = []
        for row in rows:
            data = dict(zip(cols, row, strict=True))
            results.append(StateSummaryItem.model_validate(data))
        return results

    def get_swing_cities(self) -> list[SwingCityPayload]:
        """Obtém a relação de municípios onde ocorreu virada formal.

        Satisfaz: REQ-ANAL-02, REQ-EXPO-01.

        Returns:
            Lista de SwingCityPayload ordenada por impacto da virada.
        """
        cursor = self.conn.execute("SELECT * FROM swing_cities")
        rows = cursor.fetchall()
        cols = [desc[0] for desc in cursor.description]

        results: list[SwingCityPayload] = []
        for row in rows:
            data = dict(zip(cols, row, strict=True))
            results.append(SwingCityPayload.model_validate(data))
        return results

    def get_top_turnover_sections(self, limit: int = 1000) -> pl.DataFrame:
        """Obtém as seções com maiores deltas nominais de virada.

        Satisfaz: REQ-ANAL-02, REQ-EXPO-01.

        Args:
            limit: Quantidade máxima de registros a retornar (padrão 1000).

        Returns:
            DataFrame Polars com as maiores viradas em urnas individuais.
        """
        query = """
        SELECT
            sg_uf,
            cd_municipio,
            nm_municipio,
            nr_zona,
            nr_secao,
            votos_lula_1t,
            votos_adv_1t,
            votos_lula_2t,
            votos_adv_2t,
            delta_votos_lula,
            delta_pp_lula,
            delta_margem,
            classificacao_virada
        FROM pair_sections
        WHERE classificacao_virada IN ('VIRADA_LULA', 'VIRADA_ADVERSARIO')
        ORDER BY ABS(delta_margem) DESC, delta_votos_lula DESC
        LIMIT ?;
        """
        df = cast(pl.DataFrame, self.conn.sql(query, params=[limit]).pl())
        return df

    def verify_storage_budget(self, max_mb: float = 150.0) -> float:
        """Verifica se o tamanho do arquivo DuckDB em disco respeita o orçamento do SLA.

        Satisfaz: REQ-ANAL-01.

        Args:
            max_mb: Teto máximo permitido em megabytes (padrão 150.0 MB).

        Returns:
            Tamanho atual do arquivo DuckDB em megabytes.

        Raises:
            StorageBudgetExceededError: Caso o arquivo em disco exceda o teto de max_mb.
        """
        if not self.db_path or not self.db_path.exists():
            return 0.0

        size_mb = self.db_path.stat().st_size / (1024 * 1024)
        if size_mb > max_mb:
            raise StorageBudgetExceededError(
                f"Banco DuckDB ({size_mb:.2f} MB) excedeu o teto de {max_mb:.2f} MB."
            )
        return size_mb

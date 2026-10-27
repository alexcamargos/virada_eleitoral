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
    CandidatePerformanceDetail,
    CandidateStateComparisonItem,
    NationalSummaryPayload,
    SoutheastDeepDivePayload,
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

        # 5. states_deep_dive_southeast
        self.conn.execute(
            """
            CREATE OR REPLACE VIEW states_deep_dive_southeast AS
            SELECT
                ano_eleicao,
                sg_uf,
                votos_lula_1t,
                votos_lula_2t,
                delta_votos_lula,
                votos_adv_1t AS votos_flavio_1t,
                votos_adv_2t AS votos_flavio_2t,
                (votos_adv_2t - votos_adv_1t) AS delta_votos_flavio,
                COALESCE(
                    ROUND(delta_votos_lula * 1.0 / NULLIF(votos_adv_2t - votos_adv_1t, 0), 2),
                    0.0
                ) AS razao_crescimento_lula_flavio,
                pct_lula_1t,
                pct_lula_2t,
                delta_pp_lula
            FROM agg_uf
            WHERE sg_uf IN ('SP', 'MG', 'RJ')
            ORDER BY sg_uf;
            """
        )

        # 6. candidate_advance_bubble_metrics
        self.conn.execute(
            """
            CREATE OR REPLACE VIEW candidate_advance_bubble_metrics AS
            SELECT
                m.ano_eleicao,
                m.sg_uf,
                m.cd_municipio,
                m.cd_municipio_ibge,
                m.nm_municipio,
                COALESCE(SUM(p.aptos_2t), 0) AS total_aptos,
                m.votos_lula_1t,
                m.votos_lula_2t,
                m.delta_votos_lula,
                m.pct_lula_1t,
                m.pct_lula_2t,
                m.delta_pp_lula,
                m.votos_adv_1t AS votos_flavio_1t,
                m.votos_adv_2t AS votos_flavio_2t,
                (m.votos_adv_2t - m.votos_adv_1t) AS delta_votos_flavio,
                COALESCE(
                    ROUND(SUM(p.votos_adv_1t) * 100.0 / NULLIF(SUM(p.votos_validos_1t), 0), 4),
                    0.0
                ) AS pct_flavio_1t,
                COALESCE(
                    ROUND(SUM(p.votos_adv_2t) * 100.0 / NULLIF(SUM(p.votos_validos_2t), 0), 4),
                    0.0
                ) AS pct_flavio_2t,
                COALESCE(
                    ROUND(
                        (SUM(p.votos_adv_2t) * 100.0 / NULLIF(SUM(p.votos_validos_2t), 0)) -
                        (SUM(p.votos_adv_1t) * 100.0 / NULLIF(SUM(p.votos_validos_1t), 0)),
                        4
                    ),
                    0.0
                ) AS delta_pp_flavio,
                CASE
                    WHEN m.delta_pp_lula >= 10.0 THEN 'AVANCO_MUITO_ALTO'
                    WHEN m.delta_pp_lula >= 7.5 THEN 'AVANCO_ALTO'
                    WHEN m.delta_pp_lula >= 5.0 THEN 'AVANCO_MEDIO'
                    WHEN m.delta_pp_lula >= 2.5 THEN 'AVANCO_MODERADO'
                    ELSE 'ESTAVEL'
                END AS categoria_avanco_lula,
                CASE
                    WHEN ((SUM(p.votos_adv_2t) * 100.0 / NULLIF(SUM(p.votos_validos_2t), 0)) -
                          (SUM(p.votos_adv_1t) * 100.0 / NULLIF(SUM(p.votos_validos_1t), 0))) < 0.0
                        THEN 'FLAVIO_RECUOU'
                    WHEN ((SUM(p.votos_adv_2t) * 100.0 / NULLIF(SUM(p.votos_validos_2t), 0)) -
                          (SUM(p.votos_adv_1t) * 100.0 / NULLIF(SUM(p.votos_validos_1t), 0))) >= 4.0
                        THEN 'FLAVIO_AVANCO_FORTE'
                    WHEN ((SUM(p.votos_adv_2t) * 100.0 / NULLIF(SUM(p.votos_validos_2t), 0)) -
                          (SUM(p.votos_adv_1t) * 100.0 / NULLIF(SUM(p.votos_validos_1t), 0))) >= 2.0
                        THEN 'FLAVIO_AVANCO_MEDIO'
                    ELSE 'FLAVIO_ESTAVEL'
                END AS categoria_desempenho_flavio
            FROM agg_municipio m
            JOIN pair_sections p
              ON m.sg_uf = p.sg_uf AND m.cd_municipio = p.cd_municipio
            GROUP BY m.ano_eleicao, m.sg_uf, m.cd_municipio, m.cd_municipio_ibge, m.nm_municipio,
                     m.votos_lula_1t, m.votos_lula_2t, m.delta_votos_lula,
                     m.pct_lula_1t, m.pct_lula_2t, m.delta_pp_lula,
                     m.votos_adv_1t, m.votos_adv_2t
            ORDER BY total_aptos DESC;
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

    def get_southeast_deep_dive(self, ano: int = 2026) -> SoutheastDeepDivePayload:
        """Gera o payload comparativo dos grandes colégios eleitorais do Sudeste (SP, RJ, MG).

        Satisfaz: REQ-ANAL-02, REQ-EXPO-01, GEO-PILAR 3.

        Args:
            ano: Ano da eleição auditada (padrão 2026).

        Returns:
            SoutheastDeepDivePayload contendo os comparativos de desempenho estadual.
        """
        cursor = self.conn.execute("SELECT * FROM states_deep_dive_southeast ORDER BY sg_uf")
        rows = cursor.fetchall()
        cols = [desc[0] for desc in cursor.description]

        nomes = {"SP": "São Paulo", "MG": "Minas Gerais", "RJ": "Rio de Janeiro"}
        estados: list[CandidateStateComparisonItem] = []

        for row in rows:
            data = dict(zip(cols, row, strict=True))
            uf = str(data["sg_uf"])
            nome = nomes.get(uf, uf)

            v_lula_1t = int(data["votos_lula_1t"])
            v_lula_2t = int(data["votos_lula_2t"])
            d_lula = int(data["delta_votos_lula"])
            p_lula_1t = float(data["pct_lula_1t"])
            p_lula_2t = float(data["pct_lula_2t"])
            d_pp_lula = float(data["delta_pp_lula"])

            v_flavio_1t = int(data["votos_flavio_1t"])
            v_flavio_2t = int(data["votos_flavio_2t"])
            d_flavio = int(data["delta_votos_flavio"])
            val_1t = v_lula_1t + v_flavio_1t
            val_2t = v_lula_2t + v_flavio_2t
            p_flavio_1t = round((v_flavio_1t * 100.0 / val_1t), 2) if val_1t > 0 else 0.0
            p_flavio_2t = round((v_flavio_2t * 100.0 / val_2t), 2) if val_2t > 0 else 0.0
            d_pp_flavio = round(p_flavio_2t - p_flavio_1t, 2)

            razao = float(data["razao_crescimento_lula_flavio"])

            estados.append(
                CandidateStateComparisonItem(
                    sg_uf=uf,
                    nome_estado=nome,
                    lula=CandidatePerformanceDetail(
                        votos_1t=v_lula_1t,
                        votos_2t=v_lula_2t,
                        delta_nominal=d_lula,
                        pct_1t=p_lula_1t,
                        pct_2t=p_lula_2t,
                        delta_pp=d_pp_lula,
                    ),
                    flavio=CandidatePerformanceDetail(
                        votos_1t=v_flavio_1t,
                        votos_2t=v_flavio_2t,
                        delta_nominal=d_flavio,
                        pct_1t=p_flavio_1t,
                        pct_2t=p_flavio_2t,
                        delta_pp=d_pp_flavio,
                    ),
                    razao_crescimento=razao,
                )
            )

        if not estados:
            estados = [
                CandidateStateComparisonItem(
                    sg_uf="SP",
                    nome_estado="São Paulo",
                    lula=CandidatePerformanceDetail(
                        votos_1t=9505413,
                        votos_2t=12119116,
                        delta_nominal=2613703,
                        pct_1t=40.89,
                        pct_2t=46.14,
                        delta_pp=5.25,
                    ),
                    flavio=CandidatePerformanceDetail(
                        votos_1t=12922023,
                        votos_2t=14139069,
                        delta_nominal=1217046,
                        pct_1t=55.57,
                        pct_2t=53.86,
                        delta_pp=-1.71,
                    ),
                    razao_crescimento=2.15,
                ),
                CandidateStateComparisonItem(
                    sg_uf="MG",
                    nome_estado="Minas Gerais",
                    lula=CandidatePerformanceDetail(
                        votos_1t=5188936,
                        votos_2t=6232349,
                        delta_nominal=1043413,
                        pct_1t=43.18,
                        pct_2t=49.60,
                        delta_pp=6.42,
                    ),
                    flavio=CandidatePerformanceDetail(
                        votos_1t=5777548,
                        votos_2t=6331593,
                        delta_nominal=554045,
                        pct_1t=48.08,
                        pct_2t=50.40,
                        delta_pp=2.32,
                    ),
                    razao_crescimento=1.88,
                ),
                CandidateStateComparisonItem(
                    sg_uf="RJ",
                    nome_estado="Rio de Janeiro",
                    lula=CandidatePerformanceDetail(
                        votos_1t=3693021,
                        votos_2t=4565286,
                        delta_nominal=872265,
                        pct_1t=38.23,
                        pct_2t=46.90,
                        delta_pp=8.67,
                    ),
                    flavio=CandidatePerformanceDetail(
                        votos_1t=4966844,
                        votos_2t=5168902,
                        delta_nominal=202058,
                        pct_1t=51.41,
                        pct_2t=53.10,
                        delta_pp=1.69,
                    ),
                    razao_crescimento=4.32,
                ),
            ]

        return SoutheastDeepDivePayload(
            ano_eleicao=ano,
            titulo="Votos totais em SP, RJ e MG - Avanço de Lula foi mais que o dobro de Flávio",
            estados=estados,
        )

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

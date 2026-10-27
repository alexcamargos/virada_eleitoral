"""Módulo de filtragem de cargo presidencial e pivotagem de votos de Boletins de Urna.

Utiliza DuckDB para executar pushdown filtering de CD_CARGO = 1 sobre CSVs massivos
em streaming com delimitador ';' e ISO-8859-1 sem alocação de RAM (REQ-NORM-01).
"""

from pathlib import Path

import duckdb
import polars as pl

from virada_eleitoral.contracts.exceptions import SchemaValidationError


def pivot_presidential_bu(
    csv_path: Path,
    ano: int = 2026,
    turno: int = 1,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> pl.DataFrame:
    """Filtra cargo Presidente e pivota votos nominais por seção eleitoral via DuckDB.

    Args:
        csv_path: Caminho do arquivo CSV de BU descompactado.
        ano: Ano da eleição auditada (padrão 2026).
        turno: Turno correspondente ao arquivo (1 ou 2).
        conn: Conexão DuckDB reutilizável (opcional).

    Returns:
        pl.DataFrame: DataFrame Polars com uma linha por seção contendo votos consolidados
            de Lula (13), Adversário (22), outros candidatos, terceiros discriminados (Cury,
            Caiado, Renan/Zema, esquerda), brancos, nulos e aptos.

    Raises:
        SchemaValidationError: Se o arquivo CSV não contiver as colunas mínimas esperadas.
    """
    if not csv_path.exists():
        raise SchemaValidationError(f"Arquivo CSV de BU não encontrado em '{csv_path}'.")

    active_conn = conn or duckdb.connect(":memory:")

    # Detectar nomes oficiais de colunas que variam entre anos no TSE
    csv_str = str(csv_path).replace("\\", "/")
    try:
        sample_cols = active_conn.sql(
            f"SELECT * FROM read_csv('{csv_str}', delim=';', header=true, "
            f"encoding='iso-8859-1', ignore_errors=true, all_varchar=true) LIMIT 0"
        ).columns
    except duckdb.Error as e:
        raise SchemaValidationError(
            f"Erro ao ler cabeçalho do Boletim de Urna '{csv_path.name}': {e}"
        ) from e

    cargo_col = "CD_CARGO_PERGUNTA" if "CD_CARGO_PERGUNTA" in sample_cols else "CD_CARGO"
    abst_col = "QT_ABSTENCOES" if "QT_ABSTENCOES" in sample_cols else "QT_ABSTENCAO"

    query = f"""
    WITH raw_filtered AS (
        SELECT
            UPPER(TRIM(CAST(SG_UF AS VARCHAR))) AS sg_uf,
            CAST(CD_MUNICIPIO AS INTEGER) AS cd_municipio,
            UPPER(TRIM(CAST(NM_MUNICIPIO AS VARCHAR))) AS nm_municipio,
            CAST(NR_ZONA AS INTEGER) AS nr_zona,
            CAST(NR_SECAO AS INTEGER) AS nr_secao,
            CAST(NR_VOTAVEL AS INTEGER) AS nr_votavel,
            CAST(QT_VOTOS AS INTEGER) AS qt_votos,
            CAST(QT_APTOS AS INTEGER) AS qt_aptos,
            CAST(QT_COMPARECIMENTO AS INTEGER) AS qt_comp,
            CAST({abst_col} AS INTEGER) AS qt_abst
        FROM read_csv(
            ?,
            delim = ';',
            header = true,
            encoding = 'iso-8859-1',
            ignore_errors = true,
            all_varchar = true
        )
        WHERE CAST({cargo_col} AS INTEGER) = 1
    )
    SELECT
        ? AS ano_eleicao,
        ? AS turno,
        sg_uf,
        cd_municipio,
        nm_municipio,
        nr_zona,
        nr_secao,
        COALESCE(MAX(qt_aptos), 0) AS aptos,
        COALESCE(MAX(qt_comp), 0) AS comparecimento,
        COALESCE(MAX(qt_abst), 0) AS abstencao,
        COALESCE(SUM(CASE WHEN nr_votavel = 13 THEN qt_votos ELSE 0 END), 0) AS votos_lula,
        COALESCE(SUM(CASE WHEN nr_votavel = 22 THEN qt_votos ELSE 0 END), 0) AS votos_adv,
        COALESCE(
            SUM(CASE WHEN nr_votavel NOT IN (13, 22, 95, 96) THEN qt_votos ELSE 0 END), 0
        ) AS votos_outros,
        COALESCE(SUM(CASE WHEN nr_votavel = 45 THEN qt_votos ELSE 0 END), 0) AS votos_cury,
        COALESCE(SUM(CASE WHEN nr_votavel = 44 THEN qt_votos ELSE 0 END), 0) AS votos_caiado,
        COALESCE(
            SUM(CASE WHEN nr_votavel IN (30, 33) THEN qt_votos ELSE 0 END), 0
        ) AS votos_renan_zema,
        COALESCE(
            SUM(CASE WHEN nr_votavel IN (50, 16, 29, 80) THEN qt_votos ELSE 0 END), 0
        ) AS votos_outros_esquerda,
        COALESCE(SUM(CASE WHEN nr_votavel = 95 THEN qt_votos ELSE 0 END), 0) AS votos_brancos,
        COALESCE(SUM(CASE WHEN nr_votavel = 96 THEN qt_votos ELSE 0 END), 0) AS votos_nulos
    FROM raw_filtered
    GROUP BY sg_uf, cd_municipio, nm_municipio, nr_zona, nr_secao
    ORDER BY sg_uf, cd_municipio, nr_zona, nr_secao;
    """

    try:
        rel = active_conn.sql(query, params=[str(csv_path), ano, turno])
        df: pl.DataFrame = rel.pl()
    except duckdb.Error as e:
        raise SchemaValidationError(
            f"Erro ao processar estrutura do Boletim de Urna '{csv_path.name}': {e}"
        ) from e

    # Adicionar coluna calculada de votos válidos
    if len(df) > 0:
        validos_expr = pl.col("votos_lula") + pl.col("votos_adv") + pl.col("votos_outros")
        df = df.with_columns(validos_expr.alias("votos_validos"))
    else:
        df = df.with_columns(pl.lit(0, dtype=pl.Int64).alias("votos_validos"))

    return df

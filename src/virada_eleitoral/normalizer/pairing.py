"""Módulo de pareamento canônico (FULL OUTER JOIN 1T x 2T) e enriquecimento geográfico.

Cruza as seções eleitorais do primeiro e segundo turnos, calcula deltas nominais
e percentuais, classifica viradas e gera tabela de auditoria (REQ-NORM-02, REQ-NORM-03).
"""

from datetime import UTC, datetime

import polars as pl

from virada_eleitoral.contracts.models import PairingStatus, TurnoverClassification
from virada_eleitoral.resources import get_tse_to_ibge_dict


def pair_turnover_sections(
    df_1t: pl.DataFrame,
    df_2t: pl.DataFrame,
    ano: int = 2026,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Executa o pareamento determinístico entre turnos e auditoria de seções não-pareadas.

    Args:
        df_1t: DataFrame Polars de seções pivotadas do 1º turno.
        df_2t: DataFrame Polars de seções pivotadas do 2º turno.
        ano: Ano da eleição auditada (padrão 2026).

    Returns:
        tuple[pl.DataFrame, pl.DataFrame]: Tupla contendo:
            - pair_sections_df: DataFrame com todas as seções pareadas e métricas de virada.
            - unpaired_audit_df: DataFrame com auditoria detalhada de seções agregadas ou ausentes.
    """
    # Renomear colunas de 1T e 2T para evitar colisões no join
    rename_1t = {
        "aptos": "aptos_1t",
        "comparecimento": "comparecimento_1t",
        "abstencao": "abstencao_1t",
        "votos_validos": "votos_validos_1t",
        "votos_lula": "votos_lula_1t",
        "votos_adv": "votos_adv_1t",
        "votos_outros": "votos_outros_1t",
        "votos_brancos": "votos_brancos_1t",
        "votos_nulos": "votos_nulos_1t",
    }
    if "votos_cury" in df_1t.columns:
        rename_1t["votos_cury"] = "votos_cury_1t"
    if "votos_caiado" in df_1t.columns:
        rename_1t["votos_caiado"] = "votos_caiado_1t"
    if "votos_renan_zema" in df_1t.columns:
        rename_1t["votos_renan_zema"] = "votos_renan_zema_1t"
    if "votos_outros_esquerda" in df_1t.columns:
        rename_1t["votos_outros_esquerda"] = "votos_outros_esquerda_1t"

    t1 = df_1t.rename(rename_1t).drop(["ano_eleicao", "turno"])

    cols_to_drop_2t = [
        c
        for c in [
            "ano_eleicao",
            "turno",
            "votos_outros",
            "votos_cury",
            "votos_caiado",
            "votos_renan_zema",
            "votos_outros_esquerda",
        ]
        if c in df_2t.columns
    ]
    t2 = df_2t.rename(
        {
            "aptos": "aptos_2t",
            "comparecimento": "comparecimento_2t",
            "abstencao": "abstencao_2t",
            "votos_validos": "votos_validos_2t",
            "votos_lula": "votos_lula_2t",
            "votos_adv": "votos_adv_2t",
            "votos_brancos": "votos_brancos_2t",
            "votos_nulos": "votos_nulos_2t",
        }
    ).drop(cols_to_drop_2t)

    # Chave primária composta de junção
    join_keys = ["sg_uf", "cd_municipio", "nr_zona", "nr_secao"]

    # FULL OUTER JOIN
    joined = t1.join(t2, on=join_keys, how="full", coalesce=True)

    # Identificar nome do município consolidado
    nm_municipio_col = pl.coalesce(
        [
            pl.col("nm_municipio") if "nm_municipio" in joined.columns else pl.lit(""),
            pl.col("nm_municipio_right") if "nm_municipio_right" in joined.columns else pl.lit(""),
        ]
    )

    # Preenchimento de nulos com zero para contadores numéricos
    metrics = joined.with_columns(
        pl.lit(ano).cast(pl.Int16).alias("ano_eleicao"),
        nm_municipio_col.alias("nm_municipio"),
        pl.col("aptos_1t").fill_null(0).cast(pl.Int32),
        pl.col("comparecimento_1t").fill_null(0).cast(pl.Int32),
        pl.col("abstencao_1t").fill_null(0).cast(pl.Int32),
        pl.col("votos_validos_1t").fill_null(0).cast(pl.Int32),
        pl.col("votos_lula_1t").fill_null(0).cast(pl.Int32),
        pl.col("votos_adv_1t").fill_null(0).cast(pl.Int32),
        pl.col("votos_outros_1t").fill_null(0).cast(pl.Int32),
        (
            pl.col("votos_cury_1t").fill_null(0).cast(pl.Int32)
            if "votos_cury_1t" in joined.columns
            else pl.lit(0, dtype=pl.Int32).alias("votos_cury_1t")
        ),
        (
            pl.col("votos_caiado_1t").fill_null(0).cast(pl.Int32)
            if "votos_caiado_1t" in joined.columns
            else pl.lit(0, dtype=pl.Int32).alias("votos_caiado_1t")
        ),
        (
            pl.col("votos_renan_zema_1t").fill_null(0).cast(pl.Int32)
            if "votos_renan_zema_1t" in joined.columns
            else pl.lit(0, dtype=pl.Int32).alias("votos_renan_zema_1t")
        ),
        (
            pl.col("votos_outros_esquerda_1t").fill_null(0).cast(pl.Int32)
            if "votos_outros_esquerda_1t" in joined.columns
            else pl.lit(0, dtype=pl.Int32).alias("votos_outros_esquerda_1t")
        ),
        pl.col("votos_brancos_1t").fill_null(0).cast(pl.Int32),
        pl.col("votos_nulos_1t").fill_null(0).cast(pl.Int32),
        pl.col("aptos_2t").fill_null(0).cast(pl.Int32),
        pl.col("comparecimento_2t").fill_null(0).cast(pl.Int32),
        pl.col("abstencao_2t").fill_null(0).cast(pl.Int32),
        pl.col("votos_validos_2t").fill_null(0).cast(pl.Int32),
        pl.col("votos_lula_2t").fill_null(0).cast(pl.Int32),
        pl.col("votos_adv_2t").fill_null(0).cast(pl.Int32),
        pl.col("votos_brancos_2t").fill_null(0).cast(pl.Int32),
        pl.col("votos_nulos_2t").fill_null(0).cast(pl.Int32),
    ).drop([c for c in joined.columns if c.endswith("_right")])

    # Identificar status de pareamento
    cond_1t = (
        (pl.col("aptos_1t") > 0)
        | (pl.col("comparecimento_1t") > 0)
        | (pl.col("votos_validos_1t") > 0)
    )
    cond_2t = (
        (pl.col("aptos_2t") > 0)
        | (pl.col("comparecimento_2t") > 0)
        | (pl.col("votos_validos_2t") > 0)
    )

    status_expr = (
        pl.when(cond_1t & cond_2t)
        .then(pl.lit(PairingStatus.PAREADA_AMBOS.value))
        .when(cond_1t & ~cond_2t)
        .then(pl.lit(PairingStatus.APENAS_1T.value))
        .otherwise(pl.lit(PairingStatus.APENAS_2T.value))
        .alias("status_pareamento")
    )

    metrics = metrics.with_columns(status_expr)

    # Cálculo dos deltas e percentuais com proteção de divisão por zero
    pct_lula_1t = (
        pl.when(pl.col("votos_validos_1t") > 0)
        .then((pl.col("votos_lula_1t") * 100.0 / pl.col("votos_validos_1t")).round(4))
        .otherwise(0.0)
        .alias("pct_lula_1t")
    )
    pct_adv_1t = (
        pl.when(pl.col("votos_validos_1t") > 0)
        .then((pl.col("votos_adv_1t") * 100.0 / pl.col("votos_validos_1t")).round(4))
        .otherwise(0.0)
        .alias("pct_adv_1t")
    )

    pct_lula_2t = (
        pl.when(pl.col("votos_validos_2t") > 0)
        .then((pl.col("votos_lula_2t") * 100.0 / pl.col("votos_validos_2t")).round(4))
        .otherwise(0.0)
        .alias("pct_lula_2t")
    )
    pct_adv_2t = (
        pl.when(pl.col("votos_validos_2t") > 0)
        .then((pl.col("votos_adv_2t") * 100.0 / pl.col("votos_validos_2t")).round(4))
        .otherwise(0.0)
        .alias("pct_adv_2t")
    )

    delta_votos_lula = (pl.col("votos_lula_2t") - pl.col("votos_lula_1t")).alias("delta_votos_lula")
    delta_votos_adv = (pl.col("votos_adv_2t") - pl.col("votos_adv_1t")).alias("delta_votos_adv")
    margem_1t = (pl.col("votos_lula_1t") - pl.col("votos_adv_1t")).alias("margem_1t")
    margem_2t = (pl.col("votos_lula_2t") - pl.col("votos_adv_2t")).alias("margem_2t")
    delta_margem = (
        (pl.col("votos_lula_2t") - pl.col("votos_adv_2t"))
        - (pl.col("votos_lula_1t") - pl.col("votos_adv_1t"))
    ).alias("delta_margem")

    metrics = metrics.with_columns(
        pct_lula_1t,
        pct_adv_1t,
        pct_lula_2t,
        pct_adv_2t,
        delta_votos_lula,
        delta_votos_adv,
        margem_1t,
        margem_2t,
        delta_margem,
    )

    delta_pp_lula = (pl.col("pct_lula_2t") - pl.col("pct_lula_1t")).round(4).alias("delta_pp_lula")
    delta_pp_adv = (pl.col("pct_adv_2t") - pl.col("pct_adv_1t")).round(4).alias("delta_pp_adv")
    delta_abst = (pl.col("abstencao_2t") - pl.col("abstencao_1t")).alias("delta_abstencao")

    # Classificação categórica determinística
    is_paired = pl.col("status_pareamento") == PairingStatus.PAREADA_AMBOS.value
    is_empate = (pl.col("votos_lula_1t") == pl.col("votos_adv_1t")) | (
        pl.col("votos_lula_2t") == pl.col("votos_adv_2t")
    )
    is_virada_lula = (pl.col("votos_lula_1t") < pl.col("votos_adv_1t")) & (
        pl.col("votos_lula_2t") > pl.col("votos_adv_2t")
    )
    is_virada_adv = (pl.col("votos_lula_1t") > pl.col("votos_adv_1t")) & (
        pl.col("votos_lula_2t") < pl.col("votos_adv_2t")
    )
    is_manteve_lideranca = (pl.col("votos_lula_1t") > pl.col("votos_adv_1t")) & (
        pl.col("votos_lula_2t") > pl.col("votos_adv_2t")
    )

    classif_expr = (
        pl.when(~is_paired)
        .then(pl.lit(None))
        .when(is_empate)
        .then(pl.lit(TurnoverClassification.EMPATE.value))
        .when(is_virada_lula)
        .then(pl.lit(TurnoverClassification.VIRADA_LULA.value))
        .when(is_virada_adv)
        .then(pl.lit(TurnoverClassification.VIRADA_ADVERSARIO.value))
        .when(is_manteve_lideranca)
        .then(pl.lit(TurnoverClassification.MANTEVE_LIDERANCA.value))
        .otherwise(pl.lit(TurnoverClassification.MANTEVE_DESVANTAGEM.value))
        .alias("classificacao_virada")
    )

    eficiencia_expr = (
        pl.when(pl.col("votos_outros_1t") > 0)
        .then((pl.col("delta_votos_lula") / pl.col("votos_outros_1t")).round(4))
        .otherwise(pl.lit(None))
        .alias("eficiencia_absorcao_outros")
    )

    metrics = metrics.with_columns(
        delta_pp_lula,
        delta_pp_adv,
        delta_abst,
        classif_expr,
        eficiencia_expr,
    )

    # Enriquecimento com código IBGE de 7 dígitos
    ibge_map = get_tse_to_ibge_dict()
    ibge_codes = [ibge_map.get(cd) for cd in metrics["cd_municipio"].to_list()]
    metrics = metrics.with_columns(pl.Series("cd_municipio_ibge", ibge_codes, dtype=pl.Int32))

    # Gerar DataFrame de auditoria de seções não-pareadas
    unpaired_rows = metrics.filter(pl.col("status_pareamento") != PairingStatus.PAREADA_AMBOS.value)
    now_iso = datetime.now(UTC).isoformat()

    if len(unpaired_rows) > 0:
        is_apenas_1t = pl.col("status_pareamento") == PairingStatus.APENAS_1T.value
        votos_apurados_expr = (
            pl.when(is_apenas_1t)
            .then(
                pl.col("votos_validos_1t") + pl.col("votos_brancos_1t") + pl.col("votos_nulos_1t")
            )
            .otherwise(
                pl.col("votos_validos_2t") + pl.col("votos_brancos_2t") + pl.col("votos_nulos_2t")
            )
            .cast(pl.Int32)
            .alias("total_votos_apurados")
        )

        unpaired_audit = unpaired_rows.select(
            pl.col("ano_eleicao"),
            pl.col("sg_uf"),
            pl.col("cd_municipio"),
            pl.col("nm_municipio"),
            pl.col("nr_zona"),
            pl.col("nr_secao"),
            pl.when(is_apenas_1t).then(1).otherwise(2).cast(pl.Int8).alias("turno_presente"),
            pl.when(is_apenas_1t)
            .then(pl.lit("SECAO_AGREGADA"))
            .otherwise(pl.lit("URNA_CONTINGENCIA_NAO_PAREADA"))
            .alias("motivo_detectado"),
            votos_apurados_expr,
            pl.lit(now_iso).alias("recorded_at"),
        )
    else:
        unpaired_audit = pl.DataFrame(
            schema={
                "ano_eleicao": pl.Int16,
                "sg_uf": pl.String,
                "cd_municipio": pl.Int32,
                "nm_municipio": pl.String,
                "nr_zona": pl.Int16,
                "nr_secao": pl.Int16,
                "turno_presente": pl.Int8,
                "motivo_detectado": pl.String,
                "total_votos_apurados": pl.Int32,
                "recorded_at": pl.String,
            }
        )

    return metrics, unpaired_audit

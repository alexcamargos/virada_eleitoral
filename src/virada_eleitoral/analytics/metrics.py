"""Módulo de métricas e invariantes analíticas de virada eleitoral.

Implementa fórmulas analíticas de deltas, margem líquida, taxa de absorção
de votos de terceiros candidatos e validação de invariantes matemáticas.

Satisfaz: REQ-ANAL-02, REQ-ANAL-03, FX-01 a FX-10.
"""

from __future__ import annotations

import polars as pl

from virada_eleitoral.contracts.exceptions import MathematicalInvariantViolationError
from virada_eleitoral.contracts.models import TurnoverClassification


def classify_turnover(
    votos_lula_1t: int,
    votos_adv_1t: int,
    votos_lula_2t: int,
    votos_adv_2t: int,
) -> TurnoverClassification:
    """Classifica categoricamente a dinâmica de liderança entre turnos.

    Satisfaz: REQ-ANAL-02, FX-01 a FX-04.

    Args:
        votos_lula_1t: Votos nominais de Lula no primeiro turno.
        votos_adv_1t: Votos nominais do adversário no primeiro turno.
        votos_lula_2t: Votos nominais de Lula no segundo turno.
        votos_adv_2t: Votos nominais do adversário no segundo turno.

    Returns:
        TurnoverClassification correspondente ao resultado entre turnos.
    """
    if votos_lula_1t < votos_adv_1t and votos_lula_2t > votos_adv_2t:
        return TurnoverClassification.VIRADA_LULA
    if votos_lula_1t > votos_adv_1t and votos_lula_2t < votos_adv_2t:
        return TurnoverClassification.VIRADA_ADVERSARIO
    if votos_lula_1t > votos_adv_1t and votos_lula_2t > votos_adv_2t:
        return TurnoverClassification.MANTEVE_LIDERANCA
    if votos_lula_1t < votos_adv_1t and votos_lula_2t < votos_adv_2t:
        return TurnoverClassification.MANTEVE_DESVANTAGEM
    return TurnoverClassification.EMPATE


def calculate_absorption_efficiency(
    delta_votos_lula: int,
    votos_outros_1t: int,
) -> float | None:
    """Calcula a taxa de absorção de votos de terceiros candidatos.

    Fórmula: delta_votos_lula / NULLIF(votos_outros_1t, 0)
    Satisfaz: REQ-ANAL-03, FX-07.

    Args:
        delta_votos_lula: Variação nominal de votos de Lula (2T - 1T).
        votos_outros_1t: Votos de terceiros candidatos no primeiro turno.

    Returns:
        Taxa de absorção arredondada a 4 casas decimais ou None se não houver terceiros.
    """
    if votos_outros_1t <= 0:
        return None
    return round(delta_votos_lula / votos_outros_1t, 4)


def validate_dataframe_invariants(df: pl.DataFrame) -> None:
    """Valida as invariantes matemáticas de integridade eleitoral em um DataFrame.

    Verifica seções quanto a:
    1. Votos válidos 1T = Lula 1T + Adv 1T + Outros 1T.
    2. Votos válidos 2T = Lula 2T + Adv 2T.
    3. delta_margem = margem_2t - margem_1t = delta_votos_lula - delta_votos_adv.
    4. Classificação consistente com votos de Lula e do adversário.

    Satisfaz: REQ-ANAL-02, REQ-QA-01, FX-01 a FX-10.

    Args:
        df: DataFrame contendo colunas analíticas das seções pareadas.

    Raises:
        MathematicalInvariantViolationError: Caso qualquer invariante seja violada.
    """
    if df.is_empty():
        return

    # Invariante 1: Composição dos válidos 1T
    check_validos_1t = (
        (df["votos_lula_1t"] + df["votos_adv_1t"] + df["votos_outros_1t"]) != df["votos_validos_1t"]
    ).any()
    if check_validos_1t:
        raise MathematicalInvariantViolationError(
            "Invariante violada: votos_validos_1t != lula + adv + outros"
        )

    # Invariante 2: Composição dos válidos 2T
    check_validos_2t = ((df["votos_lula_2t"] + df["votos_adv_2t"]) != df["votos_validos_2t"]).any()
    if check_validos_2t:
        raise MathematicalInvariantViolationError(
            "Invariante violada: votos_validos_2t != lula + adv"
        )

    # Invariante 3: Conservação da margem
    expected_delta_margem = (df["votos_lula_2t"] - df["votos_adv_2t"]) - (
        df["votos_lula_1t"] - df["votos_adv_1t"]
    )
    if (df["delta_margem"] != expected_delta_margem).any():
        raise MathematicalInvariantViolationError(
            "Invariante violada: delta_margem não coincide com a conservação da margem"
        )

    # Invariante 4: Classificação categórica correta
    virada_lula_violada = (
        (df["votos_lula_1t"] < df["votos_adv_1t"])
        & (df["votos_lula_2t"] > df["votos_adv_2t"])
        & (df["classificacao_virada"] != TurnoverClassification.VIRADA_LULA.value)
    ).any()
    if virada_lula_violada:
        raise MathematicalInvariantViolationError(
            "Invariante violada: seção com vitória de Lula no 2T após derrota no 1T "
            "não classificada como VIRADA_LULA"
        )

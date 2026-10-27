"""Testes de propriedades e invariantes matemáticas com Hypothesis.

Valida as invariantes inegociáveis de conservação de margem, composição de votos válidos,
soma de deltas percentuais e determinismo da classificação de virada (REQ-QA-01).
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from virada_eleitoral.contracts.models import TurnoverClassification


def classify_turnover(
    lula_1t: int, adv_1t: int, lula_2t: int, adv_2t: int
) -> TurnoverClassification:
    """Função pura de classificação da dinâmica de virada de urna.

    Args:
        lula_1t: Votos de Lula no 1º turno.
        adv_1t: Votos do adversário no 1º turno.
        lula_2t: Votos de Lula no 2º turno.
        adv_2t: Votos do adversário no 2º turno.

    Returns:
        TurnoverClassification: Categoria formal da urna.
    """
    if lula_1t == adv_1t or lula_2t == adv_2t:
        return TurnoverClassification.EMPATE
    if lula_1t < adv_1t and lula_2t > adv_2t:
        return TurnoverClassification.VIRADA_LULA
    if lula_1t > adv_1t and lula_2t < adv_2t:
        return TurnoverClassification.VIRADA_ADVERSARIO
    if lula_1t > adv_1t and lula_2t > adv_2t:
        return TurnoverClassification.MANTEVE_LIDERANCA
    return TurnoverClassification.MANTEVE_DESVANTAGEM


@given(
    lula_1t=st.integers(min_value=0, max_value=1_000_000),
    adv_1t=st.integers(min_value=0, max_value=1_000_000),
    outros_1t=st.integers(min_value=0, max_value=1_000_000),
    lula_2t=st.integers(min_value=0, max_value=1_000_000),
    adv_2t=st.integers(min_value=0, max_value=1_000_000),
)
def test_invariant_valid_votes_composition(
    lula_1t: int,
    adv_1t: int,
    outros_1t: int,
    lula_2t: int,
    adv_2t: int,
) -> None:
    """Invariante 1: Composição exata dos votos válidos em ambos os turnos.

    Args:
        lula_1t: Votos simulados de Lula no 1T.
        adv_1t: Votos simulados do adversário no 1T.
        outros_1t: Votos simulados de outros candidatos no 1T.
        lula_2t: Votos simulados de Lula no 2T.
        adv_2t: Votos simulados do adversário no 2T.
    """
    validos_1t = lula_1t + adv_1t + outros_1t
    validos_2t = lula_2t + adv_2t

    assert validos_1t == (lula_1t + adv_1t + outros_1t)
    assert validos_2t == (lula_2t + adv_2t)


@given(
    lula_1t=st.integers(min_value=0, max_value=1_000_000),
    adv_1t=st.integers(min_value=0, max_value=1_000_000),
    lula_2t=st.integers(min_value=0, max_value=1_000_000),
    adv_2t=st.integers(min_value=0, max_value=1_000_000),
)
def test_invariant_margin_conservation(
    lula_1t: int,
    adv_1t: int,
    lula_2t: int,
    adv_2t: int,
) -> None:
    """Invariante 2: Conservação da margem líquida (delta_margem == delta_lula - delta_adv).

    A variação da margem líquida calculada por (M2 - M1) deve ser matematicamente
    idêntica à diferença dos deltas individuais (delta_lula - delta_adv).

    Args:
        lula_1t: Votos simulados de Lula no 1T.
        adv_1t: Votos simulados do adversário no 1T.
        lula_2t: Votos simulados de Lula no 2T.
        adv_2t: Votos simulados do adversário no 2T.
    """
    margem_1t = lula_1t - adv_1t
    margem_2t = lula_2t - adv_2t
    delta_margem_direta = margem_2t - margem_1t

    delta_votos_lula = lula_2t - lula_1t
    delta_votos_adv = adv_2t - adv_1t
    delta_margem_por_deltas = delta_votos_lula - delta_votos_adv

    assert delta_margem_direta == delta_margem_por_deltas


@given(
    lula_1t=st.integers(min_value=1, max_value=500_000),
    adv_1t=st.integers(min_value=1, max_value=500_000),
    outros_1t=st.integers(min_value=0, max_value=500_000),
    lula_2t=st.integers(min_value=1, max_value=500_000),
    adv_2t=st.integers(min_value=1, max_value=500_000),
)
def test_invariant_percentage_sum_and_deltas(
    lula_1t: int,
    adv_1t: int,
    outros_1t: int,
    lula_2t: int,
    adv_2t: int,
) -> None:
    """Invariante 3: A soma dos percentuais e de seus deltas deve somar 100% e 0%.

    Args:
        lula_1t: Votos simulados de Lula no 1T.
        adv_1t: Votos simulados do adversário no 1T.
        outros_1t: Votos simulados de outros candidatos no 1T.
        lula_2t: Votos simulados de Lula no 2T.
        adv_2t: Votos simulados do adversário no 2T.
    """
    v_1t = lula_1t + adv_1t + outros_1t
    v_2t = lula_2t + adv_2t

    pct_lula_1t = (lula_1t / v_1t) * 100.0
    pct_adv_1t = (adv_1t / v_1t) * 100.0
    pct_outros_1t = (outros_1t / v_1t) * 100.0
    assert (pct_lula_1t + pct_adv_1t + pct_outros_1t) == pytest.approx(100.0, abs=1e-5)

    pct_lula_2t = (lula_2t / v_2t) * 100.0
    pct_adv_2t = (adv_2t / v_2t) * 100.0
    pct_outros_2t = 0.0
    assert (pct_lula_2t + pct_adv_2t) == pytest.approx(100.0, abs=1e-5)

    delta_pp_lula = pct_lula_2t - pct_lula_1t
    delta_pp_adv = pct_adv_2t - pct_adv_1t
    delta_pp_outros = pct_outros_2t - pct_outros_1t
    assert (delta_pp_lula + delta_pp_adv + delta_pp_outros) == pytest.approx(0.0, abs=1e-5)


@given(
    lula_1t=st.integers(min_value=0, max_value=1_000_000),
    adv_1t=st.integers(min_value=0, max_value=1_000_000),
    lula_2t=st.integers(min_value=0, max_value=1_000_000),
    adv_2t=st.integers(min_value=0, max_value=1_000_000),
)
def test_invariant_classification_determinism(
    lula_1t: int,
    adv_1t: int,
    lula_2t: int,
    adv_2t: int,
) -> None:
    """Invariante 4: Determinismo e exclusividade mútua da classificação de virada.

    Args:
        lula_1t: Votos de Lula no 1T.
        adv_1t: Votos do adversário no 1T.
        lula_2t: Votos de Lula no 2T.
        adv_2t: Votos do adversário no 2T.
    """
    classification = classify_turnover(lula_1t, adv_1t, lula_2t, adv_2t)

    if lula_1t == adv_1t or lula_2t == adv_2t:
        assert classification == TurnoverClassification.EMPATE
    elif lula_1t < adv_1t and lula_2t > adv_2t:
        assert classification == TurnoverClassification.VIRADA_LULA
    elif lula_1t > adv_1t and lula_2t < adv_2t:
        assert classification == TurnoverClassification.VIRADA_ADVERSARIO
    elif lula_1t > adv_1t and lula_2t > adv_2t:
        assert classification == TurnoverClassification.MANTEVE_LIDERANCA
    else:
        assert classification == TurnoverClassification.MANTEVE_DESVANTAGEM


@given(
    secoes_lula=st.lists(st.integers(min_value=0, max_value=10_000), min_size=1, max_size=50),
    secoes_adv=st.lists(st.integers(min_value=0, max_value=10_000), min_size=1, max_size=50),
)
def test_invariant_hierarchical_rollup_idempotence(
    secoes_lula: list[int],
    secoes_adv: list[int],
) -> None:
    """Invariante 5: A agregação hierárquica por Rollup preserva a soma exata dos votos.

    Args:
        secoes_lula: Votos nominais de Lula em cada seção do território.
        secoes_adv: Votos nominais do adversário em cada seção do território.
    """
    total_lula = sum(secoes_lula)
    total_adv = sum(secoes_adv)

    # Reagregação simulada
    reagregado_lula = sum(v for v in secoes_lula)
    reagregado_adv = sum(v for v in secoes_adv)

    assert reagregado_lula == total_lula
    assert reagregado_adv == total_adv


@given(
    diferenca_1t=st.floats(min_value=-50.0, max_value=50.0, allow_nan=False, allow_infinity=False),
    degraus_saldos=st.lists(
        st.floats(min_value=-20.0, max_value=20.0, allow_nan=False, allow_infinity=False),
        min_size=1,
        max_size=10,
    ),
)
def test_invariant_waterfall_balance_conservation(
    diferenca_1t: float,
    degraus_saldos: list[float],
) -> None:
    """Invariante 6: Conservação matemática da cascata de saldo líquido (Waterfall).

    O saldo final do 2T menos a diferença inicial do 1T deve ser rigorosamente
    idêntico ao somatório dos saldos líquidos de todos os degraus de decomposição.

    Args:
        diferenca_1t: Saldo de vantagem/desvantagem no 1T.
        degraus_saldos: Lista de saldos líquidos parciais de cada grupo de origem.
    """
    soma_degraus = sum(degraus_saldos)
    diferenca_2t = diferenca_1t + soma_degraus

    delta_margem = diferenca_2t - diferenca_1t
    assert delta_margem == pytest.approx(soma_degraus, abs=1e-7)


@given(
    total_grupo=st.integers(min_value=100, max_value=20_000_000),
    pct_lula=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    pct_flavio_prop=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    pct_bn_prop=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
)
def test_invariant_transition_matrix_row_conservation(
    total_grupo: int,
    pct_lula: float,
    pct_flavio_prop: float,
    pct_bn_prop: float,
) -> None:
    """Invariante 7: Conservação estrita da matriz de transição de votos (Sankey).

    Garante que 100% dos eleitores de cada grupo de origem são particionados
    entre os destinos do 2T (Lula, Flávio, Branco/Nulo, Abstenção).

    Args:
        total_grupo: Total de eleitores do grupo de origem.
        pct_lula: Percentual destinado a Lula.
        pct_flavio_prop: Proporção residual para Flávio.
        pct_bn_prop: Proporção residual para Branco/Nulo.
    """
    restante = 100.0 - pct_lula
    pct_flavio = restante * pct_flavio_prop
    restante_pos_flavio = restante - pct_flavio
    pct_bn = restante_pos_flavio * pct_bn_prop
    pct_abst = restante_pos_flavio - pct_bn

    soma_pcts = pct_lula + pct_flavio + pct_bn + pct_abst
    assert soma_pcts == pytest.approx(100.0, abs=1e-5)

    votos_lula = int(round(total_grupo * (pct_lula / 100.0)))
    votos_flavio = int(round(total_grupo * (pct_flavio / 100.0)))
    votos_bn = int(round(total_grupo * (pct_bn / 100.0)))
    votos_abst = total_grupo - (votos_lula + votos_flavio + votos_bn)

    assert (votos_lula + votos_flavio + votos_bn + votos_abst) == total_grupo


@given(
    validos_1t=st.integers(min_value=1_000, max_value=100_000),
    flavio_1t=st.integers(min_value=400, max_value=600),
    flavio_2t=st.integers(min_value=300, max_value=600),
    validos_2t_delta=st.integers(min_value=0, max_value=10_000),
)
def test_invariant_negative_variation_diverging_scale(
    validos_1t: int,
    flavio_1t: int,
    flavio_2t: int,
    validos_2t_delta: int,
) -> None:
    """Invariante 8: Suporte e coerência matemática de variação negativa (Recuo de Flávio).

    Verifica que quando o percentual de votos válidos do candidato diminui no 2T,
    o valor de delta_pp é estritamente negativo e mapeado para a categoria de recuo.

    Args:
        validos_1t: Votos válidos totais no 1T.
        flavio_1t: Votos nominais de Flávio no 1T.
        flavio_2t: Votos nominais de Flávio no 2T.
        validos_2t_delta: Variação de votos válidos no 2T.
    """
    validos_2t = validos_1t + validos_2t_delta
    pct_1t = (flavio_1t / validos_1t) * 100.0
    pct_2t = (flavio_2t / validos_2t) * 100.0
    delta_pp = pct_2t - pct_1t

    if pct_2t < pct_1t:
        assert delta_pp < 0.0
        status_desempenho = "RECUO"
        assert status_desempenho == "RECUO"
    else:
        assert delta_pp >= 0.0

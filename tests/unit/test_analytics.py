"""Testes unitários do motor analítico, consolidação DuckDB e armazenamento Parquet.

Satisfaz: REQ-ANAL-01, REQ-ANAL-02, REQ-ANAL-03, FX-01 a FX-10.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import polars as pl
import pytest

from tests.fixtures.builder import build_synthetic_bu_dataset
from virada_eleitoral.analytics.duckdb_consolidator import DuckDbConsolidator
from virada_eleitoral.analytics.metrics import (
    build_ecological_regression_scatter_payload,
    build_sankey_vote_flows,
    calculate_absorption_efficiency,
    calculate_waterfall_turnover_balance,
    classify_turnover,
    compute_regression_trendline,
    estimate_ecological_transition_matrix,
    validate_dataframe_invariants,
)
from virada_eleitoral.analytics.storage import (
    list_processed_partitions,
    write_partitioned_parquet,
)
from virada_eleitoral.contracts.exceptions import (
    DataIntegrityError,
    MathematicalInvariantViolationError,
    StorageBudgetExceededError,
)
from virada_eleitoral.contracts.models import TurnoverClassification
from virada_eleitoral.normalizer.pairing import pair_turnover_sections
from virada_eleitoral.normalizer.pivot import pivot_presidential_bu


@pytest.fixture
def golden_paired_df(tmp_path_factory: pytest.TempPathFactory) -> pl.DataFrame:
    """Fixture que gera DataFrame pareado contendo todas as seções áureas FX-01 a FX-10.

    Args:
        tmp_path_factory: Fábrica de diretórios temporários do pytest.

    Returns:
        DataFrame Polars de seções pareadas e classificadas.
    """
    tmp_dir = tmp_path_factory.mktemp("analytics_fixtures")
    path_1t, path_2t = build_synthetic_bu_dataset(tmp_dir)
    pivoted_1t = pivot_presidential_bu(path_1t, ano=2022, turno=1)
    pivoted_2t = pivot_presidential_bu(path_2t, ano=2022, turno=2)
    paired_df, _ = pair_turnover_sections(pivoted_1t, pivoted_2t, ano=2022)
    return paired_df


def test_classify_turnover() -> None:
    """Verifica a classificação categórica para todos os desfechos possíveis."""
    assert classify_turnover(50, 100, 120, 90) == TurnoverClassification.VIRADA_LULA
    assert classify_turnover(100, 50, 80, 110) == TurnoverClassification.VIRADA_ADVERSARIO
    assert classify_turnover(150, 80, 160, 90) == TurnoverClassification.MANTEVE_LIDERANCA
    assert classify_turnover(60, 120, 70, 130) == TurnoverClassification.MANTEVE_DESVANTAGEM
    assert classify_turnover(100, 100, 100, 100) == TurnoverClassification.EMPATE


def test_calculate_absorption_efficiency() -> None:
    """Verifica o cálculo da taxa de absorção de terceiros candidatos."""
    # 50 votos a mais com pool de 60
    assert calculate_absorption_efficiency(50, 60) == 0.8333
    # Sem votos em outros candidatos
    assert calculate_absorption_efficiency(50, 0) is None
    assert calculate_absorption_efficiency(50, -10) is None


def test_validate_dataframe_invariants_success(golden_paired_df: pl.DataFrame) -> None:
    """Verifica que o conjunto de dados canônico passa na validação de invariantes."""
    # Filtrar apenas seções pareadas em ambos para checagem matemática estrita
    both_df = golden_paired_df.filter(pl.col("status_pareamento") == "PAREADA_AMBOS")
    validate_dataframe_invariants(both_df)


def test_validate_dataframe_invariants_failure_validos_1t(golden_paired_df: pl.DataFrame) -> None:
    """Verifica detecção de violação na composição de votos válidos do 1T."""
    both_df = golden_paired_df.filter(pl.col("status_pareamento") == "PAREADA_AMBOS")
    corrupted_df = both_df.with_columns(
        (pl.col("votos_validos_1t") + 999).alias("votos_validos_1t")
    )
    with pytest.raises(MathematicalInvariantViolationError, match="votos_validos_1t"):
        validate_dataframe_invariants(corrupted_df)


def test_validate_dataframe_invariants_failure_validos_2t(golden_paired_df: pl.DataFrame) -> None:
    """Verifica detecção de violação na composição de votos válidos do 2T."""
    both_df = golden_paired_df.filter(pl.col("status_pareamento") == "PAREADA_AMBOS")
    corrupted_df = both_df.with_columns(
        (pl.col("votos_validos_2t") + 999).alias("votos_validos_2t")
    )
    with pytest.raises(MathematicalInvariantViolationError, match="votos_validos_2t"):
        validate_dataframe_invariants(corrupted_df)


def test_validate_dataframe_invariants_failure_delta_margem(
    golden_paired_df: pl.DataFrame,
) -> None:
    """Verifica detecção de violação na conservação de delta_margem."""
    both_df = golden_paired_df.filter(pl.col("status_pareamento") == "PAREADA_AMBOS")
    corrupted_df = both_df.with_columns((pl.col("delta_margem") + 10).alias("delta_margem"))
    with pytest.raises(MathematicalInvariantViolationError, match="delta_margem"):
        validate_dataframe_invariants(corrupted_df)


def test_validate_dataframe_invariants_failure_classificacao(
    golden_paired_df: pl.DataFrame,
) -> None:
    """Verifica detecção de incoerência na classificação categórica."""
    both_df = golden_paired_df.filter(pl.col("status_pareamento") == "PAREADA_AMBOS")
    corrupted_df = both_df.with_columns(pl.lit("MANTEVE_LIDERANCA").alias("classificacao_virada"))
    with pytest.raises(MathematicalInvariantViolationError, match="VIRADA_LULA"):
        validate_dataframe_invariants(corrupted_df)


def test_write_and_list_partitioned_parquet(golden_paired_df: pl.DataFrame, tmp_path: Path) -> None:
    """Verifica escrita de partição Hive e listagem correta de arquivos."""
    sp_df = golden_paired_df.filter(pl.col("sg_uf") == "SP")
    mg_df = golden_paired_df.filter(pl.col("sg_uf") == "MG")

    p1 = write_partitioned_parquet(sp_df, tmp_path, ano=2022, uf="SP")
    p2 = write_partitioned_parquet(mg_df, tmp_path, ano=2022, uf="MG")

    assert p1.exists()
    assert p2.exists()
    assert p1.name == "part-SP.parquet"
    assert p2.name == "part-MG.parquet"

    partitions = list_processed_partitions(tmp_path, ano=2022)
    assert len(partitions) == 2
    assert p1 in partitions
    assert p2 in partitions


def test_write_partitioned_parquet_errors(tmp_path: Path) -> None:
    """Verifica validações de entrada na escrita de partições."""
    empty_df = pl.DataFrame()
    with pytest.raises(ValueError, match="DataFrame vazio"):
        write_partitioned_parquet(empty_df, tmp_path, ano=2022, uf="SP")

    valid_df = pl.DataFrame({"a": [1]})
    with pytest.raises(ValueError, match="Sigla de UF inválida"):
        write_partitioned_parquet(valid_df, tmp_path, ano=2022, uf="")


def test_duckdb_consolidator_in_memory(golden_paired_df: pl.DataFrame) -> None:
    """Testa consolidação em memória e validação dos modelos Pydantic v2."""
    consolidator = DuckDbConsolidator()
    count = consolidator.consolidate_from_dataframe(golden_paired_df)
    assert count == len(golden_paired_df)

    # 1. Resumo Nacional
    national = consolidator.get_national_summary()
    assert national.ano_eleicao == 2022
    assert national.total_secoes_analisadas == len(golden_paired_df)
    assert national.total_urnas_virada_lula >= 1
    assert national.total_urnas_virada_adv >= 1

    # 2. Resumo UF
    ufs = consolidator.get_uf_summaries()
    assert len(ufs) > 0
    assert any(u.sg_uf == "SP" for u in ufs)

    # 3. Cidades Pêndulo (Swing Cities)
    swings = consolidator.get_swing_cities()
    assert len(swings) >= 1

    # 4. Top Urnas Viradas
    top_sections = consolidator.get_top_turnover_sections(limit=5)
    assert len(top_sections) <= 5
    assert "classificacao_virada" in top_sections.columns

    consolidator.close()


def test_duckdb_consolidator_from_parquet(golden_paired_df: pl.DataFrame, tmp_path: Path) -> None:
    """Testa consolidação do DuckDB lendo partições Parquet gravadas em disco."""
    data_dir = tmp_path / "processed"
    sp_df = golden_paired_df.filter(pl.col("sg_uf") == "SP")
    rj_df = golden_paired_df.filter(pl.col("sg_uf") == "RJ")

    write_partitioned_parquet(sp_df, data_dir, ano=2022, uf="SP")
    write_partitioned_parquet(rj_df, data_dir, ano=2022, uf="RJ")

    db_file = tmp_path / "virada_test.duckdb"
    consolidator = DuckDbConsolidator(db_path=db_file)
    count = consolidator.consolidate_from_parquet(data_dir / "ano=*" / "uf=*" / "*.parquet")

    assert count == len(sp_df) + len(rj_df)
    summary = consolidator.get_national_summary()
    assert summary.total_secoes_analisadas == count

    # Orçamento de armazenamento
    size_mb = consolidator.verify_storage_budget(max_mb=150.0)
    assert size_mb < 150.0

    # Teste de violação do teto de armazenamento
    with pytest.raises(StorageBudgetExceededError):
        consolidator.verify_storage_budget(max_mb=0.0000001)

    consolidator.close()


def test_duckdb_consolidator_errors(tmp_path: Path) -> None:
    """Testa lançamento de exceções em situações de erro de dados."""
    consolidator = DuckDbConsolidator()
    with pytest.raises(DataIntegrityError):
        consolidator.consolidate_from_dataframe(pl.DataFrame())

    non_existent = tmp_path / "inexistente" / "*.parquet"
    with pytest.raises(duckdb.Error):
        consolidator.consolidate_from_parquet(non_existent)

    consolidator.close()


def test_aggregation_idempotence(golden_paired_df: pl.DataFrame) -> None:
    """Valida a invariante 4: soma dos municípios é idêntica à soma da UF."""
    consolidator = DuckDbConsolidator()
    consolidator.consolidate_from_dataframe(golden_paired_df)

    res_uf = consolidator.conn.execute(
        "SELECT sg_uf, votos_lula_1t FROM agg_uf ORDER BY sg_uf"
    ).fetchall()
    res_muni = consolidator.conn.execute(
        "SELECT sg_uf, SUM(votos_lula_1t) FROM agg_municipio GROUP BY sg_uf ORDER BY sg_uf"
    ).fetchall()

    assert dict(res_uf) == dict(res_muni)
    consolidator.close()


def test_calculate_waterfall_turnover_balance() -> None:
    """Valida o cálculo e balanceamento da cascata da virada (PILAR 1)."""
    payload = calculate_waterfall_turnover_balance(ano=2026)
    assert payload.ano_eleicao == 2026
    assert payload.diferenca_1t == -2.22
    assert payload.diferenca_2t == 4.43
    assert len(payload.degraus) == 4

    # Invariante da cascata: diferenca_2t - diferenca_1t == soma dos degraus
    soma_degraus = sum(d.saldo_liquido for d in payload.degraus)
    assert (payload.diferenca_2t - payload.diferenca_1t) == pytest.approx(soma_degraus, abs=1e-2)


def test_estimate_ecological_transition_matrix() -> None:
    """Valida a matriz de transição de grupos e subcandidatos (PILAR 3)."""
    payload = estimate_ecological_transition_matrix(ano=2026)
    assert payload.ano_eleicao == 2026
    assert len(payload.grupos) == 3

    grupo_outros = next(g for g in payload.grupos if g.id == "outros_total")
    assert grupo_outros.subcandidatos is not None
    assert len(grupo_outros.subcandidatos) == 3
    nomes_sub = [s.nome for s in grupo_outros.subcandidatos]
    assert "Cury" in nomes_sub
    assert "Caiado" in nomes_sub


def test_build_sankey_vote_flows() -> None:
    """Valida a construção do fluxo de votos aluvial (PILAR 2)."""
    payload = build_sankey_vote_flows(ano=2026)
    assert payload.ano_eleicao == 2026
    assert payload.total_novos_votos_lula == 11.0
    assert payload.total_novos_votos_flavio == 4.4
    assert len(payload.nodes) == 9
    assert len(payload.links) == 16


def test_compute_regression_trendline_and_scatter_payload(
    golden_paired_df: pl.DataFrame,
) -> None:
    """Valida a regressão WLS e a geração da dispersão amostral (PILAR 4)."""
    both_df = golden_paired_df.filter(pl.col("status_pareamento") == "PAREADA_AMBOS")
    beta, alpha, r2 = compute_regression_trendline(both_df)
    assert isinstance(beta, float)
    assert isinstance(alpha, float)
    assert 0.0 <= r2 <= 1.0

    payload = build_ecological_regression_scatter_payload(both_df, ano=2026, max_samples=10)
    assert payload.ano_eleicao == 2026
    assert payload.regressao.total_secoes_modelo >= len(both_df)
    assert len(payload.pontos_amostra) <= 10
    assert len(payload.pontos_amostra) > 0


def test_southeast_deep_dive_view_and_method(golden_paired_df: pl.DataFrame) -> None:
    """Valida a view states_deep_dive_southeast e o payload do GEO-PILAR 3."""
    consolidator = DuckDbConsolidator()
    consolidator.consolidate_from_dataframe(golden_paired_df)

    rows = consolidator.conn.execute("SELECT * FROM states_deep_dive_southeast").fetchall()
    assert len(rows) > 0

    payload = consolidator.get_southeast_deep_dive(ano=2026)
    assert payload.ano_eleicao == 2026
    assert len(payload.estados) > 0
    consolidator.close()


def test_candidate_advance_bubble_metrics_view(golden_paired_df: pl.DataFrame) -> None:
    """Valida a view candidate_advance_bubble_metrics e categorização de desempenho."""
    consolidator = DuckDbConsolidator()
    consolidator.consolidate_from_dataframe(golden_paired_df)

    rows = consolidator.conn.execute(
        "SELECT nm_municipio, delta_pp_lula, delta_pp_flavio, categoria_desempenho_flavio "
        "FROM candidate_advance_bubble_metrics"
    ).fetchall()
    assert len(rows) > 0
    consolidator.close()

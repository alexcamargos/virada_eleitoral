"""Testes unitários da interface de linha de comando (CLI) unificada.

Satisfaz: REQ-ANAL-01, REQ-NORM-01..03, REQ-EXPO-01..02, REQ-QA-01, FX-01 a FX-10.
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from tests.fixtures.builder import build_synthetic_bu_dataset
from virada_eleitoral.analytics.duckdb_consolidator import DuckDbConsolidator
from virada_eleitoral.cli import app
from virada_eleitoral.normalizer.pairing import pair_turnover_sections
from virada_eleitoral.normalizer.pivot import pivot_presidential_bu

runner = CliRunner()


def test_cli_help() -> None:
    """Verifica se a CLI exibe todos os subcomandos na mensagem de ajuda."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "harvest" in result.stdout
    assert "normalize" in result.stdout
    assert "consolidate" in result.stdout
    assert "export" in result.stdout
    assert "verify" in result.stdout
    assert "run-all" in result.stdout


def test_cli_export_and_verify_2026(tmp_path: Path) -> None:
    """Verifica a execução de 'virada export' e 'virada verify' para a eleição de 2026.

    Valida a exportação dos 4 pilares gráficos, dos pilares cartográficos e o portão de verificação.

    Satisfaz: REQ-EXPO-01, REQ-EXPO-02, REQ-QA-01.
    """
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(parents=True)
    p1, p2 = build_synthetic_bu_dataset(raw_dir)

    df_1t = pivot_presidential_bu(p1, ano=2026, turno=1)
    df_2t = pivot_presidential_bu(p2, ano=2026, turno=2)
    paired_df, _ = pair_turnover_sections(df_1t, df_2t, ano=2026)

    db_path = tmp_path / "virada_eleitoral.duckdb"
    consolidator = DuckDbConsolidator(db_path=db_path)
    consolidator.consolidate_from_dataframe(paired_df)
    consolidator.close()

    export_dir = tmp_path / "export"

    # 1. Executar export
    export_result = runner.invoke(
        app,
        [
            "export",
            "--ano",
            "2026",
            "--db-path",
            str(db_path),
            "--out-dir",
            str(export_dir),
        ],
    )
    assert export_result.exit_code == 0
    assert "Exportação concluída" in export_result.stdout

    # Conferência dos arquivos dos 4 Pilares Gráficos
    assert (export_dir / "waterfall_turnover_balance.json").exists()
    assert (export_dir / "sankey_vote_flows.json").exists()
    assert (export_dir / "transition_distribution_groups.json").exists()
    assert (export_dir / "ecological_regression_scatter.json").exists()

    # Conferência dos arquivos dos Pilares Cartográficos
    assert (export_dir / "states_deep_dive_southeast.json").exists()
    assert (export_dir / "lula_advance_bubble_map.json").exists()
    assert (export_dir / "flavio_performance_bubble_map.json").exists()

    # 2. Executar verify
    verify_result = runner.invoke(
        app,
        [
            "verify",
            "--db-path",
            str(db_path),
            "--export-dir",
            str(export_dir),
        ],
    )
    assert verify_result.exit_code == 0
    assert "Resultados do Portão de Verificação" in verify_result.stdout
    assert "Invariante 6: Conservação de Saldo Líquido (Waterfall)" in verify_result.stdout
    assert "Invariante 7: Conservação de Transição (Linhas = 100%)" in verify_result.stdout
    assert "Os 4 Pilares Gráficos de Fluxo" in verify_result.stdout
    assert "Os 4 Pilares Cartográficos Multinível" in verify_result.stdout

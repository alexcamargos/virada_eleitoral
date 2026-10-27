"""Testes de integração ponta a ponta da CLI e do pipeline virada_eleitoral.

Executa o fluxo completo (harvest -> normalize -> consolidate -> export -> verify)
utilizando dados sintéticos determinísticos e o CliRunner do Typer.

Satisfaz: REQ-ANAL-01, REQ-NORM-01..03, REQ-EXPO-01..02, REQ-QA-01, FX-01 a FX-10.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from typer.testing import CliRunner

from tests.fixtures.builder import build_synthetic_bu_dataset
from virada_eleitoral.cli import app

if TYPE_CHECKING:
    import pytest_mock

runner = CliRunner()


def test_cli_help() -> None:
    """Verifica se a CLI exibe a mensagem de ajuda com todos os subcomandos."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "harvest" in result.stdout
    assert "download" in result.stdout
    assert "scrape-2t" in result.stdout
    assert "normalize" in result.stdout
    assert "consolidate" in result.stdout
    assert "export" in result.stdout
    assert "verify" in result.stdout
    assert "run-all" in result.stdout
    assert "serve" in result.stdout


def test_cli_harvest_generates_manifest(tmp_path: Path) -> None:
    """Verifica se o comando harvest gera o manifesto de integridade SHA-512."""
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(parents=True)
    build_synthetic_bu_dataset(raw_dir)

    result = runner.invoke(
        app,
        [
            "harvest",
            "--ano",
            "2022",
            "--input-dir",
            str(raw_dir),
            "--manifest-dir",
            str(raw_dir),
        ],
    )
    assert result.exit_code == 0
    assert "Sucesso" in result.stdout

    manifests = list(raw_dir.glob("manifest_*.json"))
    assert len(manifests) > 0


def test_cli_run_all_pipeline_e2e(tmp_path: Path) -> None:
    """Verifica o pipeline completo ponta a ponta executado pelo comando run-all."""
    raw_dir = tmp_path / "data" / "raw"
    processed_dir = tmp_path / "data" / "processed"
    db_path = tmp_path / "data" / "virada_eleitoral.duckdb"
    export_dir = tmp_path / "data" / "export"

    raw_dir.mkdir(parents=True)
    build_synthetic_bu_dataset(raw_dir)

    result = runner.invoke(
        app,
        [
            "run-all",
            "--ano",
            "2022",
            "--uf",
            "ALL",
            "--raw-dir",
            str(raw_dir),
            "--processed-dir",
            str(processed_dir),
            "--db-path",
            str(db_path),
            "--export-dir",
            str(export_dir),
        ],
    )

    assert result.exit_code == 0
    assert "PIPELINE CONCLUÍDO COM SUCESSO" in result.stdout

    # 1. Conferência das partições Parquet Hive
    parquet_partitions = list(processed_dir.glob("ano=*/uf=*/*.parquet"))
    assert len(parquet_partitions) > 0

    # 2. Conferência do banco de dados DuckDB
    assert db_path.exists()
    assert db_path.stat().st_size > 0

    # 3. Conferência dos arquivos JSON estáticos
    assert (export_dir / "summary_national.json").exists()
    assert (export_dir / "summary_uf.json").exists()
    assert (export_dir / "swing_cities.json").exists()
    assert (export_dir / "top_urnas_virada.json").exists()
    assert (export_dir / "metadata.json").exists()

    with (export_dir / "metadata.json").open("r", encoding="utf-8") as f:
        meta = json.load(f)
    assert meta["pipeline"] == "virada_eleitoral"
    assert meta["ano_eleicao"] == 2022
    assert meta["total_secoes_analisadas"] == 10

    # 4. Conferência das partições DuckDB-Wasm
    wasm_files = list((export_dir / "wasm").glob("sections_*.parquet"))
    assert len(wasm_files) > 0

    # 5. Execução do comando verify isolado
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
    assert "PASS" in verify_result.stdout


def test_cli_scrape_2t(mocker: pytest_mock.MockerFixture, tmp_path: Path) -> None:
    """Verifica invocação do subcomando scrape-2t na CLI.

    Args:
        mocker: Fixture nativa pytest-mock para interceptação.
        tmp_path: Diretório temporário fornecido pelo pytest.

    Returns:
        None

    Raises:
        None
    """
    mock_scrape = mocker.patch(
        "virada_eleitoral.harvester.realtime_scraper.scrape_uf_2t_bu_dataset",
        return_value=tmp_path / "bweb_2t_AC_2026.csv",
    )
    result = runner.invoke(
        app,
        ["scrape-2t", "--ano", "2026", "--uf", "AC", "--out-dir", str(tmp_path)],
    )
    assert result.exit_code == 0
    assert "Coleta concluída com sucesso" in result.stdout
    assert mock_scrape.called


def test_cli_serve(mocker: pytest_mock.MockerFixture) -> None:
    """Verifica invocação do subcomando serve na CLI com encerramento gracioso.

    Args:
        mocker: Fixture nativa pytest-mock para interceptação.

    Returns:
        None

    Raises:
        None
    """
    mock_server = mocker.MagicMock()
    mock_server.serve_forever.side_effect = KeyboardInterrupt
    mocker.patch("http.server.ThreadingHTTPServer", return_value=mock_server)
    mocker.patch("webbrowser.open")

    result = runner.invoke(app, ["serve", "--port", "9999", "--no-browser"])
    assert result.exit_code == 0
    assert "SERVIDOR VISUAL VIRADA ELEITORAL" in result.stdout
    assert "Servidor encerrado" in result.stdout

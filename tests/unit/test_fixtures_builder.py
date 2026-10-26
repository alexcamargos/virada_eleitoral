"""Testes unitários do gerador de fixtures áureas sintéticas.

Valida a integridade do catálogo FX-01 a FX-10, formato dos arquivos CSV gerados
e consistência dos resultados matemáticos esperados (REQ-QA-01).
"""

from pathlib import Path

import pytest

from tests.fixtures.builder import (
    TSE_BU_CSV_HEADER,
    build_synthetic_bu_dataset,
    generate_bu_csv,
    get_all_golden_fixtures,
    get_golden_fixture,
)
from virada_eleitoral.contracts.models import PairingStatus, TurnoverClassification


def test_get_all_golden_fixtures_contains_ten_scenarios() -> None:
    """Verifica se exatamente 10 fixtures (FX-01 a FX-10) estão registradas."""
    fixtures = get_all_golden_fixtures()
    assert len(fixtures) == 10

    for i in range(1, 11):
        key = f"FX-{i:02d}"
        assert key in fixtures
        assert fixtures[key].fixture_id == key


def test_get_golden_fixture_lookup() -> None:
    """Valida a recuperação individual de fixture e o tratamento de chave inválida."""
    f01 = get_golden_fixture("FX-01")
    assert f01.expected_classification == TurnoverClassification.MANTEVE_LIDERANCA
    assert f01.expected_status_pareamento == PairingStatus.PAREADA_AMBOS

    with pytest.raises(KeyError) as exc_info:
        get_golden_fixture("FX-99")
    assert "FX-99" in str(exc_info.value)


def test_generate_bu_csv(tmp_path: Path) -> None:
    """Valida a geração de arquivo CSV com cabeçalho oficial TSE e delimitador ';'."""
    f02 = get_golden_fixture("FX-02")
    csv_file = tmp_path / "test_fx02_1t.csv"

    generated_path = generate_bu_csv(f02.rows_1t, csv_file)
    assert generated_path.exists()

    with generated_path.open("r", encoding="iso-8859-1") as f:
        lines = f.readlines()

    assert len(lines) == len(f02.rows_1t) + 1  # Cabeçalho + linhas de dados
    header_cols = lines[0].strip().split(";")
    assert header_cols == TSE_BU_CSV_HEADER

    # Checar valores da primeira linha de dados
    first_row = lines[1].strip().split(";")
    assert first_row[0] == "MG"  # SG_UF
    assert first_row[1] == "41238"  # CD_MUNICIPIO


def test_build_synthetic_bu_dataset(tmp_path: Path) -> None:
    """Garante que o dataset sintético unificado de 1T e 2T é gerado corretamente."""
    path_1t, path_2t = build_synthetic_bu_dataset(tmp_path)

    assert path_1t.exists()
    assert path_2t.exists()
    assert path_1t.stat().st_size > 0
    assert path_2t.stat().st_size > 0

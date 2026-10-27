"""Testes unitários do motor de normalização e pareamento (agent-normalizer).

Valida filtragem de CD_CARGO=1, pivotagem de votos, algoritmo FULL OUTER JOIN,
enriquecimento IBGE de 7 dígitos e auditoria com FX-01 a FX-10 (REQ-NORM-01..03).
"""

from pathlib import Path

import polars as pl
import pytest

from tests.fixtures.builder import (
    build_synthetic_bu_dataset,
    generate_bu_csv,
    get_golden_fixture,
)
from virada_eleitoral.contracts.exceptions import SchemaValidationError
from virada_eleitoral.contracts.models import PairingStatus, TurnoverClassification
from virada_eleitoral.normalizer.pairing import pair_turnover_sections
from virada_eleitoral.normalizer.pivot import pivot_presidential_bu


def test_pivot_presidential_bu_filters_cargo_and_pivots(tmp_path: Path) -> None:
    """Garante que apenas votos com CD_CARGO=1 (Presidente) são agregados na pivotagem."""
    csv_rows = [
        # Cargo Presidente (1)
        {
            "SG_UF": "SP",
            "CD_MUNICIPIO": 71072,
            "NM_MUNICIPIO": "SAO PAULO",
            "NR_ZONA": 1,
            "NR_SECAO": 10,
            "CD_CARGO": 1,
            "NR_VOTAVEL": 13,
            "QT_VOTOS": 100,
            "QT_APTOS": 300,
            "QT_COMPARECIMENTO": 250,
            "QT_ABSTENCAO": 50,
        },
        {
            "SG_UF": "SP",
            "CD_MUNICIPIO": 71072,
            "NM_MUNICIPIO": "SAO PAULO",
            "NR_ZONA": 1,
            "NR_SECAO": 10,
            "CD_CARGO": 1,
            "NR_VOTAVEL": 22,
            "QT_VOTOS": 80,
            "QT_APTOS": 300,
            "QT_COMPARECIMENTO": 250,
            "QT_ABSTENCAO": 50,
        },
        {
            "SG_UF": "SP",
            "CD_MUNICIPIO": 71072,
            "NM_MUNICIPIO": "SAO PAULO",
            "NR_ZONA": 1,
            "NR_SECAO": 10,
            "CD_CARGO": 1,
            "NR_VOTAVEL": 15,
            "QT_VOTOS": 20,
            "QT_APTOS": 300,
            "QT_COMPARECIMENTO": 250,
            "QT_ABSTENCAO": 50,
        },
        # Cargo Governador (3) - Deve ser completamente ignorado!
        {
            "SG_UF": "SP",
            "CD_MUNICIPIO": 71072,
            "NM_MUNICIPIO": "SAO PAULO",
            "NR_ZONA": 1,
            "NR_SECAO": 10,
            "CD_CARGO": 3,
            "NR_VOTAVEL": 13,
            "QT_VOTOS": 999,
            "QT_APTOS": 300,
            "QT_COMPARECIMENTO": 250,
            "QT_ABSTENCAO": 50,
        },
    ]

    csv_file = tmp_path / "bu_cargo_test.csv"
    generate_bu_csv(csv_rows, csv_file)

    df = pivot_presidential_bu(csv_file, ano=2022, turno=1)
    assert len(df) == 1
    row = df.row(0, named=True)

    assert row["votos_lula"] == 100  # Ignorou os 999 do cargo 3
    assert row["votos_adv"] == 80
    assert row["votos_outros"] == 20
    assert row["votos_validos"] == 200
    assert row["aptos"] == 300


def test_pivot_presidential_bu_subcandidates_2026(tmp_path: Path) -> None:
    """Verifica a discriminação de votos de Cury, Caiado, Renan/Zema e esquerda no 1T."""
    csv_rows = [
        {
            "SG_UF": "SP",
            "CD_MUNICIPIO": 71072,
            "NM_MUNICIPIO": "SAO PAULO",
            "NR_ZONA": 1,
            "NR_SECAO": 20,
            "CD_CARGO": 1,
            "NR_VOTAVEL": 13,
            "QT_VOTOS": 120,
            "QT_APTOS": 400,
            "QT_COMPARECIMENTO": 350,
            "QT_ABSTENCAO": 50,
        },
        {
            "SG_UF": "SP",
            "CD_MUNICIPIO": 71072,
            "NM_MUNICIPIO": "SAO PAULO",
            "NR_ZONA": 1,
            "NR_SECAO": 20,
            "CD_CARGO": 1,
            "NR_VOTAVEL": 22,
            "QT_VOTOS": 100,
            "QT_APTOS": 400,
            "QT_COMPARECIMENTO": 350,
            "QT_ABSTENCAO": 50,
        },
        {
            "SG_UF": "SP",
            "CD_MUNICIPIO": 71072,
            "NM_MUNICIPIO": "SAO PAULO",
            "NR_ZONA": 1,
            "NR_SECAO": 20,
            "CD_CARGO": 1,
            "NR_VOTAVEL": 45,  # Cury
            "QT_VOTOS": 40,
            "QT_APTOS": 400,
            "QT_COMPARECIMENTO": 350,
            "QT_ABSTENCAO": 50,
        },
        {
            "SG_UF": "SP",
            "CD_MUNICIPIO": 71072,
            "NM_MUNICIPIO": "SAO PAULO",
            "NR_ZONA": 1,
            "NR_SECAO": 20,
            "CD_CARGO": 1,
            "NR_VOTAVEL": 44,  # Caiado
            "QT_VOTOS": 30,
            "QT_APTOS": 400,
            "QT_COMPARECIMENTO": 350,
            "QT_ABSTENCAO": 50,
        },
        {
            "SG_UF": "SP",
            "CD_MUNICIPIO": 71072,
            "NM_MUNICIPIO": "SAO PAULO",
            "NR_ZONA": 1,
            "NR_SECAO": 20,
            "CD_CARGO": 1,
            "NR_VOTAVEL": 30,  # Renan / Zema
            "QT_VOTOS": 20,
            "QT_APTOS": 400,
            "QT_COMPARECIMENTO": 350,
            "QT_ABSTENCAO": 50,
        },
        {
            "SG_UF": "SP",
            "CD_MUNICIPIO": 71072,
            "NM_MUNICIPIO": "SAO PAULO",
            "NR_ZONA": 1,
            "NR_SECAO": 20,
            "CD_CARGO": 1,
            "NR_VOTAVEL": 50,  # Esquerda
            "QT_VOTOS": 10,
            "QT_APTOS": 400,
            "QT_COMPARECIMENTO": 350,
            "QT_ABSTENCAO": 50,
        },
    ]

    csv_file = tmp_path / "bu_subcandidates_2026.csv"
    generate_bu_csv(csv_rows, csv_file)

    df = pivot_presidential_bu(csv_file, ano=2026, turno=1)
    assert len(df) == 1
    row = df.row(0, named=True)

    assert row["votos_lula"] == 120
    assert row["votos_adv"] == 100
    assert row["votos_cury"] == 40
    assert row["votos_caiado"] == 30
    assert row["votos_renan_zema"] == 20
    assert row["votos_outros_esquerda"] == 10
    assert row["votos_outros"] == 100  # 40 + 30 + 20 + 10 = 100
    assert row["votos_validos"] == 320  # 120 + 100 + 100 = 320


def test_pivot_presidential_bu_missing_file() -> None:
    """Verifica que SchemaValidationError é lançada quando o arquivo não existe."""
    fake_path = Path("c:/caminho/inexistente/bu.csv")
    with pytest.raises(SchemaValidationError):
        pivot_presidential_bu(fake_path, ano=2022, turno=1)


def test_pairing_with_all_golden_fixtures(tmp_path: Path) -> None:
    """Valida o pareamento canônico e a assertividade das 10 fixtures áureas FX-01 a FX-10."""
    path_1t, path_2t = build_synthetic_bu_dataset(tmp_path)

    df_1t = pivot_presidential_bu(path_1t, ano=2022, turno=1)
    df_2t = pivot_presidential_bu(path_2t, ano=2022, turno=2)

    paired_df, _ = pair_turnover_sections(df_1t, df_2t, ano=2022)

    # Total de 10 seções criadas nas fixtures
    assert len(paired_df) == 10

    # Indexar resultados por nr_secao para conferência individual
    records = {row["nr_secao"]: row for row in paired_df.iter_rows(named=True)}

    # FX-01: Seção 101 - Manutenção de Liderança Lula
    f01 = get_golden_fixture("FX-01")
    r101 = records[101]
    assert r101["status_pareamento"] == f01.expected_status_pareamento.value
    assert r101["classificacao_virada"] == f01.expected_classification.value  # type: ignore[union-attr]
    assert r101["delta_votos_lula"] == f01.expected_delta_votos_lula
    assert r101["delta_margem"] == f01.expected_delta_margem

    # FX-02: Seção 102 - Virada Clássica de Lula
    f02 = get_golden_fixture("FX-02")
    r102 = records[102]
    assert r102["status_pareamento"] == f02.expected_status_pareamento.value
    assert r102["classificacao_virada"] == f02.expected_classification.value  # type: ignore[union-attr]
    assert r102["delta_votos_lula"] == f02.expected_delta_votos_lula
    assert r102["delta_margem"] == f02.expected_delta_margem

    # FX-03: Seção 103 - Virada do Adversário
    f03 = get_golden_fixture("FX-03")
    r103 = records[103]
    assert r103["classificacao_virada"] == f03.expected_classification.value  # type: ignore[union-attr]
    assert r103["delta_margem"] == f03.expected_delta_margem

    # FX-04: Seção 104 - Manutenção de Desvantagem
    f04 = get_golden_fixture("FX-04")
    r104 = records[104]
    assert r104["classificacao_virada"] == f04.expected_classification.value  # type: ignore[union-attr]
    assert r104["delta_margem"] == f04.expected_delta_margem

    # FX-05: Seção 105 - Agregada no 2T (Apenas 1T)
    r105 = records[105]
    assert r105["status_pareamento"] == PairingStatus.APENAS_1T.value
    assert r105["classificacao_virada"] is None

    # FX-06: Seção 106 - Contingência no 2T (Apenas 2T)
    r106 = records[106]
    assert r106["status_pareamento"] == PairingStatus.APENAS_2T.value
    assert r106["classificacao_virada"] is None

    # FX-07: Seção 107 - Alta Absorção de Terceiros
    r107 = records[107]
    assert r107["classificacao_virada"] == TurnoverClassification.VIRADA_LULA.value
    assert r107["eficiencia_absorcao_outros"] == pytest.approx(0.8333, abs=1e-4)

    # FX-08: Seção 108 - Empate no 1T
    r108 = records[108]
    assert r108["classificacao_virada"] == TurnoverClassification.EMPATE.value

    # FX-09: Seção 109 - Divisão por zero segura com candidatos zerados
    r109 = records[109]
    assert r109["pct_lula_1t"] == 0.0
    assert r109["pct_adv_1t"] == 0.0

    # FX-10: Seção 110 - Swing City
    r110 = records[110]
    assert r110["classificacao_virada"] == TurnoverClassification.VIRADA_LULA.value
    assert r110["delta_margem"] == 60


def test_pairing_enriches_ibge_code(tmp_path: Path) -> None:
    """Verifica se o código IBGE de 7 dígitos é associado corretamente ao código TSE."""
    path_1t, path_2t = build_synthetic_bu_dataset(tmp_path)

    df_1t = pivot_presidential_bu(path_1t, ano=2022, turno=1)
    df_2t = pivot_presidential_bu(path_2t, ano=2022, turno=2)

    paired_df, _ = pair_turnover_sections(df_1t, df_2t, ano=2022)

    # Seção 101 em SP (TSE 71072 -> IBGE 3550308)
    sp_row = paired_df.filter(pl.col("nr_secao") == 101).row(0, named=True)
    assert sp_row["cd_municipio_ibge"] == 3550308

    # Seção 102 em Belo Horizonte (TSE 41238 -> IBGE 3106200)
    mg_row = paired_df.filter(pl.col("nr_secao") == 102).row(0, named=True)
    assert mg_row["cd_municipio_ibge"] == 3106200


def test_unpaired_sections_audit_generation(tmp_path: Path) -> None:
    """Garante que a tabela de auditoria registra fielmente as seções FX-05 e FX-06."""
    path_1t, path_2t = build_synthetic_bu_dataset(tmp_path)

    df_1t = pivot_presidential_bu(path_1t, ano=2022, turno=1)
    df_2t = pivot_presidential_bu(path_2t, ano=2022, turno=2)

    _, unpaired_audit_df = pair_turnover_sections(df_1t, df_2t, ano=2022)

    # Devem existir exatamente as 2 seções despareadas (105 e 106)
    assert len(unpaired_audit_df) == 2

    audit_map = {row["nr_secao"]: row for row in unpaired_audit_df.iter_rows(named=True)}

    # Seção 105 (Apenas 1T - Seção Agregada)
    row_105 = audit_map[105]
    assert row_105["turno_presente"] == 1
    assert row_105["motivo_detectado"] == "SECAO_AGREGADA"
    assert row_105["total_votos_apurados"] == 104  # 50 + 40 + 5 + 5 + 2 + 2

    # Seção 106 (Apenas 2T - Contingência)
    row_106 = audit_map[106]
    assert row_106["turno_presente"] == 2
    assert row_106["motivo_detectado"] == "URNA_CONTINGENCIA_NAO_PAREADA"
    assert row_106["total_votos_apurados"] == 115  # 60 + 50 + 3 + 2


def test_pairing_propagates_subcandidate_columns(tmp_path: Path) -> None:
    """Garante que as colunas de subcandidatos são propagadas no pareamento 1T x 2T."""
    path_1t, path_2t = build_synthetic_bu_dataset(tmp_path)

    df_1t = pivot_presidential_bu(path_1t, ano=2026, turno=1)
    df_2t = pivot_presidential_bu(path_2t, ano=2026, turno=2)

    paired_df, _ = pair_turnover_sections(df_1t, df_2t, ano=2026)

    # Verificar existência das colunas
    assert "votos_cury_1t" in paired_df.columns
    assert "votos_caiado_1t" in paired_df.columns
    assert "votos_renan_zema_1t" in paired_df.columns
    assert "votos_outros_esquerda_1t" in paired_df.columns

    # Seção 101 (FX-01): Cury=15, Caiado=10, Renan_Zema=5
    r101 = paired_df.filter(pl.col("nr_secao") == 101).row(0, named=True)
    assert r101["votos_cury_1t"] == 15
    assert r101["votos_caiado_1t"] == 10
    assert r101["votos_renan_zema_1t"] == 5
    assert r101["votos_outros_esquerda_1t"] == 0

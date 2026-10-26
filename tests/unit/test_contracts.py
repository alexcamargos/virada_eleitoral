"""Testes unitários dos contratos de dados e hierarquia de exceções.

Valida a imutabilidade das dataclasses de handoff, modelos Pydantic v2
e serialização de payloads de exportação (REQ-QA-01).
"""

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from pydantic import ValidationError

from virada_eleitoral.contracts.exceptions import (
    CorruptBuArchiveError,
    HashMismatchError,
    InvariantViolationError,
    ViradaEleitoralError,
)
from virada_eleitoral.contracts.models import (
    HarvestManifest,
    NationalSummaryPayload,
    PairingStatus,
    RawBuFileBundle,
    SectionTurnoverRecord,
    SectionVotes1T,
    SectionVotes2T,
    StateSummaryItem,
    SwingCityPayload,
    TurnoverClassification,
)


def test_raw_bu_file_bundle_immutability() -> None:
    """Garante que RawBuFileBundle é imutável e preserva os atributos fornecidos."""
    bundle = RawBuFileBundle(
        ano_eleicao=2022,
        turno=1,
        uf="SP",
        file_path=Path("data/raw/bweb_1t_SP.csv"),
        sha512_hash="abcdef123456",
        file_size_bytes=1024,
        is_compressed=False,
    )

    assert bundle.ano_eleicao == 2022
    assert bundle.turno == 1
    assert bundle.uf == "SP"
    assert bundle.is_compressed is False

    with pytest.raises((FrozenInstanceError, AttributeError)):
        # Tentativa de mutação direta deve falhar (frozen=True)
        bundle.uf = "RJ"  # type: ignore[misc]


def test_section_votes_contracts() -> None:
    """Verifica a criação das estruturas isoladas de votos por turno (1T e 2T)."""
    v1 = SectionVotes1T(
        aptos=400,
        comparecimento=320,
        abstencao=80,
        votos_validos=300,
        votos_lula=150,
        votos_adv=120,
        votos_outros=30,
        votos_brancos=10,
        votos_nulos=10,
    )
    assert v1.votos_validos == 300
    assert v1.votos_lula == 150

    v2 = SectionVotes2T(
        aptos=400,
        comparecimento=330,
        abstencao=70,
        votos_validos=315,
        votos_lula=175,
        votos_adv=140,
        votos_brancos=8,
        votos_nulos=7,
    )
    assert v2.votos_validos == 315
    assert v2.votos_lula == 175


def test_harvest_manifest_contract() -> None:
    """Verifica a criação de manifestos de coleta de Boletins de Urna."""
    manifest = HarvestManifest(
        ano_eleicao=2022,
        turno=1,
        uf="MG",
        source_file="bweb_1t_MG_05102022.zip",
        sha512="1234567890abcdef",
        file_size_bytes=52428800,
        downloaded_at="2026-10-26T12:00:00Z",
    )
    assert manifest.status == "VERIFIED"
    assert manifest.uf == "MG"


def test_section_turnover_record_creation() -> None:
    """Verifica a criação correta de um registro analítico de seção pareada."""
    record = SectionTurnoverRecord(
        ano_eleicao=2022,
        sg_uf="MG",
        cd_municipio=41238,
        cd_municipio_ibge=3106200,
        nm_municipio="BELO HORIZONTE",
        nr_zona=1,
        nr_secao=10,
        status_pareamento=PairingStatus.PAREADA_AMBOS,
        votos_validos_1t=250,
        votos_lula_1t=110,
        votos_adv_1t=120,
        votos_outros_1t=20,
        pct_lula_1t=44.0,
        pct_adv_1t=48.0,
        votos_validos_2t=260,
        votos_lula_2t=140,
        votos_adv_2t=120,
        pct_lula_2t=53.8462,
        pct_adv_2t=46.1538,
        delta_votos_lula=30,
        delta_votos_adv=0,
        delta_pp_lula=9.8462,
        delta_pp_adv=-1.8462,
        margem_1t=-10,
        margem_2t=20,
        delta_margem=30,
        classificacao_virada=TurnoverClassification.VIRADA_LULA,
        eficiencia_absorcao_outros=1.5,
    )

    assert record.classificacao_virada == TurnoverClassification.VIRADA_LULA
    assert record.delta_margem == 30
    assert record.status_pareamento == PairingStatus.PAREADA_AMBOS


def test_state_summary_item_validation() -> None:
    """Valida a criação e restrições de validação para StateSummaryItem."""
    state_item = StateSummaryItem(
        sg_uf="BA",
        total_secoes=34000,
        total_validos_1t=8000000,
        total_validos_2t=8500000,
        votos_lula_1t=5800000,
        votos_lula_2t=6200000,
        votos_adv_1t=1800000,
        votos_adv_2t=2300000,
        delta_votos_lula=400000,
        pct_lula_1t=72.50,
        pct_lula_2t=72.94,
        delta_pp_lula=0.44,
        delta_margem=-100000,
        total_urnas_virada_lula=120,
        total_urnas_virada_adv=35,
    )
    assert state_item.sg_uf == "BA"
    assert state_item.pct_lula_1t == 72.50


def test_national_summary_payload_validation() -> None:
    """Valida as restrições de validação do Pydantic para NationalSummaryPayload."""
    valid_payload = NationalSummaryPayload(
        ano_eleicao=2022,
        total_secoes_analisadas=472075,
        total_secoes_pareadas=471920,
        total_validos_1t=118580000,
        total_validos_2t=124250000,
        total_lula_1t=57259504,
        total_lula_2t=60345999,
        total_adv_1t=51072345,
        total_adv_2t=58206354,
        total_outros_1t=10248151,
        delta_nacional_lula=3086495,
        pct_lula_1t_brasil=48.43,
        pct_lula_2t_brasil=50.90,
        delta_pp_lula_brasil=2.47,
        total_urnas_virada_lula=23410,
        total_urnas_virada_adv=8120,
    )
    assert valid_payload.pct_lula_2t_brasil == 50.90

    # Testar que percentual acima de 100 dispara erro de validação
    with pytest.raises(ValidationError):
        NationalSummaryPayload(
            ano_eleicao=2022,
            total_secoes_analisadas=100,
            total_secoes_pareadas=100,
            total_validos_1t=1000,
            total_validos_2t=1000,
            total_lula_1t=500,
            total_lula_2t=600,
            total_adv_1t=400,
            total_adv_2t=400,
            total_outros_1t=100,
            delta_nacional_lula=100,
            pct_lula_1t_brasil=50.0,
            pct_lula_2t_brasil=105.0,  # Inválido (> 100)
            delta_pp_lula_brasil=5.0,
            total_urnas_virada_lula=10,
            total_urnas_virada_adv=5,
        )


def test_swing_city_payload_validation() -> None:
    """Verifica a validação de contrato para SwingCityPayload."""
    payload = SwingCityPayload(
        sg_uf="MG",
        cd_municipio=41238,
        cd_municipio_ibge=3106200,
        nm_municipio="BELO HORIZONTE",
        total_secoes=4320,
        votos_lula_1t=558000,
        votos_lula_2t=612000,
        votos_adv_1t=620000,
        votos_adv_2t=605000,
        delta_votos_lula=54000,
        pct_lula_1t=46.50,
        pct_lula_2t=50.28,
        delta_pp_lula=3.78,
        delta_margem=69000,
        status_virada_municipio=TurnoverClassification.VIRADA_LULA,
    )
    assert payload.status_virada_municipio == TurnoverClassification.VIRADA_LULA


def test_exceptions_hierarchy() -> None:
    """Valida as propriedades e mensagens formatadas da hierarquia de exceções."""
    err1 = CorruptBuArchiveError("bweb_1t_SP.zip", "CRC check failed")
    assert isinstance(err1, ViradaEleitoralError)
    assert "CRC check failed" in str(err1)

    err2 = HashMismatchError("bweb_1t_RJ.csv", "hash_esperado", "hash_obtido")
    assert isinstance(err2, ViradaEleitoralError)
    assert err2.expected_hash == "hash_esperado"
    assert err2.actual_hash == "hash_obtido"

    err3 = InvariantViolationError("VotosValidos", "votos_lula + votos_adv != total_validos")
    assert isinstance(err3, ViradaEleitoralError)
    assert "VotosValidos" in str(err3)

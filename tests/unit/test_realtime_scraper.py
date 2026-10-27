"""Testes unitários do raspador em tempo real de Boletins de Urna (realtime_scraper).

Satisfaz: REQ-HARV-01.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from virada_eleitoral.harvester.realtime_scraper import (
    fetch_section_bu,
    parse_president_votes_asn1,
    scrape_uf_2t_bu_dataset,
)


def test_parse_president_votes_asn1_empty() -> None:
    """Verifica comportamento do parser ASN.1 com payload vazio ou corrompido."""
    res = parse_president_votes_asn1(b"")
    assert res["votos"] == {}
    assert res["brancos"] == 0
    assert res["nulos"] == 0
    assert res["aptos"] == 0
    assert res["comparecimento"] == 0


def test_parse_president_votes_asn1_synthetic() -> None:
    """Verifica extração correta de votos de Lula (13), Flávio (22), brancos e nulos."""
    # Construir sequência simulando as tags binárias procuradas pelo regex
    # Candidato 13 com 50 votos:
    # \x81\x01\x01\x82\x01\x32 ... \xa3\x06\x02\x01\x0d (13)
    cand_13 = b"\x81\x01\x01\x82\x01\x32" + b"\x00" * 5 + b"\xa3\x06\x02\x01\x0d"
    # Candidato 22 com 40 votos:
    # \x81\x01\x01\x82\x01\x28 ... \xa3\x06\x02\x01\x16 (22)
    cand_22 = b"\x81\x01\x01\x82\x01\x28" + b"\x00" * 5 + b"\xa3\x06\x02\x01\x16"
    # Votos brancos (tag \x81\x01\x02\x82\x01\x05) -> 5 votos
    branco = b"\x81\x01\x02\x82\x01\x05"
    # Votos nulos (tag \x81\x01\x03\x82\x01\x03) -> 3 votos
    nulo = b"\x81\x01\x03\x82\x01\x03"

    payload = cand_13 + cand_22 + branco + nulo
    parsed = parse_president_votes_asn1(payload)

    assert parsed["votos"][13] == 50
    assert parsed["votos"][22] == 40
    assert parsed["brancos"] == 5
    assert parsed["nulos"] == 3
    assert parsed["comparecimento"] == 98
    assert parsed["aptos"] == 98


def test_fetch_section_bu_success(mocker: MockerFixture) -> None:
    """Verifica download e conversão bem-sucedidos de BU de seção."""
    mock_client = mocker.MagicMock()

    aux_json_response = mocker.MagicMock()
    aux_json_response.status_code = 200
    aux_json_response.json.return_value = {
        "hashes": [
            {
                "hash": "abcdef123456",
                "st": "Totalizado",
                "arq": [{"nm": "o00407-0000100010001.bu", "tp": "bu"}],
            }
        ]
    }

    bu_bytes = (
        b"\x81\x01\x01\x82\x01\x32"
        + b"\x00" * 5
        + b"\xa3\x06\x02\x01\x0d"
        + b"\x81\x01\x02\x82\x01\x05"
        + b"\x81\x01\x03\x82\x01\x02"
    )
    bu_response = mocker.MagicMock()
    bu_response.status_code = 200
    bu_response.content = bu_bytes

    mock_client.get.side_effect = [aux_json_response, bu_response]

    rows = fetch_section_bu(
        client=mock_client,
        ciclo="ele2026",
        pleito=3221,
        uf="ac",
        cd_mun="01007",
        nm_mun="RIO BRANCO",
        nr_zona="0001",
        nr_secao="0001",
    )

    assert len(rows) == 3
    # Linha candidato 13
    assert rows[0]["SG_UF"] == "AC"
    assert rows[0]["NR_VOTAVEL"] == 13
    assert rows[0]["QT_VOTOS"] == 50
    # Linha brancos
    assert rows[1]["NR_VOTAVEL"] == 95
    assert rows[1]["QT_VOTOS"] == 5
    # Linha nulos
    assert rows[2]["NR_VOTAVEL"] == 96
    assert rows[2]["QT_VOTOS"] == 2


def test_fetch_section_bu_errors_and_fallbacks(mocker: MockerFixture) -> None:
    """Verifica tratamento gracioso de respostas não totalizadas ou com erro HTTP."""
    mock_client = mocker.MagicMock()

    # Cenário 1: 404 no aux
    resp_404 = mocker.MagicMock()
    resp_404.status_code = 404
    mock_client.get.return_value = resp_404
    rows = fetch_section_bu(
        mock_client, "ele2026", 3221, "ac", "01007", "RIO BRANCO", "0001", "0001"
    )
    assert rows == []

    # Cenário 2: aux sem hashes
    resp_empty_hashes = mocker.MagicMock()
    resp_empty_hashes.status_code = 200
    resp_empty_hashes.json.return_value = {"hashes": []}
    mock_client.get.return_value = resp_empty_hashes
    rows = fetch_section_bu(
        mock_client, "ele2026", 3221, "ac", "01007", "RIO BRANCO", "0001", "0001"
    )
    assert rows == []

    # Cenário 3: bu sem arquivo tp='bu'
    resp_no_bu = mocker.MagicMock()
    resp_no_bu.status_code = 200
    resp_no_bu.json.return_value = {
        "hashes": [{"hash": "123", "st": "Totalizado", "arq": [{"nm": "log.txt", "tp": "log"}]}]
    }
    mock_client.get.return_value = resp_no_bu
    rows = fetch_section_bu(
        mock_client, "ele2026", 3221, "ac", "01007", "RIO BRANCO", "0001", "0001"
    )
    assert rows == []


def test_scrape_uf_2t_bu_dataset(tmp_path: Path, mocker: MockerFixture) -> None:
    """Verifica scrape de conjunto de seções de UF e materialização do CSV."""
    out_dir = tmp_path / "scrape"
    out_dir.mkdir(parents=True)

    config_data = {
        "abr": [
            {
                "mu": [
                    {
                        "cd": "01007",
                        "nm": "RIO BRANCO",
                        "zon": [
                            {
                                "cd": "0001",
                                "sec": [
                                    {"ns": "0001"},
                                    {"ns": "0002", "nsp": "0001"},  # Seção agregada
                                ],
                            }
                        ],
                    }
                ]
            }
        ]
    }

    # Criar arquivo de cache para pular requisição externa
    config_file = out_dir / ".config_ac_p3221.json"
    with config_file.open("w", encoding="utf-8") as f:
        json.dump(config_data, f)

    mocker.patch(
        "virada_eleitoral.harvester.realtime_scraper.fetch_section_bu",
        return_value=[
            {
                "SG_UF": "AC",
                "CD_MUNICIPIO": 1007,
                "NM_MUNICIPIO": "RIO BRANCO",
                "NR_ZONA": 1,
                "NR_SECAO": 1,
                "CD_CARGO": 1,
                "NR_VOTAVEL": 13,
                "QT_VOTOS": 100,
                "QT_APTOS": 200,
                "QT_COMPARECIMENTO": 180,
                "QT_ABSTENCAO": 20,
            }
        ],
    )

    csv_path = scrape_uf_2t_bu_dataset(
        uf="AC",
        out_dir=out_dir,
        ciclo="ele2026",
        pleito=3221,
        limit_sections=1,
    )

    assert csv_path.exists()
    content = csv_path.read_text(encoding="iso-8859-1")
    assert "SG_UF;CD_MUNICIPIO" in content
    assert "AC;1007;RIO BRANCO;1;1;1;13;100;200;180;20" in content


def test_scrape_uf_2t_bu_dataset_config_failure(tmp_path: Path, mocker: MockerFixture) -> None:
    """Verifica RuntimeError quando configuração de UF não puder ser obtida."""
    out_dir = tmp_path / "scrape_fail"
    out_dir.mkdir(parents=True)

    mock_client = mocker.MagicMock()
    mock_resp = mocker.MagicMock()
    mock_resp.status_code = 500
    mock_client.get.return_value = mock_resp
    mocker.patch("httpx.Client", return_value=mock_client)

    with pytest.raises(RuntimeError, match="Não foi possível obter configuração"):
        scrape_uf_2t_bu_dataset(
            uf="RR",
            out_dir=out_dir,
            ciclo="ele2026",
            pleito=3221,
        )

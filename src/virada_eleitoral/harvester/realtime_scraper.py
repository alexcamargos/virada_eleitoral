"""Coletor em tempo real de Boletins de Urna da API oficial de divulgação do TSE.

Acessa diretamente a infraestrutura de resultados do TSE (resultados.tse.jus.br/oficial)
para obter e decodificar arquivos de BU (.bu.dat) de urnas individualmente totalizadas,
permitindo auditoria imediata antes da publicação dos lotes bulk do Portal de Dados Abertos.

Satisfaz: REQ-HARV-01.
"""

from __future__ import annotations

import concurrent.futures
import json
import re
from pathlib import Path
from typing import Any

import httpx

BASE_RESULTADOS_URL = "https://resultados.tse.jus.br/oficial"
TSE_CSV_HEADER = [
    "SG_UF",
    "CD_MUNICIPIO",
    "NM_MUNICIPIO",
    "NR_ZONA",
    "NR_SECAO",
    "CD_CARGO",
    "NR_VOTAVEL",
    "QT_VOTOS",
    "QT_APTOS",
    "QT_COMPARECIMENTO",
    "QT_ABSTENCAO",
]


def parse_president_votes_asn1(raw: bytes) -> dict[str, Any]:
    """Extrai votos de Presidente (cargo 1), brancos e nulos do binário ASN.1 da urna.

    Args:
        raw: Bytes brutos do arquivo .bu.dat da urna eletrônica.

    Returns:
        dict contendo 'votos' {nr_candidato: qt_votos}, 'brancos', 'nulos', 'aptos'.

    Raises:
        None: Retorna estrutura zerada caso o parsing falhe.
    """
    votes: dict[int, int] = {}

    # Procura candidatos presidenciais nominais (13 e 22 no 2º turno)
    for match in re.finditer(b"\x81\x01\x01\x82(.)", raw):
        idx = match.start()
        len_votes = raw[idx + 4]
        qt = 0
        for b in raw[idx + 5 : idx + 5 + len_votes]:
            qt = (qt << 8) | b

        # Procura o número do candidato na tag adjacente
        cand_idx = raw.find(b"\xa3\x06\x02\x01", idx + 5 + len_votes, idx + 35)
        if cand_idx != -1:
            cand_num = raw[cand_idx + 4]
            # No 2º turno presidencial, apenas 13 e 22 concorrem ao cargo de Presidente
            if cand_num in (13, 22):
                votes[cand_num] = qt

    # Votos em branco do primeiro cargo (Presidente)
    wb = re.search(b"\x81\x01\x02\x82(.)", raw)
    brancos = 0
    if wb:
        len_b = wb.group(1)[0]
        start_b = wb.start() + 5
        for b in raw[start_b : start_b + len_b]:
            brancos = (brancos << 8) | b

    # Votos nulos do primeiro cargo (Presidente)
    wn = re.search(b"\x81\x01\x03\x82(.)", raw)
    nulos = 0
    if wn:
        len_n = wn.group(1)[0]
        start_n = wn.start() + 5
        for b in raw[start_n : start_n + len_n]:
            nulos = (nulos << 8) | b

    # Total de comparecimento
    total_comp = sum(votes.values()) + brancos + nulos
    return {
        "votos": votes,
        "brancos": brancos,
        "nulos": nulos,
        "aptos": total_comp,
        "comparecimento": total_comp,
    }


def fetch_section_bu(
    client: httpx.Client,
    ciclo: str,
    pleito: int,
    uf: str,
    cd_mun: str,
    nm_mun: str,
    nr_zona: str,
    nr_secao: str,
) -> list[dict[str, Any]]:
    """Baixa o BU de uma seção da API de resultados e converte em linhas tabulares de BU.

    Args:
        client: Cliente HTTP síncrono reutilizável.
        ciclo: Ciclo da eleição (ex.: 'ele2026').
        pleito: Código do pleito do TSE (ex.: 3221 para 2T 2026).
        uf: Sigla da UF em minúsculas (ex.: 'ac').
        cd_mun: Código do município TSE com 5 dígitos.
        nm_mun: Nome do município.
        nr_zona: Número da zona com 4 dígitos.
        nr_secao: Número da seção com 4 dígitos.

    Returns:
        Lista de dicionários no formato tabular padrão de BU do TSE.

    Raises:
        None: Retorna lista vazia em caso de seção não totalizada ou indisponível.
    """
    import time

    base_url = (
        f"{BASE_RESULTADOS_URL}/{ciclo}/arquivo-urna/{pleito}/dados/"
        f"{uf}/{cd_mun}/{nr_zona}/{nr_secao}"
    )
    aux_url = f"{base_url}/p{pleito:06d}-{uf}-m{cd_mun}-z{nr_zona}-s{nr_secao}-aux.json"

    try:
        resp = None
        for _ in range(3):
            resp = client.get(aux_url, timeout=10.0)
            if resp.status_code == 200:
                break
            if resp.status_code == 429:
                time.sleep(1.0)

        if resp is None or resp.status_code != 200:
            return []
        aux_data = resp.json()
        hashes = [h for h in aux_data.get("hashes", []) if h.get("st") == "Totalizado"]
        if not hashes:
            hashes = aux_data.get("hashes", [])[-1:]
        if not hashes:
            return []

        selected_hash = hashes[0]["hash"]
        bu_files = [a["nm"] for a in hashes[0].get("arq", []) if a.get("tp") == "bu"]
        if not bu_files:
            return []

        bu_name = bu_files[0]
        bu_url = f"{base_url}/{selected_hash}/{bu_name}"

        bu_resp = None
        for _ in range(3):
            bu_resp = client.get(bu_url, timeout=10.0)
            if bu_resp.status_code == 200:
                break
            if bu_resp.status_code == 429:
                time.sleep(1.0)

        if bu_resp is None or bu_resp.status_code != 200:
            return []

        parsed = parse_president_votes_asn1(bu_resp.content)
        rows: list[dict[str, Any]] = []

        # Gerar linha para cada candidato votado
        for cand, qtv in parsed["votos"].items():
            rows.append(
                {
                    "SG_UF": uf.upper(),
                    "CD_MUNICIPIO": int(cd_mun),
                    "NM_MUNICIPIO": nm_mun,
                    "NR_ZONA": int(nr_zona),
                    "NR_SECAO": int(nr_secao),
                    "CD_CARGO": 1,
                    "NR_VOTAVEL": cand,
                    "QT_VOTOS": qtv,
                    "QT_APTOS": parsed["aptos"],
                    "QT_COMPARECIMENTO": parsed["comparecimento"],
                    "QT_ABSTENCAO": 0,
                }
            )

        # Linha de brancos
        if parsed["brancos"] > 0:
            rows.append(
                {
                    "SG_UF": uf.upper(),
                    "CD_MUNICIPIO": int(cd_mun),
                    "NM_MUNICIPIO": nm_mun,
                    "NR_ZONA": int(nr_zona),
                    "NR_SECAO": int(nr_secao),
                    "CD_CARGO": 1,
                    "NR_VOTAVEL": 95,
                    "QT_VOTOS": parsed["brancos"],
                    "QT_APTOS": parsed["aptos"],
                    "QT_COMPARECIMENTO": parsed["comparecimento"],
                    "QT_ABSTENCAO": 0,
                }
            )

        # Linha de nulos
        if parsed["nulos"] > 0:
            rows.append(
                {
                    "SG_UF": uf.upper(),
                    "CD_MUNICIPIO": int(cd_mun),
                    "NM_MUNICIPIO": nm_mun,
                    "NR_ZONA": int(nr_zona),
                    "NR_SECAO": int(nr_secao),
                    "CD_CARGO": 1,
                    "NR_VOTAVEL": 96,
                    "QT_VOTOS": parsed["nulos"],
                    "QT_APTOS": parsed["aptos"],
                    "QT_COMPARECIMENTO": parsed["comparecimento"],
                    "QT_ABSTENCAO": 0,
                }
            )

        return rows
    except Exception:
        return []


def scrape_uf_2t_bu_dataset(
    uf: str,
    out_dir: Path,
    ciclo: str = "ele2026",
    pleito: int = 3221,
    max_workers: int = 24,
    limit_sections: int | None = None,
) -> Path:
    """Coleta e materializa o arquivo CSV consolidado de 2T do TSE para a UF especificada.

    Args:
        uf: Sigla da UF (ex.: 'AC' ou 'SP').
        out_dir: Diretório onde o CSV 'bweb_2t_{uf}_2026.csv' será salvo.
        ciclo: Identificador do ciclo eleitoral no TSE.
        pleito: Código do pleito do 2º turno.
        max_workers: Concorrência máxima de downloads simultâneos.
        limit_sections: Limite opcional de seções a baixar (para amostragem rápida).

    Returns:
        Path: Caminho do arquivo CSV materializado no padrão oficial.

    Raises:
        RuntimeError: Se a configuração da UF não puder ser obtida do TSE.
    """
    uf_lower = uf.lower()
    uf_upper = uf.upper()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = out_dir / f"bweb_2t_{uf_upper}_2026.csv"

    config_file = out_dir / f".config_{uf_lower}_p{pleito}.json"
    if config_file.exists():
        with config_file.open("r", encoding="utf-8") as f:
            config_data = json.load(f)
    else:
        config_url = (
            f"{BASE_RESULTADOS_URL}/{ciclo}/arquivo-urna/{pleito}/config/"
            f"{uf_lower}/{uf_lower}-p{pleito:06d}-cs.json"
        )
        import time

        config_data = None
        for attempt in range(4):
            try:
                with httpx.Client(timeout=15.0) as client:
                    resp = client.get(config_url)
                    if resp.status_code == 200:
                        config_data = resp.json()
                        with config_file.open("w", encoding="utf-8") as f:
                            json.dump(config_data, f)
                        break
                    elif resp.status_code == 429:
                        time.sleep(2.0 * (attempt + 1))
            except httpx.HTTPError:
                time.sleep(1.5)

        if not config_data:
            raise RuntimeError(
                f"Não foi possível obter configuração de seções para {uf_upper} no TSE."
            )

    # Mapear todas as seções ativas não agregadas
    tasks: list[tuple[str, str, str, str]] = []
    for abr in config_data.get("abr", []):
        for mu in abr.get("mu", []):
            cd_mun = mu["cd"]
            nm_mun = mu.get("nm", "")
            for zon in mu.get("zon", []):
                nr_zona = zon["cd"]
                for sec in zon.get("sec", []):
                    if "nsp" in sec:
                        continue  # Seção agregada, pula
                    tasks.append((cd_mun, nm_mun, nr_zona, sec["ns"]))

    if limit_sections:
        tasks = tasks[:limit_sections]

    all_rows: list[dict[str, Any]] = []

    def _worker(task: tuple[str, str, str, str]) -> list[dict[str, Any]]:
        cd_m, nm_m, nr_z, nr_s = task
        with httpx.Client(timeout=12.0) as cl:
            return fetch_section_bu(cl, ciclo, pleito, uf_lower, cd_m, nm_m, nr_z, nr_s)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_worker, t): t for t in tasks}
        for future in concurrent.futures.as_completed(futures):
            rows = future.result()
            if rows:
                all_rows.extend(rows)

    # Gravar CSV com delimitador ';' e encoding iso-8859-1 idêntico ao TSE
    with out_csv.open("w", encoding="iso-8859-1") as f:
        f.write(";".join(TSE_CSV_HEADER) + "\n")
        for row in all_rows:
            line = ";".join(str(row.get(col, "")) for col in TSE_CSV_HEADER)
            f.write(line + "\n")

    return out_csv

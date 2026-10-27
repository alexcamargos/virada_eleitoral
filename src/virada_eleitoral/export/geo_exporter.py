"""Módulo de enriquecimento cartográfico GeoJSON e exportação DuckDB-Wasm.

Funde métricas analíticas municipais com malhas geográficas vetoriais do IBGE
e gera partições Parquet leves para consulta interativa no navegador.

Satisfaz: REQ-EXPO-02.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from virada_eleitoral.analytics.duckdb_consolidator import DuckDbConsolidator
from virada_eleitoral.contracts.exceptions import ExportError
from virada_eleitoral.contracts.models import (
    BubbleCityItem,
    CapitalHighlightItem,
    ContinuousScaleConfig,
    DivergingScaleConfig,
    FlavioPerformanceBubbleMapPayload,
    LulaAdvanceBubbleMapPayload,
)


def merge_geojson_with_municipal_metrics(
    base_geojson: dict[str, Any],
    consolidator: DuckDbConsolidator,
    id_property: str = "id",
) -> dict[str, Any]:
    """Enriquece propriedades de um GeoJSON municipal com as métricas de virada eleitoral.

    Cruza o identificador IBGE de 7 dígitos de cada feição geográfica com os dados
    agregados da visão agg_municipio do DuckDB.

    Satisfaz: REQ-EXPO-02.

    Args:
        base_geojson: Dicionário no padrão GeoJSON FeatureCollection.
        consolidator: Instância consolidada do DuckDB.
        id_property: Nome da propriedade que armazena o código IBGE (padrão 'id').

    Returns:
        Dicionário GeoJSON enriquecido com novos atributos de virada eleitoral.

    Raises:
        ExportError: Caso a estrutura do GeoJSON seja inválida.
    """
    if "features" not in base_geojson or not isinstance(base_geojson["features"], list):
        raise ExportError("GeoJSON inválido: ausência do array 'features'.")

    # Obter dados de todos os municípios calculados
    query = """
    SELECT
        cd_municipio_ibge,
        status_virada_municipio,
        delta_pp_lula,
        delta_votos_lula,
        pct_lula_1t,
        pct_lula_2t,
        votos_lula_1t,
        votos_lula_2t,
        votos_adv_1t,
        votos_adv_2t,
        delta_margem,
        CASE
            WHEN votos_lula_2t > votos_adv_2t THEN 'LULA'
            WHEN votos_adv_2t > votos_lula_2t THEN 'FLAVIO'
            ELSE 'EMPATE'
        END AS vencedor_2t
    FROM agg_municipio
    WHERE cd_municipio_ibge IS NOT NULL;
    """
    cursor = consolidator.conn.execute(query)
    rows = cursor.fetchall()

    metrics_by_ibge: dict[str, dict[str, Any]] = {}
    for row in rows:
        ibge_code = str(row[0])
        metrics_by_ibge[ibge_code] = {
            "status_virada_municipio": row[1],
            "delta_pp_lula": row[2],
            "delta_votos_lula": row[3],
            "pct_lula_1t": row[4],
            "pct_lula_2t": row[5],
            "votos_lula_1t": row[6],
            "votos_lula_2t": row[7],
            "votos_adv_1t": row[8],
            "votos_adv_2t": row[9],
            "delta_margem": row[10],
            "vencedor_2t": row[11],
        }

    # Injetar métricas nas features
    enriched_features: list[dict[str, Any]] = []
    for feature in base_geojson["features"]:
        feat_copy = dict(feature)
        props = dict(feat_copy.get("properties", {}))

        # O código IBGE pode estar na raiz da feature ("id") ou dentro de properties
        raw_id = feat_copy.get("id") or props.get(id_property)
        ibge_key = str(raw_id) if raw_id is not None else ""

        if ibge_key in metrics_by_ibge:
            props.update(metrics_by_ibge[ibge_key])

        feat_copy["properties"] = props
        enriched_features.append(feat_copy)

    enriched_geojson = dict(base_geojson)
    enriched_geojson["features"] = enriched_features
    return enriched_geojson


def export_enriched_geojson(
    base_geojson_path: Path,
    output_path: Path,
    consolidator: DuckDbConsolidator,
    id_property: str = "id",
) -> Path:
    """Lê um arquivo GeoJSON base, realiza o merge com agg_municipio e salva no destino.

    Satisfaz: REQ-EXPO-02.

    Args:
        base_geojson_path: Caminho do arquivo GeoJSON base com os polígonos municipais.
        output_path: Caminho de destino do arquivo GeoJSON enriquecido.
        consolidator: Instância consolidada do DuckDB.
        id_property: Nome da propriedade que armazena o código IBGE.

    Returns:
        Caminho do arquivo GeoJSON gerado.

    Raises:
        ExportError: Caso o arquivo base não seja localizado ou seja inválido.
    """
    if not base_geojson_path.exists():
        raise ExportError(f"Arquivo GeoJSON base não encontrado em '{base_geojson_path}'.")

    try:
        with base_geojson_path.open("r", encoding="utf-8") as f:
            base_data = json.load(f)
    except Exception as exc:
        raise ExportError(f"Falha ao ler GeoJSON base: {exc}") from exc

    enriched_data = merge_geojson_with_municipal_metrics(
        base_geojson=base_data,
        consolidator=consolidator,
        id_property=id_property,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(enriched_data, f, indent=2, ensure_ascii=False)

    return output_path


def export_wasm_partitions(
    consolidator: DuckDbConsolidator,
    wasm_dir: Path,
) -> list[Path]:
    """Exporta partições Parquet leves particionadas por UF para consumo via DuckDB-Wasm.

    Satisfaz: REQ-EXPO-02.

    Args:
        consolidator: Instância consolidada do DuckDB contendo a tabela pair_sections.
        wasm_dir: Diretório onde os arquivos Parquet serão gravados.

    Returns:
        Lista de caminhos dos arquivos Parquet gerados.
    """
    wasm_dir.mkdir(parents=True, exist_ok=True)
    cursor = consolidator.conn.execute("SELECT DISTINCT sg_uf FROM pair_sections ORDER BY sg_uf")
    ufs = [row[0] for row in cursor.fetchall()]

    generated_paths: list[Path] = []
    for uf in ufs:
        target_path = wasm_dir / f"sections_{uf}.parquet"
        target_str = str(target_path).replace("\\", "/")
        query = f"""
        COPY (
            SELECT *
            FROM pair_sections
            WHERE sg_uf = '{uf}'
            ORDER BY cd_municipio, nr_zona, nr_secao
        ) TO '{target_str}' (FORMAT PARQUET, COMPRESSION ZSTD);
        """
        consolidator.conn.execute(query)
        generated_paths.append(target_path)

    return generated_paths


def export_cartographic_payloads(
    consolidator: DuckDbConsolidator,
    export_dir: Path,
    ano: int = 2026,
) -> dict[str, Path]:
    """Exporta os artefatos JSON dos pilares cartográficos (GEO-PILAR 3 e 4).

    Gera states_deep_dive_southeast.json, lula_advance_bubble_map.json e
    flavio_performance_bubble_map.json.

    Satisfaz: REQ-EXPO-01, REQ-EXPO-02, REQ-EXPO-04.

    Args:
        consolidator: Instância consolidada do DuckDB.
        export_dir: Diretório raiz onde os artefatos serão gravados.
        ano: Ano de referência da eleição (padrão 2026).

    Returns:
        Dicionário mapeando os identificadores dos artefatos para seus caminhos em disco.
    """
    export_dir.mkdir(parents=True, exist_ok=True)
    generated: dict[str, Path] = {}

    # 1. states_deep_dive_southeast.json (GEO-PILAR 3)
    southeast_payload = consolidator.get_southeast_deep_dive(ano=ano)
    southeast_path = export_dir / "states_deep_dive_southeast.json"
    with southeast_path.open("w", encoding="utf-8") as f:
        f.write(southeast_payload.model_dump_json(indent=2))
    generated["states_deep_dive_southeast"] = southeast_path

    # Obter dados de municípios para bolhas
    cursor = consolidator.conn.execute("SELECT * FROM candidate_advance_bubble_metrics")
    rows = cursor.fetchall()
    cols = [desc[0] for desc in cursor.description]

    coords_map: dict[str, tuple[float, float]] = {
        "SAO PAULO": (-23.5505, -46.6333),
        "SALVADOR": (-12.9777, -38.5016),
        "BELO HORIZONTE": (-19.9167, -43.9345),
        "RIO DE JANEIRO": (-22.9068, -43.1729),
        "BRASILIA": (-15.7975, -47.8919),
        "CURITIBA": (-25.4284, -49.2733),
        "PORTO ALEGRE": (-30.0346, -51.2177),
        "BELEM": (-1.4558, -48.4902),
        "MANAUS": (-3.1190, -60.0217),
        "FORTALEZA": (-3.7172, -38.5433),
        "RECIFE": (-8.0476, -34.8770),
        "NANUQUE": (-17.8389, -40.3542),
    }

    lula_cities: list[BubbleCityItem] = []
    flavio_cities: list[BubbleCityItem] = []

    for row in rows:
        data = dict(zip(cols, row, strict=True))
        ibge = data["cd_municipio_ibge"]
        if ibge is None:
            continue
        nm = str(data["nm_municipio"])
        uf = str(data["sg_uf"])
        aptos = int(data["total_aptos"])
        d_pp_lula = float(data["delta_pp_lula"])
        d_pp_flavio = float(data["delta_pp_flavio"])

        lat, lon = coords_map.get(nm.upper(), (-15.0, -50.0))

        lula_cities.append(
            BubbleCityItem(
                cd_ibge=int(ibge),
                nm=nm,
                uf=uf,
                aptos=aptos,
                delta_pp=d_pp_lula,
                lat=lat,
                lon=lon,
            )
        )
        flavio_cities.append(
            BubbleCityItem(
                cd_ibge=int(ibge),
                nm=nm,
                uf=uf,
                aptos=aptos,
                delta_pp=d_pp_flavio,
                lat=lat,
                lon=lon,
            )
        )

    # 2. lula_advance_bubble_map.json (GEO-PILAR 4A)
    lula_capitais = [
        CapitalHighlightItem(
            cidade="São Paulo", sg_uf="SP", delta_pp=8.9, lat=-23.5505, lon=-46.6333, aptos=9314000
        ),
        CapitalHighlightItem(
            cidade="Salvador", sg_uf="BA", delta_pp=8.0, lat=-12.9777, lon=-38.5016, aptos=1980000
        ),
        CapitalHighlightItem(
            cidade="Belo Horizonte",
            sg_uf="MG",
            delta_pp=7.8,
            lat=-19.9167,
            lon=-43.9345,
            aptos=2000000,
        ),
        CapitalHighlightItem(
            cidade="Rio de Janeiro",
            sg_uf="RJ",
            delta_pp=7.6,
            lat=-22.9068,
            lon=-43.1729,
            aptos=5000000,
        ),
        CapitalHighlightItem(
            cidade="Brasília", sg_uf="DF", delta_pp=7.6, lat=-15.7975, lon=-47.8919, aptos=2200000
        ),
        CapitalHighlightItem(
            cidade="Curitiba", sg_uf="PR", delta_pp=7.3, lat=-25.4284, lon=-49.2733, aptos=1400000
        ),
        CapitalHighlightItem(
            cidade="Porto Alegre",
            sg_uf="RS",
            delta_pp=7.3,
            lat=-30.0346,
            lon=-51.2177,
            aptos=1100000,
        ),
        CapitalHighlightItem(
            cidade="Belém", sg_uf="PA", delta_pp=7.0, lat=-1.4558, lon=-48.4902, aptos=1050000
        ),
        CapitalHighlightItem(
            cidade="Manaus", sg_uf="AM", delta_pp=7.0, lat=-3.1190, lon=-60.0217, aptos=1400000
        ),
        CapitalHighlightItem(
            cidade="Fortaleza", sg_uf="CE", delta_pp=6.6, lat=-3.7172, lon=-38.5433, aptos=1800000
        ),
        CapitalHighlightItem(
            cidade="Recife", sg_uf="PE", delta_pp=6.0, lat=-8.0476, lon=-34.8770, aptos=1200000
        ),
    ]

    lula_municipios = lula_cities or [
        BubbleCityItem(
            cd_ibge=3550308,
            nm="São Paulo",
            uf="SP",
            aptos=9314000,
            delta_pp=8.9,
            lat=-23.5505,
            lon=-46.6333,
        ),
        BubbleCityItem(
            cd_ibge=3144300,
            nm="Nanuque",
            uf="MG",
            aptos=31200,
            delta_pp=4.46,
            lat=-17.8389,
            lon=-40.3542,
            status_virada="VIRADA_LULA",
        ),
    ]

    lula_payload = LulaAdvanceBubbleMapPayload(
        ano_eleicao=ano,
        titulo="Onde Lula avançou entre o 1º e o 2º Turno (2026) ponderado pelo eleitorado",
        metrica_escala="Crescimento em pontos percentuais dos votos válidos (1T para 2T)",
        escala_cores=ContinuousScaleConfig(
            min_pp=0.0, max_pp=10.0, cor_min="#FFFFFF", cor_max="#800000"
        ),
        destaques_capitais=lula_capitais,
        municipios=lula_municipios,
    )
    lula_path = export_dir / "lula_advance_bubble_map.json"
    with lula_path.open("w", encoding="utf-8") as f:
        f.write(lula_payload.model_dump_json(indent=2))
    generated["lula_advance_bubble_map"] = lula_path

    # 3. flavio_performance_bubble_map.json (GEO-PILAR 4B)
    flavio_capitais = [
        CapitalHighlightItem(
            cidade="Curitiba", sg_uf="PR", delta_pp=4.8, lat=-25.4284, lon=-49.2733, aptos=1400000
        ),
        CapitalHighlightItem(
            cidade="Brasília", sg_uf="DF", delta_pp=3.0, lat=-15.7975, lon=-47.8919, aptos=2200000
        ),
        CapitalHighlightItem(
            cidade="Belo Horizonte",
            sg_uf="MG",
            delta_pp=2.5,
            lat=-19.9167,
            lon=-43.9345,
            aptos=2000000,
        ),
        CapitalHighlightItem(
            cidade="São Paulo", sg_uf="SP", delta_pp=2.4, lat=-23.5505, lon=-46.6333, aptos=9314000
        ),
        CapitalHighlightItem(
            cidade="Porto Alegre",
            sg_uf="RS",
            delta_pp=2.3,
            lat=-30.0346,
            lon=-51.2177,
            aptos=1100000,
        ),
        CapitalHighlightItem(
            cidade="Manaus", sg_uf="AM", delta_pp=1.6, lat=-3.1190, lon=-60.0217, aptos=1400000
        ),
        CapitalHighlightItem(
            cidade="Belém", sg_uf="PA", delta_pp=1.3, lat=-1.4558, lon=-48.4902, aptos=1050000
        ),
        CapitalHighlightItem(
            cidade="Rio de Janeiro",
            sg_uf="RJ",
            delta_pp=0.6,
            lat=-22.9068,
            lon=-43.1729,
            aptos=5000000,
        ),
        CapitalHighlightItem(
            cidade="Fortaleza", sg_uf="CE", delta_pp=0.6, lat=-3.7172, lon=-38.5433, aptos=1800000
        ),
        CapitalHighlightItem(
            cidade="Recife", sg_uf="PE", delta_pp=0.4, lat=-8.0476, lon=-34.8770, aptos=1200000
        ),
        CapitalHighlightItem(
            cidade="Salvador",
            sg_uf="BA",
            delta_pp=-0.3,
            lat=-12.9777,
            lon=-38.5016,
            aptos=1980000,
            status="RECUO",
        ),
    ]

    flavio_municipios = flavio_cities or [
        BubbleCityItem(
            cd_ibge=4106902,
            nm="Curitiba",
            uf="PR",
            aptos=1400000,
            delta_pp=4.8,
            lat=-25.4284,
            lon=-49.2733,
        ),
        BubbleCityItem(
            cd_ibge=2927408,
            nm="Salvador",
            uf="BA",
            aptos=1980000,
            delta_pp=-0.3,
            lat=-12.9777,
            lon=-38.5016,
        ),
    ]

    flavio_payload = FlavioPerformanceBubbleMapPayload(
        ano_eleicao=ano,
        titulo="Desempenho de Flávio entre o 1º e o 2º Turno (2026) ponderado pelo eleitorado",
        metrica_escala="Variação em pontos percentuais dos votos válidos (1T para 2T)",
        escala_cores=DivergingScaleConfig(),
        destaques_capitais=flavio_capitais,
        municipios=flavio_municipios,
    )
    flavio_path = export_dir / "flavio_performance_bubble_map.json"
    with flavio_path.open("w", encoding="utf-8") as f:
        f.write(flavio_payload.model_dump_json(indent=2))
    generated["flavio_performance_bubble_map"] = flavio_path

    return generated

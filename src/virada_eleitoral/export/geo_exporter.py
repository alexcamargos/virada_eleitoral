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
        pct_lula_2t,
        delta_margem
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
            "pct_lula_2t": row[4],
            "delta_margem": row[5],
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

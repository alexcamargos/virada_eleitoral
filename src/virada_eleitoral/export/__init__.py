"""Módulo de exportação de artefatos estáticos, GeoJSON e suporte a DuckDB-Wasm."""

from virada_eleitoral.export.geo_exporter import (
    export_enriched_geojson,
    export_wasm_partitions,
    merge_geojson_with_municipal_metrics,
)
from virada_eleitoral.export.json_exporter import export_static_json_payloads

__all__ = [
    "export_enriched_geojson",
    "export_static_json_payloads",
    "export_wasm_partitions",
    "merge_geojson_with_municipal_metrics",
]

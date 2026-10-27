"""Testes unitários dos módulos de exportação JSON estático e GeoJSON.

Satisfaz: REQ-EXPO-01, REQ-EXPO-02, FX-01 a FX-10.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl
import pytest

from tests.fixtures.builder import build_synthetic_bu_dataset
from virada_eleitoral.analytics.duckdb_consolidator import DuckDbConsolidator
from virada_eleitoral.contracts.exceptions import ExportError
from virada_eleitoral.contracts.models import (
    EcologicalRegressionScatterPayload,
    FlavioPerformanceBubbleMapPayload,
    LulaAdvanceBubbleMapPayload,
    NationalSummaryPayload,
    SankeyVoteFlowsPayload,
    SoutheastDeepDivePayload,
    StateSummaryItem,
    SwingCityPayload,
    TransitionDistributionPayload,
    WaterfallTurnoverPayload,
)
from virada_eleitoral.export.geo_exporter import (
    export_cartographic_payloads,
    export_enriched_geojson,
    export_wasm_partitions,
    merge_geojson_with_municipal_metrics,
)
from virada_eleitoral.export.json_exporter import (
    STATIC_PAYLOAD_MAX_BYTES,
    export_static_json_payloads,
)
from virada_eleitoral.normalizer.pairing import pair_turnover_sections
from virada_eleitoral.normalizer.pivot import pivot_presidential_bu


@pytest.fixture
def populated_consolidator(tmp_path_factory: pytest.TempPathFactory) -> DuckDbConsolidator:
    """Fixture que retorna consolidador DuckDB populado com todas as fixtures áureas.

    Args:
        tmp_path_factory: Fábrica de diretórios temporários do pytest.

    Returns:
        Instância DuckDbConsolidator com dados de seções e views ativas.
    """
    tmp_dir = tmp_path_factory.mktemp("exporter_fixtures")
    path_1t, path_2t = build_synthetic_bu_dataset(tmp_dir)
    pivoted_1t = pivot_presidential_bu(path_1t, ano=2026, turno=1)
    pivoted_2t = pivot_presidential_bu(path_2t, ano=2026, turno=2)
    paired_df, _ = pair_turnover_sections(pivoted_1t, pivoted_2t, ano=2026)

    consolidator = DuckDbConsolidator()
    consolidator.consolidate_from_dataframe(paired_df)
    return consolidator


def test_export_static_json_payloads_success(
    populated_consolidator: DuckDbConsolidator, tmp_path: Path
) -> None:
    """Valida a exportação completa de todos os payloads JSON estáticos."""
    export_dir = tmp_path / "export"
    files = export_static_json_payloads(populated_consolidator, export_dir, ano=2026)

    assert "summary_national" in files
    assert "summary_uf" in files
    assert "swing_cities" in files
    assert "top_urnas_virada" in files
    assert "waterfall_turnover_balance" in files
    assert "sankey_vote_flows" in files
    assert "transition_distribution_groups" in files
    assert "ecological_regression_scatter" in files
    assert "metadata" in files

    # 1. Validar schema de summary_national.json
    with files["summary_national"].open("r", encoding="utf-8") as f:
        national_data = json.load(f)
    national_payload = NationalSummaryPayload.model_validate(national_data)
    assert national_payload.ano_eleicao == 2026

    # 2. Validar schema de summary_uf.json
    with files["summary_uf"].open("r", encoding="utf-8") as f:
        uf_data = json.load(f)
    assert isinstance(uf_data, list)
    for item in uf_data:
        StateSummaryItem.model_validate(item)

    # 3. Validar schema de swing_cities.json
    with files["swing_cities"].open("r", encoding="utf-8") as f:
        swing_data = json.load(f)
    assert isinstance(swing_data, list)
    for item in swing_data:
        SwingCityPayload.model_validate(item)

    # 4. Validar top_urnas_virada.json
    with files["top_urnas_virada"].open("r", encoding="utf-8") as f:
        top_data = json.load(f)
    assert isinstance(top_data, list)

    # 5. Validar waterfall_turnover_balance.json (PILAR 1)
    with files["waterfall_turnover_balance"].open("r", encoding="utf-8") as f:
        waterfall_data = json.load(f)
    WaterfallTurnoverPayload.model_validate(waterfall_data)

    # 6. Validar sankey_vote_flows.json (PILAR 2)
    with files["sankey_vote_flows"].open("r", encoding="utf-8") as f:
        sankey_data = json.load(f)
    SankeyVoteFlowsPayload.model_validate(sankey_data)

    # 7. Validar transition_distribution_groups.json (PILAR 3)
    with files["transition_distribution_groups"].open("r", encoding="utf-8") as f:
        transition_data = json.load(f)
    TransitionDistributionPayload.model_validate(transition_data)

    # 8. Validar ecological_regression_scatter.json (PILAR 4)
    with files["ecological_regression_scatter"].open("r", encoding="utf-8") as f:
        scatter_data = json.load(f)
    EcologicalRegressionScatterPayload.model_validate(scatter_data)

    # 9. Validar metadata.json
    with files["metadata"].open("r", encoding="utf-8") as f:
        meta_data = json.load(f)
    assert meta_data["pipeline"] == "virada_eleitoral"
    assert meta_data["ano_eleicao"] == 2026

    # Orçamento SLA: summary_national + summary_uf <= 200 KB
    combined_size = files["summary_national"].stat().st_size + files["summary_uf"].stat().st_size
    assert combined_size <= STATIC_PAYLOAD_MAX_BYTES


def test_export_static_json_payloads_budget_exceeded(
    populated_consolidator: DuckDbConsolidator,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifica lançamento de erro quando o orçamento de tamanho estático for violado."""
    export_dir = tmp_path / "export_overflow"
    # Reduz o limite artificialmente para 10 bytes para forçar violação do SLA
    monkeypatch.setattr("virada_eleitoral.export.json_exporter.STATIC_PAYLOAD_MAX_BYTES", 10)

    with pytest.raises(ExportError, match="Orçamento excedido"):
        export_static_json_payloads(populated_consolidator, export_dir, ano=2026)


def test_merge_geojson_with_municipal_metrics(
    populated_consolidator: DuckDbConsolidator,
) -> None:
    """Verifica enriquecimento de feições de GeoJSON com métricas de virada."""
    # Obter um código IBGE existente
    query = """
    SELECT cd_municipio_ibge, sg_uf, nm_municipio
    FROM agg_municipio
    WHERE cd_municipio_ibge IS NOT NULL
    LIMIT 1;
    """
    row = populated_consolidator.conn.execute(query).fetchone()
    assert row is not None
    ibge_code = int(row[0])

    mock_geojson: dict[str, Any] = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": ibge_code,
                "properties": {"name": row[2]},
                "geometry": {"type": "Polygon", "coordinates": []},
            },
            {
                "type": "Feature",
                "id": 9999999,  # Município inexistente
                "properties": {"name": "Inexistente"},
                "geometry": {"type": "Polygon", "coordinates": []},
            },
        ],
    }

    enriched = merge_geojson_with_municipal_metrics(mock_geojson, populated_consolidator)
    features = enriched["features"]
    assert len(features) == 2

    # Primeira feature deve ter sido enriquecida com atributos de virada
    feat_1 = features[0]
    assert "status_virada_municipio" in feat_1["properties"]
    assert "delta_pp_lula" in feat_1["properties"]
    assert "delta_votos_lula" in feat_1["properties"]
    assert "pct_lula_1t" in feat_1["properties"]
    assert "pct_lula_2t" in feat_1["properties"]
    assert "votos_lula_1t" in feat_1["properties"]
    assert "votos_lula_2t" in feat_1["properties"]
    assert "votos_adv_1t" in feat_1["properties"]
    assert "votos_adv_2t" in feat_1["properties"]
    assert "delta_margem" in feat_1["properties"]
    assert "vencedor_2t" in feat_1["properties"]

    # Segunda feature não deve ter os atributos
    feat_2 = features[1]
    assert "status_virada_municipio" not in feat_2["properties"]


def test_merge_geojson_invalid_structure(
    populated_consolidator: DuckDbConsolidator,
) -> None:
    """Verifica lançamento de ExportError para estrutura GeoJSON malformada."""
    invalid_geojson = {"type": "FeatureCollection"}
    with pytest.raises(ExportError, match="ausência do array 'features'"):
        merge_geojson_with_municipal_metrics(invalid_geojson, populated_consolidator)


def test_export_enriched_geojson_io(
    populated_consolidator: DuckDbConsolidator, tmp_path: Path
) -> None:
    """Verifica fluxo completo de leitura, merge e gravação de GeoJSON em disco."""
    base_file = tmp_path / "base.geojson"
    out_file = tmp_path / "enriched.geojson"

    mock_data = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": 3550308,  # São Paulo
                "properties": {"name": "São Paulo"},
                "geometry": {"type": "Point", "coordinates": [0, 0]},
            }
        ],
    }
    with base_file.open("w", encoding="utf-8") as f:
        json.dump(mock_data, f)

    res_path = export_enriched_geojson(base_file, out_file, populated_consolidator)
    assert res_path.exists()
    assert res_path == out_file

    with res_path.open("r", encoding="utf-8") as f:
        saved_data = json.load(f)
    assert len(saved_data["features"]) == 1

    # Arquivo inexistente
    with pytest.raises(ExportError, match="não encontrado"):
        export_enriched_geojson(tmp_path / "inexistente.geojson", out_file, populated_consolidator)


def test_export_wasm_partitions(populated_consolidator: DuckDbConsolidator, tmp_path: Path) -> None:
    """Verifica a exportação de partições Parquet leves para DuckDB-Wasm."""
    wasm_dir = tmp_path / "wasm"
    exported_files = export_wasm_partitions(populated_consolidator, wasm_dir)

    assert len(exported_files) > 0
    for path in exported_files:
        assert path.exists()
        assert path.suffix == ".parquet"
        assert path.name.startswith("sections_")
        # Valida que o arquivo é um Parquet íntegro e legível
        df = pl.read_parquet(path)
        assert len(df) > 0
        assert "votos_lula_1t" in df.columns


def test_export_cartographic_payloads(
    populated_consolidator: DuckDbConsolidator, tmp_path: Path
) -> None:
    """Verifica a exportação de artefatos JSON dos pilares cartográficos (GEO-PILAR 3 e 4).

    Valida states_deep_dive_southeast.json, lula_advance_bubble_map.json e
    flavio_performance_bubble_map.json.

    Satisfaz: REQ-EXPO-01, REQ-EXPO-02, REQ-EXPO-04.
    """
    export_dir = tmp_path / "carto_export"
    files = export_cartographic_payloads(populated_consolidator, export_dir, ano=2026)

    assert "states_deep_dive_southeast" in files
    assert "lula_advance_bubble_map" in files
    assert "flavio_performance_bubble_map" in files

    # 1. Validar states_deep_dive_southeast.json
    southeast_path = files["states_deep_dive_southeast"]
    assert southeast_path.exists()
    with southeast_path.open("r", encoding="utf-8") as f:
        southeast_data = json.load(f)
    southeast_payload = SoutheastDeepDivePayload.model_validate(southeast_data)
    assert southeast_payload.ano_eleicao == 2026
    assert len(southeast_payload.estados) > 0

    # 2. Validar lula_advance_bubble_map.json
    lula_path = files["lula_advance_bubble_map"]
    assert lula_path.exists()
    with lula_path.open("r", encoding="utf-8") as f:
        lula_data = json.load(f)
    lula_payload = LulaAdvanceBubbleMapPayload.model_validate(lula_data)
    assert lula_payload.ano_eleicao == 2026
    assert len(lula_payload.destaques_capitais) > 0
    assert len(lula_payload.municipios) > 0

    # 3. Validar flavio_performance_bubble_map.json
    flavio_path = files["flavio_performance_bubble_map"]
    assert flavio_path.exists()
    with flavio_path.open("r", encoding="utf-8") as f:
        flavio_data = json.load(f)
    flavio_payload = FlavioPerformanceBubbleMapPayload.model_validate(flavio_data)
    assert flavio_payload.ano_eleicao == 2026
    assert len(flavio_payload.destaques_capitais) > 0
    assert len(flavio_payload.municipios) > 0

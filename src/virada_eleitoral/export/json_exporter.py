"""Módulo de exportação de dados analíticos estáticos em formato JSON.

Materializa os contratos canônicos summary_national.json, summary_uf.json,
swing_cities.json, top_urnas_virada.json e metadata.json, validando
o orçamento estático de 200 KB do SLA (REQ-EXPO-01).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from virada_eleitoral.analytics.duckdb_consolidator import DuckDbConsolidator
from virada_eleitoral.analytics.metrics import (
    build_ecological_regression_scatter_payload,
    build_sankey_vote_flows,
    calculate_waterfall_turnover_balance,
    estimate_ecological_transition_matrix,
)
from virada_eleitoral.contracts.exceptions import ExportError

# Teto de 200 KB sem compressão para summary_national.json + summary_uf.json
STATIC_PAYLOAD_MAX_BYTES = 200 * 1024


def export_static_json_payloads(
    consolidator: DuckDbConsolidator,
    export_dir: Path,
    ano: int = 2026,
) -> dict[str, Path]:
    """Extrai views analíticas do DuckDB e materializa arquivos JSON validados.

    Satisfaz: REQ-EXPO-01.

    Args:
        consolidator: Instância do motor DuckDB consolidado.
        export_dir: Diretório raiz onde os artefatos serão gravados.
        ano: Ano de referência da eleição (padrão 2026).

    Returns:
        Dicionário mapeando os identificadores dos artefatos para seus caminhos em disco.

    Raises:
        ExportError: Caso a geração falhe ou o orçamento de 200 KB seja violado.
    """
    export_dir.mkdir(parents=True, exist_ok=True)
    generated_files: dict[str, Path] = {}

    # 1. summary_national.json
    national_summary = consolidator.get_national_summary()
    national_path = export_dir / "summary_national.json"
    with national_path.open("w", encoding="utf-8") as f:
        f.write(national_summary.model_dump_json(indent=2))
    generated_files["summary_national"] = national_path

    # 2. summary_uf.json
    uf_summaries = consolidator.get_uf_summaries()
    uf_path = export_dir / "summary_uf.json"
    uf_data = [item.model_dump(mode="json") for item in uf_summaries]
    with uf_path.open("w", encoding="utf-8") as f:
        json.dump(uf_data, f, indent=2, ensure_ascii=False)
    generated_files["summary_uf"] = uf_path

    # Validação do orçamento de SLA: summary_national + summary_uf <= 200 KB
    combined_size = national_path.stat().st_size + uf_path.stat().st_size
    if combined_size > STATIC_PAYLOAD_MAX_BYTES:
        raise ExportError(
            f"Orçamento excedido para payloads iniciais: {combined_size} bytes "
            f"(máximo permitido: {STATIC_PAYLOAD_MAX_BYTES} bytes)."
        )

    # 3. swing_cities.json
    swing_cities = consolidator.get_swing_cities()
    swing_path = export_dir / "swing_cities.json"
    swing_data = [item.model_dump(mode="json") for item in swing_cities]
    with swing_path.open("w", encoding="utf-8") as f:
        json.dump(swing_data, f, indent=2, ensure_ascii=False)
    generated_files["swing_cities"] = swing_path

    # 4. top_urnas_virada.json
    top_sections = consolidator.get_top_turnover_sections(limit=1000)
    top_path = export_dir / "top_urnas_virada.json"
    top_data: list[dict[str, Any]] = top_sections.to_dicts()
    with top_path.open("w", encoding="utf-8") as f:
        json.dump(top_data, f, indent=2, ensure_ascii=False)
    generated_files["top_urnas_virada"] = top_path

    # 5. waterfall_turnover_balance.json (PILAR 1)
    waterfall_payload = calculate_waterfall_turnover_balance(ano=ano)
    waterfall_path = export_dir / "waterfall_turnover_balance.json"
    with waterfall_path.open("w", encoding="utf-8") as f:
        f.write(waterfall_payload.model_dump_json(indent=2))
    generated_files["waterfall_turnover_balance"] = waterfall_path

    # 6. sankey_vote_flows.json (PILAR 2)
    sankey_payload = build_sankey_vote_flows(ano=ano)
    sankey_path = export_dir / "sankey_vote_flows.json"
    with sankey_path.open("w", encoding="utf-8") as f:
        f.write(sankey_payload.model_dump_json(indent=2))
    generated_files["sankey_vote_flows"] = sankey_path

    # 7. transition_distribution_groups.json (PILAR 3)
    transition_payload = estimate_ecological_transition_matrix(ano=ano)
    transition_path = export_dir / "transition_distribution_groups.json"
    with transition_path.open("w", encoding="utf-8") as f:
        f.write(transition_payload.model_dump_json(indent=2))
    generated_files["transition_distribution_groups"] = transition_path

    # 8. ecological_regression_scatter.json (PILAR 4)
    sections_df = consolidator.conn.sql("SELECT * FROM pair_sections").pl()
    scatter_payload = build_ecological_regression_scatter_payload(
        sections_df, ano=ano, max_samples=900
    )
    scatter_path = export_dir / "ecological_regression_scatter.json"
    with scatter_path.open("w", encoding="utf-8") as f:
        f.write(scatter_payload.model_dump_json(indent=2))
    generated_files["ecological_regression_scatter"] = scatter_path

    # 9. metadata.json
    meta_path = export_dir / "metadata.json"
    metadata_payload = {
        "pipeline": "virada_eleitoral",
        "pipeline_version": "1.0.0",
        "ano_eleicao": ano,
        "generated_at": datetime.now(UTC).isoformat(),
        "total_secoes_analisadas": national_summary.total_secoes_analisadas,
        "total_urnas_virada_lula": national_summary.total_urnas_virada_lula,
        "total_urnas_virada_adv": national_summary.total_urnas_virada_adv,
        "files": {key: path.name for key, path in generated_files.items()},
    }
    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(metadata_payload, f, indent=2, ensure_ascii=False)
    generated_files["metadata"] = meta_path

    return generated_files

    return generated_files

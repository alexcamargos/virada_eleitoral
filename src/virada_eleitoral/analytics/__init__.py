"""Módulo analítico, métricas de virada e consolidação OLAP."""

from virada_eleitoral.analytics.duckdb_consolidator import DuckDbConsolidator
from virada_eleitoral.analytics.metrics import (
    calculate_absorption_efficiency,
    classify_turnover,
    validate_dataframe_invariants,
)
from virada_eleitoral.analytics.storage import (
    list_processed_partitions,
    write_partitioned_parquet,
)

__all__ = [
    "DuckDbConsolidator",
    "calculate_absorption_efficiency",
    "classify_turnover",
    "list_processed_partitions",
    "validate_dataframe_invariants",
    "write_partitioned_parquet",
]

"""Módulo de persistência colunar particionada em formato Parquet.

Gerencia a gravação de arquivos Parquet compatíveis com Hive particionados
por ano e UF com compressão ZSTD e estatísticas ativadas.

Satisfaz: REQ-ANAL-01.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl


def write_partitioned_parquet(
    df: pl.DataFrame,
    base_dir: Path,
    ano: int,
    uf: str,
) -> Path:
    """Grava DataFrame de seções em partição Hive Parquet com compressão ZSTD.

    Cria a hierarquia de diretórios: `{base_dir}/ano={ano}/uf={uf}/part-{uf}.parquet`.
    Utiliza compressão ZSTD nível 3 e habilita estatísticas colunares para
    aceleração de pushdown predicates no DuckDB.

    Satisfaz: REQ-ANAL-01.

    Args:
        df: DataFrame de seções pareadas a ser gravado.
        base_dir: Diretório raiz de dados processados.
        ano: Ano da eleição (ex.: 2022).
        uf: Sigla da UF em maiúsculas (ex.: 'SP').

    Returns:
        Caminho absoluto do arquivo Parquet gerado.

    Raises:
        ValueError: Caso o DataFrame esteja vazio ou a sigla da UF seja inválida.
    """
    if df.is_empty():
        raise ValueError("DataFrame vazio não pode ser gravado como partição.")

    uf_clean = uf.strip().upper()
    if not uf_clean:
        raise ValueError("Sigla de UF inválida.")

    partition_dir = base_dir / f"ano={ano}" / f"uf={uf_clean}"
    partition_dir.mkdir(parents=True, exist_ok=True)
    target_path = partition_dir / f"part-{uf_clean}.parquet"

    # Escrita com compressão zstd (nível 3) e estatísticas
    df.write_parquet(
        target_path,
        compression="zstd",
        compression_level=3,
        statistics=True,
    )

    return target_path


def list_processed_partitions(base_dir: Path, ano: int | None = None) -> list[Path]:
    """Lista todos os arquivos Parquet de partições existentes.

    Satisfaz: REQ-ANAL-01.

    Args:
        base_dir: Diretório raiz de dados processados.
        ano: Filtro opcional por ano específico.

    Returns:
        Lista de caminhos de arquivos Parquet encontrados ordenados por caminho.
    """
    if not base_dir.exists():
        return []

    pattern = f"ano={ano}/uf=*/*.parquet" if ano else "ano=*/uf=*/*.parquet"
    return sorted(base_dir.glob(pattern))

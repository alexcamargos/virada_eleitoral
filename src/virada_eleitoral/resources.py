"""Gerenciamento e carregamento de recursos analíticos e tabelas De-Para.

Fornece acesso otimizado em memória à tabela de correspondência entre
códigos municipais do TSE (5 dígitos) e códigos oficiais do IBGE (7 dígitos).
"""

from functools import lru_cache
from pathlib import Path

import polars as pl

from virada_eleitoral.config import get_settings
from virada_eleitoral.contracts.exceptions import ResourceNotFoundError


@lru_cache(maxsize=1)
def load_tse_ibge_mapping() -> pl.DataFrame:
    """Carrega em memória o mapeamento de códigos TSE para IBGE.

    Returns:
        pl.DataFrame: DataFrame Polars com colunas cd_municipio_tse, cd_municipio_ibge,
            sg_uf e nm_municipio.

    Raises:
        ResourceNotFoundError: Se o arquivo Parquet de De-Para não for encontrado.
    """
    settings = get_settings()
    parquet_path: Path = settings.resources_dir / "tse_ibge_municipios.parquet"

    if not parquet_path.exists():
        raise ResourceNotFoundError(
            f"Tabela de De-Para não encontrada em '{parquet_path}'. "
            "Execute o gerador de recursos antes de iniciar o pipeline."
        )

    return pl.read_parquet(parquet_path)


@lru_cache(maxsize=1)
def get_tse_to_ibge_dict() -> dict[int, int]:
    """Retorna dicionário em memória para resolução O(1) de código TSE para IBGE.

    Returns:
        dict[int, int]: Mapeamento {cd_municipio_tse: cd_municipio_ibge}.

    Raises:
        ResourceNotFoundError: Se a tabela de De-Para não estiver disponível.
    """
    df = load_tse_ibge_mapping()
    return dict(
        zip(
            df["cd_municipio_tse"].to_list(),
            df["cd_municipio_ibge"].to_list(),
            strict=False,
        )
    )


def lookup_ibge_code(cd_municipio_tse: int) -> int | None:
    """Busca o código IBGE de 7 dígitos correspondente ao código TSE de 5 dígitos.

    Args:
        cd_municipio_tse: Código numérico do município adotado pela Justiça Eleitoral.

    Returns:
        int | None: Código de 7 dígitos do IBGE ou None caso o município não seja localizado.
    """
    mapping = get_tse_to_ibge_dict()
    return mapping.get(cd_municipio_tse)

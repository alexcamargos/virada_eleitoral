"""Testes unitários de configuração do pipeline e recursos analíticos.

Valida a inicialização tipada do PipelineSettings e a resolução O(1) de códigos
municipais TSE para IBGE a partir da tabela Parquet versionada (REQ-QA-01).
"""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from virada_eleitoral.config import PipelineSettings, get_settings
from virada_eleitoral.contracts.exceptions import ResourceNotFoundError
from virada_eleitoral.resources import (
    get_tse_to_ibge_dict,
    load_tse_ibge_mapping,
    lookup_ibge_code,
)


def test_pipeline_settings_defaults() -> None:
    """Verifica se os valores padrão do PipelineSettings estão em conformidade com as specs."""
    settings = get_settings()

    assert settings.ano_eleicao_padrao == 2022
    assert settings.cargo_presidente_codigo == 1
    assert settings.numero_candidato_lula == 13
    assert settings.numero_candidato_bolsonaro == 22
    assert settings.numero_voto_branco == 95
    assert settings.numero_voto_nulo == 96
    assert settings.parquet_compression == "zstd"
    assert settings.data_dir.name == "data"
    assert settings.raw_data_dir.name == "raw"
    assert settings.processed_data_dir.name == "processed"
    assert settings.export_dir.name == "export"
    assert settings.resources_dir.name == "resources"
    assert settings.duckdb_path.name == "virada_eleitoral.duckdb"


def test_tse_ibge_mapping_loading() -> None:
    """Garante que a tabela De-Para tse_ibge_municipios.parquet é carregada com sucesso."""
    df = load_tse_ibge_mapping()

    assert len(df) == 5570
    assert "cd_municipio_tse" in df.columns
    assert "cd_municipio_ibge" in df.columns
    assert "sg_uf" in df.columns
    assert "nm_municipio" in df.columns


def test_lookup_ibge_code() -> None:
    """Valida a correspondência exata para municípios conhecidos do Brasil."""
    # São Paulo / SP: TSE 71072 -> IBGE 3550308
    ibge_sp = lookup_ibge_code(71072)
    assert ibge_sp == 3550308

    # Rio de Janeiro / RJ: TSE 60011 -> IBGE 3304557
    ibge_rj = lookup_ibge_code(60011)
    assert ibge_rj == 3304557

    # Código inexistente retorna None
    assert lookup_ibge_code(999999) is None


def test_resource_not_found_handling(mocker: MockerFixture) -> None:
    """Valida que ResourceNotFoundError é levantada se o arquivo Parquet não existir.

    Args:
        mocker: Fixture do pytest-mock para interceptar chamadas ao sistema de arquivos.
    """
    # Limpar caches de lru_cache para forçar nova leitura
    load_tse_ibge_mapping.cache_clear()
    get_tse_to_ibge_dict.cache_clear()

    mock_settings = mocker.MagicMock(spec=PipelineSettings)
    mock_settings.resources_dir = Path("c:/caminho/inexistente/para/teste")
    mocker.patch("virada_eleitoral.resources.get_settings", return_value=mock_settings)

    with pytest.raises(ResourceNotFoundError) as exc_info:
        load_tse_ibge_mapping()

    assert "Tabela de De-Para não encontrada" in str(exc_info.value)

    # Restaurar caches limpos após o teste
    load_tse_ibge_mapping.cache_clear()
    get_tse_to_ibge_dict.cache_clear()

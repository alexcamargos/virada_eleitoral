"""Fixtures compartilhadas para a suíte de testes do virada_eleitoral."""

from pathlib import Path

import pytest

from virada_eleitoral.config import PipelineSettings, get_settings


@pytest.fixture
def settings() -> PipelineSettings:
    """Fixture que fornece as configurações ativas do pipeline.

    Returns:
        PipelineSettings: Configuração padrão para os testes.
    """
    return get_settings()


@pytest.fixture
def sample_csv_dir(tmp_path: Path) -> Path:
    """Fixture que fornece um diretório temporário para arquivos simulados.

    Args:
        tmp_path: Fixture nativa do pytest com caminho temporário isolado.

    Returns:
        Path: Caminho do diretório temporário criado.
    """
    csv_dir = tmp_path / "raw"
    csv_dir.mkdir(parents=True, exist_ok=True)
    return csv_dir

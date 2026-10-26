"""Módulo de configuração centralizada do pipeline virada_eleitoral.

Utiliza Pydantic Settings para carregar variáveis de ambiente e definir
caminhos, limites de memória, concorrência e identificadores eleitorais.
"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class PipelineSettings(BaseSettings):
    """Configurações globais tipadas para o pipeline de virada eleitoral.

    Atributos:
        base_dir: Diretório raiz do projeto.
        data_dir: Diretório base para armazenamento temporário e final de dados.
        raw_data_dir: Diretório de arquivos brutos baixados do TSE (CSVs/ZIPs).
        processed_data_dir: Diretório de partições Parquet processadas.
        export_dir: Diretório de saída dos artefatos estáticos JSON e TopoJSON.
        resources_dir: Diretório de recursos estáticos versionados (De-Para e malha).
        duckdb_path: Caminho do banco analítico local DuckDB.
        ano_eleicao_padrao: Ano padrão da eleição presidencial auditada.
        cargo_presidente_codigo: Código numérico do cargo de Presidente no TSE.
        numero_candidato_lula: Número eleitoral oficial do candidato Lula.
        numero_candidato_bolsonaro: Número eleitoral oficial do candidato Bolsonaro.
        numero_voto_branco: Número eleitoral que identifica voto em branco.
        numero_voto_nulo: Número eleitoral que identifica voto nulo.
        max_concurrent_downloads: Número máximo de downloads simultâneos permitidos.
        download_timeout_seconds: Tempo limite em segundos para requisições HTTP.
        token_bucket_rate: Taxa máxima de requisições por segundo para a CDN do TSE.
        parquet_compression: Algoritmo de compressão para arquivos Parquet.
        parquet_compression_level: Nível de compressão ZSTD utilizado.
    """

    model_config = SettingsConfigDict(
        env_prefix="VIRADA_",
        env_file=".env",
        extra="ignore",
    )

    base_dir: Path = Field(default_factory=lambda: Path(__file__).resolve().parent.parent.parent)

    @property
    def data_dir(self) -> Path:
        """Retorna o diretório de dados principal.

        Returns:
            Path: Caminho absoluto para o diretório de dados.
        """
        return self.base_dir / "data"

    @property
    def raw_data_dir(self) -> Path:
        """Retorna o diretório de dados brutos do TSE.

        Returns:
            Path: Caminho absoluto para os dados brutos.
        """
        return self.data_dir / "raw"

    @property
    def processed_data_dir(self) -> Path:
        """Retorna o diretório de partições Parquet processadas.

        Returns:
            Path: Caminho absoluto para os dados processados.
        """
        return self.data_dir / "processed"

    @property
    def export_dir(self) -> Path:
        """Retorna o diretório de artefatos finais exportados.

        Returns:
            Path: Caminho absoluto para os dados exportados.
        """
        return self.data_dir / "export"

    @property
    def resources_dir(self) -> Path:
        """Retorna o diretório de recursos versionados.

        Returns:
            Path: Caminho absoluto para os recursos do projeto.
        """
        return self.base_dir / "resources"

    @property
    def duckdb_path(self) -> Path:
        """Retorna o caminho padrão do banco de dados DuckDB.

        Returns:
            Path: Caminho do arquivo .duckdb.
        """
        return self.data_dir / "virada_eleitoral.duckdb"

    # Parâmetros eleitorais canônicos
    ano_eleicao_padrao: int = 2022
    cargo_presidente_codigo: int = 1
    numero_candidato_lula: int = 13
    numero_candidato_bolsonaro: int = 22
    numero_voto_branco: int = 95
    numero_voto_nulo: int = 96

    # Parâmetros de infraestrutura e performance
    max_concurrent_downloads: int = 16
    download_timeout_seconds: float = 60.0
    token_bucket_rate: float = 30.0
    parquet_compression: str = "zstd"
    parquet_compression_level: int = 3


def get_settings() -> PipelineSettings:
    """Instancia e retorna o singleton de configurações do pipeline.

    Returns:
        PipelineSettings: Instância carregada das configurações.
    """
    return PipelineSettings()

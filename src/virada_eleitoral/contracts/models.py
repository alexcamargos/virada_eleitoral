"""Modelos de dados imutáveis e schemas de handoff entre estágios do pipeline.

Define dataclasses otimizadas para processamento em lote e modelos Pydantic v2
para validação de contratos de saída e artefatos de exportação estática.
"""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class TurnoverClassification(StrEnum):
    """Classificação categórica da dinâmica de virada eleitoral."""

    VIRADA_LULA = "VIRADA_LULA"
    VIRADA_ADVERSARIO = "VIRADA_ADVERSARIO"
    MANTEVE_LIDERANCA = "MANTEVE_LIDERANCA"
    MANTEVE_DESVANTAGEM = "MANTEVE_DESVANTAGEM"
    EMPATE = "EMPATE"


class PairingStatus(StrEnum):
    """Status de pareamento de uma seção eleitoral entre os dois turnos."""

    PAREADA_AMBOS = "PAREADA_AMBOS"
    APENAS_1T = "APENAS_1T"
    APENAS_2T = "APENAS_2T"


@dataclass(slots=True, frozen=True)
class RawBuFileBundle:
    """Contrato imutável de entrega de arquivo de BU pelo agent-harvester.

    Atributos:
        ano_eleicao: Ano da eleição (ex.: 2022).
        turno: Número do turno (1 ou 2).
        uf: Sigla da Unidade Federativa em maiúsculas (ex.: "SP").
        file_path: Caminho no sistema de arquivos para o arquivo CSV ou ZIP.
        sha512_hash: Hash criptográfico SHA-512 calculado sobre o arquivo.
        file_size_bytes: Tamanho do arquivo em bytes.
        is_compressed: Indica se o arquivo referenciado é um contêiner compactado ZIP.
    """

    ano_eleicao: int
    turno: int
    uf: str
    file_path: Path
    sha512_hash: str
    file_size_bytes: int
    is_compressed: bool


@dataclass(slots=True, frozen=True)
class HarvestManifest:
    """Manifesto de auditoria gerado após o download ou validação de um arquivo.

    Atributos:
        ano_eleicao: Ano da eleição.
        turno: Turno correspondente.
        uf: Sigla da UF.
        source_file: Nome do arquivo original.
        sha512: Hash SHA-512 apurado.
        file_size_bytes: Tamanho do arquivo em bytes.
        downloaded_at: Timestamp ISO 8601 da operação.
        status: Estado de integridade ('VERIFIED' ou 'ERROR').
    """

    ano_eleicao: int
    turno: int
    uf: str
    source_file: str
    sha512: str
    file_size_bytes: int
    downloaded_at: str
    status: str = "VERIFIED"


@dataclass(slots=True, frozen=True)
class SectionVotes1T:
    """Votos consolidados do primeiro turno para uma seção eleitoral.

    Atributos:
        aptos: Quantidade de eleitores aptos a votar na seção.
        comparecimento: Total de eleitores que compareceram à urna.
        abstencao: Total de eleitores faltosos.
        votos_validos: Soma de votos nominais válidos.
        votos_lula: Votos recebidos pelo candidato Lula (13).
        votos_adv: Votos recebidos pelo principal adversário (22).
        votos_outros: Soma de votos recebidos por terceiros candidatos.
        votos_brancos: Total de votos em branco (95).
        votos_nulos: Total de votos nulos (96).
    """

    aptos: int
    comparecimento: int
    abstencao: int
    votos_validos: int
    votos_lula: int
    votos_adv: int
    votos_outros: int
    votos_brancos: int
    votos_nulos: int


@dataclass(slots=True, frozen=True)
class SectionVotes2T:
    """Votos consolidados do segundo turno para uma seção eleitoral.

    Atributos:
        aptos: Quantidade de eleitores aptos a votar na seção.
        comparecimento: Total de eleitores que compareceram à urna.
        abstencao: Total de eleitores faltosos.
        votos_validos: Soma de votos nominais válidos (Lula + Adversário).
        votos_lula: Votos recebidos pelo candidato Lula (13).
        votos_adv: Votos recebidos pelo adversário (22).
        votos_brancos: Total de votos em branco (95).
        votos_nulos: Total de votos nulos (96).
    """

    aptos: int
    comparecimento: int
    abstencao: int
    votos_validos: int
    votos_lula: int
    votos_adv: int
    votos_brancos: int
    votos_nulos: int


@dataclass(slots=True, frozen=True)
class SectionTurnoverRecord:
    """Representação analítica atômica de uma seção eleitoral pareada.

    Atributos:
        ano_eleicao: Ano da eleição.
        sg_uf: Sigla da UF.
        cd_municipio: Código TSE do município.
        cd_municipio_ibge: Código IBGE de 7 dígitos (ou None se não localizado).
        nm_municipio: Nome oficial do município.
        nr_zona: Número da zona eleitoral.
        nr_secao: Número da seção eleitoral.
        status_pareamento: Status de pareamento entre turnos.
        votos_validos_1t: Total de votos válidos no 1T.
        votos_lula_1t: Votos de Lula no 1T.
        votos_adv_1t: Votos do adversário no 1T.
        votos_outros_1t: Votos de outros candidatos no 1T.
        pct_lula_1t: Percentual de votos válidos de Lula no 1T.
        pct_adv_1t: Percentual de votos válidos do adversário no 1T.
        votos_validos_2t: Total de votos válidos no 2T.
        votos_lula_2t: Votos de Lula no 2T.
        votos_adv_2t: Votos do adversário no 2T.
        pct_lula_2t: Percentual de votos válidos de Lula no 2T.
        pct_adv_2t: Percentual de votos válidos do adversário no 2T.
        delta_votos_lula: Diferença de votos de Lula (2T - 1T).
        delta_votos_adv: Diferença de votos do adversário (2T - 1T).
        delta_pp_lula: Variação em pontos percentuais de Lula.
        delta_pp_adv: Variação em pontos percentuais do adversário.
        margem_1t: Margem líquida no 1T (Lula - Adversário).
        margem_2t: Margem líquida no 2T (Lula - Adversário).
        delta_margem: Variação da margem líquida (2T - 1T).
        classificacao_virada: Classificação categórica da urna.
        eficiencia_absorcao_outros: Taxa de atração de votos de terceiros.
    """

    ano_eleicao: int
    sg_uf: str
    cd_municipio: int
    cd_municipio_ibge: int | None
    nm_municipio: str
    nr_zona: int
    nr_secao: int
    status_pareamento: PairingStatus
    votos_validos_1t: int
    votos_lula_1t: int
    votos_adv_1t: int
    votos_outros_1t: int
    pct_lula_1t: float
    pct_adv_1t: float
    votos_validos_2t: int
    votos_lula_2t: int
    votos_adv_2t: int
    pct_lula_2t: float
    pct_adv_2t: float
    delta_votos_lula: int
    delta_votos_adv: int
    delta_pp_lula: float
    delta_pp_adv: float
    margem_1t: int
    margem_2t: int
    delta_margem: int
    classificacao_virada: TurnoverClassification
    eficiencia_absorcao_outros: float | None = None


# ==============================================================================
# Modelos Pydantic v2 para Validação de Contratos de Exportação JSON Estática
# ==============================================================================


class NationalSummaryPayload(BaseModel):
    """Payload de KPIs consolidados para o Brasil."""

    model_config = ConfigDict(frozen=True)

    ano_eleicao: int
    total_secoes_analisadas: int
    total_secoes_pareadas: int
    total_validos_1t: int
    total_validos_2t: int
    total_lula_1t: int
    total_lula_2t: int
    total_adv_1t: int
    total_adv_2t: int
    total_outros_1t: int
    delta_nacional_lula: int
    pct_lula_1t_brasil: float = Field(..., ge=0.0, le=100.0)
    pct_lula_2t_brasil: float = Field(..., ge=0.0, le=100.0)
    delta_pp_lula_brasil: float
    total_urnas_virada_lula: int
    total_urnas_virada_adv: int


class StateSummaryItem(BaseModel):
    """Resumo de indicadores de virada eleitoral para uma Unidade Federativa."""

    model_config = ConfigDict(frozen=True)

    sg_uf: str = Field(..., min_length=2, max_length=2)
    total_secoes: int
    total_validos_1t: int
    total_validos_2t: int
    votos_lula_1t: int
    votos_lula_2t: int
    votos_adv_1t: int
    votos_adv_2t: int
    delta_votos_lula: int
    pct_lula_1t: float = Field(..., ge=0.0, le=100.0)
    pct_lula_2t: float = Field(..., ge=0.0, le=100.0)
    delta_pp_lula: float
    delta_margem: int
    total_urnas_virada_lula: int
    total_urnas_virada_adv: int


class SwingCityPayload(BaseModel):
    """Contrato de cidade onde ocorreu reversão de vencedor entre turnos."""

    model_config = ConfigDict(frozen=True)

    sg_uf: str = Field(..., min_length=2, max_length=2)
    cd_municipio: int
    cd_municipio_ibge: int | None
    nm_municipio: str
    total_secoes: int
    votos_lula_1t: int
    votos_lula_2t: int
    votos_adv_1t: int
    votos_adv_2t: int
    delta_votos_lula: int
    pct_lula_1t: float = Field(..., ge=0.0, le=100.0)
    pct_lula_2t: float = Field(..., ge=0.0, le=100.0)
    delta_pp_lula: float
    delta_margem: int
    status_virada_municipio: TurnoverClassification

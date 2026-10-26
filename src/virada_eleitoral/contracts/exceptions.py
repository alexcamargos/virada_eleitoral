"""Hierarquia de exceções canônicas de auditoria e pipeline do virada_eleitoral.

Define exceções tipadas para cada estágio do pipeline, facilitando o diagnóstico
preciso e o tratamento determinístico de falhas pelo orquestrador.
"""


class ViradaEleitoralError(Exception):
    """Exceção base para todas as falhas de execução do virada_eleitoral."""

    def __init__(self, message: str) -> None:
        """Inicializa a exceção com mensagem explicativa.

        Args:
            message: Mensagem detalhada da causa do erro.
        """
        super().__init__(message)
        self.message = message


class ConfigurationError(ViradaEleitoralError):
    """Lançada quando parâmetros ou variáveis de configuração são inválidos."""


class ResourceNotFoundError(ViradaEleitoralError):
    """Lançada quando um recurso versionado obrigatório não for localizado."""


class HarvesterError(ViradaEleitoralError):
    """Exceção base para falhas no módulo de coleta de Boletins de Urna."""


class CorruptBuArchiveError(HarvesterError):
    """Lançada quando um arquivo ZIP ou CSV de BU do TSE estiver corrompido ou truncado."""

    def __init__(self, path: str, reason: str) -> None:
        """Inicializa a exceção com caminho do arquivo e motivo.

        Args:
            path: Caminho do arquivo afetado.
            reason: Motivo técnico do erro de leitura.
        """
        super().__init__(f"Arquivo de BU corrompido em '{path}': {reason}")
        self.path = path
        self.reason = reason


class HashMismatchError(HarvesterError):
    """Lançada quando o hash SHA-512 do arquivo divergir do valor esperado."""

    def __init__(self, filename: str, expected_hash: str, actual_hash: str) -> None:
        """Inicializa a exceção com detalhes da divergência de integridade.

        Args:
            filename: Nome do arquivo inspecionado.
            expected_hash: Hash SHA-512 esperado pelo manifesto.
            actual_hash: Hash SHA-512 calculado sobre os bytes recebidos.
        """
        msg = (
            f"Divergência de hash SHA-512 para '{filename}'. "
            f"Esperado: {expected_hash}, Obtido: {actual_hash}"
        )
        super().__init__(msg)
        self.filename = filename
        self.expected_hash = expected_hash
        self.actual_hash = actual_hash


class NormalizerError(ViradaEleitoralError):
    """Exceção base para falhas durante a normalização e pareamento de urnas."""


class SchemaValidationError(NormalizerError):
    """Lançada quando o Boletim de Urna não contiver as colunas mínimas esperadas."""


class AnalyticsError(ViradaEleitoralError):
    """Exceção base para falhas no motor analítico ou consolidação OLAP."""


class InvariantViolationError(AnalyticsError):
    """Lançada quando uma invariante matemática mandatória for violada."""

    def __init__(self, invariant_name: str, details: str = "") -> None:
        """Inicializa a exceção com o nome da invariante e detalhes numéricos.

        Args:
            invariant_name: Identificador da invariante quebrada.
            details: Descrição e valores dos operandos divergentes.
        """
        msg = f"Violação da invariante matemática '{invariant_name}'"
        if details:
            msg += f": {details}"
        super().__init__(msg)
        self.invariant_name = invariant_name
        self.details = details


MathematicalInvariantViolationError = InvariantViolationError


class DataIntegrityError(AnalyticsError):
    """Lançada quando dados esperados para consolidação estão vazios ou corrompidos."""


class StorageBudgetExceededError(AnalyticsError):
    """Lançada quando o banco consolidado excede o teto de armazenamento do SLA."""


class ExportError(ViradaEleitoralError):
    """Exceção base para falhas na geração e validação de artefatos estáticos."""

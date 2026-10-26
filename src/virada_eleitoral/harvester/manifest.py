"""Módulo de manifesto e verificação de integridade de arquivos do TSE.

Calcula hashes SHA-512 em blocos para controle de memória e gerencia a gravação
e leitura de manifestos de auditoria JSON (REQ-HARV-02).
"""

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import orjson

from virada_eleitoral.contracts.exceptions import CorruptBuArchiveError, HashMismatchError
from virada_eleitoral.contracts.models import HarvestManifest

# Tamanho do bloco para streaming de hash em disco (64 KB)
BUFFER_CHUNK_SIZE = 65536


def compute_sha512(file_path: Path) -> str:
    """Calcula o hash SHA-512 de um arquivo em disco via streaming de blocos.

    Args:
        file_path: Caminho do arquivo a ser verificado.

    Returns:
        str: Hexdigest SHA-512 em minúsculas (128 caracteres).

    Raises:
        CorruptBuArchiveError: Se o arquivo não existir ou não puder ser lido.
    """
    if not file_path.exists() or not file_path.is_file():
        raise CorruptBuArchiveError(str(file_path), "Arquivo inexistente ou inacessível.")

    sha = hashlib.sha512()
    try:
        with file_path.open("rb") as f:
            while chunk := f.read(BUFFER_CHUNK_SIZE):
                sha.update(chunk)
    except OSError as e:
        raise CorruptBuArchiveError(str(file_path), f"Erro de I/O na leitura: {e}") from e

    return sha.hexdigest()


def verify_file_integrity(file_path: Path, expected_sha512: str) -> None:
    """Verifica se o arquivo em disco coincide com o hash SHA-512 esperado.

    Args:
        file_path: Caminho do arquivo a ser auditado.
        expected_sha512: Hash SHA-512 esperado em hexadecimal.

    Raises:
        HashMismatchError: Se o hash calculado divergir do esperado.
        CorruptBuArchiveError: Se o arquivo estiver corrompido ou inacessível.
    """
    actual_hash = compute_sha512(file_path)
    if actual_hash.lower() != expected_sha512.lower():
        raise HashMismatchError(file_path.name, expected_sha512, actual_hash)


class ManifestManager:
    """Gerencia a persistência e consulta de manifestos de coleta de Boletins de Urna."""

    def __init__(self, manifest_dir: Path) -> None:
        """Inicializa o gerenciador com o diretório onde os manifestos residem.

        Args:
            manifest_dir: Diretório onde os arquivos manifest_*.json serão gravados.
        """
        self.manifest_dir = manifest_dir
        self.manifest_dir.mkdir(parents=True, exist_ok=True)

    def get_manifest_path(self, ano: int, turno: int, uf: str) -> Path:
        """Gera o caminho canônico do arquivo de manifesto para uma UF e turno.

        Args:
            ano: Ano da eleição.
            turno: Turno da eleição (1 ou 2).
            uf: Sigla da UF em maiúsculas (ex.: 'SP').

        Returns:
            Path: Caminho do arquivo JSON de manifesto.
        """
        return self.manifest_dir / f"manifest_{ano}_{turno}_{uf.upper()}.json"

    def is_already_harvested(self, ano: int, turno: int, uf: str) -> bool:
        """Verifica se já existe manifesto com status VERIFIED para o conjunto.

        Args:
            ano: Ano da eleição.
            turno: Turno da eleição.
            uf: Sigla da UF.

        Returns:
            bool: True se o manifesto existir e indicar integridade verificada.
        """
        path = self.get_manifest_path(ano, turno, uf)
        if not path.exists():
            return False

        try:
            manifest = self.load_manifest(path)
            return manifest.status == "VERIFIED"
        except Exception:
            return False

    def create_and_save_manifest(
        self,
        ano: int,
        turno: int,
        uf: str,
        file_path: Path,
        expected_sha512: str | None = None,
    ) -> HarvestManifest:
        """Audita a integridade do arquivo e grava o manifesto JSON correspondente.

        Args:
            ano: Ano da eleição.
            turno: Turno da eleição.
            uf: Sigla da UF.
            file_path: Caminho do arquivo coletado.
            expected_sha512: Hash SHA-512 esperado (opcional).

        Returns:
            HarvestManifest: Instância do manifesto gravado em disco.

        Raises:
            HashMismatchError: Se expected_sha512 for informado e divergir.
            CorruptBuArchiveError: Se o arquivo não puder ser lido.
        """
        actual_hash = compute_sha512(file_path)
        if expected_sha512 and actual_hash.lower() != expected_sha512.lower():
            raise HashMismatchError(file_path.name, expected_sha512, actual_hash)

        manifest = HarvestManifest(
            ano_eleicao=ano,
            turno=turno,
            uf=uf.upper(),
            source_file=file_path.name,
            sha512=actual_hash,
            file_size_bytes=file_path.stat().st_size,
            downloaded_at=datetime.now(UTC).isoformat(),
            status="VERIFIED",
        )

        out_path = self.get_manifest_path(ano, turno, uf)
        data = {
            "ano_eleicao": manifest.ano_eleicao,
            "turno": manifest.turno,
            "uf": manifest.uf,
            "source_file": manifest.source_file,
            "sha512": manifest.sha512,
            "file_size_bytes": manifest.file_size_bytes,
            "downloaded_at": manifest.downloaded_at,
            "status": manifest.status,
        }
        out_path.write_bytes(orjson.dumps(data, option=orjson.OPT_INDENT_2))
        return manifest

    def load_manifest(self, manifest_path: Path) -> HarvestManifest:
        """Carrega e valida um arquivo de manifesto JSON existente em disco.

        Args:
            manifest_path: Caminho do arquivo JSON de manifesto.

        Returns:
            HarvestManifest: Objeto carregado com os metadados da auditoria.

        Raises:
            CorruptBuArchiveError: Se o manifesto não puder ser lido ou for inválido.
        """
        if not manifest_path.exists():
            raise CorruptBuArchiveError(str(manifest_path), "Manifesto não encontrado.")

        try:
            content = manifest_path.read_bytes()
            data = orjson.loads(content)
            return HarvestManifest(
                ano_eleicao=int(data["ano_eleicao"]),
                turno=int(data["turno"]),
                uf=str(data["uf"]).upper(),
                source_file=str(data["source_file"]),
                sha512=str(data["sha512"]),
                file_size_bytes=int(data["file_size_bytes"]),
                downloaded_at=str(data["downloaded_at"]),
                status=str(data.get("status", "VERIFIED")),
            )
        except Exception as e:
            raise CorruptBuArchiveError(
                str(manifest_path), f"Falha ao decodificar JSON de manifesto: {e}"
            ) from e

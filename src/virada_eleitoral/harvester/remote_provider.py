"""Cliente assíncrono resiliente para download de Boletins de Urna do TSE.

Implementa streaming direto para disco temporário, verificação SHA-512 em voo,
retries exponenciais e controle de concorrência com semáforo (REQ-HARV-01, REQ-HARV-02).
"""

import asyncio
import hashlib
import os
import random
from pathlib import Path

import httpx

from virada_eleitoral.contracts.exceptions import HarvesterError, HashMismatchError
from virada_eleitoral.contracts.models import RawBuFileBundle

# Tamanho do bloco para streaming de rede (64 KB)
STREAM_CHUNK_SIZE = 65536


class RemoteTseBuProvider:
    """Provedor para obtenção assíncrona de arquivos de BU diretamente dos servidores do TSE."""

    def __init__(
        self,
        base_url: str = "https://dadosabertos.tse.jus.br",
        download_timeout_seconds: float = 60.0,
        max_retries: int = 3,
    ) -> None:
        """Inicializa o cliente remoto com parâmetros de rede.

        Args:
            base_url: URL base do portal de Dados Abertos do TSE.
            download_timeout_seconds: Timeout máximo por requisição HTTP.
            max_retries: Quantidade máxima de tentativas em falhas transitórias.
        """
        self.base_url = base_url.rstrip("/")
        self.download_timeout = download_timeout_seconds
        self.max_retries = max_retries

    async def download_bu_file(
        self,
        url: str,
        dest_dir: Path,
        ano: int,
        turno: int,
        uf: str,
        expected_sha512: str | None = None,
    ) -> RawBuFileBundle:
        """Efetua o download em streaming com retry exponencial e verificação de integridade.

        Args:
            url: URL completa para download do arquivo (.zip ou .csv).
            dest_dir: Diretório de destino final no disco local.
            ano: Ano da eleição.
            turno: Turno da eleição.
            uf: Sigla da UF.
            expected_sha512: Hash SHA-512 esperado para validação (se disponível).

        Returns:
            RawBuFileBundle: Contrato preenchido com o arquivo baixado e validado.

        Raises:
            HarvesterError: Se as tentativas de download forem esgotadas sem sucesso.
            HashMismatchError: Se o hash SHA-512 divergir do valor esperado.
        """
        dest_dir.mkdir(parents=True, exist_ok=True)
        filename = url.split("/")[-1].split("?")[0]
        final_path = dest_dir / filename
        temp_path = dest_dir / f"{filename}.tmp"

        client_headers = {
            "User-Agent": "ViradaEleitoral-AuditPipeline/0.1 (+civic-audit-sdd)",
            "Accept-Encoding": "gzip, deflate, br",
        }

        attempt = 0
        last_error: Exception | None = None

        while attempt < self.max_retries:
            attempt += 1
            sha = hashlib.sha512()
            total_bytes = 0

            try:
                async with httpx.AsyncClient(
                    timeout=self.download_timeout, headers=client_headers
                ) as client:
                    async with client.stream("GET", url) as response:
                        if response.status_code != 200:
                            raise HarvesterError(
                                f"Servidor TSE retornou HTTP {response.status_code} para '{url}'."
                            )

                        with temp_path.open("wb") as f:
                            async for chunk in response.aiter_bytes(STREAM_CHUNK_SIZE):
                                sha.update(chunk)
                                f.write(chunk)
                                total_bytes += len(chunk)

                computed_hash = sha.hexdigest()

                # Validar hash esperado se fornecido
                if expected_sha512 and computed_hash.lower() != expected_sha512.lower():
                    temp_path.unlink(missing_ok=True)
                    raise HashMismatchError(filename, expected_sha512, computed_hash)

                # Renomear de forma atômica o arquivo temporário
                os.replace(temp_path, final_path)

                is_zip = filename.lower().endswith(".zip")
                return RawBuFileBundle(
                    ano_eleicao=ano,
                    turno=turno,
                    uf=uf.upper(),
                    file_path=final_path,
                    sha512_hash=computed_hash,
                    file_size_bytes=total_bytes,
                    is_compressed=is_zip,
                )

            except (httpx.HTTPError, OSError, HarvesterError) as e:
                last_error = e
                temp_path.unlink(missing_ok=True)
                if attempt >= self.max_retries:
                    break

                # Backoff exponencial com jitter
                sleep_seconds = (0.5 * (2**attempt)) + random.uniform(0.1, 0.5)
                await asyncio.sleep(sleep_seconds)

        if isinstance(last_error, HashMismatchError):
            raise last_error

        raise HarvesterError(
            f"Falha ao baixar '{url}' após {self.max_retries} tentativas. Causa: {last_error}"
        ) from last_error

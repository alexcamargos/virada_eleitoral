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

    def fetch_dataset_catalog(self, ano: int) -> dict[tuple[str, int], tuple[str, str | None]]:
        """Consulta o catálogo CKAN do TSE e mapeia URLs de BUs e hashes SHA-512.

        Args:
            ano: Ano da eleição (ex.: 2022 ou 2026).

        Returns:
            dict[tuple[str, int], tuple[str, str | None]]: Dicionário mapeando
                (sigla_uf, turno) para tupla (url_arquivo_bu, url_hash_sha512).

        Raises:
            HarvesterError: Se a API CKAN do TSE retornar erro ou pacote não encontrado.
        """
        api_url = f"{self.base_url}/api/3/action/package_show?id=resultados-{ano}-boletim-de-urna"
        headers = {"User-Agent": "ViradaEleitoral-AuditPipeline/0.1 (+civic-audit-sdd)"}
        try:
            with httpx.Client(timeout=self.download_timeout, headers=headers) as client:
                resp = client.get(api_url)
                if resp.status_code != 200:
                    raise HarvesterError(
                        f"TSE CKAN API retornou status HTTP {resp.status_code} para ano {ano}."
                    )
                data = resp.json()
        except httpx.HTTPError as e:
            raise HarvesterError(f"Falha de conexão com TSE CKAN API: {e}") from e

        resources = data.get("result", {}).get("resources", [])
        bu_map: dict[tuple[str, int], str] = {}
        hash_map: dict[tuple[str, int], str] = {}

        for res in resources:
            name = str(res.get("name", ""))
            url = str(res.get("url", ""))
            parts = name.split(" - ")
            if len(parts) >= 3:
                uf = parts[0].strip().upper()
                tipo = parts[1].strip()
                turno = 1 if "primeiro" in parts[2].lower() or "1t" in parts[2].lower() else 2
                if "Boletim de Urna" in tipo:
                    bu_map[(uf, turno)] = url
                elif "Hash" in tipo or "SHA" in tipo:
                    hash_map[(uf, turno)] = url

        catalog: dict[tuple[str, int], tuple[str, str | None]] = {}
        for key, bu_url in bu_map.items():
            catalog[key] = (bu_url, hash_map.get(key))

        return catalog

    def fetch_expected_sha512(self, hash_url: str) -> str | None:
        """Obtém o hash SHA-512 oficial publicado pelo TSE a partir da URL.

        Args:
            hash_url: URL para o arquivo de hash .sha512.

        Returns:
            str | None: String contendo os 128 caracteres hexadecimais do hash.

        Raises:
            None: Retorna None em caso de falha de conexão.
        """
        headers = {"User-Agent": "ViradaEleitoral-AuditPipeline/0.1 (+civic-audit-sdd)"}
        try:
            with httpx.Client(timeout=15.0, headers=headers) as client:
                resp = client.get(hash_url)
                if resp.status_code == 200:
                    parts = resp.text.strip().split()
                    return parts[0] if parts else None
        except httpx.HTTPError:
            pass
        return None

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

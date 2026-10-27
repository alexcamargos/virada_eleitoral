"""Testes unitários do módulo de coleta, integridade e streaming (agent-harvester).

Valida cálculo de hash SHA-512, manifestos de auditoria, inspeção e extração seletiva
de pacotes ZIP, e cliente assíncrono com retries e mock (REQ-HARV-01, REQ-HARV-02).
"""

import hashlib
import zipfile
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from virada_eleitoral.contracts.exceptions import (
    CorruptBuArchiveError,
    HarvesterError,
    HashMismatchError,
    ResourceNotFoundError,
)
from virada_eleitoral.harvester.local_provider import LocalBuProvider
from virada_eleitoral.harvester.manifest import (
    ManifestManager,
    compute_sha512,
    verify_file_integrity,
)
from virada_eleitoral.harvester.remote_provider import RemoteTseBuProvider


def test_compute_sha512_and_integrity(tmp_path: Path) -> None:
    """Verifica o cálculo de SHA-512 e a assertiva de integridade em arquivo temporário."""
    content = b"TESTE DE INTEGRIDADE BU TSE" * 1000
    test_file = tmp_path / "teste_hash.txt"
    test_file.write_bytes(content)

    expected_hash = hashlib.sha512(content).hexdigest()
    computed = compute_sha512(test_file)
    assert computed == expected_hash

    # Verificação com hash correto não deve levantar erro
    verify_file_integrity(test_file, expected_hash)

    # Verificação com hash incorreto deve lançar HashMismatchError
    with pytest.raises(HashMismatchError) as exc_info:
        verify_file_integrity(test_file, "0" * 128)
    assert "Divergência de hash SHA-512" in str(exc_info.value)


def test_compute_sha512_nonexistent_file() -> None:
    """Garante que CorruptBuArchiveError é levantada se o arquivo não existir."""
    fake_path = Path("c:/caminho/fake/que/nao/existe.csv")
    with pytest.raises(CorruptBuArchiveError):
        compute_sha512(fake_path)


def test_manifest_manager_lifecycle(tmp_path: Path) -> None:
    """Valida o ciclo de gravação, idempotência e recuperação de manifestos de coleta."""
    manager = ManifestManager(tmp_path / "manifests")
    dummy_file = tmp_path / "bweb_1t_SP_2022.csv"
    dummy_file.write_bytes(b"CONTEUDO BU DUMMY")

    assert manager.is_already_harvested(2022, 1, "SP") is False

    manifest = manager.create_and_save_manifest(2022, 1, "SP", dummy_file)
    assert manifest.status == "VERIFIED"
    assert manifest.uf == "SP"

    assert manager.is_already_harvested(2022, 1, "SP") is True

    manifest_path = manager.get_manifest_path(2022, 1, "SP")
    loaded = manager.load_manifest(manifest_path)
    assert loaded.sha512 == manifest.sha512
    assert loaded.file_size_bytes == dummy_file.stat().st_size


def test_manifest_manager_corrupt_manifest(tmp_path: Path) -> None:
    """Valida que arquivo JSON de manifesto inválido dispara CorruptBuArchiveError."""
    manager = ManifestManager(tmp_path / "manifests")
    corrupt_file = tmp_path / "manifests" / "manifest_2022_1_RJ.json"
    corrupt_file.write_text("JSON_INVALIDO_NAO_PARSEAVEL")

    with pytest.raises(CorruptBuArchiveError):
        manager.load_manifest(corrupt_file)


def test_local_bu_provider_find_and_bundle(tmp_path: Path) -> None:
    """Verifica a descoberta e empacotamento de arquivo CSV de BU local."""
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(parents=True)
    sample_csv = raw_dir / "bweb_1t_MG_02102022.csv"
    sample_csv.write_text("SG_UF;CD_MUNICIPIO\nMG;41238\n", encoding="iso-8859-1")

    provider = LocalBuProvider(raw_dir)
    found_path = provider.find_bu_file(2022, 1, "MG")
    assert found_path == sample_csv

    bundle = provider.get_bundle(2022, 1, "MG")
    assert bundle.ano_eleicao == 2022
    assert bundle.turno == 1
    assert bundle.uf == "MG"
    assert bundle.is_compressed is False
    assert bundle.file_size_bytes > 0


def test_local_bu_provider_missing_file(tmp_path: Path) -> None:
    """Garante que ResourceNotFoundError é lançada para UF sem arquivo correspondente."""
    provider = LocalBuProvider(tmp_path)
    with pytest.raises(ResourceNotFoundError):
        provider.find_bu_file(2022, 1, "RR")


def test_local_bu_provider_zip_handling_and_extraction(tmp_path: Path) -> None:
    """Valida a detecção por magic bytes e a extração seletiva de CSV dentro de ZIP."""
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(parents=True)
    zip_path = raw_dir / "bweb_1t_BA_02102022.zip"

    # Criar um ZIP válido contendo um CSV
    csv_content = "SG_UF;CD_MUNICIPIO\nBA;38490\n"
    with zipfile.ZipFile(zip_path, mode="w") as zf:
        zf.writestr("bweb_1t_BA_02102022.csv", csv_content)

    provider = LocalBuProvider(raw_dir)
    assert provider.is_zip_file(zip_path) is True
    assert provider.validate_archive(zip_path) is True

    bundle = provider.get_bundle(2022, 1, "BA")
    assert bundle.is_compressed is True

    extracted_dir = tmp_path / "extracted"
    extracted_csv = provider.extract_csv_from_zip(zip_path, extracted_dir)
    assert extracted_csv.exists()
    assert extracted_csv.read_text(encoding="iso-8859-1") == csv_content

    # Segunda chamada deve reutilizar arquivo existente
    reused_csv = provider.extract_csv_from_zip(zip_path, extracted_dir)
    assert reused_csv == extracted_csv


def test_local_bu_provider_corrupt_zip(tmp_path: Path) -> None:
    """Valida detecção de arquivo com extensão .zip mas dados corrompidos."""
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(parents=True)
    corrupt_zip = raw_dir / "bweb_1t_RS_02102022.zip"
    corrupt_zip.write_bytes(b"\x50\x4b\x03\x04LIXO_CORROMPIDO_SEM_CENTRAL_DIRECTORY")

    provider = LocalBuProvider(raw_dir)
    with pytest.raises(CorruptBuArchiveError):
        provider.validate_archive(corrupt_zip)


def test_local_bu_provider_zip_without_csv(tmp_path: Path) -> None:
    """Garante que CorruptBuArchiveError é levantada se o ZIP não contiver arquivos CSV."""
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(parents=True)
    zip_path = raw_dir / "bweb_1t_TO_02102022.zip"

    with zipfile.ZipFile(zip_path, mode="w") as zf:
        zf.writestr("arquivo_qualquer.txt", "conteudo txt sem csv")

    provider = LocalBuProvider(raw_dir)
    with pytest.raises(CorruptBuArchiveError) as exc_info:
        provider.extract_csv_from_zip(zip_path, tmp_path / "extracted")
    assert "Nenhum arquivo CSV encontrado" in str(exc_info.value)


def test_manifest_manager_hash_mismatch(tmp_path: Path) -> None:
    """Garante que create_and_save_manifest falha se expected_sha512 divergir."""
    manager = ManifestManager(tmp_path / "manifests")
    dummy_file = tmp_path / "bweb_1t_AM_2022.csv"
    dummy_file.write_bytes(b"DADOS AM")

    with pytest.raises(HashMismatchError):
        manager.create_and_save_manifest(2022, 1, "AM", dummy_file, expected_sha512="0" * 128)


def test_manifest_manager_load_nonexistent(tmp_path: Path) -> None:
    """Valida erro ao tentar carregar manifesto que não existe."""
    manager = ManifestManager(tmp_path / "manifests")
    with pytest.raises(CorruptBuArchiveError):
        manager.load_manifest(tmp_path / "manifests" / "inexistente.json")


def test_manifest_manager_is_already_harvested_with_invalid_json(tmp_path: Path) -> None:
    """Valida que is_already_harvested retorna False caso o JSON existente esteja corrompido."""
    manager = ManifestManager(tmp_path / "manifests")
    corrupt_manifest = tmp_path / "manifests" / "manifest_2022_1_CE.json"
    corrupt_manifest.parent.mkdir(parents=True, exist_ok=True)
    corrupt_manifest.write_text("INVALID_JSON")

    assert manager.is_already_harvested(2022, 1, "CE") is False


def test_local_bu_provider_is_zip_nonexistent_or_tiny(tmp_path: Path) -> None:
    """Garante que arquivos minúsculos (<4 bytes) ou inexistentes retornam False em is_zip_file."""
    provider = LocalBuProvider(tmp_path)
    assert provider.is_zip_file(tmp_path / "nao_existe.zip") is False

    tiny_file = tmp_path / "tiny.zip"
    tiny_file.write_bytes(b"PK")  # 2 bytes (< 4)
    assert provider.is_zip_file(tiny_file) is False


def test_local_bu_provider_validate_non_zip(tmp_path: Path) -> None:
    """Garante que validate_archive retorna False para arquivos que não são ZIP."""
    provider = LocalBuProvider(tmp_path)
    txt_file = tmp_path / "arquivo.csv"
    txt_file.write_text("col1;col2\n")
    assert provider.validate_archive(txt_file) is False


@pytest.mark.asyncio
async def test_remote_tse_bu_provider_download_success(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    """Valida o fluxo assíncrono de download com streaming e verificação de integridade."""
    dest_dir = tmp_path / "downloads"
    dummy_payload = b"DADOS_REMOTOS_BOLETIM_URNA_TSE" * 100
    expected_hash = hashlib.sha512(dummy_payload).hexdigest()

    # Mockar a resposta com stream de bytes
    class MockStreamResponse:
        status_code = 200

        async def aiter_bytes(self, chunk_size: int = 65536) -> AsyncIterator[bytes]:
            yield dummy_payload

        async def __aenter__(self) -> "MockStreamResponse":
            return self

        async def __aexit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
            pass

    class MockAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def __aenter__(self) -> "MockAsyncClient":
            return self

        async def __aexit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
            pass

        def stream(self, method: str, url: str) -> MockStreamResponse:
            return MockStreamResponse()

    mocker.patch("httpx.AsyncClient", MockAsyncClient)

    provider = RemoteTseBuProvider()
    bundle = await provider.download_bu_file(
        url="https://dadosabertos.tse.jus.br/dataset/bweb_1t_AC.csv",
        dest_dir=dest_dir,
        ano=2022,
        turno=1,
        uf="AC",
        expected_sha512=expected_hash,
    )

    assert bundle.uf == "AC"
    assert bundle.file_path.exists()
    assert bundle.sha512_hash == expected_hash
    assert bundle.file_size_bytes == len(dummy_payload)


@pytest.mark.asyncio
async def test_remote_tse_bu_provider_download_hash_mismatch(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    """Verifica que divergência de hash SHA-512 remove o arquivo temporário e levanta erro."""
    dest_dir = tmp_path / "downloads"
    dummy_payload = b"PAYLOAD_COM_HASH_DIVERGENTE"

    class MockStreamResponse:
        status_code = 200

        async def aiter_bytes(self, chunk_size: int = 65536) -> AsyncIterator[bytes]:
            yield dummy_payload

        async def __aenter__(self) -> "MockStreamResponse":
            return self

        async def __aexit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
            pass

    class MockAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def __aenter__(self) -> "MockAsyncClient":
            return self

        async def __aexit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
            pass

        def stream(self, method: str, url: str) -> MockStreamResponse:
            return MockStreamResponse()

    mocker.patch("httpx.AsyncClient", MockAsyncClient)

    provider = RemoteTseBuProvider()
    with pytest.raises(HashMismatchError):
        await provider.download_bu_file(
            url="https://dadosabertos.tse.jus.br/dataset/bweb_1t_AL.csv",
            dest_dir=dest_dir,
            ano=2022,
            turno=1,
            uf="AL",
            expected_sha512="0" * 128,  # Hash incompatível
        )


@pytest.mark.asyncio
async def test_remote_tse_bu_provider_retries_exhausted(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    """Garante que erro HTTP 500 em todas as tentativas levanta HarvesterError."""
    dest_dir = tmp_path / "downloads"

    class MockErrorResponse:
        status_code = 500

        async def __aenter__(self) -> "MockErrorResponse":
            return self

        async def __aexit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
            pass

    class MockAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def __aenter__(self) -> "MockAsyncClient":
            return self

        async def __aexit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
            pass

        def stream(self, method: str, url: str) -> MockErrorResponse:
            return MockErrorResponse()

    mocker.patch("httpx.AsyncClient", MockAsyncClient)

    provider = RemoteTseBuProvider(max_retries=2)
    with pytest.raises(HarvesterError) as exc_info:
        await provider.download_bu_file(
            url="https://dadosabertos.tse.jus.br/dataset/bweb_1t_DF.csv",
            dest_dir=dest_dir,
            ano=2022,
            turno=1,
            uf="DF",
        )
    assert "Falha ao baixar" in str(exc_info.value)


def test_remote_tse_bu_provider_fetch_dataset_catalog_ckan_success(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    """Verifica consulta de catálogo à API CKAN do TSE com extração de BUs e hashes."""
    mock_client = mocker.MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_resp = mocker.MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "result": {
            "resources": [
                {
                    "name": "SP - Boletim de Urna - 1T",
                    "url": "https://dadosabertos.tse.jus.br/dataset/bweb_1t_SP.zip",
                },
                {
                    "name": "SP - Hash SHA-512 - 1T",
                    "url": "https://dadosabertos.tse.jus.br/dataset/bweb_1t_SP.zip.sha512",
                },
            ]
        }
    }
    mock_client.get.return_value = mock_resp
    mocker.patch("httpx.Client", return_value=mock_client)

    provider = RemoteTseBuProvider()
    catalog = provider.fetch_dataset_catalog(ano=2026, cache_dir=tmp_path)

    assert ("SP", 1) in catalog
    bu_url, hash_url = catalog[("SP", 1)]
    assert bu_url == "https://dadosabertos.tse.jus.br/dataset/bweb_1t_SP.zip"
    assert hash_url == "https://dadosabertos.tse.jus.br/dataset/bweb_1t_SP.zip.sha512"

    # Segunda chamada deve usar o cache em disco
    cached_catalog = provider.fetch_dataset_catalog(ano=2026, cache_dir=tmp_path)
    assert ("SP", 1) in cached_catalog


def test_remote_tse_bu_provider_fetch_dataset_catalog_fallback(mocker: MockerFixture) -> None:
    """Verifica fallback determinístico quando CKAN retorna 429."""
    mock_client = mocker.MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_resp = mocker.MagicMock()
    mock_resp.status_code = 429
    mock_client.get.return_value = mock_resp
    mocker.patch("httpx.Client", return_value=mock_client)

    provider = RemoteTseBuProvider(max_retries=1)
    catalog = provider.fetch_dataset_catalog(ano=2026)
    assert len(catalog) > 0
    assert ("SP", 1) in catalog
    assert ("AC", 1) in catalog


def test_remote_tse_bu_provider_fetch_dataset_catalog_unsupported_year(
    mocker: MockerFixture,
) -> None:
    """Garante que ano sem fallback canônico levanta HarvesterError em falha de API."""
    mock_client = mocker.MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_resp = mocker.MagicMock()
    mock_resp.status_code = 500
    mock_client.get.return_value = mock_resp
    mocker.patch("httpx.Client", return_value=mock_client)

    provider = RemoteTseBuProvider(max_retries=1)
    with pytest.raises(HarvesterError, match="sem fallback"):
        provider.fetch_dataset_catalog(ano=1990)


def test_remote_tse_bu_provider_fetch_expected_sha512(mocker: MockerFixture) -> None:
    """Verifica obtenção do hash SHA-512 oficial da URL e tratamento de erro."""
    mock_client = mocker.MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_resp = mocker.MagicMock()
    mock_resp.status_code = 200
    expected_hash = "a" * 128
    mock_resp.text = f"{expected_hash}  bweb_1t_SP.zip\n"
    mock_client.get.return_value = mock_resp
    mocker.patch("httpx.Client", return_value=mock_client)

    provider = RemoteTseBuProvider()
    res = provider.fetch_expected_sha512("https://cdn.tse.jus.br/bu.sha512")
    assert res == expected_hash

    # Erro de rede
    mock_resp.status_code = 404
    res_none = provider.fetch_expected_sha512("https://cdn.tse.jus.br/notfound.sha512")
    assert res_none is None

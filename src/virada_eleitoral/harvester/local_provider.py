"""Provedor local de Boletins de Urna com streaming e suporte a ZIP.

Localiza e valida arquivos brutos CSV ou ZIP em diretório local sem
carregamento desnecessário na memória RAM (REQ-HARV-01).
"""

import zipfile
from pathlib import Path

from virada_eleitoral.contracts.exceptions import CorruptBuArchiveError, ResourceNotFoundError
from virada_eleitoral.contracts.models import RawBuFileBundle
from virada_eleitoral.harvester.manifest import compute_sha512

# Magic bytes oficiais de arquivos ZIP padrão (PK\x03\x04)
ZIP_MAGIC_BYTES = b"\x50\x4b\x03\x04"


class LocalBuProvider:
    """Provedor de arquivos de Boletim de Urna a partir do sistema de arquivos local."""

    def __init__(self, raw_dir: Path) -> None:
        """Inicializa o provedor com o diretório raiz de arquivos brutos.

        Args:
            raw_dir: Caminho do diretório contendo arquivos .zip ou .csv do TSE.
        """
        self.raw_dir = raw_dir

    def find_bu_file(self, ano: int, turno: int, uf: str) -> Path:
        """Localiza o arquivo de BU bruto (ZIP ou CSV) correspondente aos parâmetros.

        Args:
            ano: Ano da eleição (ex.: 2022).
            turno: Turno da eleição (1 ou 2).
            uf: Sigla da UF em minúsculas ou maiúsculas (ex.: 'SP').

        Returns:
            Path: Caminho do arquivo de BU localizado.

        Raises:
            ResourceNotFoundError: Se nenhum arquivo compatível for localizado.
        """
        uf_upper = uf.upper()
        uf_lower = uf.lower()

        patterns = [
            f"bweb_{turno}t_{uf_upper}*.zip",
            f"bweb_{turno}t_{uf_lower}*.zip",
            f"bweb_{turno}t_{uf_upper}*.csv",
            f"bweb_{turno}t_{uf_lower}*.csv",
        ]

        for pattern in patterns:
            matches = sorted(self.raw_dir.glob(pattern))
            if matches:
                return matches[0]

        raise ResourceNotFoundError(
            f"Nenhum Boletim de Urna localizado para {ano} turno {turno} UF '{uf}' "
            f"no diretório '{self.raw_dir}'."
        )

    def is_zip_file(self, path: Path) -> bool:
        r"""Determina se o arquivo é um contêiner ZIP inspecionando seus magic bytes.

        Args:
            path: Caminho do arquivo a ser inspecionado.

        Returns:
            bool: True se os primeiros 4 bytes coincidirem com PK\x03\x04.
        """
        if not path.exists() or path.stat().st_size < 4:
            return False

        with path.open("rb") as f:
            header = f.read(4)
            return header.startswith(ZIP_MAGIC_BYTES)

    def validate_archive(self, path: Path) -> bool:
        """Valida a integridade estrutural de um arquivo ZIP sem extração completa.

        Args:
            path: Caminho do arquivo ZIP a ser validado.

        Returns:
            bool: True se o arquivo for um ZIP válido.

        Raises:
            CorruptBuArchiveError: Se o arquivo estiver corrompido ou truncado.
        """
        if not self.is_zip_file(path):
            return False

        try:
            with zipfile.ZipFile(path, mode="r") as zf:
                # testzip() lê os CRC32 de cada membro sem alocar os dados em RAM
                bad_file = zf.testzip()
                if bad_file:
                    raise CorruptBuArchiveError(
                        str(path), f"Membro '{bad_file}' falhou na verificação de integridade CRC."
                    )
            return True
        except zipfile.BadZipFile as e:
            raise CorruptBuArchiveError(str(path), f"Arquivo ZIP inválido ou truncado: {e}") from e

    def extract_csv_from_zip(self, zip_path: Path, output_dir: Path) -> Path:
        """Extrai seletivamente apenas o arquivo CSV interno de um pacote ZIP do TSE.

        Args:
            zip_path: Caminho do pacote ZIP do TSE.
            output_dir: Diretório de destino para o CSV extraído.

        Returns:
            Path: Caminho do arquivo CSV descompactado.

        Raises:
            CorruptBuArchiveError: Se o ZIP não contiver nenhum arquivo CSV válido.
        """
        self.validate_archive(zip_path)
        output_dir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path, mode="r") as zf:
            csv_members = [m for m in zf.namelist() if m.lower().endswith(".csv")]
            if not csv_members:
                raise CorruptBuArchiveError(
                    str(zip_path), "Nenhum arquivo CSV encontrado dentro do pacote ZIP."
                )

            csv_name = csv_members[0]
            extracted_path = output_dir / Path(csv_name).name

            # Evita extrair novamente se já existir e tiver tamanho compatível
            info = zf.getinfo(csv_name)
            if extracted_path.exists() and extracted_path.stat().st_size == info.file_size:
                return extracted_path

            # Extração em streaming para não estourar teto de 8 GB RAM
            with zf.open(csv_name) as source, extracted_path.open("wb") as target:
                while chunk := source.read(65536):
                    target.write(chunk)

            return extracted_path

    def get_bundle(self, ano: int, turno: int, uf: str) -> RawBuFileBundle:
        """Localiza, valida e encapsula o artefato de BU no contrato RawBuFileBundle.

        Args:
            ano: Ano da eleição.
            turno: Turno da eleição.
            uf: Sigla da UF.

        Returns:
            RawBuFileBundle: Contrato pronto para handoff ao agent-normalizer.

        Raises:
            ResourceNotFoundError: Se o arquivo não existir.
            CorruptBuArchiveError: Se o arquivo for corrompido.
        """
        file_path = self.find_bu_file(ano, turno, uf)
        is_zip = self.is_zip_file(file_path)

        if is_zip:
            self.validate_archive(file_path)

        sha512_hash = compute_sha512(file_path)
        file_size = file_path.stat().st_size

        return RawBuFileBundle(
            ano_eleicao=ano,
            turno=turno,
            uf=uf.upper(),
            file_path=file_path,
            sha512_hash=sha512_hash,
            file_size_bytes=file_size,
            is_compressed=is_zip,
        )

    def unpack_national_dataset_if_present(self, ano: int = 2026) -> int:
        """Extrai e particiona o arquivo nacional de votação por seção em CSVs de BU por UF.

        Caso raw_dir contenha o ZIP nacional ou CSV extraído correspondente,
        descompacta e divide via DuckDB em 'bweb_1t_{UF}_{ano}.csv' e 'bweb_2t_{UF}_{ano}.csv'.

        Args:
            ano: Ano da eleição a processar (padrão: 2026).

        Returns:
            int: Quantidade de arquivos de UF gerados ou 0 caso não aplicável.

        Raises:
            None: Falhas são tratadas graciosamente retornando 0.
        """
        import duckdb

        national_zip = self.raw_dir / f"votacao_secao_{ano}_BR.zip"
        extracted_dir = self.raw_dir / "extracted"
        extracted_csv = extracted_dir / f"votacao_secao_{ano}_BR.csv"

        if not extracted_csv.exists() and national_zip.exists():
            try:
                self.extract_csv_from_zip(national_zip, extracted_dir)
            except Exception:
                return 0

        if not extracted_csv.exists():
            return 0

        csv_str = str(extracted_csv).replace("\\", "/")
        generated_count = 0

        try:
            conn = duckdb.connect(":memory:")
            conn.execute(
                f"""
                CREATE OR REPLACE TABLE bu_pres_all AS
                SELECT
                    sg_uf AS SG_UF,
                    cd_municipio AS CD_MUNICIPIO,
                    nm_municipio AS NM_MUNICIPIO,
                    nr_zona AS NR_ZONA,
                    nr_secao AS NR_SECAO,
                    cd_cargo AS CD_CARGO,
                    nr_votavel AS NR_VOTAVEL,
                    qt_votos AS QT_VOTOS,
                    0 AS QT_APTOS,
                    0 AS QT_COMPARECIMENTO,
                    0 AS QT_ABSTENCAO,
                    sg_uf,
                    nr_turno
                FROM read_csv('{csv_str}', delim=';', header=true, encoding='iso-8859-1')
                WHERE cd_cargo = 1;
                """
            )
            ufs = [
                row[0]
                for row in conn.execute(
                    "SELECT DISTINCT sg_uf FROM bu_pres_all ORDER BY sg_uf"
                ).fetchall()
            ]

            for uf in ufs:
                for turno in (1, 2):
                    out_file = self.raw_dir / f"bweb_{turno}t_{uf}_{ano}.csv"
                    if not out_file.exists():
                        out_str = str(out_file).replace("\\", "/")
                        conn.execute(
                            f"""
                            COPY (
                                SELECT
                                    SG_UF, CD_MUNICIPIO, NM_MUNICIPIO, NR_ZONA, NR_SECAO,
                                    CD_CARGO, NR_VOTAVEL, QT_VOTOS, QT_APTOS,
                                    QT_COMPARECIMENTO, QT_ABSTENCAO
                                FROM bu_pres_all
                                WHERE sg_uf = '{uf}' AND nr_turno = {turno}
                            ) TO '{out_str}' (HEADER, DELIMITER ';');
                            """
                        )
                        generated_count += 1
            conn.close()
        except Exception:
            return 0

        return generated_count

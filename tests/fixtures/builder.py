"""Gerador e catálogo determinístico de fixtures áureas (FX-01 a FX-10).

Codifica os 10 cenários canônicos de teste para Boletins de Urna (BUs)
presidenciais do TSE, abrangendo viradas, manutenções, seções agregadas,
contingências e cálculos de absorção de votos (REQ-QA-01).
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from virada_eleitoral.contracts.models import PairingStatus, TurnoverClassification

# Cabeçalho padrão do Boletim de Urna (BWeb) do TSE para votação por seção
TSE_BU_CSV_HEADER = [
    "SG_UF",
    "CD_MUNICIPIO",
    "NM_MUNICIPIO",
    "NR_ZONA",
    "NR_SECAO",
    "CD_CARGO",
    "NR_VOTAVEL",
    "QT_VOTOS",
    "QT_APTOS",
    "QT_COMPARECIMENTO",
    "QT_ABSTENCAO",
]

# Mapeamento canônico dos números de votáveis para as Eleições Presidenciais de 2026
NR_VOTAVEL_LULA = 13
NR_VOTAVEL_FLAVIO = 22
NR_VOTAVEL_CURY = 45
NR_VOTAVEL_CAIADO = 44
NR_VOTAVEL_RENAN_ZEMA = 30
NR_VOTAVEL_OUTROS_ESQUERDA = 50
NR_VOTAVEL_BRANCO = 95
NR_VOTAVEL_NULO = 96
ANO_ELEICAO_PADRAO = 2026


@dataclass(slots=True, frozen=True)
class GoldenFixture:
    """Representa um cenário de teste sintético determinístico com resultado esperado.

    Atributos:
        fixture_id: Identificador canônico da fixture (ex.: 'FX-01').
        description: Descrição da regra ou caso de borda testado.
        expected_classification: Classificação categórica esperada para a urna pareada.
        expected_status_pareamento: Status de pareamento esperado (PAREADA_AMBOS, etc.).
        expected_delta_votos_lula: Delta nominal esperado de Lula (2T - 1T).
        expected_delta_margem: Variação da margem líquida esperada (2T - 1T).
        rows_1t: Linhas simuladas de BU do primeiro turno.
        rows_2t: Linhas simuladas de BU do segundo turno.
    """

    fixture_id: str
    description: str
    expected_classification: TurnoverClassification | None
    expected_status_pareamento: PairingStatus
    expected_delta_votos_lula: int
    expected_delta_margem: int
    rows_1t: list[dict[str, Any]]
    rows_2t: list[dict[str, Any]]


def _create_bu_rows(
    sg_uf: str,
    cd_municipio: int,
    nm_municipio: str,
    nr_zona: int,
    nr_secao: int,
    votos_map: dict[int, int],
    aptos: int,
    comparecimento: int,
    abstencao: int,
) -> list[dict[str, Any]]:
    """Gera linhas no formato de Boletim de Urna do TSE para uma seção eleitoral.

    Args:
        sg_uf: Sigla da UF.
        cd_municipio: Código TSE do município.
        nm_municipio: Nome do município.
        nr_zona: Número da zona.
        nr_secao: Número da seção.
        votos_map: Mapeamento {nr_votavel: quantidade_de_votos}.
        aptos: Total de aptos da seção.
        comparecimento: Total de comparecimento.
        abstencao: Total de abstenções.

    Returns:
        list[dict[str, Any]]: Lista de registros com as colunas oficiais do BWeb TSE.
    """
    rows: list[dict[str, Any]] = []
    for votavel, votos in votos_map.items():
        rows.append(
            {
                "SG_UF": sg_uf,
                "CD_MUNICIPIO": cd_municipio,
                "NM_MUNICIPIO": nm_municipio,
                "NR_ZONA": nr_zona,
                "NR_SECAO": nr_secao,
                "CD_CARGO": 1,  # 1 = Presidente
                "NR_VOTAVEL": votavel,
                "QT_VOTOS": votos,
                "QT_APTOS": aptos,
                "QT_COMPARECIMENTO": comparecimento,
                "QT_ABSTENCAO": abstencao,
            }
        )
    return rows


def get_all_golden_fixtures() -> dict[str, GoldenFixture]:
    """Retorna o catálogo completo das 10 fixtures áureas determinísticas.

    Returns:
        dict[str, GoldenFixture]: Dicionário mapeando {fixture_id: GoldenFixture}.
    """
    fixtures: dict[str, GoldenFixture] = {}

    # FX-01: Manutenção de liderança Lula em ambos os turnos
    f01_1t = _create_bu_rows(
        "SP",
        71072,
        "SAO PAULO",
        1,
        101,
        {
            NR_VOTAVEL_LULA: 120,
            NR_VOTAVEL_FLAVIO: 80,
            NR_VOTAVEL_CURY: 15,
            NR_VOTAVEL_CAIADO: 10,
            NR_VOTAVEL_RENAN_ZEMA: 5,
            NR_VOTAVEL_BRANCO: 10,
            NR_VOTAVEL_NULO: 10,
        },
        aptos=300,
        comparecimento=250,
        abstencao=50,
    )
    f01_2t = _create_bu_rows(
        "SP",
        71072,
        "SAO PAULO",
        1,
        101,
        {
            NR_VOTAVEL_LULA: 140,
            NR_VOTAVEL_FLAVIO: 90,
            NR_VOTAVEL_BRANCO: 12,
            NR_VOTAVEL_NULO: 8,
        },
        aptos=300,
        comparecimento=250,
        abstencao=50,
    )
    fixtures["FX-01"] = GoldenFixture(
        fixture_id="FX-01",
        description="Manutenção de liderança Lula em ambos os turnos",
        expected_classification=TurnoverClassification.MANTEVE_LIDERANCA,
        expected_status_pareamento=PairingStatus.PAREADA_AMBOS,
        expected_delta_votos_lula=20,
        expected_delta_margem=10,  # (140 - 90) - (120 - 80) = 50 - 40 = 10
        rows_1t=f01_1t,
        rows_2t=f01_2t,
    )

    # FX-02: Virada clássica de Lula (perdeu no 1T e venceu no 2T)
    f02_1t = _create_bu_rows(
        "MG",
        41238,
        "BELO HORIZONTE",
        1,
        102,
        {
            NR_VOTAVEL_LULA: 90,
            NR_VOTAVEL_FLAVIO: 130,
            NR_VOTAVEL_CURY: 20,
            NR_VOTAVEL_CAIADO: 15,
            NR_VOTAVEL_RENAN_ZEMA: 5,
            NR_VOTAVEL_BRANCO: 10,
            NR_VOTAVEL_NULO: 10,
        },
        aptos=330,
        comparecimento=280,
        abstencao=50,
    )
    f02_2t = _create_bu_rows(
        "MG",
        41238,
        "BELO HORIZONTE",
        1,
        102,
        {
            NR_VOTAVEL_LULA: 145,
            NR_VOTAVEL_FLAVIO: 115,
            NR_VOTAVEL_BRANCO: 12,
            NR_VOTAVEL_NULO: 8,
        },
        aptos=330,
        comparecimento=280,
        abstencao=50,
    )
    fixtures["FX-02"] = GoldenFixture(
        fixture_id="FX-02",
        description="Virada clássica de Lula (perdeu no 1T e venceu no 2T)",
        expected_classification=TurnoverClassification.VIRADA_LULA,
        expected_status_pareamento=PairingStatus.PAREADA_AMBOS,
        expected_delta_votos_lula=55,
        expected_delta_margem=70,  # (145 - 115) - (90 - 130) = 30 - (-40) = 70
        rows_1t=f02_1t,
        rows_2t=f02_2t,
    )

    # FX-03: Virada do Adversário (Lula venceu no 1T e perdeu no 2T)
    f03_1t = _create_bu_rows(
        "PR",
        75353,
        "CURITIBA",
        1,
        103,
        {
            NR_VOTAVEL_LULA: 110,
            NR_VOTAVEL_FLAVIO: 100,
            NR_VOTAVEL_CURY: 10,
            NR_VOTAVEL_CAIADO: 6,
            NR_VOTAVEL_OUTROS_ESQUERDA: 4,
            NR_VOTAVEL_BRANCO: 5,
            NR_VOTAVEL_NULO: 5,
        },
        aptos=280,
        comparecimento=240,
        abstencao=40,
    )
    f03_2t = _create_bu_rows(
        "PR",
        75353,
        "CURITIBA",
        1,
        103,
        {
            NR_VOTAVEL_LULA: 112,
            NR_VOTAVEL_FLAVIO: 118,
            NR_VOTAVEL_BRANCO: 6,
            NR_VOTAVEL_NULO: 4,
        },
        aptos=280,
        comparecimento=240,
        abstencao=40,
    )
    fixtures["FX-03"] = GoldenFixture(
        fixture_id="FX-03",
        description="Virada do adversário (Lula venceu no 1T e perdeu no 2T)",
        expected_classification=TurnoverClassification.VIRADA_ADVERSARIO,
        expected_status_pareamento=PairingStatus.PAREADA_AMBOS,
        expected_delta_votos_lula=2,
        expected_delta_margem=-16,  # (112 - 118) - (110 - 100) = -6 - 10 = -16
        rows_1t=f03_1t,
        rows_2t=f03_2t,
    )

    # FX-04: Manutenção de desvantagem Lula (adversário venceu em ambos os turnos)
    f04_1t = _create_bu_rows(
        "SC",
        81051,
        "FLORIANOPOLIS",
        1,
        104,
        {
            NR_VOTAVEL_LULA: 70,
            NR_VOTAVEL_FLAVIO: 140,
            NR_VOTAVEL_CURY: 10,
            NR_VOTAVEL_CAIADO: 5,
            NR_VOTAVEL_RENAN_ZEMA: 5,
            NR_VOTAVEL_BRANCO: 5,
            NR_VOTAVEL_NULO: 5,
        },
        aptos=280,
        comparecimento=240,
        abstencao=40,
    )
    f04_2t = _create_bu_rows(
        "SC",
        81051,
        "FLORIANOPOLIS",
        1,
        104,
        {
            NR_VOTAVEL_LULA: 80,
            NR_VOTAVEL_FLAVIO: 150,
            NR_VOTAVEL_BRANCO: 6,
            NR_VOTAVEL_NULO: 4,
        },
        aptos=280,
        comparecimento=240,
        abstencao=40,
    )
    fixtures["FX-04"] = GoldenFixture(
        fixture_id="FX-04",
        description="Manutenção de desvantagem Lula (adversário liderou em ambos)",
        expected_classification=TurnoverClassification.MANTEVE_DESVANTAGEM,
        expected_status_pareamento=PairingStatus.PAREADA_AMBOS,
        expected_delta_votos_lula=10,
        expected_delta_margem=0,  # (80 - 150) - (70 - 140) = -70 - (-70) = 0
        rows_1t=f04_1t,
        rows_2t=f04_2t,
    )

    # FX-05: Seção Agregada no 2T (presente apenas no 1T)
    f05_1t = _create_bu_rows(
        "BA",
        38490,
        "SALVADOR",
        1,
        105,
        {
            NR_VOTAVEL_LULA: 50,
            NR_VOTAVEL_FLAVIO: 40,
            NR_VOTAVEL_CURY: 5,
            NR_VOTAVEL_CAIADO: 5,
            NR_VOTAVEL_BRANCO: 2,
            NR_VOTAVEL_NULO: 2,
        },
        aptos=120,
        comparecimento=104,
        abstencao=16,
    )
    fixtures["FX-05"] = GoldenFixture(
        fixture_id="FX-05",
        description="Seção agregada pelo TRE no 2T (existiu apenas no 1T)",
        expected_classification=None,
        expected_status_pareamento=PairingStatus.APENAS_1T,
        expected_delta_votos_lula=-50,
        expected_delta_margem=-10,
        rows_1t=f05_1t,
        rows_2t=[],
    )

    # FX-06: Urna Nova / Contingência no 2T (presente apenas no 2T)
    f06_2t = _create_bu_rows(
        "BA",
        38490,
        "SALVADOR",
        1,
        106,
        {
            NR_VOTAVEL_LULA: 60,
            NR_VOTAVEL_FLAVIO: 50,
            NR_VOTAVEL_BRANCO: 3,
            NR_VOTAVEL_NULO: 2,
        },
        aptos=140,
        comparecimento=115,
        abstencao=25,
    )
    fixtures["FX-06"] = GoldenFixture(
        fixture_id="FX-06",
        description="Urna de contingência ativada apenas no 2T",
        expected_classification=None,
        expected_status_pareamento=PairingStatus.APENAS_2T,
        expected_delta_votos_lula=60,
        expected_delta_margem=10,
        rows_1t=[],
        rows_2t=f06_2t,
    )

    # FX-07: Alta absorção de votos de terceiros colocados
    f07_1t = _create_bu_rows(
        "CE",
        13897,
        "FORTALEZA",
        1,
        107,
        {
            NR_VOTAVEL_LULA: 70,
            NR_VOTAVEL_FLAVIO: 80,
            NR_VOTAVEL_CURY: 35,
            NR_VOTAVEL_CAIADO: 25,
            NR_VOTAVEL_BRANCO: 5,
            NR_VOTAVEL_NULO: 5,
        },
        aptos=280,
        comparecimento=220,
        abstencao=60,
    )
    f07_2t = _create_bu_rows(
        "CE",
        13897,
        "FORTALEZA",
        1,
        107,
        {
            NR_VOTAVEL_LULA: 120,
            NR_VOTAVEL_FLAVIO: 90,
            NR_VOTAVEL_BRANCO: 6,
            NR_VOTAVEL_NULO: 4,
        },
        aptos=280,
        comparecimento=220,
        abstencao=60,
    )
    fixtures["FX-07"] = GoldenFixture(
        fixture_id="FX-07",
        description="Alta absorção de votos de terceiros colocados (Cury/Caiado 2026)",
        expected_classification=TurnoverClassification.VIRADA_LULA,
        expected_status_pareamento=PairingStatus.PAREADA_AMBOS,
        expected_delta_votos_lula=50,
        expected_delta_margem=40,  # (120 - 90) - (70 - 80) = 30 - (-10) = 40
        rows_1t=f07_1t,
        rows_2t=f07_2t,
    )

    # FX-08: Empate no 1º Turno com desempate no 2º Turno
    f08_1t = _create_bu_rows(
        "RJ",
        60011,
        "RIO DE JANEIRO",
        1,
        108,
        {
            NR_VOTAVEL_LULA: 100,
            NR_VOTAVEL_FLAVIO: 100,
            NR_VOTAVEL_CURY: 10,
            NR_VOTAVEL_RENAN_ZEMA: 10,
            NR_VOTAVEL_BRANCO: 5,
            NR_VOTAVEL_NULO: 5,
        },
        aptos=270,
        comparecimento=230,
        abstencao=40,
    )
    f08_2t = _create_bu_rows(
        "RJ",
        60011,
        "RIO DE JANEIRO",
        1,
        108,
        {
            NR_VOTAVEL_LULA: 115,
            NR_VOTAVEL_FLAVIO: 105,
            NR_VOTAVEL_BRANCO: 6,
            NR_VOTAVEL_NULO: 4,
        },
        aptos=270,
        comparecimento=230,
        abstencao=40,
    )
    fixtures["FX-08"] = GoldenFixture(
        fixture_id="FX-08",
        description="Empate exato no 1º turno com vitória de Lula no 2º turno",
        expected_classification=TurnoverClassification.EMPATE,
        expected_status_pareamento=PairingStatus.PAREADA_AMBOS,
        expected_delta_votos_lula=15,
        expected_delta_margem=10,  # (115 - 105) - (100 - 100) = 10 - 0 = 10
        rows_1t=f08_1t,
        rows_2t=f08_2t,
    )

    # FX-09: Seção com votos zerados em candidato (divisão por zero segura)
    f09_1t = _create_bu_rows(
        "AM",
        2550,
        "MANAUS",
        1,
        109,
        {
            NR_VOTAVEL_LULA: 0,
            NR_VOTAVEL_FLAVIO: 0,
            NR_VOTAVEL_BRANCO: 5,
            NR_VOTAVEL_NULO: 5,
        },
        aptos=20,
        comparecimento=10,
        abstencao=10,
    )
    f09_2t = _create_bu_rows(
        "AM",
        2550,
        "MANAUS",
        1,
        109,
        {
            NR_VOTAVEL_LULA: 2,
            NR_VOTAVEL_FLAVIO: 0,
            NR_VOTAVEL_BRANCO: 4,
            NR_VOTAVEL_NULO: 4,
        },
        aptos=20,
        comparecimento=10,
        abstencao=10,
    )
    fixtures["FX-09"] = GoldenFixture(
        fixture_id="FX-09",
        description="Seção especial prisional com candidatos zerados (divisão por zero)",
        expected_classification=TurnoverClassification.EMPATE,
        expected_status_pareamento=PairingStatus.PAREADA_AMBOS,
        expected_delta_votos_lula=2,
        expected_delta_margem=2,
        rows_1t=f09_1t,
        rows_2t=f09_2t,
    )

    # FX-10: Seção de Município Pêndulo (Swing City)
    f10_1t = _create_bu_rows(
        "MG",
        54321,
        "CIDADE PENDULO",
        1,
        110,
        {
            NR_VOTAVEL_LULA: 150,
            NR_VOTAVEL_FLAVIO: 170,
            NR_VOTAVEL_CURY: 15,
            NR_VOTAVEL_CAIADO: 10,
            NR_VOTAVEL_RENAN_ZEMA: 5,
            NR_VOTAVEL_BRANCO: 10,
            NR_VOTAVEL_NULO: 10,
        },
        aptos=420,
        comparecimento=370,
        abstencao=50,
    )
    f10_2t = _create_bu_rows(
        "MG",
        54321,
        "CIDADE PENDULO",
        1,
        110,
        {
            NR_VOTAVEL_LULA: 200,
            NR_VOTAVEL_FLAVIO: 160,
            NR_VOTAVEL_BRANCO: 5,
            NR_VOTAVEL_NULO: 5,
        },
        aptos=420,
        comparecimento=370,
        abstencao=50,
    )
    fixtures["FX-10"] = GoldenFixture(
        fixture_id="FX-10",
        description="Seção determinante em município pêndulo (swing city)",
        expected_classification=TurnoverClassification.VIRADA_LULA,
        expected_status_pareamento=PairingStatus.PAREADA_AMBOS,
        expected_delta_votos_lula=50,
        expected_delta_margem=60,  # (200 - 160) - (150 - 170) = 40 - (-20) = 60
        rows_1t=f10_1t,
        rows_2t=f10_2t,
    )

    return fixtures


def get_nanuque_fixture() -> GoldenFixture:
    """Retorna o cenário áureo de aceitação canônico para o município de Nanuque/MG (2026).

    No 1T Flávio liderou com 48,54% vs 46,87% de Lula.
    No 2T Lula venceu com 51,33% vs 48,67% de Flávio, com avanço de +4,46 pp.

    Returns:
        GoldenFixture: Fixture de Nanuque/MG com métricas exatas do BDD.
    """
    nanuque_1t = _create_bu_rows(
        "MG",
        48852,
        "NANUQUE",
        1,
        201,
        {
            NR_VOTAVEL_LULA: 10359,
            NR_VOTAVEL_FLAVIO: 10729,
            NR_VOTAVEL_CURY: 550,
            NR_VOTAVEL_CAIADO: 300,
            NR_VOTAVEL_RENAN_ZEMA: 162,
            NR_VOTAVEL_BRANCO: 500,
            NR_VOTAVEL_NULO: 400,
        },
        aptos=31200,
        comparecimento=23000,
        abstencao=8200,
    )
    nanuque_2t = _create_bu_rows(
        "MG",
        48852,
        "NANUQUE",
        1,
        201,
        {
            NR_VOTAVEL_LULA: 11703,
            NR_VOTAVEL_FLAVIO: 11097,
            NR_VOTAVEL_BRANCO: 400,
            NR_VOTAVEL_NULO: 350,
        },
        aptos=31200,
        comparecimento=23550,
        abstencao=7650,
    )
    return GoldenFixture(
        fixture_id="FX-NANUQUE",
        description="Virada canônica em Nanuque/MG (1T: 46,87% vs 48,54%; 2T: 51,33% vs 48,67%)",
        expected_classification=TurnoverClassification.VIRADA_LULA,
        expected_status_pareamento=PairingStatus.PAREADA_AMBOS,
        expected_delta_votos_lula=1344,
        expected_delta_margem=976,
        rows_1t=nanuque_1t,
        rows_2t=nanuque_2t,
    )


def get_golden_fixture(fixture_id: str) -> GoldenFixture:
    """Recupera uma fixture áurea específica pelo identificador.

    Args:
        fixture_id: Identificador canônico da fixture ('FX-01' a 'FX-10').

    Returns:
        GoldenFixture: Instância da fixture encontrada.

    Raises:
        KeyError: Se o identificador da fixture não existir.
    """
    fixtures = get_all_golden_fixtures()
    if fixture_id not in fixtures:
        raise KeyError(
            f"Fixture '{fixture_id}' não encontrada. "
            f"Identificadores disponíveis: {list(fixtures.keys())}"
        )
    return fixtures[fixture_id]


def generate_bu_csv(rows: list[dict[str, Any]], out_path: Path) -> Path:
    """Grava uma lista de registros em arquivo CSV com delimitador ';' no padrão TSE.

    Args:
        rows: Lista de dicionários representando as linhas do BU.
        out_path: Caminho do arquivo CSV de saída.

    Returns:
        Path: Caminho do arquivo gerado.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="iso-8859-1") as f:
        # Gravar cabeçalho separado por ';'
        f.write(";".join(TSE_BU_CSV_HEADER) + "\n")
        for row in rows:
            line = ";".join(str(row.get(col, "")) for col in TSE_BU_CSV_HEADER)
            f.write(line + "\n")
    return out_path


def build_synthetic_bu_dataset(out_dir: Path, include_nanuque: bool = False) -> tuple[Path, Path]:
    """Materializa o conjunto sintético consolidado de 1T e 2T das 10 fixtures áureas.

    Args:
        out_dir: Diretório onde os arquivos CSV serão criados.
        include_nanuque: Se True, inclui também a seção áurea de Nanuque/MG (FX-NANUQUE).

    Returns:
        tuple[Path, Path]: Par de caminhos para os arquivos (bweb_1t_TEST.csv, bweb_2t_TEST.csv).
    """
    fixtures = get_all_golden_fixtures()
    all_1t_rows: list[dict[str, Any]] = []
    all_2t_rows: list[dict[str, Any]] = []

    for fix in fixtures.values():
        all_1t_rows.extend(fix.rows_1t)
        all_2t_rows.extend(fix.rows_2t)

    if include_nanuque:
        nanuque = get_nanuque_fixture()
        all_1t_rows.extend(nanuque.rows_1t)
        all_2t_rows.extend(nanuque.rows_2t)

    path_1t = out_dir / "bweb_1t_TEST.csv"
    path_2t = out_dir / "bweb_2t_TEST.csv"

    generate_bu_csv(all_1t_rows, path_1t)
    generate_bu_csv(all_2t_rows, path_2t)

    return path_1t, path_2t

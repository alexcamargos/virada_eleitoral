"""Testes unitários dos contratos de dados e hierarquia de exceções.

Valida a imutabilidade das dataclasses de handoff, modelos Pydantic v2
e serialização de payloads de exportação (REQ-QA-01).
"""

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from pydantic import ValidationError

from virada_eleitoral.contracts.exceptions import (
    CorruptBuArchiveError,
    HashMismatchError,
    InvariantViolationError,
    ViradaEleitoralError,
)
from virada_eleitoral.contracts.models import (
    AxisRangeItem,
    BubbleCityItem,
    CandidatePerformanceDetail,
    CandidateStateComparisonItem,
    CapitalHighlightItem,
    ContinuousScaleConfig,
    DivergingScaleConfig,
    EcologicalRegressionScatterPayload,
    FlavioPerformanceBubbleMapPayload,
    HarvestManifest,
    LulaAdvanceBubbleMapPayload,
    NationalSummaryPayload,
    PairedSection,
    PairingStatus,
    RawBuFileBundle,
    RegressionMetaItem,
    SankeyLinkItem,
    SankeyNodeItem,
    SankeyVoteFlowsPayload,
    ScatterPointItem,
    SectionTurnoverRecord,
    SectionVotes1T,
    SectionVotes2T,
    SoutheastDeepDivePayload,
    StateSummaryItem,
    SubcandidateItem,
    SwingCityPayload,
    TransitionDistributionPayload,
    TransitionGroupItem,
    TurnoverClassification,
    WaterfallStepItem,
    WaterfallTurnoverPayload,
)


def test_raw_bu_file_bundle_immutability() -> None:
    """Garante que RawBuFileBundle é imutável e preserva os atributos fornecidos."""
    bundle = RawBuFileBundle(
        ano_eleicao=2022,
        turno=1,
        uf="SP",
        file_path=Path("data/raw/bweb_1t_SP.csv"),
        sha512_hash="abcdef123456",
        file_size_bytes=1024,
        is_compressed=False,
    )

    assert bundle.ano_eleicao == 2022
    assert bundle.turno == 1
    assert bundle.uf == "SP"
    assert bundle.is_compressed is False

    with pytest.raises((FrozenInstanceError, AttributeError)):
        # Tentativa de mutação direta deve falhar (frozen=True)
        bundle.uf = "RJ"  # type: ignore[misc]


def test_section_votes_contracts() -> None:
    """Verifica a criação das estruturas isoladas de votos por turno (1T e 2T)."""
    v1 = SectionVotes1T(
        aptos=400,
        comparecimento=320,
        abstencao=80,
        votos_validos=300,
        votos_lula=150,
        votos_adv=120,
        votos_outros=30,
        votos_brancos=10,
        votos_nulos=10,
    )
    assert v1.votos_validos == 300
    assert v1.votos_lula == 150

    v2 = SectionVotes2T(
        aptos=400,
        comparecimento=330,
        abstencao=70,
        votos_validos=315,
        votos_lula=175,
        votos_adv=140,
        votos_brancos=8,
        votos_nulos=7,
    )
    assert v2.votos_validos == 315
    assert v2.votos_lula == 175


def test_harvest_manifest_contract() -> None:
    """Verifica a criação de manifestos de coleta de Boletins de Urna."""
    manifest = HarvestManifest(
        ano_eleicao=2022,
        turno=1,
        uf="MG",
        source_file="bweb_1t_MG_05102022.zip",
        sha512="1234567890abcdef",
        file_size_bytes=52428800,
        downloaded_at="2026-10-26T12:00:00Z",
    )
    assert manifest.status == "VERIFIED"
    assert manifest.uf == "MG"


def test_section_turnover_record_creation() -> None:
    """Verifica a criação correta de um registro analítico de seção pareada."""
    record = SectionTurnoverRecord(
        ano_eleicao=2022,
        sg_uf="MG",
        cd_municipio=41238,
        cd_municipio_ibge=3106200,
        nm_municipio="BELO HORIZONTE",
        nr_zona=1,
        nr_secao=10,
        status_pareamento=PairingStatus.PAREADA_AMBOS,
        votos_validos_1t=250,
        votos_lula_1t=110,
        votos_adv_1t=120,
        votos_outros_1t=20,
        pct_lula_1t=44.0,
        pct_adv_1t=48.0,
        votos_validos_2t=260,
        votos_lula_2t=140,
        votos_adv_2t=120,
        pct_lula_2t=53.8462,
        pct_adv_2t=46.1538,
        delta_votos_lula=30,
        delta_votos_adv=0,
        delta_pp_lula=9.8462,
        delta_pp_adv=-1.8462,
        margem_1t=-10,
        margem_2t=20,
        delta_margem=30,
        classificacao_virada=TurnoverClassification.VIRADA_LULA,
        eficiencia_absorcao_outros=1.5,
    )

    assert record.classificacao_virada == TurnoverClassification.VIRADA_LULA
    assert record.delta_margem == 30
    assert record.status_pareamento == PairingStatus.PAREADA_AMBOS


def test_state_summary_item_validation() -> None:
    """Valida a criação e restrições de validação para StateSummaryItem."""
    state_item = StateSummaryItem(
        sg_uf="BA",
        total_secoes=34000,
        total_validos_1t=8000000,
        total_validos_2t=8500000,
        votos_lula_1t=5800000,
        votos_lula_2t=6200000,
        votos_adv_1t=1800000,
        votos_adv_2t=2300000,
        delta_votos_lula=400000,
        pct_lula_1t=72.50,
        pct_lula_2t=72.94,
        delta_pp_lula=0.44,
        delta_margem=-100000,
        total_urnas_virada_lula=120,
        total_urnas_virada_adv=35,
    )
    assert state_item.sg_uf == "BA"
    assert state_item.pct_lula_1t == 72.50


def test_national_summary_payload_validation() -> None:
    """Valida as restrições de validação do Pydantic para NationalSummaryPayload."""
    valid_payload = NationalSummaryPayload(
        ano_eleicao=2022,
        total_secoes_analisadas=472075,
        total_secoes_pareadas=471920,
        total_validos_1t=118580000,
        total_validos_2t=124250000,
        total_lula_1t=57259504,
        total_lula_2t=60345999,
        total_adv_1t=51072345,
        total_adv_2t=58206354,
        total_outros_1t=10248151,
        delta_nacional_lula=3086495,
        pct_lula_1t_brasil=48.43,
        pct_lula_2t_brasil=50.90,
        delta_pp_lula_brasil=2.47,
        total_urnas_virada_lula=23410,
        total_urnas_virada_adv=8120,
    )
    assert valid_payload.pct_lula_2t_brasil == 50.90

    # Testar que percentual acima de 100 dispara erro de validação
    with pytest.raises(ValidationError):
        NationalSummaryPayload(
            ano_eleicao=2022,
            total_secoes_analisadas=100,
            total_secoes_pareadas=100,
            total_validos_1t=1000,
            total_validos_2t=1000,
            total_lula_1t=500,
            total_lula_2t=600,
            total_adv_1t=400,
            total_adv_2t=400,
            total_outros_1t=100,
            delta_nacional_lula=100,
            pct_lula_1t_brasil=50.0,
            pct_lula_2t_brasil=105.0,  # Inválido (> 100)
            delta_pp_lula_brasil=5.0,
            total_urnas_virada_lula=10,
            total_urnas_virada_adv=5,
        )


def test_swing_city_payload_validation() -> None:
    """Verifica a validação de contrato para SwingCityPayload."""
    payload = SwingCityPayload(
        sg_uf="MG",
        cd_municipio=41238,
        cd_municipio_ibge=3106200,
        nm_municipio="BELO HORIZONTE",
        total_secoes=4320,
        votos_lula_1t=558000,
        votos_lula_2t=612000,
        votos_adv_1t=620000,
        votos_adv_2t=605000,
        delta_votos_lula=54000,
        pct_lula_1t=46.50,
        pct_lula_2t=50.28,
        delta_pp_lula=3.78,
        delta_margem=69000,
        status_virada_municipio=TurnoverClassification.VIRADA_LULA,
    )
    assert payload.status_virada_municipio == TurnoverClassification.VIRADA_LULA


def test_exceptions_hierarchy() -> None:
    """Valida as propriedades e mensagens formatadas da hierarquia de exceções."""
    err1 = CorruptBuArchiveError("bweb_1t_SP.zip", "CRC check failed")
    assert isinstance(err1, ViradaEleitoralError)
    assert "CRC check failed" in str(err1)

    err2 = HashMismatchError("bweb_1t_RJ.csv", "hash_esperado", "hash_obtido")
    assert isinstance(err2, ViradaEleitoralError)
    assert err2.expected_hash == "hash_esperado"
    assert err2.actual_hash == "hash_obtido"

    err3 = InvariantViolationError("VotosValidos", "votos_lula + votos_adv != total_validos")
    assert isinstance(err3, ViradaEleitoralError)
    assert "VotosValidos" in str(err3)


def test_waterfall_turnover_payload_validation() -> None:
    """Valida a instanciação e integridade do payload do Pilar 1 (Cascata da Virada)."""
    payload = WaterfallTurnoverPayload(
        ano_eleicao=2026,
        metodologia="Estimativa por inferência ecológica",
        unidade="milhoes_de_votos",
        diferenca_1t=-2.22,
        rotulo_1t="Flávio à frente (-2,22 mi)",
        degraus=[
            WaterfallStepItem(
                grupo="Ex-brancos e nulos",
                saldo_liquido=3.23,
                favorece="Lula",
                votos_para_lula=3.61,
                votos_para_flavio=0.38,
            ),
            WaterfallStepItem(
                grupo="Ausentes que voltaram a votar",
                saldo_liquido=1.83,
                favorece="Lula",
                votos_para_lula=3.04,
                votos_para_flavio=1.21,
            ),
        ],
        diferenca_2t=4.43,
        rotulo_2t="Lula à frente (+4,43 mi)",
    )
    assert payload.diferenca_1t == -2.22
    assert payload.diferenca_2t == 4.43
    assert len(payload.degraus) == 2
    assert payload.degraus[0].saldo_liquido == 3.23


def test_sankey_vote_flows_payload_validation() -> None:
    """Valida a instanciação e regras de integridade do payload do Pilar 2 (Sankey)."""
    payload = SankeyVoteFlowsPayload(
        ano_eleicao=2026,
        metrica="milhoes_de_eleitores",
        total_novos_votos_lula=11.0,
        total_novos_votos_flavio=4.4,
        nodes=[
            SankeyNodeItem(id="branco_nulo_1t", label="Branco ou nulo (1T)", total=5.98),
            SankeyNodeItem(id="lula_2t", label="Lula (2T)", total=11.00),
        ],
        links=[
            SankeyLinkItem(source="branco_nulo_1t", target="lula_2t", value=3.61),
        ],
    )
    assert payload.total_novos_votos_lula == 11.0
    assert len(payload.nodes) == 2
    assert len(payload.links) == 1

    with pytest.raises(ValidationError):
        SankeyLinkItem(source="branco_nulo_1t", target="lula_2t", value=-1.0)


def test_transition_distribution_payload_validation() -> None:
    """Valida a modelagem do Pilar 3 (Barras 100% de Destino por Grupo)."""
    payload = TransitionDistributionPayload(
        ano_eleicao=2026,
        grupos=[
            TransitionGroupItem(
                id="outros_total",
                nome="Eleitores de outros candidatos",
                total_eleitores=9320000,
                distribuicao_percentual={
                    "lula": 45.0,
                    "flavio": 41.0,
                    "branco_nulo": 12.0,
                    "nao_votou": 2.0,
                },
                distribuicao_nominal={
                    "lula": 4160000,
                    "flavio": 3840000,
                    "branco_nulo": 1140000,
                    "nao_votou": 184000,
                },
                subcandidatos=[
                    SubcandidateItem(
                        nome="Cury",
                        total=3400000,
                        distribuicao_pct={"lula": 55.0, "flavio": 27.0},
                    ),
                    SubcandidateItem(
                        nome="Caiado",
                        total=2900000,
                        distribuicao_pct={"lula": 34.0, "flavio": 52.0},
                    ),
                ],
            )
        ],
    )
    assert len(payload.grupos) == 1
    assert payload.grupos[0].subcandidatos is not None
    assert len(payload.grupos[0].subcandidatos) == 2


def test_ecological_regression_scatter_payload_validation() -> None:
    """Valida a modelagem do Pilar 4 (Scatter Plot e Reta WLS)."""
    payload = EcologicalRegressionScatterPayload(
        ano_eleicao=2026,
        titulo="Lula conquista brancos e nulos",
        eixo_x=AxisRangeItem(nome="Brancos e nulos 1T", min=0.0, max=10.0),
        eixo_y=AxisRangeItem(nome="Crescimento de Lula (pp)", min=-2.0, max=16.0),
        regressao=RegressionMetaItem(
            coeficiente_angular_beta=0.80,
            intercepto_alpha=3.65,
            r_quadrado=0.44,
            chamada_destaque="+0,8 pp para Lula a cada 1 pp de branco e nulo",
            total_secoes_modelo=472075,
            secoes_amostra_visualizacao=900,
        ),
        pontos_amostra=[
            ScatterPointItem(
                sg_uf="SP",
                nr_secao=101,
                x_pct_branco_nulo=4.2,
                y_delta_pp_lula=7.1,
                aptos=395,
            ),
            ScatterPointItem(
                sg_uf="MG",
                nr_secao=45,
                x_pct_branco_nulo=5.8,
                y_delta_pp_lula=8.4,
                aptos=340,
            ),
        ],
    )
    assert payload.regressao.r_quadrado == 0.44
    assert len(payload.pontos_amostra) == 2

    # R-quadrado inválido (> 1.0)
    with pytest.raises(ValidationError):
        RegressionMetaItem(
            coeficiente_angular_beta=0.80,
            intercepto_alpha=3.65,
            r_quadrado=1.44,
            chamada_destaque="Invalido",
            total_secoes_modelo=100,
            secoes_amostra_visualizacao=10,
        )

    # Aptos inválido (<= 0)
    with pytest.raises(ValidationError):
        ScatterPointItem(
            sg_uf="SP",
            nr_secao=101,
            x_pct_branco_nulo=4.2,
            y_delta_pp_lula=7.1,
            aptos=0,
        )


def test_southeast_deep_dive_payload_validation() -> None:
    """Valida a modelagem do Geo-Pilar 3 (Painel Comparativo Sudeste SP, RJ, MG)."""
    payload = SoutheastDeepDivePayload(
        ano_eleicao=2026,
        titulo="Painel Sudeste",
        estados=[
            CandidateStateComparisonItem(
                sg_uf="SP",
                nome_estado="São Paulo",
                lula=CandidatePerformanceDetail(
                    votos_1t=9505413,
                    votos_2t=12119116,
                    delta_nominal=2613703,
                    pct_1t=40.89,
                    pct_2t=46.14,
                    delta_pp=5.25,
                ),
                flavio=CandidatePerformanceDetail(
                    votos_1t=12922023,
                    votos_2t=14139069,
                    delta_nominal=1217046,
                    pct_1t=55.57,
                    pct_2t=53.86,
                    delta_pp=-1.71,
                ),
                razao_crescimento=2.15,
            )
        ],
    )
    assert payload.estados[0].sg_uf == "SP"
    assert payload.estados[0].razao_crescimento == 2.15


def test_bubble_map_payloads_validation() -> None:
    """Valida a modelagem do Geo-Pilar 4 (Díptico de Bolhas Proporcionais Ponderadas)."""
    lula_map = LulaAdvanceBubbleMapPayload(
        ano_eleicao=2026,
        titulo="Onde Lula avançou",
        metrica_escala="Crescimento em pp dos votos válidos",
        escala_cores=ContinuousScaleConfig(min_pp=0.0, max_pp=10.0),
        destaques_capitais=[
            CapitalHighlightItem(
                cidade="São Paulo",
                sg_uf="SP",
                delta_pp=8.9,
                lat=-23.5505,
                lon=-46.6333,
                aptos=9314000,
            )
        ],
        municipios=[
            BubbleCityItem(
                cd_ibge=3550308,
                nm="São Paulo",
                uf="SP",
                aptos=9314000,
                delta_pp=8.9,
                lat=-23.5505,
                lon=-46.6333,
            )
        ],
    )
    assert lula_map.destaques_capitais[0].delta_pp == 8.9

    flavio_map = FlavioPerformanceBubbleMapPayload(
        ano_eleicao=2026,
        titulo="Desempenho de Flávio",
        metrica_escala="Variação em pp dos votos válidos",
        escala_cores=DivergingScaleConfig(min_pp=-3.0, max_pp=6.0),
        destaques_capitais=[
            CapitalHighlightItem(
                cidade="Salvador",
                sg_uf="BA",
                delta_pp=-0.3,
                lat=-12.9777,
                lon=-38.5016,
                aptos=1980000,
                status="RECUO",
            )
        ],
        municipios=[
            BubbleCityItem(
                cd_ibge=2927408,
                nm="Salvador",
                uf="BA",
                aptos=1980000,
                delta_pp=-0.3,
                lat=-12.9777,
                lon=-38.5016,
            )
        ],
    )
    assert flavio_map.destaques_capitais[0].delta_pp == -0.3
    assert flavio_map.destaques_capitais[0].status == "RECUO"


def test_section_subcandidates_and_paired_section_alias() -> None:
    """Valida os campos de subcandidatos em SectionVotes1T e PairedSection."""
    v1 = SectionVotes1T(
        aptos=400,
        comparecimento=320,
        abstencao=80,
        votos_validos=300,
        votos_lula=150,
        votos_adv=100,
        votos_outros=50,
        votos_brancos=10,
        votos_nulos=10,
        votos_cury=25,
        votos_caiado=15,
        votos_renan_zema=8,
        votos_outros_esquerda=2,
    )
    assert v1.votos_cury == 25
    assert v1.votos_caiado == 15
    assert v1.votos_renan_zema == 8
    assert v1.votos_outros_esquerda == 2

    assert PairedSection is SectionTurnoverRecord

    paired = PairedSection(
        ano_eleicao=2026,
        sg_uf="MG",
        cd_municipio=41238,
        cd_municipio_ibge=3106200,
        nm_municipio="BELO HORIZONTE",
        nr_zona=1,
        nr_secao=10,
        status_pareamento=PairingStatus.PAREADA_AMBOS,
        votos_validos_1t=250,
        votos_lula_1t=110,
        votos_adv_1t=120,
        votos_outros_1t=20,
        pct_lula_1t=44.0,
        pct_adv_1t=48.0,
        votos_validos_2t=260,
        votos_lula_2t=140,
        votos_adv_2t=120,
        pct_lula_2t=53.8462,
        pct_adv_2t=46.1538,
        delta_votos_lula=30,
        delta_votos_adv=0,
        delta_pp_lula=9.8462,
        delta_pp_adv=-1.8462,
        margem_1t=-10,
        margem_2t=20,
        delta_margem=30,
        classificacao_virada=TurnoverClassification.VIRADA_LULA,
        votos_cury_1t=10,
        votos_caiado_1t=6,
        votos_renan_zema_1t=3,
        votos_outros_esquerda_1t=1,
    )
    assert paired.votos_cury_1t == 10
    assert paired.votos_caiado_1t == 6

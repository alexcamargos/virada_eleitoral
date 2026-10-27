# AGENTS.MD: Governança de Agentes e Desenvolvimento Orientado por Especificações (SDD)

## 1. Visão Geral do Sistema e Missão Analítica
O projeto **`virada_eleitoral`** é uma plataforma de engenharia de dados, modelagem analítica OLAP e exportação de artefatos geoespaciais e tabulares de alta performance para auditoria técnica do desempenho eleitoral nas eleições presidenciais brasileiras.

> [!IMPORTANT]
> **MANDATO EXCLUSIVO E DEFINITIVO DE ESCOPO ELEITORAL:**
> O sistema tem como objeto de análise estrito, mandatório e único o **2º Turno da Eleição Presidencial de 2026**, realizado em **25/10/2026**, disputado entre os candidatos **Luiz Inácio Lula da Silva** (PT, número 13) e **Flávio Bolsonaro** (PL, número 22).
> É **terminantemente vedado** a qualquer agente autônomo de inteligência artificial, subagente ou processo automatizado inferir, alternar, retroceder ou configurar o pipeline para outro pleito (como 2022 ou pleitos municipais). Todo e qualquer desenvolvimento, teste e contrato deve refletir exclusivamente a eleição de 2026.

A missão primordial do sistema é processar e parear de ponta a ponta mais de **40 milhões de linhas de registros de Boletins de Urna (BUs)** disponibilizados pelo Tribunal Superior Eleitoral (TSE) para as **Eleições Presidenciais de 2026**, analisando determinística e exaustivamente as cerca de **470.000 a 500.000 seções eleitorais** do país entre o 1º turno e o 2º turno (25/10/2026) para quantificar e evidenciar:
- **Construção dos Votos Finais de Lula no 2º Turno:** Análise matemática, estatística e contábil discriminando exatamente de onde vieram os votos obtidos por Luiz Inácio Lula da Silva no 2T que ele não possuía no 1T:
  1. Absorção de votos de terceiros candidatos do 1º turno.
  2. Absorção/migração de eleitores que votaram em branco no 1T.
  3. Absorção/migração de eleitores que votaram nulo no 1T.
  4. Absorção de novos comparecentes decorrentes da redução de abstenção ($\Delta \text{Comparecimento}$).
- **Deltas de Votação Nominal e Pontos Percentuais:** Variação absoluta e relativa do candidato Luiz Inácio Lula da Silva (13) e de seu adversário Flávio Bolsonaro (22) em cada urna do país.
- **Classificação Formal de Viradas:** Categorização objetiva das seções e territórios em `VIRADA_LULA`, `VIRADA_ADVERSARIO`, `MANTEVE_LIDERANCA` ou `MANTEVE_DESVANTAGEM`.
- **Visualização e Entrega Mínima Obrigatória (Os 4 Pilares Gráficos):** Estruturação e exportação obrigatória dos dados analíticos para 4 produtos visuais de alto impacto:
  1. *Gráfico em Cascata da Virada (Waterfall de Saldo Líquido):* Decomposição de como a desvantagem de 2,22 mi no 1T virou vitória de 4,43 mi no 2T.
  2. *Diagrama de Fluxo Aluvial / Sankey:* Mapeamento bruto dos fluxos de votos migrados de cada grupo do 1T para os destinos do 2T.
  3. *Matriz de Destino em Barras Horizontais Empilhadas (100% Stacked Bar):* Decomposição percentual e nominal para onde foram os eleitores de terceiros candidatos, brancos/nulos e ausentes.
  4. *Dispersão e Regressão Linear Seção a Seção (Scatter Plot):* Evidência empírica da sensibilidade do crescimento de Lula em função da densidade de brancos e nulos no 1T (+0,8 pp por 1 pp de branco/nulo).
- **Rollup Hierárquico Multinível:** Agregação estrita sem distorção em três níveis territoriais:
  1. **Nível Macro (Nacional e UF):** Contribuição de cada estado e região para a margem líquida final.
  2. **Nível Meso (Município):** Identificação de cidades pêndulo (*swing cities*), reversões de liderança e enriquecimento com código IBGE de 7 dígitos.
  3. **Nível Micro (Seção / Urna Individual):** Detecção de seções de virada atípica (*turnover outliers*) e variações locais em bairros e periferias.

---

## 2. Protocolo de Desenvolvimento Orientado por Especificações (AI-Native SDD)

Todo agente autônomo de inteligência artificial ou engenheiro de software atuando neste repositório **DEVE** seguir estritamente o protocolo **AI-Native Spec-Driven Development**:

### 2.1. Princípios Inegociáveis
1. **Fonte Única da Verdade (*Single Source of Truth*):**
   - Nenhuma linha de código, coluna de tabela, fórmula de agregação ou contrato JSON pode ser implementada sem estar previamente formalizada em [`specs.md`](./specs.md) e nos módulos detalhados em [`specs/`](./specs/).
   - Diante de qualquer ambiguidade, caso omisso ou divergência entre requisitos, o agente **NÃO DEVE inferir silenciosamente**: deve atualizar a especificação cabível (ou solicitar alinhamento humano) antes de alterar o código.
2. **Rastreabilidade Bidirecional (`REQ-*`, `FX-*`, `TASKS-*`):**
   - Toda função, classe, método público e suíte de testes deve citar explicitamente em sua docstring o ID do requisito (`REQ-HARV-*`, `REQ-NORM-*`, `REQ-ANAL-*`, `REQ-EXPO-*`, `REQ-QA-*`) e a fixture áurea (`FX-01` a `FX-10`) que satisfaz.
3. **Congelamento de Contratos (*Contracts Freeze — Fase 0*):**
   - Os modelos de dados de transferência (`src/virada_eleitoral/contracts/models.py`) e exceções canônicas (`src/virada_eleitoral/contracts/exceptions.py`) formam o contrato compartilhado imutável. Nenhum agente de processamento pode alterar contratos compartilhados sem validação prévia de conformidade.
4. **Isolamento de Escopo e Concorrência:**
   - Cada agente atua exclusivamente em seu diretório de especialização, consumindo e produzindo contratos tipados imutáveis.

### 2.2. Ciclo de Vida da Tarefa Atômica
Para cada unidade de trabalho atribuída a um agente:
1. **Passo 1 (Carga de Contexto Mínimo):** Carregar apenas `AGENTS.MD`, `specs.md` e a especificação específica do domínio (`specs/0X-*.md`). Não inflar o contexto com módulos não correlatos.
2. **Passo 2 (Teste e Fixture Primeiro — TDD):** Escrever ou atualizar os testes unitários e de integração baseados em `pytest`, cobrindo casos normais, valores nulos, divisões por zero e invariantes matemáticas com base nas fixtures áureas.
3. **Passo 3 (Implementação Estrita):** Desenvolver a lógica nos módulos do domínio do agente, respeitando tipagem estrita (`mypy --strict`) e PEP 8.
4. **Passo 4 (Portão de Verificação Automático — *Verification Gate*):** Executar a bateria de verificação obrigatória:
   ```bash
   uv run ruff check src tests
   uv run ruff format --check src tests
   uv run mypy --strict src
   uv run pytest -q --cov=virada_eleitoral --cov-fail-under=90
   ```
5. **Passo 5 (Commit Granular e Atômico):** Realizar o commit isolado respeitando a convenção de Conventional Commits em `pt-BR` (1 a 2 arquivos coesos por commit).

---

## 3. Topologia Canônica do Repositório e Fronteiras de Domínio

```text
virada_eleitoral/
├── AGENTS.MD                           # Governança de agentes, padrões e protocolo SDD
├── specs.md                            # Especificação mestra, fórmulas analíticas e índice de requisitos
├── specs/                              # Especificações técnicas executáveis e detalhadas
│   ├── 01-harvesting-and-manifest.md   # Obtenção de BUs TSE, integridade SHA-512 e streaming
│   ├── 02-normalization-and-pairing.md # Filtragem presidencial, pareamento 1T x 2T e seções agregadas
│   ├── 03-analytics-and-turnover-metrics.md # Deltas, margens líquidas, classificação e DuckDB OLAP
│   ├── 04-export-geojson-and-web.md    # TopoJSON/GeoJSON IBGE, payloads estáticos e DuckDB-Wasm
│   └── 05-testing-fixtures-and-roadmap.md # Fixtures FX-01..FX-10, BDD/Gherkin, CLI e roadmap atômico
├── src/
│   └── virada_eleitoral/
│       ├── __init__.py
│       ├── cli.py                      # CLI unificada (`virada`) com subcomandos modulares
│       ├── config.py                   # Configurações tipadas via Pydantic Settings
│       ├── contracts/                  # Contratos compartilhados imutáveis (Fase 0 Freeze)
│       │   ├── models.py               # Dataclasses imutáveis e schemas Pydantic de handoff
│       │   └── exceptions.py           # Hierarquia de exceções canônicas de auditoria
│       ├── harvester/                  # Escopo exclusivo: `agent-harvester`
│       ├── normalizer/                 # Escopo exclusivo: `agent-normalizer`
│       ├── analytics/                  # Escopo exclusivo: `agent-analytics`
│       └── export/                     # Escopo exclusivo: `agent-exporter`
├── resources/
│   ├── tse_ibge_municipios.parquet     # De-Para canônico de códigos TSE (5 dígitos) x IBGE (7 dígitos)
│   └── geo/                            # Malha cartográfica simplificada IBGE (UFs e Municípios)
├── tests/
│   ├── conftest.py                     # Fixtures nativas pytest compartilhadas
│   ├── fixtures/                       # Gerador e registros sintéticos FX-01 a FX-10
│   ├── unit/                           # Testes unitários de cada módulo
│   ├── integration/                    # Testes de integração de pipeline fim-a-fim
│   └── property/                       # Testes de propriedades e invariantes matemáticas
├── frontend/                           # Aplicação web estática opcional / explorador interativo
└── data/                               # ESTRITAMENTE IGNORADO NO GIT (.gitignore)
    ├── raw/                            # Downloads de arquivos brutos do TSE (bweb_*.zip/csv)
    ├── processed/                      # Partições colunares Parquet ZSTD
    └── export/                         # Payloads JSON e TopoJSON estáticos para publicação
```

---

## 4. Matriz de Agentes, Papéis e "Agent Cards"

| Agente | Diretório de Escopo | Especificação Mandatória | Contrato de Entrada (Input) | Contrato de Saída (Output) |
| :--- | :--- | :--- | :--- | :--- |
| **`agent-harvester`** | `src/virada_eleitoral/harvester/` | [`specs/01-harvesting-and-manifest.md`](./specs/01-harvesting-and-manifest.md) | `HarvestConfig` + URLs TSE | Stream de `RawBuFileBundle` + `HarvestManifest` |
| **`agent-normalizer`** | `src/virada_eleitoral/normalizer/` | [`specs/02-normalization-and-pairing.md`](./specs/02-normalization-and-pairing.md) | `RawBuFileBundle` + De-Para IBGE | `PairedSectionBatch` + `UnpairedSectionAudit` |
| **`agent-analytics`** | `src/virada_eleitoral/analytics/` | [`specs/03-analytics-and-turnover-metrics.md`](./specs/03-analytics-and-turnover-metrics.md) | Lotes de `PairedSectionBatch` | Parquet Hive Particionado + DuckDB Consolidado |
| **`agent-exporter`** | `src/virada_eleitoral/export/` | [`specs/04-export-geojson-and-web.md`](./specs/04-export-geojson-and-web.md) | Tabelas e Views DuckDB | JSONs validados por Schema + TopoJSON IBGE |
| **`agent-qa-verifier`** | `tests/` e `resources/` | [`specs/05-testing-fixtures-and-roadmap.md`](./specs/05-testing-fixtures-and-roadmap.md) | Código-fonte + Fixtures `FX-*` | Relatório de cobertura, invariantes e conformidade |

### 4.1. Agent Card: Data Harvester (`agent-harvester`)
- **Missão:** Obter e gerenciar os arquivos de Boletins de Urna consolidados por estado (`bweb_1t_*.csv` e `bweb_2t_*.csv`) do Portal de Dados Abertos do TSE via download resiliente ou leitura de diretório local.
- **Competências & Restrições:**
  - Suporte a download assíncrono com retries exponenciais, jitter e verificação de integridade `SHA-512`.
  - Processamento em streaming de arquivos `.zip` sem descompactação prematura em disco quando aplicável, ou descompactação controlada por UF.
  - Registro de manifesto de download contendo tamanho de arquivo, hash e timestamp.

### 4.2. Agent Card: Normalization & Pairing Specialist (`agent-normalizer`)
- **Missão:** Efetuar a limpeza de dados, filtragem presidencial (`CD_CARGO == 1`), conversão De-Para TSE/IBGE e pareamento estrito entre urnas do 1º e 2º turnos.
- **Competências & Restrições:**
  - Proibição de uso de Pandas puro: executar operações com `DuckDB` ou `Polars LazyFrame`.
  - Tratamento determinístico de seções agregadas ou ausentes no 2T por contingência (`FULL OUTER JOIN` controlado com geração de logs de auditoria em `unpaired_sections_audit`).
  - Agrupamento em pivot de candidatos (13 Luiz Inácio Lula da Silva, 22 Flávio Bolsonaro, votos em terceiros candidatos do 1T, brancos, nulos e abstenções).

### 4.3. Agent Card: Analytical Engine & Metric Calculator (`agent-analytics`)
- **Missão:** Computar todas as fórmulas matemáticas de deltas, margem líquida, taxas de conversão percentual, classificação categórica, matriz de transição de votos por inferência ecológica e consolidação OLAP.
- **Competências & Restrições:**
  - Cálculo de `delta_votos_lula`, `delta_pp_lula`, `delta_margem` e classificação categórica:
    - `VIRADA_LULA`: Lula perdeu no 1T e venceu no 2T.
    - `VIRADA_ADVERSARIO`: Lula venceu no 1T e perdeu no 2T.
    - `MANTEVE_LIDERANCA`: Lula venceu em ambos os turnos.
    - `MANTEVE_DESVANTAGEM`: Lula perdeu em ambos os turnos.
  - Modelagem estatística da matriz de transição de votos (EI / WLS) e cálculo dos degraus de saldo líquido da virada (Waterfall de $\Delta \text{Margem}$).
  - Persistência colunar em Parquet particionado (`data/processed/ano={ano}/uf={uf}/part-*.parquet`, compressão ZSTD) e consolidação idempotente no DuckDB.
  - Rollup hierárquico das visões nacional, estadual e municipal com tratamento estrito de divisão por zero via `NULLIF` e `COALESCE`.

### 4.4. Agent Card: GeoJSON & Visualization Exporter (`agent-exporter`)
- **Missão:** Transformar os dados analíticos consolidados em artefatos estáticos otimizados para consumo web, visualização cartográfica e os 4 pilares visuais de jornalismo de dados.
- **Competências & Restrições:**
  - Geração dos payloads JSON estáticos dos 4 Pilares Gráficos:
    1. `waterfall_turnover_balance.json` (Cascata de saldo líquido da virada de -2,22 mi a +4,43 mi).
    2. `sankey_vote_flows.json` (Diagrama de fluxo aluvial de votos 1T -> 2T).
    3. `transition_distribution_groups.json` (Barras 100% de destino de outros candidatos, brancos/nulos e ausentes).
    4. `ecological_regression_scatter.json` (Dispersão seção a seção e reta de regressão ponderada).
  - Geração de resumos e rankings (`summary_national.json`, `summary_uf.json`, `swing_cities.json`, `top_urnas_virada.json`).
  - Junção dos dados municipais com a malha cartográfica do IBGE (geração de TopoJSON/GeoJSON simplificado com atributos de virada).
  - Exportação opcional de partições Parquet leves para permitir consultas interativas no navegador via DuckDB-Wasm.

### 4.5. Agent Card: QA, Invariants & Fixture Verifier (`agent-qa-verifier`)
- **Missão:** Garantir a fidelidade do sistema por meio de suítes de testes automatizados, geração de fixtures áureas sintéticas (`FX-01` a `FX-10`) e verificação de invariantes matemáticas.

---

## 5. Diretrizes de Código, Testes e Engenharia de Software

1. **Padrões de Linguagem e Documentação:**
   - **Python >= 3.12** com tipagem estática rigorosa (`mypy --strict`).
   - **Google Style Docstrings Obrigatórias:** Todo módulo, classe, função e método deve possuir docstring completa contendo as seções `Args:`, `Returns:` e `Raises:`.
   - **PEP 8 Estrito:** Verificado automaticamente via `ruff` (tamanho de linha máximo de 100 caracteres).
   - **Organização de Imports:** Biblioteca padrão, pacotes de terceiros e módulos locais, agrupados e separados por linha em branco.
2. **Gerenciamento de Pacotes:**
   - Exclusivamente gerenciado via **Astral `uv`** (`uv sync`, `uv add`, `uv run`). É **estritamente proibido** sugerir ou executar comandos `pip` comuns.
3. **Padrões Rígidos de Testes Automatizados:**
   - **Framework Exclusivo:** `pytest` para 100% da suíte de testes.
   - **Mocking:** Utilizar exclusivamente `pytest-mock` (fixture nativa `mocker`).
   - **Proibição Absoluta:** É **estritamente proibido** importar ou usar o módulo padrão `unittest`, classes `unittest.TestCase` ou `unittest.mock`.
4. **Governança de Commits e Git:**
   - **Commits Granulares e Atômicos:** Todo commit deve conter a menor quantidade possível de arquivos coesos (preferencialmente 1 a 2 arquivos por commit).
   - **Conventional Commits em `pt-BR`:** No modo imperativo, concisos e padronizados (`feat`, `fix`, `test`, `docs`, `chore`, `refactor`, `perf`, `ci`, `data`). Exemplo: `feat(analytics): implementar calculo de margem liquida e classificacao de virada`.
   - **Higiene do Repositório:** Proibição absoluta de versionar dados brutos/processados (`data/`), bancos DuckDB, arquivos `.env` ou caches.

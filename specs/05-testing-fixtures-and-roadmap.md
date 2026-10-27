# Especificação 05: Testes, Fixtures Áureas, CLI e Roadmap de Execução SDD

**Agentes Responsáveis:** `agent-qa-verifier` e agentes executores  
**Requisitos Cobertos:** `REQ-QA-01` e governança de qualidade  
**Escopo Mandatório:** Eleição Presidencial de 2026 (2º turno: 25/10/2026 — Luiz Inácio Lula da Silva vs. Flávio Bolsonaro)

---

## 1. Catálogo de Fixtures Áureas (`tests/fixtures/` — `FX-01` a `FX-10`)

Antes de conectar o pipeline a dados brutos do TSE, toda a lógica de filtragem, pareamento, deltas, classificação de virada e agregação deve ser validada contra **10 cenários sintéticos determinísticos**:

| ID | Cenário Testado | Dados Simulados (1T e 2T) | Resultado Esperado |
| :--- | :--- | :--- | :--- |
| `FX-01` | Manutenção de Liderança Lula | 1T: Lula=120, Adv=80, Outros=30.<br>2T: Lula=140, Adv=90. | `classificacao_virada = 'MANTEVE_LIDERANCA'`, `delta_votos_lula = +20`, `delta_margem = +10`. |
| `FX-02` | Virada Clássica de Lula (`VIRADA_LULA`) | 1T: Lula=90, Adv=130, Outros=40.<br>2T: Lula=145, Adv=115. | `classificacao_virada = 'VIRADA_LULA'`, `delta_votos_lula = +55`, `delta_margem = +70`. |
| `FX-03` | Virada do Adversário (`VIRADA_ADVERSARIO`)| 1T: Lula=110, Adv=100, Outros=20.<br>2T: Lula=112, Adv=118. | `classificacao_virada = 'VIRADA_ADVERSARIO'`, `delta_votos_lula = +2`, `delta_margem = -16`. |
| `FX-04` | Manutenção de Desvantagem Lula | 1T: Lula=70, Adv=140, Outros=20.<br>2T: Lula=80, Adv=150. | `classificacao_virada = 'MANTEVE_DESVANTAGEM'`, `delta_votos_lula = +10`, `delta_margem = 0`. |
| `FX-05` | Seção Agregada no 2T (`APENAS_1T`) | Seção presente no 1T (Lula=50, Adv=40), mas ausente no 2T. | `status_pareamento = 'APENAS_1T'`, computado no total municipal 1T, auditado em `unpaired_sections_audit`. |
| `FX-06` | Seção de Contingência Aberta (`APENAS_2T`) | Seção ausente no 1T, presente no 2T (Lula=60, Adv=50). | `status_pareamento = 'APENAS_2T'`, computado no total municipal 2T, auditado em `unpaired_sections_audit`. |
| `FX-07` | Alta Absorção de Votos de 3ºs Colocados | 1T: Lula=80, Adv=80, Outros=60.<br>2T: Lula=130, Adv=90. | `delta_votos_lula = +50`, `eficiencia_absorcao_outros = 0.8333` (absorveu 83,3% do pool de terceiros). |
| `FX-08` | Empate em Turno | 1T: Lula=100, Adv=100, Outros=20.<br>2T: Lula=115, Adv=105. | `classificacao_virada = 'EMPATE_1T'` ou transição para vitória no 2T com tratamento de margem zero. |
| `FX-09` | Seção Especial sem Votos em Candidato | Seção prisional ou itinerante onde um dos candidatos teve 0 votos. | Divisões por zero tratadas (`COALESCE/NULLIF`), `pct = 0.0`, sem erro de execução. |
| `FX-10` | Agregação Municipal Pêndulo (*Swing City*) | Município com 3 seções: Seção A virou Lula (+30), B manteve Adv (-10), C virou Lula (+20). | Município agregado classificado como `status_virada_municipio = 'VIRADA_LULA'`. |

---

## 2. Critérios de Aceite Comportamentais (BDD / Gherkin)

```gherkin
Funcionalidade: Pareamento e classificação de viradas eleitorais entre turnos (Eleições 2026)

  Cenário: Classificação de virada de urna com absorção de votos de terceiros
    Dado um Boletim de Urna do 1º turno onde Lula teve 100 votos, Flávio Bolsonaro 120 e outros candidatos 50
    E o Boletim de Urna correspondente do 2º turno onde Lula teve 140 votos e Flávio Bolsonaro 130
    Quando o agent-normalizer e agent-analytics processarem a seção
    Então a chave de pareamento deve possuir status "PAREADA_AMBOS"
    E a classificacao_virada da urna deve ser "VIRADA_LULA"
    E delta_votos_lula deve ser 40
    E delta_margem deve ser 30

  Cenário: Conservação de votos em agregações hierárquicas
    Dado um conjunto de seções pareadas de um município
    Quando for gerada a view agg_municipio
    Então a soma de votos_lula_1t de todas as seções deve ser exatamente igual a total_lula_1t do município
    E a soma de votos_lula_2t deve ser exatamente igual a total_lula_2t do município

  Cenário: Conservação matemática da cascata de saldo líquido (Waterfall Invariant)
    Dado o cálculo de saldo líquido por grupo de origem do 1º turno
    Quando for gerado o payload waterfall_turnover_balance.json
    Então a soma dos saldos líquidos de todos os degraus deve ser rigorosamente igual a delta_margem nacional
    E a diferença_2t menos a diferença_1t deve coincidir com o somatório dos degraus

  Cenário: Conservação da matriz de transição de votos (Sankey / Inferência Ecológica)
    Dado o modelo de inferência ecológica sobre as seções eleitorais
    Quando for gerado o payload sankey_vote_flows.json
    Então cada grupo de origem do 1T deve ter 100% de seus eleitores distribuídos entre os destinos do 2T
    E o somatório dos fluxos para o destino Lula deve ser igual aos novos votos de Lula no 2T
```

---

## 3. Especificação da Interface CLI (`virada`)

A CLI unificada é implementada em `src/virada_eleitoral/cli.py` utilizando `typer`:

| Comando | Argumentos Principais | Responsabilidade |
| :--- | :--- | :--- |
| `virada harvest` | `--ano 2026`, `--turno [1\|2]`, `--uf [UF\|ALL]`, `--input-dir` | Coleta os arquivos CSV/ZIP do TSE (2026) e gera manifesto de integridade. |
| `virada normalize` | `--ano 2026`, `--uf [UF\|ALL]`, `--input-dir` | Filtra cargo Presidente, pivota candidatos (Lula x Flávio Bolsonaro) e pareia 1T x 2T. |
| `virada consolidate` | `--ano 2026`, `--db-path data/virada_eleitoral.duckdb` | Consolida os Parquets gerados no DuckDB e computa as visões analíticas. |
| `virada export` | `--ano 2026`, `--db-path`, `--out-dir data/export` | Exporta os arquivos JSON (resumos, fluxo Sankey) e TopoJSON IBGE. |
| `virada verify` | `--db-path`, `--json-dir` | Executa bateria de checagem pós-execução das 5 invariantes matemáticas. |
| `virada run-all` | `--ano 2026`, `--uf [UF\|ALL]`, `--input-dir` | Orquestra sequencialmente: `harvest` -> `normalize` -> `consolidate` -> `export` -> `verify`. |

---

## 4. Portões de Qualidade (*Definition of Done* — DoD)

Nenhum módulo é considerado concluído sem validação total nos seguintes passos:
1. `uv run ruff check src tests` (Zero advertências ou erros de linting).
2. `uv run ruff format --check src tests` (Formatação estrita de código).
3. `uv run mypy --strict src` (100% de cobertura de tipagem estática estrita).
4. `uv run pytest -q --cov=virada_eleitoral --cov-fail-under=90` (Suíte 100% em funções pytest nativas; proibido unittest).

---

## 5. Roadmap de Implementação em Tarefas Atômicas (Pronto para Agentes)

- **Fase 1 — Fundação, Ambiente e Contratos Imutáveis (`contracts` & `resources`):**
  - `chore(deps): configurar pyproject.toml com dependencias nativas polars duckdb e ruff`
  - `feat(contracts): definir dataclasses de handoff e excecoes canonicas` (`src/virada_eleitoral/contracts/`)
  - `data(resources): criar gerador de tabela de-para de codigos tse e ibge`
- **Fase 2 — Fixtures Áureas e Validador de Invariantes (`tests/fixtures/`):**
  - `test(fixtures): implementar gerador deterministico das fixtures aureas FX-01 a FX-10`
  - `test(property): implementar testes de propriedades e invariantes matematicas com hypothesis`
- **Fase 3 — Motor de Normalização e Pareamento (`agent-normalizer`):**
  - `feat(normalizer): implementar filtragem de presidente e pivotagem de votos nominais`
  - `feat(normalizer): implementar full outer join de pareamento e auditoria de secoes agregadas`
- **Fase 4 — Motor de Coleta e Streaming (`agent-harvester`):**
  - `feat(harvester): implementar provedor local e download assincrono de BUs com sha512`
- **Fase 5 — Motor Analítico e DuckDB OLAP (`agent-analytics`):**
  - `feat(analytics): implementar gravacao parquet particionada zstd`
  - `feat(analytics): implementar consolidacao duckdb views olap e classificacao de virada`
- **Fase 6 — Exportador Geoespacial, CLI e Validação Fim-a-Fim (`agent-exporter`):**
  - `feat(export): implementar exportador json tipado e merge cartografico ibge`
  - `feat(cli): implementar interface typer unificada virada e comando run-all`

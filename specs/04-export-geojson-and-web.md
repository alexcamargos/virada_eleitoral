# Especificação 04: Exportação de Dados Estáticos, GeoJSON e Visualização Web

**Agente Responsável:** `agent-exporter` (`src/virada_eleitoral/export/`)  
**Requisitos Cobertos:** `REQ-EXPO-01`, `REQ-EXPO-02`  
**Escopo Mandatório:** Eleições Presidenciais de 2026 (2º turno: 25/10/2026 — Luiz Inácio Lula da Silva vs. Flávio Bolsonaro)

---

## 1. Exportação de Payloads JSON Estáticos (`REQ-EXPO-01`)

O módulo `export` é responsável por extrair dados das views do DuckDB e materializar arquivos JSON estáticos e tipados em `data/export/`:

```text
data/export/
├── metadata.json                     # Metadados do processamento, versão do pipeline, hash do banco (2026)
├── summary_national.json             # Totais consolidados do Brasil e contagem de viradas
├── summary_uf.json                   # Resumo por Unidade Federativa
├── swing_cities.json                 # Todas as cidades que tiveram virada de liderança
├── top_urnas_virada.json             # Ranking das maiores viradas em urnas individuais
├── waterfall_turnover_balance.json   # PILAR 1: Cascata de saldo líquido da virada (de -2,22 mi a +4,43 mi)
├── sankey_vote_flows.json            # PILAR 2: Fluxos aluviais completos de migração de votos 1T -> 2T
├── transition_distribution_groups.json # PILAR 3: Barras empilhadas 100% de destino por grupo de origem
├── ecological_regression_scatter.json # PILAR 4: Dispersão seção a seção e reta de regressão ponderada
├── states_deep_dive_southeast.json   # GEO-PILAR 3: Painel comparativo de avanço em SP, RJ e MG
├── lula_advance_bubble_map.json      # GEO-PILAR 4A: Bolhas de avanço de Lula (escala sequencial 0 a +10 pp)
├── flavio_performance_bubble_map.json # GEO-PILAR 4B: Bolhas de Flávio (escala divergente -3 pp a +6 pp)
└── geo/
    ├── ufs_virada.topojson           # GEO-PILAR 1: Malha estadual com vencedor e percentuais 2T
    └── municipios_virada.topojson     # GEO-PILAR 2: Malha de 5.570 municípios com status de virada e percentuais
```

### 1.1. Contrato `summary_national.json`
```json
{
  "ano_eleicao": 2026,
  "total_secoes_analisadas": 472075,
  "total_secoes_pareadas": 471920,
  "total_validos_1t": 118580000,
  "total_validos_2t": 124250000,
  "total_lula_1t": 57259504,
  "total_lula_2t": 60345999,
  "total_adv_1t": 51072345,
  "total_adv_2t": 58206354,
  "delta_nacional_lula": 3086495,
  "pct_lula_1t_brasil": 48.43,
  "pct_lula_2t_brasil": 50.90,
  "delta_pp_lula_brasil": 2.47,
  "total_urnas_virada_lula": 23410,
  "total_urnas_virada_adv": 8120
}
```

### 1.2. Contrato `waterfall_turnover_balance.json` (PILAR 1: Cascata de Saldo Líquido da Virada)
Mapeia como a diferença mudou entre os turnos em milhões de votos, detalhando o saldo líquido de cada grupo de origem (votos que foram para Lula menos os que foram para Flávio Bolsonaro):
```json
{
  "ano_eleicao": 2026,
  "metodologia": "Estimativa por inferência ecológica ponderada sobre as seções do TSE",
  "unidade": "milhoes_de_votos",
  "diferenca_1t": -2.22,
  "rotulo_1t": "Flávio à frente (-2,22 mi)",
  "degraus": [
    {
      "grupo": "Ex-brancos e nulos",
      "saldo_liquido": 3.23,
      "favorece": "Lula",
      "votos_para_lula": 3.61,
      "votos_para_flavio": 0.38
    },
    {
      "grupo": "Ausentes que voltaram a votar",
      "saldo_liquido": 1.83,
      "favorece": "Lula",
      "votos_para_lula": 3.04,
      "votos_para_flavio": 1.21
    },
    {
      "grupo": "Perdas de base",
      "saldo_liquido": 1.27,
      "favorece": "Lula",
      "descricao": "Flávio perdeu 1,70 mi eleitores (3%); Lula perdeu 0,60 mi (1%). Ambos mantiveram 97%+ dos votos."
    },
    {
      "grupo": "Outros candidatos do 1T",
      "saldo_liquido": 0.32,
      "favorece": "Lula",
      "votos_para_lula": 4.16,
      "votos_para_flavio": 3.84
    }
  ],
  "diferenca_2t": 4.43,
  "rotulo_2t": "Lula à frente (+4,43 mi)"
}
```

### 1.3. Contrato `sankey_vote_flows.json` (PILAR 2: Diagrama de Fluxo Aluvial / Sankey)
Representa os volumes brutos em milhões de eleitores que transitaram entre os turnos (excluindo quem repetiu voto em Lula/Flávio e quem faltou nos dois turnos):
```json
{
  "ano_eleicao": 2026,
  "metrica": "milhoes_de_eleitores",
  "total_novos_votos_lula": 11.0,
  "total_novos_votos_flavio": 4.4,
  "nodes": [
    {"id": "nao_votou_1t", "label": "Não votou (1T)", "total": 4.49},
    {"id": "branco_nulo_1t", "label": "Branco ou nulo (1T)", "total": 5.98},
    {"id": "outros_1t", "label": "Outros candidatos (1T)", "total": 9.32},
    {"id": "perdas_lula_1t", "label": "Eleitores de Lula que mudaram (1T)", "total": 0.60},
    {"id": "perdas_flavio_1t", "label": "Eleitores de Flávio que mudaram (1T)", "total": 1.70},
    {"id": "lula_2t", "label": "Lula (2T)", "total": 11.00},
    {"id": "flavio_2t", "label": "Flávio (2T)", "total": 4.40},
    {"id": "branco_nulo_2t", "label": "Branco ou nulo (2T)", "total": 4.10},
    {"id": "nao_votou_2t", "label": "Não votou (2T)", "total": 1.40}
  ],
  "links": [
    {"source": "nao_votou_1t", "target": "lula_2t", "value": 3.04},
    {"source": "nao_votou_1t", "target": "flavio_2t", "value": 1.21},
    {"source": "nao_votou_1t", "target": "branco_nulo_2t", "value": 0.24},
    {"source": "branco_nulo_1t", "target": "lula_2t", "value": 3.61},
    {"source": "branco_nulo_1t", "target": "flavio_2t", "value": 0.38},
    {"source": "branco_nulo_1t", "target": "branco_nulo_2t", "value": 1.96},
    {"source": "outros_1t", "target": "lula_2t", "value": 4.16},
    {"source": "outros_1t", "target": "flavio_2t", "value": 3.84},
    {"source": "outros_1t", "target": "branco_nulo_2t", "value": 1.14},
    {"source": "outros_1t", "target": "nao_votou_2t", "value": 0.18},
    {"source": "perdas_flavio_1t", "target": "lula_2t", "value": 0.80},
    {"source": "perdas_flavio_1t", "target": "branco_nulo_2t", "value": 0.50},
    {"source": "perdas_flavio_1t", "target": "nao_votou_2t", "value": 0.40},
    {"source": "perdas_lula_1t", "target": "flavio_2t", "value": 0.20},
    {"source": "perdas_lula_1t", "target": "branco_nulo_2t", "value": 0.25},
    {"source": "perdas_lula_1t", "target": "nao_votou_2t", "value": 0.15}
  ]
}
```

### 1.4. Contrato `transition_distribution_groups.json` (PILAR 3: Barras Empilhadas 100% de Destino)
Alimenta os gráficos de barras horizontais 100% comparando para onde foi o voto de cada grupo do 1T:
```json
{
  "ano_eleicao": 2026,
  "grupos": [
    {
      "id": "outros_total",
      "nome": "Eleitores de outros candidatos",
      "total_eleitores": 9320000,
      "distribuicao_percentual": {"lula": 45.0, "flavio": 41.0, "branco_nulo": 12.0, "nao_votou": 2.0},
      "distribuicao_nominal": {"lula": 4160000, "flavio": 3840000, "branco_nulo": 1140000, "nao_votou": 184000},
      "subcandidatos": [
        {"nome": "Cury", "total": 3400000, "distribuicao_pct": {"lula": 55.0, "flavio": 27.0, "branco_nulo": 15.0, "nao_votou": 3.0}},
        {"nome": "Caiado", "total": 2900000, "distribuicao_pct": {"lula": 34.0, "flavio": 52.0, "branco_nulo": 11.0, "nao_votou": 3.0}},
        {"nome": "Renan Santos e Zema", "total": 2800000, "distribuicao_pct": {"lula": 39.0, "flavio": 44.0, "branco_nulo": 14.0, "nao_votou": 3.0}}
      ]
    },
    {
      "id": "brancos_nulos",
      "nome": "Quem votou branco ou nulo",
      "total_eleitores": 5980000,
      "distribuicao_percentual": {"lula": 60.0, "flavio": 6.0, "branco_nulo": 33.0, "nao_votou": 1.0},
      "distribuicao_nominal": {"lula": 3610000, "flavio": 380000, "branco_nulo": 1960000, "nao_votou": 25000}
    },
    {
      "id": "ausentes_retornaram",
      "nome": "Ausentes que voltaram a votar",
      "total_eleitores": 4490000,
      "pct_do_pool_ausentes_1t": 13.4,
      "distribuicao_percentual": {"lula": 68.0, "flavio": 27.0, "branco_nulo": 5.0},
      "distribuicao_nominal": {"lula": 3040000, "flavio": 1210000, "branco_nulo": 249000}
    }
  ]
}
```

### 1.5. Contrato `ecological_regression_scatter.json` (PILAR 4: Dispersão com Regressão Ponderada)
Dados da nuvem de pontos de seções eleitorais e parâmetros da reta de tendência (relação empírica entre % de brancos/nulos no 1T e o crescimento em pontos percentuais de Lula no 2T):
```json
{
  "ano_eleicao": 2026,
  "titulo": "Lula conquista brancos e nulos",
  "eixo_x": {"nome": "Brancos e nulos no 1º turno (% do eleitorado apto)", "min": 0.0, "max": 10.0},
  "eixo_y": {"nome": "Crescimento de Lula no 2º turno (pp)", "min": -2.0, "max": 16.0},
  "regressao": {
    "coeficiente_angular_beta": 0.80,
    "intercepto_alpha": 3.65,
    "r_quadrado": 0.44,
    "chamada_destaque": "+0,8 pp para Lula a cada 1 pp de branco e nulo",
    "total_secoes_modelo": 472075,
    "secoes_amostra_visualizacao": 900
  },
  "pontos_amostra": [
    {"sg_uf": "SP", "nr_secao": 101, "x_pct_branco_nulo": 4.2, "y_delta_pp_lula": 7.1, "aptos": 395},
    {"sg_uf": "MG", "nr_secao": 45, "x_pct_branco_nulo": 5.8, "y_delta_pp_lula": 8.4, "aptos": 340},
    {"sg_uf": "BA", "nr_secao": 12, "x_pct_branco_nulo": 2.1, "y_delta_pp_lula": 5.3, "aptos": 310}
  ]
}
```

### 1.6. Contrato `swing_cities.json`
Array de municípios onde ocorreu inversão de vencedor entre turnos:
```json
[
  {
    "sg_uf": "MG",
    "cd_municipio": 41238,
    "cd_municipio_ibge": 3106200,
    "nm_municipio": "BELO HORIZONTE",
    "total_secoes": 4320,
    "votos_lula_1t": 558000,
    "votos_lula_2t": 612000,
    "votos_adv_1t": 620000,
    "votos_adv_2t": 605000,
    "delta_votos_lula": 54000,
    "pct_lula_1t": 46.50,
    "pct_lula_2t": 50.28,
    "delta_pp_lula": 3.78,
    "delta_margem": 69000,
    "status_virada_municipio": "VIRADA_LULA"
  }
]
```

### 1.7. Contrato `states_deep_dive_southeast.json` (GEO-PILAR 3: Painel Sudeste SP, RJ e MG)
Contrato com a comparação de 1T e 2T para os três maiores colégios eleitorais do país:
```json
{
  "ano_eleicao": 2026,
  "titulo": "Votos totais em SP, RJ e MG - Avanço de Lula foi mais que o dobro de Flávio",
  "estados": [
    {
      "sg_uf": "SP",
      "nome_estado": "São Paulo",
      "lula": {"votos_1t": 9505413, "votos_2t": 12119116, "delta_nominal": 2613703, "pct_1t": 40.89, "pct_2t": 46.14, "delta_pp": 5.25},
      "flavio": {"votos_1t": 12922023, "votos_2t": 14139069, "delta_nominal": 1217046, "pct_1t": 55.57, "pct_2t": 53.86, "delta_pp": -1.71},
      "razao_crescimento": 2.15
    },
    {
      "sg_uf": "MG",
      "nome_estado": "Minas Gerais",
      "lula": {"votos_1t": 5188936, "votos_2t": 6232349, "delta_nominal": 1043413, "pct_1t": 43.18, "pct_2t": 49.60, "delta_pp": 6.42},
      "flavio": {"votos_1t": 5777548, "votos_2t": 6331593, "delta_nominal": 554045, "pct_1t": 48.08, "pct_2t": 50.40, "delta_pp": 2.32},
      "razao_crescimento": 1.88
    },
    {
      "sg_uf": "RJ",
      "nome_estado": "Rio de Janeiro",
      "lula": {"votos_1t": 3693021, "votos_2t": 4565286, "delta_nominal": 872265, "pct_1t": 38.23, "pct_2t": 46.90, "delta_pp": 8.67},
      "flavio": {"votos_1t": 4966844, "votos_2t": 5168902, "delta_nominal": 202058, "pct_1t": 51.41, "pct_2t": 53.10, "delta_pp": 1.69},
      "razao_crescimento": 4.32
    }
  ]
}
```

### 1.8. Contrato `lula_advance_bubble_map.json` (GEO-PILAR 4: Bolhas Proporcionais de Avanço de Lula)
Contém os centróides, tamanho de eleitorado apto e ganho em pontos percentuais para os 5.570 municípios, com metadados para callouts das principais metrópoles:
```json
{
  "ano_eleicao": 2026,
  "titulo": "Onde Lula avançou entre o 1º e o 2º Turno (2026) ponderado pelo eleitorado",
  "metrica_escala": "Crescimento em pontos percentuais dos votos válidos (1T para 2T)",
  "escala_cores": {"min_pp": 0.0, "max_pp": 10.0, "cor_min": "#FFFFFF", "cor_max": "#800000"},
  "destaques_capitais": [
    {"cidade": "São Paulo", "sg_uf": "SP", "delta_pp": 8.9, "lat": -23.5505, "lon": -46.6333, "aptos": 9314000},
    {"cidade": "Salvador", "sg_uf": "BA", "delta_pp": 8.0, "lat": -12.9777, "lon": -38.5016, "aptos": 1980000},
    {"cidade": "Belo Horizonte", "sg_uf": "MG", "delta_pp": 7.8, "lat": -19.9167, "lon": -43.9345, "aptos": 2000000},
    {"cidade": "Rio de Janeiro", "sg_uf": "RJ", "delta_pp": 7.6, "lat": -22.9068, "lon": -43.1729, "aptos": 5000000},
    {"cidade": "Brasília", "sg_uf": "DF", "delta_pp": 7.6, "lat": -15.7975, "lon": -47.8919, "aptos": 2200000},
    {"cidade": "Curitiba", "sg_uf": "PR", "delta_pp": 7.3, "lat": -25.4284, "lon": -49.2733, "aptos": 1400000},
    {"cidade": "Porto Alegre", "sg_uf": "RS", "delta_pp": 7.3, "lat": -30.0346, "lon": -51.2177, "aptos": 1100000},
    {"cidade": "Belém", "sg_uf": "PA", "delta_pp": 7.0, "lat": -1.4558, "lon": -48.4902, "aptos": 1050000},
    {"cidade": "Manaus", "sg_uf": "AM", "delta_pp": 7.0, "lat": -3.1190, "lon": -60.0217, "aptos": 1400000},
    {"cidade": "Fortaleza", "sg_uf": "CE", "delta_pp": 6.6, "lat": -3.7172, "lon": -38.5433, "aptos": 1800000},
    {"cidade": "Recife", "sg_uf": "PE", "delta_pp": 6.0, "lat": -8.0476, "lon": -34.8770, "aptos": 1200000}
  ],
  "municipios": [
    {"cd_ibge": 3550308, "nm": "São Paulo", "uf": "SP", "aptos": 9314000, "delta_pp": 8.9, "lat": -23.5505, "lon": -46.6333},
    {"cd_ibge": 3144300, "nm": "Nanuque", "uf": "MG", "aptos": 31200, "delta_pp": 4.46, "status_virada": "VIRADA_LULA", "lat": -17.8389, "lon": -40.3542}
  ]
}
```

### 1.9. Contrato `flavio_performance_bubble_map.json` (GEO-PILAR 4B: Bolhas de Flávio com Escala Divergente)
Contém os centróides, tamanho de aptos e variação em pontos percentuais dos votos válidos para Flávio Bolsonaro, utilizando escala divergente (recuo em vermelho vs avanço em azul):
```json
{
  "ano_eleicao": 2026,
  "titulo": "Desempenho de Flávio entre o 1º e o 2º Turno (2026) ponderado pelo eleitorado",
  "metrica_escala": "Variação em pontos percentuais dos votos válidos (1T para 2T)",
  "escala_cores": {
    "tipo": "divergente",
    "min_pp": -3.0,
    "centro_pp": 0.0,
    "max_pp": 6.0,
    "cor_recuo": "#B22222",
    "cor_neutra": "#FFFFFF",
    "cor_avanco": "#002060",
    "rotulo_recuo": "Flávio recuou (-3 pp)",
    "rotulo_avanco": "Flávio avançou (>= +6 pp)"
  },
  "destaques_capitais": [
    {"cidade": "Curitiba", "sg_uf": "PR", "delta_pp": 4.8, "lat": -25.4284, "lon": -49.2733, "aptos": 1400000},
    {"cidade": "Brasília", "sg_uf": "DF", "delta_pp": 3.0, "lat": -15.7975, "lon": -47.8919, "aptos": 2200000},
    {"cidade": "Belo Horizonte", "sg_uf": "MG", "delta_pp": 2.5, "lat": -19.9167, "lon": -43.9345, "aptos": 2000000},
    {"cidade": "São Paulo", "sg_uf": "SP", "delta_pp": 2.4, "lat": -23.5505, "lon": -46.6333, "aptos": 9314000},
    {"cidade": "Porto Alegre", "sg_uf": "RS", "delta_pp": 2.3, "lat": -30.0346, "lon": -51.2177, "aptos": 1100000},
    {"cidade": "Manaus", "sg_uf": "AM", "delta_pp": 1.6, "lat": -3.1190, "lon": -60.0217, "aptos": 1400000},
    {"cidade": "Belém", "sg_uf": "PA", "delta_pp": 1.3, "lat": -1.4558, "lon": -48.4902, "aptos": 1050000},
    {"cidade": "Rio de Janeiro", "sg_uf": "RJ", "delta_pp": 0.6, "lat": -22.9068, "lon": -43.1729, "aptos": 5000000},
    {"cidade": "Fortaleza", "sg_uf": "CE", "delta_pp": 0.6, "lat": -3.7172, "lon": -38.5433, "aptos": 1800000},
    {"cidade": "Recife", "sg_uf": "PE", "delta_pp": 0.4, "lat": -8.0476, "lon": -34.8770, "aptos": 1200000},
    {"cidade": "Salvador", "sg_uf": "BA", "delta_pp": -0.3, "lat": -12.9777, "lon": -38.5016, "aptos": 1980000, "status": "RECUO"}
  ],
  "municipios": [
    {"cd_ibge": 4106902, "nm": "Curitiba", "uf": "PR", "aptos": 1400000, "delta_pp": 4.8, "lat": -25.4284, "lon": -49.2733},
    {"cd_ibge": 2927408, "nm": "Salvador", "uf": "BA", "aptos": 1980000, "delta_pp": -0.3, "lat": -12.9777, "lon": -38.5016}
  ]
}
```

---

## 2. Fusão Cartográfica com Malha IBGE e os 4 Pilares Geo-Analíticos (`REQ-EXPO-02`, `REQ-EXPO-04`)

A entrega mínima cartográfica integra 4 pilares espaciais multiníveis:

1. **GEO-PILAR 1: Mapa Coroplético Estadual (`ufs_virada.topojson`):**
   - Malha das 26 UFs + DF simplificada (< 300 KB).
   - Injeta em cada polígono:
     * `vencedor_2t`: `"LULA"` (cor vermelha) ou `"FLAVIO"` (cor azul).
     * `pct_lula_2t`, `pct_flavio_2t`, `delta_pp_lula`, `total_validos_2t`.
   - Permite ao visitante visualizar instantaneamente a divisão geopolítica macro do Brasil.

2. **GEO-PILAR 2: Mapa Coroplético de Alta Resolução dos 5.570 Municípios (`municipios_virada.topojson`):**
   - Malha de todos os municípios simplificada (tolerância `0.005°`, tamanho `< 4 MB`).
   - Injeta nas feições municipais:
     * `vencedor_2t`: `"LULA"`, `"FLAVIO"` ou `"EMPATE"`.
     * `status_virada_municipio`: `"VIRADA_LULA"`, `"VIRADA_ADVERSARIO"`, `"MANTEVE_LIDERANCA"`, `"MANTEVE_DESVANTAGEM"`.
     * Atributos de ambos os turnos para alimentar o **Card Comparativo de Cidades Pêndulo** (exemplo canônico de aceitação: **Nanuque / MG**, exibindo foto, porcentagens de 1T e 2T e selo de 'Eleito'):
       - 1T: Flávio Bolsonaro (48,54%) vs Lula (46,87%) [Azul / Flávio liderando]
       - 2T: Lula (51,33% Eleito) vs Flávio Bolsonaro (48,67%) [Vermelho / Lula virando]

3. **GEO-PILAR 3: Painel Comparativo Lado a Lado dos Grandes Colégios (SP, RJ e MG):**
   - Permite ao visitante alternar ou visualizar lado a lado o mapa municipal de 1T vs 2T nos três maiores estados do país.
   - Gráficos integrados de barras comparativas alimentados por `states_deep_dive_southeast.json` demonstrando que o crescimento de Lula superou em mais que o dobro o avanço de Flávio na região mais populosa do Brasil.

4. **GEO-PILAR 4: Díptico Cartográfico de Bolhas Proporcionais Ponderadas (Lula vs. Flávio):**
   - Renderização espelhada lado a lado ou com seletor de candidato no frontend:
     * **4A (Lula):** Alimentado por `lula_advance_bubble_map.json` com escala contínua de 0 a $\ge +10\text{ pp}$ de avanço.
     * **4B (Flávio):** Alimentado por `flavio_performance_bubble_map.json` com escala divergente de $-3\text{ pp}$ (recuo) a $\ge +6\text{ pp}$ (avanço).
   - Diâmetro das bolhas calibrado pela raiz quadrada de `total_aptos` ($\text{raio} \propto \sqrt{\text{aptos}}$).
   - Painel comparativo de callouts para metrópoles demonstrando que Lula avançou em média $3\times$ a $12\times$ mais rápido que Flávio nas principais capitais.

5. **Suporte a Consultas Locais via DuckDB-Wasm:**
   - Exportação de partições Parquet por UF em `data/export/wasm/sections_{uf}.parquet` permitindo inspeção interativa de qualquer uma das ~470.000 seções no navegador sem backend dinâmico.

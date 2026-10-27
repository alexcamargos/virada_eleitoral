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
└── geo/
    ├── ufs_virada.topojson           # Malha estadual com atributos consolidados
    └── municipios_virada.topojson     # Malha municipal simplificada com atributos de virada
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

---

## 2. Fusão Cartográfica com Malha IBGE (`REQ-EXPO-02`)

1. **Malha Vetorial Simplificada:**
   - O repositório armazena a malha municipal simplificada do IBGE (limite de tolerância `0.005°` para manter o tamanho `< 4 MB`).
2. **Algoritmo de Merge:**
   - Cruzar os atributos de `agg_municipio` com o identificador de 7 dígitos `cd_municipio_ibge` presente nas propriedades das feições geográficas.
   - Gerar `municipios_virada.topojson` injetando diretamente nos polígonos:
     `status_virada_municipio`, `delta_pp_lula`, `delta_votos_lula`, `pct_lula_2t`.
3. **Suporte a DuckDB-Wasm no Frontend:**
   - Exportação particionada por UF em `data/export/wasm/sections_{uf}.parquet` para permitir que o usuário filtre ou inspecione qualquer urna no navegador sem requisições a um servidor backend.

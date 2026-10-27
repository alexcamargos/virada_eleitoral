# Especificação 04: Exportação de Dados Estáticos, GeoJSON e Visualização Web

**Agente Responsável:** `agent-exporter` (`src/virada_eleitoral/export/`)  
**Requisitos Cobertos:** `REQ-EXPO-01`, `REQ-EXPO-02`  
**Escopo Mandatório:** Eleições Presidenciais de 2026 (2º turno: 25/10/2026 — Luiz Inácio Lula da Silva vs. Flávio Bolsonaro)

---

## 1. Exportação de Payloads JSON Estáticos (`REQ-EXPO-01`)

O módulo `export` é responsável por extrair dados das views do DuckDB e materializar arquivos JSON estáticos e tipados em `data/export/`:

```text
data/export/
├── metadata.json                 # Metadados do processamento, versão do pipeline, hash do banco (2026)
├── summary_national.json         # Totais consolidados do Brasil e contagem de viradas
├── summary_uf.json               # Resumo por Unidade Federativa
├── swing_cities.json             # Todas as cidades que tiveram virada de liderança
├── top_urnas_virada.json         # Ranking das maiores viradas em urnas individuais
├── vote_migration_flow.json      # Decomposição de fontes e fluxo Sankey da construção de votos de Lula no 2T
└── geo/
    ├── ufs_virada.topojson       # Malha estadual com atributos consolidados
    └── municipios_virada.topojson # Malha municipal simplificada com atributos de virada
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

### 1.2. Contrato `vote_migration_flow.json` (Fluxo Sankey / Decomposição de Votos de Lula)
Payload dedicado para alimentar o componente visual de fluxo aluvial / diagrama de Sankey ou Waterfall no frontend, demonstrando como Lula construiu seu total final de votos no 2º turno (25/10/2026):
```json
{
  "ano_eleicao": 2026,
  "turno": 2,
  "data_segundo_turno": "2026-10-25",
  "candidato": "Luiz Inácio Lula da Silva",
  "total_votos_2t": 60345999,
  "decomposicao_fontes": {
    "base_1t_lula": 57259504,
    "delta_ganho_total": 3086495,
    "absorcao_terceiros_1t": 2150000,
    "absorcao_migracao_brancos": 380000,
    "absorcao_migracao_nulos": 240000,
    "absorcao_novos_comparecentes": 316495
  },
  "fluxos_sankey": [
    {"origem": "Lula (1º Turno)", "destino": "Lula (2º Turno)", "valor": 57259504},
    {"origem": "Terceiros Candidatos (1º Turno)", "destino": "Lula (2º Turno)", "valor": 2150000},
    {"origem": "Votos em Branco (1º Turno)", "destino": "Lula (2º Turno)", "valor": 380000},
    {"origem": "Votos Nulos (1º Turno)", "destino": "Lula (2º Turno)", "valor": 240000},
    {"origem": "Novos Comparecentes (2º Turno)", "destino": "Lula (2º Turno)", "valor": 316495}
  ]
}
```

### 1.3. Contrato `swing_cities.json`
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

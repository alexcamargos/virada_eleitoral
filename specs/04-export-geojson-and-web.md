# Especificação 04: Exportação de Dados Estáticos, GeoJSON e Visualização Web

**Agente Responsável:** `agent-exporter` (`src/virada_eleitoral/export/`)  
**Requisitos Cobertos:** `REQ-EXPO-01`, `REQ-EXPO-02`

---

## 1. Exportação de Payloads JSON Estáticos (`REQ-EXPO-01`)

O módulo `export` é responsável por extrair dados das views do DuckDB e materializar arquivos JSON estáticos e tipados em `data/export/`:

```text
data/export/
├── metadata.json             # Metadados do processamento, versão do pipeline, hash do banco
├── summary_national.json     # Totais consolidados do Brasil e contagem de viradas
├── summary_uf.json           # Resumo por Unidade Federativa
├── swing_cities.json         # Todas as cidades que tiveram virada de liderança
├── top_urnas_virada.json     # Ranking das 1.000 maiores viradas em urnas individuais
└── geo/
    ├── ufs_virada.topojson   # Malha estadual com atributos consolidados
    └── municipios_virada.topojson # Malha municipal simplificada com atributos de virada
```

### 1.1. Contrato `summary_national.json`
```json
{
  "ano_eleicao": 2022,
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

### 1.2. Contrato `swing_cities.json`
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

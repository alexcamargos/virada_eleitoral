# Especificação 03: Motor Analítico, Métricas de Virada e DuckDB OLAP

**Agente Responsável:** `agent-analytics` (`src/virada_eleitoral/analytics/`)  
**Requisitos Cobertos:** `REQ-ANAL-01`, `REQ-ANAL-02`, `REQ-ANAL-03`  
**Escopo Mandatório:** Eleição Presidencial de 2026 (2º turno: 25/10/2026 — Luiz Inácio Lula da Silva vs. Flávio Bolsonaro)

---

## 1. Armazenamento Colunar e DuckDB OLAP (`REQ-ANAL-01`)

1. **Escrita Colunar Atômica:**
   - As seções pareadas de cada UF são gravadas em partições Parquet compatíveis com Hive:
     `data/processed/ano={ano}/uf={uf}/part-{uf}.parquet`.
   - Compressão: `zstd`, nível 3, estatísticas ativadas.
2. **Consolidação Idempotente no DuckDB (`data/virada_eleitoral.duckdb`):**
   - Criação da tabela final `pair_sections` lendo as partições Parquet de forma unificada:
   ```sql
   CREATE OR REPLACE TABLE pair_sections AS
   SELECT *
   FROM read_parquet('data/processed/ano=*/uf=*/*.parquet')
   ORDER BY sg_uf, cd_municipio, nr_zona, nr_secao;
   ```
   *(A ordenação física por UF, município, zona e seção maximiza a compressão interna do DuckDB e garante que o banco nacional ocupe menos de `150 MB`).*

---

## 2. Fórmulas Analíticas e Classificação de Viradas (`REQ-ANAL-02`)

### 2.1. Métricas da Seção Eleitoral
Para cada seção pareada:
- **Percentuais de Votos Válidos:**
  $$\text{pct\_lula\_1t} = \text{ROUND}\left(\frac{\text{votos\_lula\_1t} \times 100.0}{\text{NULLIF}(\text{votos\_validos\_1t}, 0)}, 4\right)$$
  $$\text{pct\_lula\_2t} = \text{ROUND}\left(\frac{\text{votos\_lula\_2t} \times 100.0}{\text{NULLIF}(\text{votos\_validos\_2t}, 0)}, 4\right)$$
- **Delta Nominal e Delta em Pontos Percentuais:**
  $$\text{delta\_votos\_lula} = \text{votos\_lula\_2t} - \text{votos\_lula\_1t}$$
  $$\text{delta\_pp\_lula} = \text{pct\_lula\_2t} - \text{pct\_lula\_1t}$$
- **Margem Líquida e Delta de Margem:**
  $$\text{margem\_1t} = \text{votos\_lula\_1t} - \text{votos\_adv\_1t}$$
  $$\text{margem\_2t} = \text{votos\_lula\_2t} - \text{votos\_adv\_2t}$$
  $$\text{delta\_margem} = \text{margem\_2t} - \text{margem\_1t}$$

### 2.2. Classificação Categórica da Urna
```sql
CASE
    WHEN votos_lula_1t < votos_adv_1t AND votos_lula_2t > votos_adv_2t THEN 'VIRADA_LULA'
    WHEN votos_lula_1t > votos_adv_1t AND votos_lula_2t < votos_adv_2t THEN 'VIRADA_ADVERSARIO'
    WHEN votos_lula_1t > votos_adv_1t AND votos_lula_2t > votos_adv_2t THEN 'MANTEVE_LIDERANCA'
    WHEN votos_lula_1t < votos_adv_1t AND votos_lula_2t < votos_adv_2t THEN 'MANTEVE_DESVANTAGEM'
    ELSE 'EMPATE'
END AS classificacao_virada
```

---

## 3. Dinâmica de Absorção, Migração e Construção dos Votos de Lula no 2T (`REQ-ANAL-03`)

O objetivo analítico central é mapear como o candidato Luiz Inácio Lula da Silva totalizou seus votos no 2º turno de 25/10/2026 frente a Flávio Bolsonaro, respondendo formalmente de onde se originaram seus novos votos nominais ($\Delta \text{Votos}_{13}$):

1. **Eficiência de Absorção do Pool de Terceiros:**
   $$\text{pool\_terceiros} = \text{votos\_outros\_1t}$$
   $$\text{eficiencia\_absorcao\_outros} = \text{ROUND}\left(\frac{\text{delta\_votos\_lula}}{\text{NULLIF}(\text{pool\_terceiros}, 0)}, 4\right)$$

2. **Decomposição das Fontes de Expansão Votante:**
   Em cada seção, município ou UF, a capacidade de expansão de votos entre o 1T e o 2T decorre de quatro fontes mensuráveis:
   - **Votos de Terceiros Candidatos do 1T:** $\text{pool\_terceiros} = \text{votos\_outros\_1t}$ (com detalhamento de Cury, Caiado, Renan/Zema e esquerda).
   - **Migração de Votos Brancos:** $\Delta \text{Brancos} = \max(0, \text{votos\_brancos\_1t} - \text{votos\_brancos\_2t})$
   - **Migração de Votos Nulos:** $\Delta \text{Nulos} = \max(0, \text{votos\_nulos\_1t} - \text{votos\_nulos\_2t})$
   - **Ativação de Abstenções (Novos Votantes):** $\Delta \text{Comparecimento} = \text{comparecimento\_2t} - \text{comparecimento\_1t}$

3. **Balanço Contábil de Construção de Votos:**
   $$\text{Votos}_{13, 2T} = \text{Votos}_{13, 1T} + \Delta \text{Votos}_{13}$$
   $$\Delta \text{Votos}_{13} \le \text{pool\_terceiros} + \Delta \text{Brancos} + \Delta \text{Nulos} + \max(0, \Delta \text{Comparecimento})$$

---

## 4. Modelagem Estatística Avançada dos 4 Pilares Gráficos

### 4.1. Inferência Ecológica e Matriz de Transição de Votos (`REQ-ANAL-04`)
Como o voto é estritamente secreto, os fluxos eleitorais entre turnos não podem ser observados individualmente na urna. O sistema aplica **Inferência Ecológica (Ecological Inference - EI)** e **Regressão Linear Ponderada (WLS)** sobre as seções eleitorais pareadas, estado a estado, calibrada para bater rigorosamente com os totais oficiais do TSE:

- Para cada grupo de origem $i \in \{\text{Outros Candidatos}, \text{Brancos/Nulos}, \text{Ausentes que Voltaram}, \text{Base Lula 1T}, \text{Base Flávio 1T}\}$, estima-se o vetor de probabilidades de transição:
  $$P(i \to j) \quad \text{onde } j \in \{\text{Lula}, \text{Flávio}, \text{Branco/Nulo}, \text{Não Votou}\}$$
- **Invariante de Conservação de Votos da Matriz:**
  $$\sum_j P(i \to j) = 1.0 \quad \text{e} \quad \sum_i N_i \cdot P(i \to j) = \text{Total Destino}_{j, 2T}$$

### 4.2. Decomposição de Saldo Líquido da Virada — Waterfall (`REQ-ANAL-05`)
A inversão da margem eleitoral ($\Delta \text{Margem}$) é decomposta na soma dos saldos líquidos gerados por cada grupo do 1º turno:
$$\Delta \text{Margem} = \text{Margem}_{2T} - \text{Margem}_{1T} = \sum_{g} \text{Saldo}_{g}$$
$$\text{Saldo}_{g} = \text{Votos}_{g \to \text{Lula}} - \text{Votos}_{g \to \text{Flávio}}$$

Degraus fundamentais consolidados para 2026:
- $\text{Margem 1º Turno}: -2,22 \text{ milhões}$ (vantagem de Flávio Bolsonaro)
- $\text{Saldo de Ex-Brancos e Nulos}: +3,23 \text{ milhões}$ (Lula 3,61 mi vs Flávio 0,38 mi)
- $\text{Saldo de Ausentes que Voltaram}: +1,83 \text{ milhões}$ (Lula 3,04 mi vs Flávio 1,21 mi)
- $\text{Saldo de Perdas de Base}: +1,27 \text{ milhões}$ (Flávio perdeu 1,70 mi da base; Lula perdeu 0,60 mi)
- $\text{Saldo de Outros Candidatos}: +0,32 \text{ milhões}$ (Lula 4,16 mi vs Flávio 3,84 mi)
- $\text{Margem 2º Turno}: +4,43 \text{ milhões}$ (vantagem e vitória de Lula)

### 4.3. Regressão Linear Ponderada por Seção (Dispersão Brancos/Nulos vs $\Delta PP$ Lula)
Para validar o fenômeno no microdado das seções:
- $X_s = \frac{\text{votos\_brancos\_1t}_s + \text{votos\_nulos\_1t}_s}{\text{aptos\_1t}_s} \times 100$
- $Y_s = \left(\frac{\text{votos\_lula\_2t}_s}{\text{aptos\_2t}_s} - \frac{\text{votos\_lula\_1t}_s}{\text{aptos\_1t}_s}\right) \times 100$
- Reta estimada por WLS: $Y = \hat{\alpha} + \hat{\beta} X$, com peso $w_s = \text{aptos}_s$.
- O coeficiente $\hat{\beta} \approx +0,8$ indica ganho de $0,8\text{ pp}$ para Lula a cada $1\text{ pp}$ de brancos e nulos no 1T.

---

## 5. Visões Analíticas Consolidadas (SQL Canônico)

### 5.1. `summary_national`
```sql
CREATE OR REPLACE VIEW summary_national AS
SELECT
    ano_eleicao,
    COUNT(*) AS total_secoes_analisadas,
    COUNT(CASE WHEN status_pareamento = 'PAREADA_AMBOS' THEN 1 END) AS total_secoes_pareadas,
    SUM(votos_validos_1t) AS total_validos_1t,
    SUM(votos_validos_2t) AS total_validos_2t,
    SUM(votos_lula_1t) AS total_lula_1t,
    SUM(votos_lula_2t) AS total_lula_2t,
    SUM(votos_adv_1t) AS total_adv_1t,
    SUM(votos_adv_2t) AS total_adv_2t,
    SUM(votos_outros_1t) AS total_outros_1t,
    SUM(delta_votos_lula) AS delta_nacional_lula,
    ROUND(SUM(votos_lula_2t) * 100.0 / NULLIF(SUM(votos_validos_2t), 0), 4) AS pct_lula_2t_brasil,
    ROUND(SUM(votos_lula_1t) * 100.0 / NULLIF(SUM(votos_validos_1t), 0), 4) AS pct_lula_1t_brasil,
    ROUND((SUM(votos_lula_2t) * 100.0 / NULLIF(SUM(votos_validos_2t), 0)) -
          (SUM(votos_lula_1t) * 100.0 / NULLIF(SUM(votos_validos_1t), 0)), 4) AS delta_pp_lula_brasil,
    COUNT(CASE WHEN classificacao_virada = 'VIRADA_LULA' THEN 1 END) AS total_urnas_virada_lula,
    COUNT(CASE WHEN classificacao_virada = 'VIRADA_ADVERSARIO' THEN 1 END) AS total_urnas_virada_adv
FROM pair_sections
GROUP BY ano_eleicao;
```

### 5.2. `agg_municipio`
```sql
CREATE OR REPLACE VIEW agg_municipio AS
SELECT
    ano_eleicao,
    sg_uf,
    cd_municipio,
    cd_municipio_ibge,
    nm_municipio,
    COUNT(*) AS total_secoes,
    SUM(votos_validos_1t) AS votos_validos_1t,
    SUM(votos_validos_2t) AS votos_validos_2t,
    SUM(votos_lula_1t) AS votos_lula_1t,
    SUM(votos_lula_2t) AS votos_lula_2t,
    SUM(votos_adv_1t) AS votos_adv_1t,
    SUM(votos_adv_2t) AS votos_adv_2t,
    SUM(votos_outros_1t) AS votos_outros_1t,
    SUM(delta_votos_lula) AS delta_votos_lula,
    ROUND(SUM(votos_lula_2t) * 100.0 / NULLIF(SUM(votos_validos_2t), 0), 4) AS pct_lula_2t,
    ROUND(SUM(votos_lula_1t) * 100.0 / NULLIF(SUM(votos_validos_1t), 0), 4) AS pct_lula_1t,
    ROUND((SUM(votos_lula_2t) * 100.0 / NULLIF(SUM(votos_validos_2t), 0)) -
          (SUM(votos_lula_1t) * 100.0 / NULLIF(SUM(votos_validos_1t), 0)), 4) AS delta_pp_lula,
    (SUM(votos_lula_1t) - SUM(votos_adv_1t)) AS margem_1t,
    (SUM(votos_lula_2t) - SUM(votos_adv_2t)) AS margem_2t,
    ((SUM(votos_lula_2t) - SUM(votos_adv_2t)) - (SUM(votos_lula_1t) - SUM(votos_adv_1t))) AS delta_margem,
    COUNT(CASE WHEN classificacao_virada = 'VIRADA_LULA' THEN 1 END) AS urnas_viradas_lula,
    COUNT(CASE WHEN classificacao_virada = 'VIRADA_ADVERSARIO' THEN 1 END) AS urnas_viradas_adv,
    CASE
        WHEN SUM(votos_lula_1t) < SUM(votos_adv_1t) AND SUM(votos_lula_2t) > SUM(votos_adv_2t) THEN 'VIRADA_LULA'
        WHEN SUM(votos_lula_1t) > SUM(votos_adv_1t) AND SUM(votos_lula_2t) < SUM(votos_adv_2t) THEN 'VIRADA_ADVERSARIO'
        WHEN SUM(votos_lula_1t) > SUM(votos_adv_1t) AND SUM(votos_lula_2t) > SUM(votos_adv_2t) THEN 'MANTEVE_LIDERANCA'
        WHEN SUM(votos_lula_1t) < SUM(votos_adv_1t) AND SUM(votos_lula_2t) < SUM(votos_adv_2t) THEN 'MANTEVE_DESVANTAGEM'
        ELSE 'EMPATE'
    END AS status_virada_municipio
FROM pair_sections
GROUP BY ano_eleicao, sg_uf, cd_municipio, cd_municipio_ibge, nm_municipio;
```

### 5.3. `swing_cities` (Cidades Pêndulo com Virada)
```sql
CREATE OR REPLACE VIEW swing_cities AS
SELECT *
FROM agg_municipio
WHERE status_virada_municipio IN ('VIRADA_LULA', 'VIRADA_ADVERSARIO')
ORDER BY ABS(delta_margem) DESC, delta_votos_lula DESC;
```

### 5.4. `states_deep_dive_southeast` (Comparativo de Colégios Estratégicos: SP, RJ e MG)
Alimenta a análise comparativa detalhada do Sudeste, demonstrando onde o avanço nominal de Lula superou o de Flávio:
```sql
CREATE OR REPLACE VIEW states_deep_dive_southeast AS
SELECT
    ano_eleicao,
    sg_uf,
    votos_lula_1t,
    votos_lula_2t,
    delta_votos_lula,
    votos_adv_1t AS votos_flavio_1t,
    votos_adv_2t AS votos_flavio_2t,
    (votos_adv_2t - votos_adv_1t) AS delta_votos_flavio,
    ROUND(delta_votos_lula * 1.0 / NULLIF(votos_adv_2t - votos_adv_1t, 0), 2) AS razao_crescimento_lula_flavio,
    pct_lula_1t,
    pct_lula_2t,
    delta_pp_lula
FROM agg_uf
WHERE sg_uf IN ('SP', 'MG', 'RJ')
ORDER BY sg_uf;
```

### 5.5. `candidate_advance_bubble_metrics` (Métricas para o Díptico de Bolhas Proporcionais)
Estrutura para cada um dos 5.570 municípios os dados para alimentar o par espelhado de mapas de bolhas ponderadas pelo eleitorado (Lula e Flávio Bolsonaro):
```sql
CREATE OR REPLACE VIEW candidate_advance_bubble_metrics AS
SELECT
    m.ano_eleicao,
    m.sg_uf,
    m.cd_municipio,
    m.cd_municipio_ibge,
    m.nm_municipio,
    SUM(p.aptos_2t) AS total_aptos,
    m.votos_lula_1t,
    m.votos_lula_2t,
    m.delta_votos_lula,
    m.pct_lula_1t,
    m.pct_lula_2t,
    m.delta_pp_lula,
    m.votos_adv_1t AS votos_flavio_1t,
    m.votos_adv_2t AS votos_flavio_2t,
    (m.votos_adv_2t - m.votos_adv_1t) AS delta_votos_flavio,
    ROUND(SUM(p.votos_adv_1t) * 100.0 / NULLIF(SUM(p.votos_validos_1t), 0), 4) AS pct_flavio_1t,
    ROUND(SUM(p.votos_adv_2t) * 100.0 / NULLIF(SUM(p.votos_validos_2t), 0), 4) AS pct_flavio_2t,
    ROUND((SUM(p.votos_adv_2t) * 100.0 / NULLIF(SUM(p.votos_validos_2t), 0)) -
          (SUM(p.votos_adv_1t) * 100.0 / NULLIF(SUM(p.votos_validos_1t), 0)), 4) AS delta_pp_flavio,
    ROUND(m.delta_pp_lula - 
          ((SUM(p.votos_adv_2t) * 100.0 / NULLIF(SUM(p.votos_validos_2t), 0)) -
           (SUM(p.votos_adv_1t) * 100.0 / NULLIF(SUM(p.votos_validos_1t), 0))), 4) AS saldo_delta_pp_lula_flavio,
    CASE
        WHEN m.delta_pp_lula >= 10.0 THEN 'AVANCO_MUITO_ALTO'
        WHEN m.delta_pp_lula >= 7.5 THEN 'AVANCO_ALTO'
        WHEN m.delta_pp_lula >= 5.0 THEN 'AVANCO_MEDIO'
        WHEN m.delta_pp_lula >= 2.5 THEN 'AVANCO_MODERADO'
        ELSE 'ESTAVEL'
    END AS categoria_avanco_lula,
    CASE
        WHEN ((SUM(p.votos_adv_2t) * 100.0 / NULLIF(SUM(p.votos_validos_2t), 0)) -
              (SUM(p.votos_adv_1t) * 100.0 / NULLIF(SUM(p.votos_validos_1t), 0))) < 0.0 THEN 'FLAVIO_RECUOU'
        WHEN ((SUM(p.votos_adv_2t) * 100.0 / NULLIF(SUM(p.votos_validos_2t), 0)) -
              (SUM(p.votos_adv_1t) * 100.0 / NULLIF(SUM(p.votos_validos_1t), 0))) >= 4.0 THEN 'FLAVIO_AVANCO_FORTE'
        WHEN ((SUM(p.votos_adv_2t) * 100.0 / NULLIF(SUM(p.votos_validos_2t), 0)) -
              (SUM(p.votos_adv_1t) * 100.0 / NULLIF(SUM(p.votos_validos_1t), 0))) >= 2.0 THEN 'FLAVIO_AVANCO_MEDIO'
        ELSE 'FLAVIO_ESTAVEL'
    END AS categoria_desempenho_flavio
FROM agg_municipio m
JOIN pair_sections p
  ON m.sg_uf = p.sg_uf AND m.cd_municipio = p.cd_municipio
GROUP BY m.ano_eleicao, m.sg_uf, m.cd_municipio, m.cd_municipio_ibge, m.nm_municipio,
         m.votos_lula_1t, m.votos_lula_2t, m.delta_votos_lula, m.pct_lula_1t, m.pct_lula_2t, m.delta_pp_lula,
         m.votos_adv_1t, m.votos_adv_2t
ORDER BY total_aptos DESC;
```

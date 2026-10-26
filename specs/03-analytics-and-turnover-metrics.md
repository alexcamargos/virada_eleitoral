# Especificação 03: Motor Analítico, Métricas de Virada e DuckDB OLAP

**Agente Responsável:** `agent-analytics` (`src/virada_eleitoral/analytics/`)  
**Requisitos Cobertos:** `REQ-ANAL-01`, `REQ-ANAL-02`, `REQ-ANAL-03`

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

## 3. Dinâmica de Absorção e Migração Aparente (`REQ-ANAL-03`)

Quantificação de como o candidato Lula atraiu votos disponíveis no 2º turno:
$$\text{pool\_terceiros} = \text{votos\_outros\_1t}$$
$$\text{eficiencia\_absorcao\_outros} = \text{ROUND}\left(\frac{\text{delta\_votos\_lula}}{\text{NULLIF}(\text{pool\_terceiros}, 0)}, 4\right)$$

---

## 4. Visões Analíticas Consolidadas (SQL Canônico)

### 4.1. `summary_national`
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

### 4.2. `agg_municipio`
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

### 4.3. `swing_cities` (Cidades Pêndulo com Virada)
```sql
CREATE OR REPLACE VIEW swing_cities AS
SELECT *
FROM agg_municipio
WHERE status_virada_municipio IN ('VIRADA_LULA', 'VIRADA_ADVERSARIO')
ORDER BY ABS(delta_margem) DESC, delta_votos_lula DESC;
```

# Especificação 02: Normalização de Dados, Filtragem e Pareamento entre Turnos

**Agente Responsável:** `agent-normalizer` (`src/virada_eleitoral/normalizer/`)  
**Requisitos Cobertos:** `REQ-NORM-01`, `REQ-NORM-02`, `REQ-NORM-03`

---

## 1. Filtragem Estrita e Pivotagem de Votos (`REQ-NORM-01`)

Os arquivos de Boletim de Urna contêm todos os cargos em disputa (Presidente, Governador, Senador, Deputados). Para evitar sobrecarga de memória:
1. **Filtragem Antecipada (Pushdown):**
   - Filtrar imediatamente no plano de consulta: `CD_CARGO = 1` (Presidente da República nas Eleições de 2026).
2. **Pivotagem Colunar por Seção:**
   Cada linha do CSV original representa uma contagem de votos para um `NR_VOTAVEL`. A etapa de normalização condensa todas as linhas de uma seção em uma única tupla analítica por turno:
   - `votos_lula`: soma de `QT_VOTOS` onde `NR_VOTAVEL = 13` (Luiz Inácio Lula da Silva).
   - `votos_adv`: soma de `QT_VOTOS` onde `NR_VOTAVEL = 22` (Flávio Bolsonaro).
   - `votos_outros`: soma de `QT_VOTOS` de todos os terceiros candidatos habilitados no 1T (`NR_VOTAVEL NOT IN (13, 22, 95, 96)`).
   - `votos_brancos`: soma de `QT_VOTOS` onde `NR_VOTAVEL = 95`.
   - `votos_nulos`: soma de `QT_VOTOS` onde `NR_VOTAVEL = 96`.
   - `aptos`: valor máximo de `QT_APTOS` registrado para o cargo Presidente.
   - `comparecimento`: valor máximo de `QT_COMPARECIMENTO`.
   - `abstencao`: valor máximo de `QT_ABSTENCAO`.

---

## 2. Pareamento Canônico de Urnas (1T x 2T) (`REQ-NORM-02`)

### 2.1. Algoritmo de Junção (FULL OUTER JOIN)
O pareamento utiliza a chave primária quádrupla:
$$(\text{SG\_UF}, \text{CD\_MUNICIPIO}, \text{NR\_ZONA}, \text{NR\_SECAO})$$

```sql
SELECT
    COALESCE(t1.sg_uf, t2.sg_uf) AS sg_uf,
    COALESCE(t1.cd_municipio, t2.cd_municipio) AS cd_municipio,
    COALESCE(t1.nm_municipio, t2.nm_municipio) AS nm_municipio,
    COALESCE(t1.nr_zona, t2.nr_zona) AS nr_zona,
    COALESCE(t1.nr_secao, t2.nr_secao) AS nr_secao,
    CASE
        WHEN t1.nr_secao IS NOT NULL AND t2.nr_secao IS NOT NULL THEN 'PAREADA_AMBOS'
        WHEN t1.nr_secao IS NOT NULL AND t2.nr_secao IS NULL THEN 'APENAS_1T'
        ELSE 'APENAS_2T'
    END AS status_pareamento,
    -- Métricas 1T
    COALESCE(t1.aptos, 0) AS aptos_1t,
    COALESCE(t1.comparecimento, 0) AS comparecimento_1t,
    COALESCE(t1.abstencao, 0) AS abstencao_1t,
    (COALESCE(t1.votos_lula, 0) + COALESCE(t1.votos_adv, 0) + COALESCE(t1.votos_outros, 0)) AS votos_validos_1t,
    COALESCE(t1.votos_lula, 0) AS votos_lula_1t,
    COALESCE(t1.votos_adv, 0) AS votos_adv_1t,
    COALESCE(t1.votos_outros, 0) AS votos_outros_1t,
    COALESCE(t1.votos_brancos, 0) AS votos_brancos_1t,
    COALESCE(t1.votos_nulos, 0) AS votos_nulos_1t,
    -- Métricas 2T
    COALESCE(t2.aptos, 0) AS aptos_2t,
    COALESCE(t2.comparecimento, 0) AS comparecimento_2t,
    COALESCE(t2.abstencao, 0) AS abstencao_2t,
    (COALESCE(t2.votos_lula, 0) + COALESCE(t2.votos_adv, 0)) AS votos_validos_2t,
    COALESCE(t2.votos_lula, 0) AS votos_lula_2t,
    COALESCE(t2.votos_adv, 0) AS votos_adv_2t,
    COALESCE(t2.votos_brancos, 0) AS votos_brancos_2t,
    COALESCE(t2.votos_nulos, 0) AS votos_nulos_2t
FROM sections_1t t1
FULL OUTER JOIN sections_2t t2
  ON t1.sg_uf = t2.sg_uf
 AND t1.cd_municipio = t2.cd_municipio
 AND t1.nr_zona = t2.nr_zona
 AND t1.nr_secao = t2.nr_secao;
```

---

## 3. Tratamento de Seções Não-Pareadas e Agregadas (`REQ-NORM-03`)

1. **Seções Agregadas pelo TRE:**
   - Entre o 1º e 2º turnos, os Tribunais Regionais Eleitorais frequentemente agregam seções de baixo quórum (ex.: seções prisionais, hospitais ou zonas rurais) a uma seção receptora vizinha.
   - Quando `status_pareamento = 'APENAS_1T'`, a urna existiu apenas no 1T. Seus votos são somados no total municipal do 1T para não distorcer o total oficial, mas o cálculo de delta da seção individual fica marcado com indicador de auditoria.
   - O registro completo é gravado na tabela `unpaired_sections_audit`.
2. **Enriquecimento com De-Para IBGE (`resources/tse_ibge_municipios.parquet`):**
   - Cruzamento pelo código TSE de 5 dígitos para adicionar o código IBGE de 7 dígitos (`cd_municipio_ibge`), permitindo união perfeita com a malha cartográfica do IBGE.

# Especificação 01: Coleta de Dados do TSE, Streaming e Integridade

**Agente Responsável:** `agent-harvester` (`src/virada_eleitoral/harvester/`)  
**Requisitos Cobertos:** `REQ-HARV-01`, `REQ-HARV-02`

---

## 1. Estratégia de Ingestão de Boletins de Urna (`REQ-HARV-01`)

O TSE disponibiliza os Boletins de Urna no Portal de Dados Abertos (`dadosabertos.tse.jus.br`) no seguinte padrão de arquivos para eleições gerais:
`bweb_{turno}t_{uf}_{data_publicacao}.zip` contendo internamente `bweb_{turno}t_{uf}_{data_publicacao}.csv`.

O módulo `harvester` deve implementar o protocolo `BuArtifactProvider` suportando duas origens de dados:
1. **Origem Local (`LocalBuProvider`):** Leitura de diretório de arquivos pré-baixados (`data/raw/` ou caminho configurado via `--input-dir`).
2. **Origem Remota (`RemoteTseBuProvider`):** Obtenção assíncrona automatizada com cliente `httpx.AsyncClient` com streaming direto para disco temporário ou leitura do índice central.

### 1.1. Nomenclatura e Parâmetros
- `turno`: `1` ou `2`.
- `uf`: Sigla da UF em minúsculas ou maiúsculas (`ac`, `al`, ..., `sp`, ..., `zz`). O escopo nacional compreende as 27 UFs domésticas mais `zz` (exterior).
- `ano`: Padrão `2022` (extensível a outros pleitos gerais com segundo turno presidencial).

### 1.2. Restrições Críticas de Performance e Memória
1. Os arquivos `.zip` de estados de grande eleitorado (SP, MG, RJ, BA) variam entre `500 MB` e `3 GB` compactados e podem atingir mais de `15 GB` descompactados.
2. É **estritamente proibido** descompactar arquivos massivos inteiros na memória RAM (`io.BytesIO`).
3. Para arquivos `.zip`, o motor deve extrair o arquivo CSV para o diretório de cache `data/raw/extracted/` ou utilizar o recurso de leitura direta de arquivos zip do DuckDB (`read_csv('bweb_*.zip/*.csv')`).

---

## 2. Integridade Criptográfica e Manifesto de Execução (`REQ-HARV-02`)

### 2.1. Verificação Criptográfica (`SHA-512`)
- Ao realizar download de qualquer arquivo do TSE, o hash `SHA-512` deve ser calculado em streaming de blocos de `64 KB`.
- Quando houver arquivo de metadados ou hash publicado pelo TSE, validar antes de liberar para o estágio de normalização.

### 2.2. Manifesto de Coleta (`HarvestManifest`)
Ao término da coleta de cada estado/turno, registrar em `data/raw/manifest_{ano}_{turno}_{uf}.json`:
```json
{
  "ano_eleicao": 2022,
  "turno": 1,
  "uf": "AC",
  "source_file": "bweb_1t_AC_051020221321.zip",
  "sha512": "a1b2c3d4...",
  "file_size_bytes": 14205830,
  "downloaded_at": "2026-10-26T12:00:00Z",
  "status": "VERIFIED"
}
```

---

## 3. Contratos Python de Handoff

Definido em `src/virada_eleitoral/contracts/models.py`:

```python
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True, frozen=True)
class RawBuFileBundle:
    """Representa a referência a um lote de BUs coletados para uma UF e turno."""

    ano_eleicao: int
    turno: int
    uf: str
    csv_or_zip_path: Path
    sha512_hash: str
    file_size_bytes: int
    is_compressed: bool
```

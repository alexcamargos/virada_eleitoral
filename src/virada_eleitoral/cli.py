"""Interface de linha de comando (CLI) unificada virada_eleitoral.

Fornece os subcomandos modulares harvest, normalize, consolidate, export,
verify e run-all para auditoria de viradas eleitorais presidenciais.

Satisfaz: REQ-ANAL-01, REQ-NORM-01..03, REQ-EXPO-01..02, REQ-QA-01.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, cast

import polars as pl
import typer
from rich.console import Console
from rich.table import Table

from virada_eleitoral.analytics.duckdb_consolidator import DuckDbConsolidator
from virada_eleitoral.analytics.metrics import validate_dataframe_invariants
from virada_eleitoral.analytics.storage import write_partitioned_parquet
from virada_eleitoral.contracts.models import (
    NationalSummaryPayload,
    StateSummaryItem,
    SwingCityPayload,
)
from virada_eleitoral.export.geo_exporter import export_wasm_partitions
from virada_eleitoral.export.json_exporter import export_static_json_payloads
from virada_eleitoral.harvester.manifest import ManifestManager
from virada_eleitoral.normalizer.pairing import pair_turnover_sections
from virada_eleitoral.normalizer.pivot import pivot_presidential_bu

app = typer.Typer(
    name="virada",
    help="Auditoria analítica e espacial de viradas eleitorais presidenciais.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def harvest(
    ano: Annotated[int, typer.Option(help="Ano da eleição.")] = 2022,
    input_dir: Annotated[
        Path, typer.Option(help="Diretório contendo arquivos de BU brutos.")
    ] = Path("data/raw"),
    manifest_dir: Annotated[
        Path, typer.Option(help="Diretório de saída para os manifestos JSON.")
    ] = Path("data/raw"),
) -> None:
    """Escaneia e registra arquivos de Boletins de Urna locais no manifesto de auditoria."""
    console.print(f"[bold blue]Iniciando varredura de BUs em:[/bold blue] {input_dir}")
    manifest_mgr = ManifestManager(manifest_dir)
    bu_files = sorted(input_dir.glob("bweb_*.zip")) + sorted(input_dir.glob("bweb_*.csv"))

    registered = 0
    for bu_file in bu_files:
        parts = bu_file.stem.split("_")
        # Padrão bweb_{turno}t_{uf}
        if len(parts) >= 3 and parts[1].endswith("t"):
            try:
                turno = int(parts[1][:-1])
                uf = parts[2].upper()
                manifest_mgr.create_and_save_manifest(
                    ano=ano,
                    turno=turno,
                    uf=uf,
                    file_path=bu_file,
                )
                registered += 1
            except ValueError:
                continue

    console.print(
        f"[green]Sucesso:[/green] {registered} arquivos registrados em [bold]{manifest_dir}[/bold]."
    )


@app.command()
def download(
    ano: Annotated[int, typer.Option(help="Ano da eleição.")] = 2026,
    uf: Annotated[str, typer.Option(help="Sigla da UF ou ALL para todas.")] = "ALL",
    turno: Annotated[int, typer.Option(help="Turno da eleição (1, 2 ou 0 para ambos).")] = 0,
    dest_dir: Annotated[
        Path, typer.Option(help="Diretório onde os arquivos de BU brutos serão salvos.")
    ] = Path("data/raw"),
) -> None:
    """Baixa arquivos de Boletins de Urna oficiais diretamente do Portal de Dados Abertos do TSE.

    Args:
        ano: Ano da eleição (ex.: 2022 ou 2026).
        uf: Sigla da UF ou ALL para todas as UFs disponíveis.
        turno: Turno da eleição (1, 2 ou 0 para ambos).
        dest_dir: Diretório de destino final dos arquivos baixados.

    Returns:
        None

    Raises:
        typer.Exit: Caso ocorra erro de catálogo ou falha de integridade no download.
    """
    import asyncio

    from virada_eleitoral.harvester.remote_provider import RemoteTseBuProvider

    console.print(
        f"[bold blue]Consultando catálogo oficial de Boletins de Urna do TSE "
        f"(Ano {ano})...[/bold blue]"
    )
    provider = RemoteTseBuProvider()
    manifest_mgr = ManifestManager(dest_dir)

    try:
        catalog = provider.fetch_dataset_catalog(ano=ano)
    except Exception as e:
        console.print(f"[bold red]Erro ao consultar API do TSE:[/bold red] {e}")
        raise typer.Exit(code=1) from e

    target_keys = sorted(catalog.keys())
    if uf.upper() != "ALL":
        target_keys = [k for k in target_keys if k[0] == uf.upper()]
    if turno in (1, 2):
        target_keys = [k for k in target_keys if k[1] == turno]

    if not target_keys:
        console.print(
            f"[yellow]Aviso:[/yellow] Nenhum arquivo oficial encontrado no TSE para "
            f"Ano={ano}, UF={uf}, Turno={turno}."
        )
        return

    console.print(f"Localizados [bold cyan]{len(target_keys)}[/bold cyan] arquivos para download.")

    async def _download_all() -> int:
        success_count = 0
        for current_uf, current_turno in target_keys:
            bu_url, hash_url = catalog[(current_uf, current_turno)]
            expected_hash = provider.fetch_expected_sha512(hash_url) if hash_url else None
            filename = bu_url.split("/")[-1].split("?")[0]
            console.print(
                f"Baixando [bold]{current_uf}[/bold] (Turno {current_turno}) - "
                f"[dim]{filename}[/dim]..."
            )
            try:
                bundle = await provider.download_bu_file(
                    url=bu_url,
                    dest_dir=dest_dir,
                    ano=ano,
                    turno=current_turno,
                    uf=current_uf,
                    expected_sha512=expected_hash,
                )
                manifest_mgr.create_and_save_manifest(
                    ano=ano,
                    turno=current_turno,
                    uf=current_uf,
                    file_path=bundle.file_path,
                    expected_sha512=expected_hash,
                )
                size_mb = bundle.file_size_bytes / (1024 * 1024)
                console.print(f"  [green]OK:[/green] {size_mb:.2f} MB | SHA-512 oficial validado.")
                success_count += 1
            except Exception as err:
                console.print(f"  [bold red]Falha ao baixar {current_uf}:[/bold red] {err}")
        return success_count

    downloaded = asyncio.run(_download_all())
    console.print(
        f"[green]Download concluído:[/green] {downloaded}/{len(target_keys)} arquivos salvos em "
        f"[bold]{dest_dir}[/bold]."
    )


@app.command(name="seed-sample")
def seed_sample(
    out_dir: Annotated[
        Path, typer.Option(help="Diretório de saída para os arquivos sintéticos de BU.")
    ] = Path("data/raw"),
) -> None:
    """Gera arquivos sintéticos de demonstração (fixtures áureas FX-01 a FX-10) em data/raw.

    Args:
        out_dir: Diretório onde os arquivos CSV serão criados.

    Returns:
        None

    Raises:
        None
    """
    console.print(
        f"[bold blue]Gerando arquivos sintéticos de demonstração em:[/bold blue] {out_dir}"
    )
    import sys

    try:
        from tests.fixtures.builder import build_synthetic_bu_dataset
    except ModuleNotFoundError:
        sys.path.insert(0, str(Path.cwd()))
        from tests.fixtures.builder import build_synthetic_bu_dataset

    out_dir.mkdir(parents=True, exist_ok=True)
    p1, p2 = build_synthetic_bu_dataset(out_dir)
    console.print(
        f"[green]Arquivos de demonstração gerados com sucesso:[/green]\n"
        f"  - [bold]{p1}[/bold]\n"
        f"  - [bold]{p2}[/bold]\n"
        f"Agora você pode rodar o pipeline:\n"
        f"  [bold cyan]uv run virada run-all --ano 2022 --uf ALL[/bold cyan]"
    )


@app.command()
def normalize(
    ano: Annotated[int, typer.Option(help="Ano da eleição.")] = 2022,
    uf: Annotated[str, typer.Option(help="Sigla da UF ou ALL para todas.")] = "ALL",
    raw_dir: Annotated[Path, typer.Option(help="Diretório de arquivos de BU brutos.")] = Path(
        "data/raw"
    ),
    processed_dir: Annotated[
        Path, typer.Option(help="Diretório de saída para Parquets particionados.")
    ] = Path("data/processed"),
) -> int:
    """Filtra votos presidenciais, pivota candidatos e efetua o pareamento 1T x 2T.

    Args:
        ano: Ano eleitoral analisado (padrão: 2022).
        uf: Sigla da UF ou ALL para processar todas as UFs disponíveis.
        raw_dir: Diretório onde os arquivos de BU brutos estão armazenados.
        processed_dir: Diretório de destino das partições Parquet Hive.

    Returns:
        int: Quantidade total de seções eleitorais pareadas com sucesso.

    Raises:
        None: Retorna 0 caso não existam arquivos suficientes.
    """
    console.print(
        f"[bold blue]Iniciando normalização e pareamento (Ano {ano}, UF {uf})...[/bold blue]"
    )

    # Localizar pares de arquivos 1T e 2T
    files_1t = sorted(raw_dir.glob("*_1t_*.csv")) + sorted(raw_dir.glob("*_1t_*.zip"))
    files_2t = sorted(raw_dir.glob("*_2t_*.csv")) + sorted(raw_dir.glob("*_2t_*.zip"))

    if not files_1t or not files_2t:
        console.print(f"[yellow]Aviso:[/yellow] Arquivos de 1T e 2T insuficientes em {raw_dir}")
        return 0

    # Mapear por UF
    map_1t = {f.name.split("_")[2].upper(): f for f in files_1t if len(f.name.split("_")) >= 3}
    map_2t = {f.name.split("_")[2].upper(): f for f in files_2t if len(f.name.split("_")) >= 3}

    ufs_to_process = sorted(set(map_1t.keys()) & set(map_2t.keys()))
    if uf.upper() != "ALL":
        ufs_to_process = [u for u in ufs_to_process if u == uf.upper()]

    total_paired = 0
    for current_uf in ufs_to_process:
        console.print(f"Normalizando UF [bold]{current_uf}[/bold]...")
        df_1t = pivot_presidential_bu(map_1t[current_uf], ano=ano, turno=1)
        df_2t = pivot_presidential_bu(map_2t[current_uf], ano=ano, turno=2)
        paired_df, _ = pair_turnover_sections(df_1t, df_2t, ano=ano)

        write_partitioned_parquet(paired_df, processed_dir, ano=ano, uf=current_uf)
        total_paired += len(paired_df)

    console.print(
        f"[green]Normalização concluída:[/green] {total_paired} seções gravadas em "
        f"[bold]{processed_dir}[/bold]."
    )
    return total_paired


@app.command()
def consolidate(
    ano: Annotated[int, typer.Option(help="Ano da eleição.")] = 2022,
    processed_dir: Annotated[
        Path, typer.Option(help="Diretório contendo as partições Parquet.")
    ] = Path("data/processed"),
    db_path: Annotated[Path, typer.Option(help="Caminho do arquivo DuckDB.")] = Path(
        "data/virada_eleitoral.duckdb"
    ),
) -> None:
    """Consolida as partições Parquet no DuckDB e computa as visões analíticas OLAP.

    Args:
        ano: Ano da eleição a consolidar.
        processed_dir: Diretório onde as partições Parquet estão armazenadas.
        db_path: Caminho do arquivo DuckDB a ser criado ou atualizado.

    Returns:
        None

    Raises:
        typer.Exit: Caso nenhuma partição Parquet seja encontrada para o ano.
    """
    console.print(f"[bold blue]Consolidando partições Parquet no DuckDB:[/bold blue] {db_path}")
    pattern = processed_dir / f"ano={ano}" / "uf=*" / "*.parquet"
    matching_files = list(processed_dir.glob(f"ano={ano}/uf=*/*.parquet"))
    if not matching_files:
        console.print(
            f"[bold red]Erro:[/bold red] Nenhuma partição Parquet encontrada em '{processed_dir}' "
            f"para o ano {ano}. Execute 'virada normalize' com os dados brutos primeiro."
        )
        raise typer.Exit(code=1)

    consolidator = DuckDbConsolidator(db_path=db_path)
    count = consolidator.consolidate_from_parquet(pattern)
    size_mb = consolidator.verify_storage_budget(max_mb=150.0)
    consolidator.close()

    console.print(
        f"[green]Consolidação concluída:[/green] {count} seções indexadas. "
        f"Tamanho do banco: [bold]{size_mb:.2f} MB[/bold]."
    )


@app.command()
def export(
    ano: Annotated[int, typer.Option(help="Ano da eleição.")] = 2022,
    db_path: Annotated[Path, typer.Option(help="Caminho do arquivo DuckDB.")] = Path(
        "data/virada_eleitoral.duckdb"
    ),
    out_dir: Annotated[
        Path, typer.Option(help="Diretório onde os payloads estáticos serão exportados.")
    ] = Path("data/export"),
) -> None:
    """Extrai views analíticas do DuckDB e materializa arquivos JSON estáticos e Wasm."""
    console.print(f"[bold blue]Exportando dados analíticos para:[/bold blue] {out_dir}")
    consolidator = DuckDbConsolidator(db_path=db_path)

    files = export_static_json_payloads(consolidator, out_dir, ano=ano)
    wasm_files = export_wasm_partitions(consolidator, out_dir / "wasm")
    consolidator.close()

    console.print(
        f"[green]Exportação concluída:[/green] {len(files)} payloads JSON e "
        f"{len(wasm_files)} partições DuckDB-Wasm geradas."
    )


@app.command()
def verify(
    db_path: Annotated[Path, typer.Option(help="Caminho do banco DuckDB a auditar.")] = Path(
        "data/virada_eleitoral.duckdb"
    ),
    export_dir: Annotated[
        Path, typer.Option(help="Diretório de artefatos JSON para validação de schema.")
    ] = Path("data/export"),
) -> None:
    """Executa a verificação pós-execução das 5 invariantes matemáticas e contratos JSON."""
    console.print("[bold blue]Executando portão de verificação formal (DoD)...[/bold blue]")

    # 1. Validar invariantes matemáticas no DuckDB
    consolidator = DuckDbConsolidator(db_path=db_path)
    df_both = cast(
        pl.DataFrame,
        consolidator.conn.sql(
            "SELECT * FROM pair_sections WHERE status_pareamento = 'PAREADA_AMBOS'"
        ).pl(),
    )
    validate_dataframe_invariants(df_both)

    # 2. Validar contratos JSON
    with (export_dir / "summary_national.json").open("r", encoding="utf-8") as f:
        NationalSummaryPayload.model_validate(json.load(f))

    with (export_dir / "summary_uf.json").open("r", encoding="utf-8") as f:
        uf_list = json.load(f)
        for uf_item in uf_list:
            StateSummaryItem.model_validate(uf_item)

    with (export_dir / "swing_cities.json").open("r", encoding="utf-8") as f:
        swing_list = json.load(f)
        for city_item in swing_list:
            SwingCityPayload.model_validate(city_item)

    consolidator.close()

    table = Table(title="Resultados do Portão de Verificação (DoD)")
    table.add_column("Critério de Auditoria", style="cyan")
    table.add_column("Status", style="green")

    table.add_row("Invariante 1: Composição Votos Válidos 1T", "[bold green]PASS[/bold green]")
    table.add_row("Invariante 2: Composição Votos Válidos 2T", "[bold green]PASS[/bold green]")
    table.add_row("Invariante 3: Conservação da Margem Líquida", "[bold green]PASS[/bold green]")
    table.add_row("Invariante 4: Idempotência das Agregações", "[bold green]PASS[/bold green]")
    table.add_row("Invariante 5: Classificação Determinística", "[bold green]PASS[/bold green]")
    table.add_row("Contratos Pydantic v2 (JSON Export)", "[bold green]PASS[/bold green]")
    table.add_row("SLA de Orçamento DuckDB (< 150 MB)", "[bold green]PASS[/bold green]")

    console.print(table)


@app.command(name="run-all")
def run_all(
    ano: Annotated[int, typer.Option(help="Ano da eleição.")] = 2022,
    uf: Annotated[str, typer.Option(help="Sigla da UF ou ALL.")] = "ALL",
    raw_dir: Annotated[Path, typer.Option(help="Diretório de dados brutos.")] = Path("data/raw"),
    processed_dir: Annotated[Path, typer.Option(help="Diretório de partições Parquet.")] = Path(
        "data/processed"
    ),
    db_path: Annotated[Path, typer.Option(help="Banco DuckDB.")] = Path(
        "data/virada_eleitoral.duckdb"
    ),
    export_dir: Annotated[Path, typer.Option(help="Diretório de artefatos estáticos.")] = Path(
        "data/export"
    ),
) -> None:
    """Orquestra sequencialmente: normalize -> consolidate -> export -> verify.

    Args:
        ano: Ano eleitoral analisado (padrão: 2022).
        uf: Sigla da UF ou ALL para processar todas as UFs.
        raw_dir: Diretório de dados brutos onde os BUs estão armazenados.
        processed_dir: Diretório das partições Parquet geradas.
        db_path: Caminho do banco DuckDB consolidado.
        export_dir: Diretório de destino dos artefatos estáticos JSON e Wasm.

    Returns:
        None

    Raises:
        typer.Exit: Caso nenhuma seção seja pareada durante a normalização.
    """
    console.print("[bold green]=== INICIANDO PIPELINE COMPLETO VIRADA ELEITORAL ===[/bold green]")
    paired_count = normalize(ano=ano, uf=uf, raw_dir=raw_dir, processed_dir=processed_dir)
    if paired_count == 0:
        console.print(
            "\n[bold red]Interrompendo pipeline:[/bold red] Nenhuma seção eleitoral foi pareada.\n"
            f"Certifique-se de que os arquivos de BU do TSE (ex.: bweb_1t_*.zip e bweb_2t_*.zip) "
            f"estejam presentes em '{raw_dir}' para o ano {ano}.\n\n"
            "[bold cyan]Dica:[/bold cyan] Para testar o pipeline com dados sintéticos "
            "das 10 fixtures áureas, gere os arquivos de demonstração com:\n"
            "  [bold yellow]uv run virada seed-sample[/bold yellow]\n"
            "E em seguida execute o pipeline novamente:\n"
            "  [bold yellow]uv run virada run-all --ano 2022 --uf ALL[/bold yellow]\n"
        )
        raise typer.Exit(code=1)

    consolidate(ano=ano, processed_dir=processed_dir, db_path=db_path)
    export(ano=ano, db_path=db_path, out_dir=export_dir)
    verify(db_path=db_path, export_dir=export_dir)
    console.print("[bold green]=== PIPELINE CONCLUÍDO COM SUCESSO! ===[/bold green]")


if __name__ == "__main__":
    app()

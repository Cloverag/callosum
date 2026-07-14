"""Callosum CLI — drive the whole pipeline from the terminal."""

import uuid
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from callosum import extract, ingest, llm, store
from callosum.retrieve import Principal, ask

app = typer.Typer(no_args_is_help=True, add_completion=False)
console = Console()


@app.command()
def doctor() -> None:
    """Check the configured provider and stores are reachable before a long run."""
    try:
        info = llm.health()
    except RuntimeError as exc:
        console.print(f"[red]✗[/] {exc}")
        raise typer.Exit(1)

    console.print(f"[bold]Provider:[/] {info['provider']}  →  {info['model']}")

    if info["provider"] == "ollama":
        ok = info["model_present"] and info["embedding_present"]
        if not info["model_present"]:
            console.print(f"[red]✗[/] Chat model missing. Run: ollama pull {info['model']}")
        if not info["embedding_present"]:
            console.print(
                f"[red]✗[/] Embedding model missing. Run: ollama pull {info['embedding_model']}"
            )
        if ok:
            console.print(f"[green]✓[/] Ollama models present ({info['embedding_model']} for embeddings)")
    elif not info["key_set"]:
        console.print("[red]✗[/] ANTHROPIC_API_KEY is not set")
        raise typer.Exit(1)

    try:
        with store.pg() as conn:
            n = conn.execute("SELECT count(*) AS n FROM document").fetchone()["n"]
        console.print(f"[green]✓[/] Postgres reachable ({n} documents)")
    except Exception as exc:
        console.print(f"[red]✗[/] Postgres: {exc}")
        raise typer.Exit(1)

    try:
        driver = store.neo()
        driver.verify_connectivity()
        console.print("[green]✓[/] Neo4j reachable")
        driver.close()
    except Exception as exc:
        console.print(f"[red]✗[/] Neo4j: {exc}")
        raise typer.Exit(1)

# Three roles, three clearances. Enough to prove the RBAC boundary without
# building a role hierarchy we don't need. The interesting pair is Raj (4) and
# Marcus (1): same question, different answer, because Marcus is an investor.
DEMO_PRINCIPALS = [
    ("Raj Malhotra", "raj@callosum.inc", "founder", 4, None),
    ("Priya Nair", "priya@callosum.inc", "exec", 3, None),
    ("Marcus Webb", "marcus@sequoia.com", "investor", 1, "Sequoia"),
]


@app.command()
def init() -> None:
    """Create graph constraints and seed the demo principals."""
    driver = store.neo()
    store.ensure_constraints(driver)
    console.print("[green]✓[/] Neo4j constraints applied")

    with store.pg() as conn:
        for name, email, role, clearance, org in DEMO_PRINCIPALS:
            conn.execute(
                """
                INSERT INTO principal (name, email, role, clearance, org)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (email) DO NOTHING
                """,
                (name, email, role, clearance, org),
            )
    console.print(f"[green]✓[/] {len(DEMO_PRINCIPALS)} principals seeded")
    driver.close()


@app.command()
def ingest_doc(
    path: Path,
    doc_type: str = typer.Option("transcript", "--type"),
    sensitivity: int = typer.Option(2, "--sensitivity", min=0, max=4),
    batch: bool = typer.Option(False, "--batch", help="Use the Batch API (50% cheaper, async)"),
) -> None:
    """Ingest one document: load → chunk → embed → extract → queue for approval."""
    text = ingest.load(path)
    digest = ingest.content_hash(text)
    chunks = ingest.chunk(text)
    console.print(f"[dim]{path.name}: {len(text):,} chars → {len(chunks)} chunks[/]")

    with console.status("Embedding..."):
        vectors = ingest.embed([c.text for c in chunks])

    driver = store.neo()
    with store.pg() as conn:
        doc_id, is_new = store.upsert_document(
            conn,
            title=path.stem,
            doc_type=doc_type,
            raw_text=text,
            content_hash=digest,
            sensitivity=sensitivity,
            source_uri=str(path),
        )
        if not is_new:
            console.print("[yellow]Already ingested (identical content hash) — skipping.[/]")
            driver.close()
            return

        chunk_ids = store.insert_chunks(
            conn, document_id=doc_id, texts=[c.text for c in chunks],
            embeddings=vectors, sensitivity=sensitivity,
        )

        # The bridge: the same UUID Postgres just minted becomes a graph node.
        for cid, c in zip(chunk_ids, chunks, strict=True):
            store.upsert_chunk_node(
                driver, chunk_id=cid, document_id=doc_id,
                ordinal=c.ordinal, sensitivity=sensitivity,
            )

        if batch:
            batch_id = extract.submit_batch({str(cid): c.text for cid, c in zip(chunk_ids, chunks)})
            console.print(f"[green]✓[/] Batch submitted: [bold]{batch_id}[/]")
            console.print("[dim]Collect with: callosum collect-batch <id>[/]")
            driver.close()
            return

        queued = 0
        with console.status("Extracting entities and relationships...") as status:
            for i, (cid, c) in enumerate(zip(chunk_ids, chunks, strict=True), 1):
                status.update(f"Extracting chunk {i}/{len(chunks)}...")
                result = extract.extract(c.text)
                queued += store.queue_proposals(
                    conn, document_id=doc_id, chunk_id=cid, extraction=result
                )

    console.print(f"[green]✓[/] {queued} proposed changes queued for approval")
    console.print("[dim]Review with: callosum pending[/]")
    driver.close()


@app.command()
def pending(limit: int = 20) -> None:
    """Show the approval queue, lowest confidence first."""
    with store.pg() as conn:
        rows = store.pending(conn, limit=limit)

    if not rows:
        console.print("[dim]Queue is empty.[/]")
        return

    table = Table(title="Pending changes — the LLM proposes, you approve")
    table.add_column("id", style="dim", no_wrap=True)
    table.add_column("kind")
    table.add_column("claim")
    table.add_column("conf", justify="right")

    for row in rows:
        p = row["payload"]
        if row["kind"] == "add_entity":
            claim = f"{p['type']}: {p['name']}"
        else:
            claim = f"{p['source']} —{p['type']}→ {p['target']}"
        table.add_row(
            str(row["id"])[:8],
            row["kind"].replace("add_", ""),
            claim,
            f"{row['confidence']:.2f}" if row["confidence"] is not None else "—",
        )

    console.print(table)
    console.print("[dim]Approve with: callosum approve <id>  |  callosum approve --all[/]")


@app.command()
def approve(
    change_id: str = typer.Argument(None),
    all_pending: bool = typer.Option(False, "--all", help="Approve everything (demo shortcut)"),
    min_confidence: float = typer.Option(0.0, "--min-confidence"),
) -> None:
    """Commit approved changes to the graph. The only write path that exists."""
    driver = store.neo()
    committed = 0

    with store.pg() as conn:
        if all_pending:
            rows = conn.execute(
                "SELECT id FROM proposed_change WHERE status = 'pending' "
                "AND coalesce(confidence, 1) >= %s "
                # Entities first: a relationship MATCHes both endpoints, so the
                # nodes must exist before the edge can be written.
                "ORDER BY CASE kind WHEN 'add_entity' THEN 0 ELSE 1 END",
                (min_confidence,),
            ).fetchall()
            for row in rows:
                store.approve(conn, driver, row["id"])
                committed += 1
        else:
            if not change_id:
                raise typer.BadParameter("Give a change id, or use --all")
            full = conn.execute(
                "SELECT id FROM proposed_change WHERE id::text LIKE %s AND status = 'pending'",
                (f"{change_id}%",),
            ).fetchone()
            if not full:
                console.print(f"[red]No pending change matching {change_id}[/]")
                raise typer.Exit(1)
            store.approve(conn, driver, full["id"])
            committed = 1

    console.print(f"[green]✓[/] {committed} change(s) committed to the graph")
    console.print("[dim]See it: http://localhost:7474 → MATCH (n) RETURN n[/]")
    driver.close()


@app.command()
def query(
    question: str,
    as_user: str = typer.Option("Raj Malhotra", "--as", help="Who is asking"),
) -> None:
    """Ask a question. The answer depends on who you are."""
    driver = store.neo()

    with store.pg() as conn:
        row = conn.execute(
            "SELECT id, name, role, clearance FROM principal WHERE name ILIKE %s",
            (f"%{as_user}%",),
        ).fetchone()
        if not row:
            console.print(f"[red]No principal matching '{as_user}'. Run: callosum init[/]")
            raise typer.Exit(1)

        principal = Principal(
            id=row["id"], name=row["name"], role=row["role"], clearance=row["clearance"]
        )
        console.print(
            f"[dim]Asking as [bold]{principal.name}[/] "
            f"({principal.role}, clearance {principal.clearance})[/]\n"
        )

        with console.status("Planning → searching graph + vectors → filtering → answering..."):
            answer = ask(conn, driver, question, principal)

    console.print(Panel(answer.text, title=question, border_style="cyan"))

    if answer.graph_facts:
        console.print("\n[bold]Graph facts used:[/]")
        for fact in answer.graph_facts[:10]:
            console.print(f"  [dim]•[/] {fact}")

    if answer.evidence:
        console.print("\n[bold]Sources:[/]")
        for i, e in enumerate(answer.evidence, 1):
            console.print(f"  [{i}] {e.document_title} [dim]({e.source})[/]")

    if answer.withheld:
        console.print(
            f"\n[yellow]⚠ {answer.withheld} source(s) withheld — above your clearance.[/]"
        )

    console.print(f"\n[dim]{answer.latency_ms}ms[/]")
    driver.close()


@app.command()
def collect_batch(batch_id: str) -> None:
    """Collect a finished extraction batch and queue the results."""
    results = extract.collect_batch(batch_id)
    if not results:
        console.print("[yellow]No results yet — batch may still be processing.[/]")
        return

    queued = 0
    with store.pg() as conn:
        for chunk_id, extraction in results.items():
            row = conn.execute(
                "SELECT document_id FROM chunk WHERE id = %s", (uuid.UUID(chunk_id),)
            ).fetchone()
            if row:
                queued += store.queue_proposals(
                    conn, document_id=row["document_id"],
                    chunk_id=uuid.UUID(chunk_id), extraction=extraction,
                )

    console.print(f"[green]✓[/] {queued} proposed changes queued from {len(results)} chunks")


if __name__ == "__main__":
    app()

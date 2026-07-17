"""Callosum CLI — drive the whole pipeline from the terminal."""

import uuid
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from callosum import conflicts, extract, ingest, llm, store
from callosum.retrieve import Principal, ask

app = typer.Typer(no_args_is_help=True, add_completion=False)
console = Console()


def _terminal_safe(value: object) -> str:
    """Render CLI status text on legacy Windows consoles without encoding failures."""
    return str(value).encode("ascii", errors="backslashreplace").decode("ascii")


@app.command()
def doctor() -> None:
    """Check the configured provider and stores are reachable before a long run."""
    try:
        info = llm.health()
    except RuntimeError as exc:
        console.print(f"[red]ERROR[/] {_terminal_safe(exc)}")
        raise typer.Exit(1)

    console.print(
        f"[bold]Provider:[/] {_terminal_safe(info['provider'])} -> "
        f"{_terminal_safe(info['model'])}"
    )

    if info["provider"] == "ollama":
        ok = info["model_present"] and info["embedding_present"]
        if not info["model_present"]:
            console.print(
                f"[red]ERROR[/] Chat model missing. Run: "
                f"ollama pull {_terminal_safe(info['model'])}"
            )
        if not info["embedding_present"]:
            console.print(
                f"[red]ERROR[/] Embedding model missing. Run: "
                f"ollama pull {_terminal_safe(info['embedding_model'])}"
            )
        if ok:
            console.print(
                f"[green]OK[/] Ollama models present "
                f"({_terminal_safe(info['embedding_model'])} for embeddings)"
            )
    elif not info["key_set"]:
        console.print("[red]ERROR[/] ANTHROPIC_API_KEY is not set")
        raise typer.Exit(1)

    try:
        with store.pg() as conn:
            n = conn.execute("SELECT count(*) AS n FROM document").fetchone()["n"]
        console.print(f"[green]OK[/] Postgres reachable ({n} documents)")
    except Exception as exc:
        console.print(f"[red]ERROR[/] Postgres: {_terminal_safe(exc)}")
        raise typer.Exit(1)

    try:
        driver = store.neo()
        driver.verify_connectivity()
        console.print("[green]OK[/] Neo4j reachable")
        driver.close()
    except Exception as exc:
        console.print(f"[red]ERROR[/] Neo4j: {_terminal_safe(exc)}")
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
    no_extract: bool = typer.Option(
        False, "--no-extract",
        help="Load + chunk + embed only; skip LLM extraction. For the eval, whose graph "
             "is seeded deterministically (callosum seed-eval).",
    ),
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
            conn, document_id=doc_id, chunks=chunks,
            embeddings=vectors, sensitivity=sensitivity,
        )

        # The bridge: the same UUID Postgres just minted becomes a graph node.
        for cid, c in zip(chunk_ids, chunks, strict=True):
            store.upsert_chunk_node(
                driver, chunk_id=cid, document_id=doc_id,
                ordinal=c.ordinal, sensitivity=sensitivity,
            )

        if no_extract:
            console.print(
                f"[green]✓[/] {len(chunks)} chunk(s) embedded and stored "
                "[dim](--no-extract: graph left for callosum seed-eval)[/]"
            )
            driver.close()
            return

        if batch:
            batch_id = extract.submit_batch({str(cid): c.text for cid, c in zip(chunk_ids, chunks)})
            console.print(f"[green]✓[/] Batch submitted: [bold]{batch_id}[/]")
            console.print("[dim]Collect with: callosum collect-batch <id>[/]")
            driver.close()
            return

        stamp = extract.stamp()
        queued = quarantined = 0
        with console.status("Extracting entities and relationships...") as status:
            for i, (cid, c) in enumerate(zip(chunk_ids, chunks, strict=True), 1):
                status.update(f"Extracting chunk {i}/{len(chunks)}...")
                verified = extract.extract(c.text)
                q, bad = store.queue_proposals(
                    conn, document_id=doc_id, chunk_id=cid,
                    chunk_start=c.start_char, chunk_text=c.text,
                    verified=verified, stamp=stamp,
                )
                queued += q
                quarantined += bad

    console.print(f"[green]✓[/] {queued} proposed changes queued for approval")
    if quarantined:
        console.print(
            f"[yellow]⚠ {quarantined} edge(s) quarantined[/] — evidence quote not found "
            "in source. Inspect with: [dim]callosum failures[/]"
        )
    console.print("[dim]Review with: callosum pending[/]")

    # After queuing proposals, scan for entity name conflicts (e.g. "Raj" vs "Rajesh Malhotra").
    # This is a read-only scan on the graph — nothing reaches Neo4j without a human approval.
    try:
        n_conflicts = conflicts.detect_conflicts(conn, driver)
        if n_conflicts:
            console.print(
                f"[yellow]⚠ {n_conflicts} potential entity name alias(es) flagged.[/] "
                "Run: [dim]callosum review-conflicts[/]"
            )
    except Exception as exc:
        # Degrade gracefully if entity_conflict table doesn't exist yet (pre-migration).
        console.print(
            f"[dim]Conflict detection skipped ({_terminal_safe(exc)}). "
            "Run: scripts/migrate_entity_conflict.sql[/]"
        )

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

    stamp = extract.stamp()
    queued = quarantined = 0
    with store.pg() as conn:
        for chunk_id, raw_extraction in results.items():
            row = conn.execute(
                "SELECT document_id, text, start_char FROM chunk WHERE id = %s",
                (uuid.UUID(chunk_id),),
            ).fetchone()
            if not row:
                continue
            verified = extract.verify(raw_extraction, row["text"])
            q, bad = store.queue_proposals(
                conn, document_id=row["document_id"], chunk_id=uuid.UUID(chunk_id),
                chunk_start=row["start_char"], chunk_text=row["text"],
                verified=verified, stamp=stamp,
            )
            queued += q
            quarantined += bad

    console.print(f"[green]✓[/] {queued} queued, {quarantined} quarantined "
                  f"from {len(results)} chunks")


@app.command()
def seed_eval() -> None:
    """Seed the fixed gold graph for the retrieval eval, bypassing the LLM.

    Run after ingesting the demo docs and INSTEAD of `approve --all`. Writes the
    known-correct edges (Raj APPROVED, Marcus OPPOSED, …) directly, so `callosum eval`
    measures retrieval against a stable graph rather than whatever extraction produced
    this run. Extraction quality is measured separately — see `callosum failures`.
    """
    from callosum import evaluate as ev

    driver = store.neo()
    try:
        with store.pg() as conn:
            edges, confidential = ev.seed_graph(conn, driver)
    except ValueError as exc:
        console.print(f"[red]✗[/] {exc}")
        raise typer.Exit(1)
    finally:
        driver.close()

    console.print(f"[green]✓[/] Seeded gold graph: {edges} board edges"
                  + (f" + {confidential} confidential edge(s)" if confidential else ""))
    console.print("[dim]This graph is a declared gold standard — see docs/findings.md. "
                  "Now run: callosum eval[/]")


@app.command()
def eval(
    gold_path: Path = typer.Option(Path("eval/gold.jsonl"), "--gold", help="Stratified gold set (JSONL)"),
    out: Path = typer.Option(Path("eval/results.md"), "--out", help="Where to write the results table"),
) -> None:
    """Phase 7: run every gold question under hybrid AND vector-only, scored per stratum.

    This runs two full retrievals per question (2× LLM calls each), so it is a real run,
    not a unit test — expect it to take a minute on the cloud model. The output is the
    thesis's central table: lookup ties, multi-hop separates.
    """
    from callosum import evaluate as ev

    if not gold_path.exists():
        console.print(f"[red]No gold set at {gold_path}[/]")
        raise typer.Exit(1)

    gold = ev.load_gold(gold_path)
    console.print(f"[dim]Loaded {len(gold)} gold questions across "
                  f"{len(set(g.stratum for g in gold))} strata[/]\n")

    info = llm.health()
    provider_note = f"{info['provider']} · {info['model']}"

    driver = store.neo()
    with store.pg() as conn:
        with console.status("Running hybrid + vector-only over the gold set..."):
            results, scores = ev.evaluate(conn, driver, gold)
    driver.close()

    table = Table(title="Phase 7 — hybrid vs vector-only, by stratum")
    table.add_column("stratum")
    table.add_column("n", justify="right")
    table.add_column("vector-only", justify="right")
    table.add_column("hybrid", justify="right")
    table.add_column("graph-fact recall", justify="right")
    for s in ev.STRATUM_ORDER:
        sc = scores.get(s)
        if not sc or sc.n == 0:
            continue
        gr = sc.graph_fact_recall
        table.add_row(
            s, str(sc.n),
            f"{sc.vector_correct}/{sc.n}",
            f"{sc.hybrid_correct}/{sc.n}",
            "—" if gr is None else f"{gr*100:.0f}%",
        )
    console.print(table)

    gt = ev.grounding_traversal(results)
    if gt:
        stage = Table(title="Entity grounding vs traversal (the multi-hop bottleneck)")
        stage.add_column("stage")
        stage.add_column("accuracy", justify="right")
        trav = "—" if gt["traversal_acc"] is None else f"{gt['traversal_acc']*100:.0f}%"
        stage.add_row("entity grounding (correct seed)", f"{gt['grounding_acc']*100:.0f}% "
                      f"({gt['grounded']}/{gt['n']})")
        stage.add_row("grounding error rate (GER)", f"{gt['ger']*100:.0f}%")
        if gt["grounding_precision"] is not None:
            stage.add_row("grounding precision (negatives)", f"{gt['grounding_precision']*100:.0f}% "
                          f"({gt['n_neg'] - gt['false_positives']}/{gt['n_neg']})")
        stage.add_row("traversal (given grounding)", trav)
        console.print(stage)

        ablation = Table(title="Ablation — grounding on vs off (same graph engine)")
        ablation.add_column("configuration")
        ablation.add_column("graph-fact recall", justify="right")
        ablation.add_row("exact match only (no grounding)", f"{gt['recall_ungrounded']*100:.0f}%")
        ablation.add_row("planner grounding", f"{gt['recall_grounded']*100:.0f}%")
        console.print(ablation)
        console.print("[dim]Only the grounding stage changes between rows — the delta is its "
                      "measured contribution.[/]")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(ev.render_markdown(results, scores, provider_note), encoding="utf-8")
    csv_path = out.with_suffix(".csv")
    ev.write_csv(results, csv_path, info["model"])
    console.print(f"\n[green]✓[/] Wrote {out} and appended {csv_path}")
    console.print("[dim]Read it by row: lookup should tie, multi_hop should separate.[/]")


@app.command()
def detect_conflicts(
    threshold: float = typer.Option(75.0, "--threshold",
                                    help="Token-sort similarity threshold (0–100). "
                                         "75 catches 'R. Malhotra'/'Rajesh Malhotra' (~77) "
                                         "while keeping 'Raj Malhotra'/'Raj Patel' (~57) separate."),
) -> None:
    """Scan entity names for potential aliases and queue them for human review.

    Runs automatically at the end of `callosum ingest-doc`. Use this command to
    re-scan after graph changes without re-ingesting a document.
    """
    driver = store.neo()
    try:
        with store.pg() as conn:
            n = conflicts.detect_conflicts(conn, driver, threshold=threshold)
    except Exception as exc:
        console.print(f"[red]ERROR[/] {_terminal_safe(exc)}")
        console.print(
            "[dim]If the entity_conflict table is missing, run:\n"
            "  docker exec -i callosum-postgres-1 psql -U callosum -d callosum "
            "< scripts/migrate_entity_conflict.sql[/]"
        )
        raise typer.Exit(1)
    finally:
        driver.close()

    if n:
        console.print(
            f"[yellow]⚠ {n} new entity conflict(s) queued.[/] "
            "Run: [dim]callosum review-conflicts[/]"
        )
    else:
        console.print("[green]No new entity conflicts detected.[/]")


@app.command()
def review_conflicts(
    limit: int = typer.Option(20, "--limit"),
    as_user: str = typer.Option("Raj Malhotra", "--as", help="Who is reviewing (sets clearance)"),
) -> None:
    """Show entity name conflicts awaiting human review.

    Each row shows both names, their similarity score, and the exact source sentence
    that introduced each name. Decide per row:
      Approve (creates ALIAS_OF edge): callosum approve-conflict <id>
      Reject  (marks as distinct):     callosum reject-conflict <id>
    """
    with store.pg() as conn:
        row = conn.execute(
            "SELECT id, name, role, clearance FROM principal WHERE name ILIKE %s",
            (f"%{as_user}%",),
        ).fetchone()
        if not row:
            console.print(f"[red]No principal matching '{as_user}'. Run: callosum init[/]")
            raise typer.Exit(1)
        clearance = row["clearance"]
        rows = store.pending_entity_conflicts(conn, clearance=clearance, limit=limit)

    if not rows:
        console.print("[green]No entity conflicts pending review.[/] "
                      "(Either none detected, or all above your clearance.")
        return

    table = Table(
        title="Entity name conflicts — you decide whether these are the same",
        show_lines=True,
    )
    table.add_column("id", style="dim", no_wrap=True)
    table.add_column("sim", justify="right")
    table.add_column("type")
    table.add_column("name A")
    table.add_column("evidence A")
    table.add_column("name B")
    table.add_column("evidence B")

    for r in rows:
        sim_pct = f"{r['similarity']*100:.0f}%"
        table.add_row(
            str(r["id"])[:8],
            sim_pct,
            r["type_a"],
            f"[bold]{r['name_a']}[/]",
            f"[dim]{(r['quote_a'] or '—')[:120]}[/]",
            f"[bold]{r['name_b']}[/]",
            f"[dim]{(r['quote_b'] or '—')[:120]}[/]",
        )

    console.print(table)
    console.print(
        "\n[dim]Approve (ALIAS_OF edge written to graph): [/]"
        "[bold]callosum approve-conflict <id>[/]"
    )
    console.print(
        "[dim]Reject  (mark as distinct, never re-queued): [/]"
        "[bold]callosum reject-conflict <id>[/]"
    )


@app.command()
def approve_conflict(
    conflict_id: str,
    as_user: str = typer.Option("Raj Malhotra", "--as", help="Who is approving"),
) -> None:
    """Approve an entity alias conflict — writes an ALIAS_OF edge to the graph.

    This is a human decision. The ALIAS_OF edge goes through the normal
    proposed_change → approve() path so all provenance is preserved.
    """
    import uuid as _uuid
    driver = store.neo()
    try:
        with store.pg() as conn:
            reviewer = conn.execute(
                "SELECT id FROM principal WHERE name ILIKE %s",
                (f"%{as_user}%",),
            ).fetchone()
            reviewer_id = reviewer["id"] if reviewer else None

            # Resolve short id prefix to full UUID
            full = conn.execute(
                "SELECT id FROM entity_conflict WHERE id::text LIKE %s AND status = 'pending'",
                (f"{conflict_id}%",),
            ).fetchone()
            if not full:
                console.print(f"[red]No pending conflict matching {conflict_id}[/]")
                raise typer.Exit(1)

            change_id = conflicts.approve_conflict(
                conn, driver, full["id"], reviewer_id
            )
    except typer.Exit:
        raise
    except Exception as exc:
        console.print(f"[red]ERROR[/] {_terminal_safe(exc)}")
        raise typer.Exit(1)
    finally:
        driver.close()

    console.print(
        f"[green]✓[/] ALIAS_OF edge written to graph. "
        f"[dim]Change: {str(change_id)[:8]}[/]"
    )
    console.print("[dim]Verify: http://localhost:7474 → MATCH (a)-[:ALIAS_OF]->(b) RETURN a,b[/]")


@app.command()
def reject_conflict(
    conflict_id: str,
    as_user: str = typer.Option("Raj Malhotra", "--as", help="Who is rejecting"),
) -> None:
    """Reject an entity alias conflict — marks these as definitively distinct entities.

    This pair will never appear in the review queue again. No graph change is made.
    """
    try:
        with store.pg() as conn:
            reviewer = conn.execute(
                "SELECT id FROM principal WHERE name ILIKE %s",
                (f"%{as_user}%",),
            ).fetchone()
            reviewer_id = reviewer["id"] if reviewer else None

            full = conn.execute(
                "SELECT id FROM entity_conflict WHERE id::text LIKE %s AND status = 'pending'",
                (f"{conflict_id}%",),
            ).fetchone()
            if not full:
                console.print(f"[red]No pending conflict matching {conflict_id}[/]")
                raise typer.Exit(1)

            conflicts.reject_conflict(conn, full["id"], reviewer_id)
    except typer.Exit:
        raise
    except Exception as exc:
        console.print(f"[red]ERROR[/] {_terminal_safe(exc)}")
        raise typer.Exit(1)

    console.print(
        f"[green]✓[/] Conflict rejected — {conflict_id} marked as distinct entities. "
        "Will not re-appear in review queue."
    )


@app.command()
def failures() -> None:
    """Inspect the quarantine — edges the evidence verifier refused.

    The extraction process is the dataset. This is where you find out that Kimi
    fabricates a quote on one edge in twelve, or that failures cluster in the longest
    chunks. Those are the numbers that go in the evaluation chapter.
    """
    with store.pg() as conn:
        rows = store.failure_stats(conn)

    if not rows:
        console.print("[green]No quarantined edges.[/] Either extraction is clean or "
                      "nothing has been ingested yet.")
        return

    table = Table(title="Quarantined edges — proposed, then refused by the verifier")
    table.add_column("model", style="dim")
    table.add_column("prompt", justify="center")
    table.add_column("relation")
    table.add_column("reason", style="yellow")
    table.add_column("n", justify="right")
    table.add_column("claimed conf", justify="right")
    table.add_column("avg chars", justify="right")

    for r in rows:
        table.add_row(
            r["extractor_model"], r["prompt_version"], r["relation"] or "—",
            r["reason"], str(r["n"]),
            str(r["avg_claimed_confidence"]) if r["avg_claimed_confidence"] else "—",
            str(r["avg_chunk_chars"]) if r["avg_chunk_chars"] else "—",
        )

    console.print(table)
    console.print(
        "[dim]High claimed-confidence + quote_not_found = confident fabrication. "
        "That is the number to put on a slide.[/]"
    )


if __name__ == "__main__":
    app()

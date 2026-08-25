# Contributing to Callosum

Welcome — this guide is for collaborators (hi Devguru 👋) picking up work on Callosum.
It tells you what the system is, what is **open** for contribution, what is **frozen**,
and where to start.

## What Callosum is (in one paragraph)

An institutional-memory system: it ingests organizational documents (board transcripts,
memos), extracts a **verified knowledge graph** of people, decisions, meetings and
topics, and answers questions over a **hybrid graph + vector** store with RBAC and a
human-in-the-loop approval step. The thesis contribution is *verified* extraction — no
edge exists unless its verbatim evidence quote is found in the source — plus a
reproducible, stratified evaluation. The name: the *corpus callosum* bridges the two
hemispheres of the brain, like this system bridges the graph and the vector store.

The original product spec, use-cases, and HTML mockup live in `reference/` — that PRD is
the source of truth for scope and the ontology.

## Getting it running

```bash
docker compose up -d                 # Postgres+pgvector (:5433) + Neo4j (:7474/:7687)
uv venv && uv pip install -e .       # Python 3.12 env + the callosum CLI
.venv/bin/callosum doctor            # checks provider + both stores are reachable
bash scripts/demo.sh                 # full end-to-end: ingest → approve → two golden queries
```

Provider defaults to **Ollama** (free): `gpt-oss:120b-cloud` for extraction/synthesis and
local `bge-m3` for embeddings. Neo4j Browser at http://localhost:7474 (neo4j / callosum123)
is the demo money-shot.

Run the tests before and after any change:

```bash
.venv/bin/pytest -q                  # 24 fast deterministic tests (no LLM, no DB)
```

## The one rule: FROZEN core vs OPEN areas

The backend pipeline has been evaluated and is **architecturally frozen**. Do not modify
the frozen modules without a *measured* shortcoming against the evaluation baseline
(`callosum eval` → `eval/results.md`). "It felt cleaner" is not a reason; "GER rose from
0% to X% and here is the run" is.

**🔒 FROZEN — do not change without an eval result to justify it:**

| Module | Responsibility |
|---|---|
| `src/callosum/ingest.py` | chunking, char offsets, `locate()` quote verification |
| `src/callosum/extract.py` | extraction + the evidence `verify()` / quarantine |
| `src/callosum/retrieve.py` | planner, canonical grounding, 2-hop traversal, **RBAC gate** |
| `src/callosum/store.py` | Postgres + Neo4j writes, the shared-UUID bridge |
| `schema/postgres.sql` | the tables and the RBAC clearance model |

The RBAC gate in `retrieve.py` is security-critical and fail-closed — a real leak was
found and fixed there. Do not touch it without review.

**🟢 OPEN — this is where you come in:**

1. **Frontend (P6) — the biggest gap, best fit for the mockup work.**
   Nothing is built yet. Turn the `reference/` HTML mockup into a real UI:
   - **Founder chat** — ask a question, render the grounded answer + inline citations +
     the "N sources withheld" notice. Backend is ready: `callosum.retrieve.ask()`.
   - **Approval queue** — the human-in-the-loop screen: list `proposed_change` rows,
     approve/reject each. Backend is ready: `callosum pending` / `callosum approve`.
   - **Graph viewer** — visualize the Neo4j graph (or embed Neo4j Browser).
   Suggested stack: a thin FastAPI layer over the existing functions + any frontend you
   like. Keep it a separate `web/` package so it never imports into the frozen core.

2. **Evaluation dataset + gold questions — highest-value non-code work.**
   Everything currently rides on ONE board transcript, which is the biggest risk to the
   thesis (single-corpus overfitting). Add realistic, varied documents under `data/`:
   - a **hiring** decision, a **fundraising** discussion, and importantly a
     **superseding** decision (decision B overrides A — exercises the `SUPERSEDES` edge)
   - for each, add gold questions to `eval/gold.jsonl`, binned by `stratum`
     (`lookup` / `relational` / `multi_hop`), and **trace each back to a PRD use-case**
     (that traceability is worth marks). See the existing entries for the schema.

3. **PRD ↔ implementation traceability.** Verify every `EntityType` / `RelationType` in
   `src/callosum/ontology.py` maps to a requirement in the PRD, and write the
   requirements→system mapping doc under `docs/`.

4. **Approval-workflow UX.** Design what a founder sees when reviewing proposed edges —
   a product/design problem, not a backend one.

## House rules for the product domain (`meridian/`)

Small conventions that every P2 aggregate follows. They are written down because
each has now been re-explained at more than one checkpoint review.

**`version` vs `version_no` — they are different things, and both are correct.**

| Column | Meaning |
|---|---|
| `version` | Optimistic-concurrency counter. Bumped by *every* mutation, and guarded with `WHERE id = %s AND version = %s`. A stale value raises a typed `Stale*Error`. |
| `version_no` | Published-artifact lineage. Incremented only when supersession creates a **new row**, so a reader can follow amendment history. |

A board pack edited three times as a draft and then published once is `version = 4,
version_no = 1`. They are not redundant and neither should be folded into the other.

**Never pin a migration number in a spec, an issue, or a plan.**

Claim the slot when you implement, by reading `meridian/migrations/versions/`. A
number written at design time will be taken by the time anyone builds it — this has
happened on every checkpoint from CP3 onward. Issue #21 pinned `0009_board_pack`;
CP4 took `0009` first and CP3 shipped as `0010`. The CP5–CP9 proposal then pinned
`0011`–`0015` and every one of those was claimed by something else.

Nothing broke either time, because Alembic linearises on `down_revision` and not on
the number in the filename. The cost is confusion and rework, not corruption — but
it is entirely avoidable. Refer to checkpoints by name in specs ("CP8 — audit
event"), and let the number be decided by whoever writes the file.

**Never edit a migration that has been applied. Add a new one.**

Alembic records which revisions a database has run and never re-runs one, so an edit
splits the estate in two: databases migrated before it never receive the change,
databases built fresh after it have it from the start, and both report the same
`alembic_version`. Nothing notices until a constraint exists in one environment and
not another.

This is the invariant CP10 was accepted on — a full-chain downgrade and return
reproducing 628 schema facts identical to a fresh build. It is now enforced by
`tests/test_migration_immutability.py`, which checksums every migration against
`meridian/migrations/CHECKSUMS.json`. When you add a migration, record it in the same
commit:

```bash
python scripts/record_migration_checksums.py
```

If the test fails, do **not** regenerate the manifest to match — the recorder refuses
that on purpose. Revert the file and put the change in a new migration.

**The one exception: `downgrade()` may be corrected when it acts on objects the
migration did not create.**

`upgrade()` and everything outside the two functions — the docstring, `revision`,
**`down_revision`** — may never be edited. `down_revision` is the chain itself.

The asymmetry follows from the harm above rather than from convenience. Two
populations that never converge is an **upgrade-path** harm: Alembic stores version
numbers and never stores downgrade SQL, so no applied database holds a copy of
`downgrade()` that could diverge from an edit. A downgrade that is wrong is wrong in
the file, for everyone, at once — and can therefore be corrected for everyone, at
once. There is no estate to split.

The boundary is **enforced, not trusted**. `CHECKSUMS.json` records three hashes per
migration rather than one:

```json
"0019_composite_tenant_fks": {
  "header":    "...",   // immutable
  "upgrade":   "...",   // immutable
  "downgrade": "..."    // correctable
}
```

The recorder exits non-zero rather than overwrite `header` or `upgrade`, and there is
deliberately no flag to widen that. A single whole-file hash could only ever be
re-recorded wholesale, which silently re-blessed the upgrade path along with the
downgrade — a boundary that lived in prose, which is a boundary that depends on the
next person having read this paragraph.

What a correction is *for*: a `downgrade()` that drops what an earlier migration
created will abort the reverse leg with `DependentObjectsStillExist`, because
downgrade runs in reverse order and the owner's dependants are still present. **A
conditional create demands an equally conditional drop** — `DROP CONSTRAINT IF EXISTS`
guards absence, not ownership. `0019` is the worked example.

**Tenant-scoped foreign keys should reference the `(id, workspace_id)` pair.**

Postgres validates foreign keys as the table owner, which **bypasses row-level
security** — so a single-column `REFERENCES other(id)` will happily validate against
a row the caller cannot see, letting one workspace reference another's data. A
composite FK against a matching `UNIQUE (id, workspace_id)` makes that impossible by
construction. `decision_stance.board_member_id` is the reference implementation.

Older FKs instead rely on an RLS-scoped existence check in the domain module before
insert (see `add_pack_item` in `meridian/packs.py`), which works but depends on every
author remembering it. New relationships should prefer the composite key. Whether the
existing ones get migrated is an open question — see the tracking issue.

## Good first tasks

- Add one new document to `data/` + 3 gold questions to `eval/gold.jsonl`, then run
  `callosum eval` and confirm the new questions score. (Gets you through the whole loop.)
- Scaffold `web/` with a FastAPI endpoint wrapping `retrieve.ask()` and a single chat page.
- Write the PRD→ontology traceability table in `docs/`.

## Workflow

- **Branch and open a PR** — do not push to `master`. Master is the maintainer's record.
- Run `pytest -q` before pushing; add tests for anything you add under `web/` or the eval.
- Keep the frozen core untouched unless your PR includes an eval run that justifies it.
- The evaluation is the source of truth. New features are justified by a measured gap
  against the baseline, not by intuition. See `docs/findings.md` for the running log and
  the freeze boundary.

## Where to read more

- `docs/findings.md` — the evaluation log and the project's research narrative (V1→V2→V3).
  Read this first; it explains *why* the system is shaped the way it is.
- `docs/architecture.md` — the architecture and diagrams.
- `reference/` — the original PRD, use-cases, and mockup.

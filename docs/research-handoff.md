# Research handoff and frozen baseline

**Status: prepared, not accepted (2026-07-16).** This is the R13 handoff package for
Meridian product work. It records what is reproducible today and what requires a live,
reviewed experiment before the research track or P0 can be authorized.

## Reproduce the evaluated baseline

The named baseline is the annotated `eval-baseline-v2` tag at commit `932f15a`. It covers
Meetings 12 and 13, ontology v2, and the run-12 temporal/grounding results recorded in the
tag annotation and `docs/findings.md`.

```powershell
# Python 3.12, Docker, Ollama, and bge-m3 are required.
docker compose up -d
.venv\Scripts\callosum.exe doctor
bash scripts/eval.sh
.venv\Scripts\pytest.exe -q
git show eval-baseline-v2
```

`scripts/eval.sh` resets local Docker volumes. Do not run it against data that must be
retained. The evaluation seeds a declared gold graph; it measures retrieval, not live
extraction quality. Append results to `eval/results.csv`; never replace historical rows.

## Capability and readiness matrix

| Capability | Corpus / evidence | Research readiness | Product readiness / limitation |
|---|---|---|---|
| Source retention, offsets, embeddings | M12-M16 and deterministic offset tests | R1 accepted | No workspace or external connectors. |
| Verified proposals and approval | `extract.py`, quarantine tests | R2 accepted | No approval UI or production authorization model. |
| Hybrid retrieval and provenance | seeded evaluation, graph/vector RBAC tests | R4-R7 accepted | Clearance ladder only; object ACL grants are not active. |
| Aliases and conflicts | M14/M15, gold cases, provenance tests | benchmark implemented; live measurement pending | No automatic merge or conflict resolution. |
| Coreference and messy files | M16 and R11 fixtures/tests | benchmark implemented; live measurement pending | No reviewed coreference stage; DOCX visual rendering unverified locally. |
| Candidate grounding and abstention | permission-scoped vector candidates, deterministic R12 tests | implementation complete; live measurement pending | Candidate recall, latency, and false-positive change need a live run. |

## Frozen-core contract and R12 exception

The core remains frozen under `CONTRIBUTING.md`: changes to ingestion, extraction,
retrieval, storage, or schema require a measured shortcoming and a reviewed baseline
comparison. R12 is the recorded exception: run 10/12 measured grounding precision at 50%
on negatives and corpus-scale GER at 15%, justifying a scoped retrieval change. The change
uses only already-readable vector hits, repeats the Neo4j chunk-clearance predicate before
supplying names to the planner, and removes any model-emitted name outside that candidate
set. It does not change graph writes, provenance, approval, or traversal RBAC.

Any further core exception must include: the gold stratum, prior and new metrics, provider,
model, corpus, prompt/ontology versions, security tests, a reviewed diff, and a decision
record in `docs/findings.md` and `ROADMAP.md`.

## Release blockers and decision

Ollama is unavailable locally at `http://localhost:11434`; `callosum doctor` fails before
embedding or evaluation. Therefore no R8-R12 live metrics have been manufactured and no
new evaluation tag is created. Before accepting R12/R13, restore Ollama with `bge-m3`, run
the expanded benchmark from a clean environment, record candidate recall, grounding
accuracy, false positives, latency, traversal effects, document-type results, alias/conflict
metrics, and RBAC outcomes, then obtain review approval.

**P0 is not authorized by this document.** It requires the above evidence and explicit
research-handoff approval. This preserves the sequential gate in `ROADMAP.md`.

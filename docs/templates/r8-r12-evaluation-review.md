# R8-R12 evaluation review template

Use one completed copy of this template for every clean, live evaluation considered for
R8-R12 acceptance. This is a review record, not a substitute for `eval/results.csv` or the
append-only findings log. Do not mark a checkpoint accepted without a reviewer decision.

## Run identity

- Review date/time (with timezone):
- Reviewer(s):
- Repository commit SHA and branch:
- Comparison baseline/tag: `eval-baseline-v2`
- Provider, chat model, embedding model:
- Prompt version / ontology version:
- Python version, OS, and Docker versions:
- Corpus documents and sensitivities:
- Commands run:
- Was `scripts/eval.sh` allowed to delete local volumes? Yes / No

## Preconditions

- [ ] `callosum doctor` completed without error.
- [ ] Fresh Postgres and Neo4j environment used.
- [ ] `eval/results.csv` was appended, not replaced.
- [ ] Fast deterministic suite passed; record exact result:
- [ ] No unreviewed changes to the frozen core affected this run.

## Results summary

Attach or link the new CSV rows and generated `eval/results.md`. Record both absolute values
and the delta from `eval-baseline-v2`; do not infer a result from a single answer.

| Metric | Baseline | Current | Delta | Evidence/link | Interpretation |
|---|---:|---:|---:|---|---|
| Grounding accuracy | | | | | |
| GER | | | | | |
| Grounding precision / false positives | | | | | |
| Candidate recall (R12) | | | | | |
| Candidate/planner latency (R12) | | | | | |
| Traversal accuracy given grounding | | | | | |
| Vector-only graph-fact recall | | | | | |
| Hybrid graph-fact recall | | | | | |
| RBAC negative cases | | | | | |

## Checkpoint evidence and decision

### R8 - aliases and resolution

- Precision, recall, GER, and false positives:
- Alias evidence/provenance preserved:
- Decision: Pass / Fail / Inconclusive

### R9 - conflicting evidence

- Conflict recall and unsupported-resolution failures:
- Both claims remain independently sourced and permission-filtered:
- Decision: Pass / Fail / Inconclusive

### R10 - context-dependent references

- Coreference stratum failure rate and no-link behavior:
- Correct links retain original source spans:
- Decision: Pass / Fail / Inconclusive

### R11 - messy-document benchmark

- Results by TXT, Markdown, VTT, DOCX, and PDF:
- Failure reasons by document type:
- DOCX/PDF rendering limitation or verification:
- Decision: Pass / Fail / Inconclusive

### R12 - grounding abstention and scalable candidates

- Candidate recall and candidate count distribution:
- Grounding accuracy, GER, precision, and false positives:
- Latency and downstream traversal effect:
- Low-clearance candidate-name/RBAC negative proof:
- Decision: Pass / Fail / Inconclusive

## Security and provenance review

- [ ] No unreadable chunk text, title, graph fact, quote, or entity name reached a
      low-clearance caller.
- [ ] Every graph result still resolves through readable, source-backed chunks.
- [ ] No model output bypassed proposal review or mutated Neo4j directly.
- [ ] Rejected extraction outcomes remain quarantined and retained.

## Approval record

- Overall recommendation: Accept R8-R12 / Reject / More evidence required
- Exceptions, limitations, and owner:
- Required follow-up and due checkpoint:
- Reviewer sign-off and date:
- ROADMAP.md updated? Yes / No
- docs/findings.md updated? Yes / No
- Is R13 now eligible for formal handoff approval? Yes / No, because:

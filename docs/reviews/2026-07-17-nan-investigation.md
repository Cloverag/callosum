# bge-m3 NaN — root cause investigation (2026-07-17)

**Status: root cause found and reproduced deterministically.** A fix is *proposed*, not
applied — per the freeze, the embedding path is not changed again without approval,
especially since the earlier `keep_alive`+backoff change was based on a wrong hypothesis
(documented below so the record is honest).

## Result in one line

**The NaN is input-specific and deterministic, not transient.** A specific query string makes
bge-m3 (via Ollama/llama.cpp) compute a NaN vector and return `HTTP 500: unsupported value:
NaN`. The same string fails every time; a trivial perturbation of it succeeds every time.

## Evidence

Direct probing of the embedding endpoint, 5 attempts each, model warm and resident:

| Input | Result |
|---|---|
| T4 exact gold: `"Who changed their position on usage-based pricing between the two board meetings?"` | **5/5 HTTP 500 (NaN)** |
| Drop the question mark: `"…between the two board meetings"` | 5/5 ok |
| Reword: `"…between meetings?"` | 5/5 ok |
| Control (T2): `"What decision reversed the earlier pricing rejection…"` | 5/5 ok |

The failure is a property of the exact token sequence. Removing a single trailing character
(`?`) eliminates it. This is a numerical fault in the embedding model's compute on that
tokenization — an overflow/underflow producing NaN — surfaced by Ollama as a 500 because it
cannot JSON-encode NaN.

## What it is NOT (each ruled out with evidence)

- **Not transient / load / warmup.** T4 fails 5/5 in isolation with nothing else running.
- **Not cold-reload or GPU eviction.** It fails with the model resident (`keep_alive`), and
  the chat model is cloud-hosted (`gpt-oss:120b-cloud`) and never occupies local VRAM.
- **Not fixed by retry.** Retrying the identical string re-triggers the identical
  deterministic fault. This is why T4 stayed unretrieved in all three stability runs despite
  the bounded harness retry — the retry cannot help a deterministic input fault.
- **Not `keep_alive`-related.** `keep_alive` keeps the model loaded; it has no bearing on a
  per-string compute fault.

## Two earlier mistakes in the record, corrected

1. **The "0/30 in isolation" result that suggested 'transient' was a false negative.** That
   probe used a *paraphrase* of T4 ("between meetings"), not T4's exact gold string. The
   paraphrase does not trigger the fault; the exact string always does. Lesson: probe the
   exact failing input, never an approximation.
2. **The eval's NaN log lines go to STDOUT, not stderr.** The stability loop captured stderr
   (`2> run_N.stderr`), which came back empty and briefly suggested "0 NaN". The real counts
   are in stdout: **3, 5, 3** NaN events across the three runs. `vector_search`'s
   `print(..., file=sys.stderr)` is being redirected — likely by the Typer/Rich CLI wrapper.
   This is a logging-capture bug worth fixing so NaN events are not silently miscounted.

## Why the metric was still safe

Even though the fix does not stop the fault, the harness handles it correctly: a NaN makes
the candidate list empty, the question is marked `unretrieved`, and it is **excluded from
grounding metrics rather than scored as a linker miss** (the R12 change). So T4 never
corrupted a grounding number — it was quarantined, honestly, every run. Impact is one
temporal question lost per run, reported, not silently mis-scored.

## Recommended fix (proposed, not applied)

Now that the cause is understood, a targeted, cause-based fix is justified — as
**infrastructure** (in `llm.embed()`), not a retrieval-algorithm change:

- **On a 500/NaN, retry with a minimally perturbed input**, since retrying the identical
  string is futile. The perturbation must change tokenization enough to dodge the fault while
  barely moving the embedding — e.g. normalise trailing punctuation/whitespace, or append a
  single space. Evidence shows dropping `?` is sufficient; a whitespace-normalisation retry
  would recover T4 with a near-identical vector.
- **Detect NaN in the returned vector directly**, not only via HTTP 500, so a future model
  that returns 200-with-NaN is also caught.
- **Fix the stderr→stdout capture** so NaN events are countable from the log.
- **Reconsider the `keep_alive`+backoff change**: it does not address this cause. `keep_alive`
  is harmless to keep (avoids cold reloads generally), but the backoff-retry loop is dead
  weight against a deterministic fault and could be replaced by the perturbation retry above.

The `_ground_with_retry` harness retry and its comment (which asserts the empty-candidate case
is transient infra recoverable by retry) should be updated: for this deterministic input
fault, the retry does not recover, it only correctly ends in exclusion. The comment currently
overstates what the retry achieves.

## Recommendation

Understood cause, safe current behaviour (excluded, not mis-scored), thin blast radius (one
question). Not urgent, but a clean fix exists. Propose implementing the perturbation-retry +
NaN-detection in `embed()` and the log-capture fix as a small, reviewed **infrastructure**
change (no retrieval-core or algorithm impact). Holding for approval per the freeze.

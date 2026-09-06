"""The gold set and the corpus, checked against each other.

---------------------------------------------------------------------------
WHY THIS FILE EXISTS
---------------------------------------------------------------------------
Two defects found on 2026-09-06, neither of which any test could have caught,
and both of which are the same shape: **an assertion that cannot fail is not an
assertion.**

1. **The corpus was binary.** Three clearances are seeded — founder 4, exec 3,
   investor 1 — but every document was sensitivity 1 or 3, with nothing at 2 or
   4. The filter is `d.sensitivity <= clearance`, so founder and exec saw
   identical material on every document that existed. The system supported three
   tiers; the data exercised two. Every RBAC test still passed, because they were
   all really testing "investor vs everyone".

2. **An RBAC negative passed vacuously.** A founder-only document was inserted
   with raw SQL, which creates a `document` row and no chunks. `_rbac_fails_closed`
   searches chunks through `vector_search`, so the exec and investor rows passed
   because *nothing was indexed to leak*. Green, and meaningless.

`test_corpus_properties.py` already states the principle this file applies:

    "a test that the engine handles CRLF is only meaningful while something
     CRLF-shaped exists to hand it"

Clearance is the same. A test that the engine withholds by clearance is only
meaningful while a document exists that some principal can read and another
cannot. These tests assert the fixtures still make the clearance tests capable of
failing. They are about the DATA, not the engine — deliberately, because the
engine was correct throughout both defects above.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pytest

from callosum.cli import DEMO_PRINCIPALS
from callosum.evaluate import load_gold

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "eval" / "gold.jsonl"
EVAL_SH = ROOT / "scripts" / "eval.sh"

#: Sensitivity as assigned by the ingestion script, which is the only authority.
#: The gold set says nothing about sensitivity and the documents do not carry it —
#: it is an argument at ingest time, so `scripts/eval.sh` is where the corpus's
#: clearance shape actually lives.
_INGEST = re.compile(
    r"ingest-doc\s+(?:\"?\$(\w+)\"?|(\S+))[^\n]*?--sensitivity\s+(\d+)"
)


def _ingested_sensitivities() -> Counter[int]:
    text = EVAL_SH.read_text(encoding="utf-8")
    found = Counter(int(m.group(3)) for m in _INGEST.finditer(text))
    assert found, (
        "Parsed no `ingest-doc ... --sensitivity N` lines out of scripts/eval.sh. "
        "The script's shape changed and this test is now measuring nothing — fix "
        "the parse rather than deleting the test."
    )
    return found


def _seeded_clearances() -> dict[str, int]:
    # (name, email, role, clearance, org)
    return {role: clearance for _n, _e, role, clearance, _o in DEMO_PRINCIPALS}


class TestTheCorpusCanDistinguishEveryClearance:
    """The data must be able to tell the seeded principals apart.

    Without this, every clearance test in the suite is a test of the same single
    boundary, and the ones that look like they cover more are passing for free.
    """

    def test_every_seeded_clearance_is_separated_by_some_document(self):
        """For each pair of clearances, a document must exist that one reads and
        the other does not.

        This is the test that would have caught the binary corpus. It failed for
        founder-vs-exec until `board_governance_note_FOUNDER_ONLY` was added at
        sensitivity 4, and it will fail again the moment that document is
        removed, reclassified, or dropped from the ingestion script.
        """
        sensitivities = sorted(_ingested_sensitivities())
        clearances = _seeded_clearances()

        unseparated: list[str] = []
        roles = sorted(clearances, key=lambda r: clearances[r])
        for i, lower in enumerate(roles):
            for higher in roles[i + 1 :]:
                lo, hi = clearances[lower], clearances[higher]
                if lo == hi:
                    continue  # same clearance by design; nothing to separate
                # A document strictly above the lower and at or below the higher
                # is visible to `higher` and withheld from `lower`.
                if not any(lo < s <= hi for s in sensitivities):
                    unseparated.append(
                        f"{higher}(clearance {hi}) vs {lower}(clearance {lo}): "
                        f"no document in ({lo}, {hi}]"
                    )

        assert not unseparated, (
            "These principals see identical material on every ingested document, "
            "so any test claiming to distinguish them passes for free:\n  "
            + "\n  ".join(unseparated)
            + f"\n\nIngested sensitivities: {sorted(_ingested_sensitivities().items())}"
            + "\nAdd a document at a separating sensitivity. Do not relax this test."
        )

    def test_the_founder_only_tier_is_ingested_at_sensitivity_four(self):
        """Named explicitly, because the general test above would also pass if a
        *different* sensitivity-4 document appeared and this one were deleted.

        The general property is what matters; this pins the specific fixture the
        rbac gold rows cite, so its removal fails here with a message that says
        which gold rows break, rather than somewhere further downstream.
        """
        text = EVAL_SH.read_text(encoding="utf-8")
        line = next(
            (l for l in text.splitlines() if "board_governance_note_FOUNDER_ONLY" in l),
            None,
        )
        assert line is not None, (
            "board_governance_note_FOUNDER_ONLY is not ingested by scripts/eval.sh. "
            "Gold items X3/X4/X5 cite it and would silently stop testing anything."
        )
        assert "--sensitivity 4" in line, (
            f"board_governance_note_FOUNDER_ONLY is ingested at the wrong sensitivity:"
            f"\n  {line.strip()}\n"
            "It is the only document separating founder from exec. At any other "
            "sensitivity, X3/X4/X5 stop distinguishing them."
        )


class TestEveryWithholdingClaimHasAPositiveControl:
    """A forbidden-answer row proves nothing on its own.

    "Priya cannot read the secret" is satisfied by clearance filtering, and it is
    equally satisfied by the secret not existing, not being chunked, not being
    embedded, or being phrased differently than the test string. Only a matching
    row where someone DOES read it separates those.
    """

    def test_every_rbac_forbid_item_has_a_matching_expect_item(self):
        gold = load_gold(GOLD)
        rbac = [g for g in gold if g.stratum == "rbac"]
        assert rbac, "No rbac gold items at all — the stratum vanished."

        # A positive control is a gold item asking the SAME question that expects
        # the forbidden string rather than forbidding it.
        positives: dict[str, set[str]] = {}
        for g in rbac:
            if g.expect_answer:
                positives.setdefault(g.question.strip().lower(), set()).update(
                    s.lower() for s in g.expect_answer
                )

        orphans: list[str] = []
        for g in rbac:
            if not g.forbid_answer:
                continue
            expected_somewhere = positives.get(g.question.strip().lower(), set())
            proven = {f.lower() for f in g.forbid_answer} & expected_somewhere
            if not proven:
                orphans.append(
                    f"{g.id} (as {g.as_user}) forbids {g.forbid_answer} but no rbac "
                    f"item asks {g.question!r} and expects any of them"
                )

        assert not orphans, (
            "These rbac rows assert a withholding no other row proves is "
            "withholdable. If the string is absent, misspelled, unchunked or "
            "unembedded, they pass anyway:\n  " + "\n  ".join(orphans)
            + "\n\nAdd a row asking the same question as a principal who may read it."
        )

    def test_rbac_forbidden_strings_appear_somewhere_in_the_corpus(self):
        """A forbidden string that exists in no document cannot leak from one.

        Catches the typo case directly: `forbid_answer: ["Whitfeld"]` would pass
        every retrieval test ever written, because nothing can surface a string
        the corpus does not contain.
        """
        gold = load_gold(GOLD)
        demo = ROOT / "data" / "demo"
        corpus = "\n".join(
            p.read_bytes().decode("utf-8", errors="ignore").lower()
            for p in sorted(demo.iterdir())
            if p.is_file() and p.suffix in {".txt", ".md", ".vtt"}
        )

        missing: list[str] = []
        for g in gold:
            if g.stratum != "rbac":
                continue
            for token in g.forbid_answer:
                if token.lower() not in corpus:
                    missing.append(f"{g.id}: {token!r}")

        assert not missing, (
            "These rbac forbidden strings appear in no corpus document, so the "
            "rows forbidding them cannot fail:\n  " + "\n  ".join(missing)
        )


class TestTheGoldSetStaysTraceable:
    """Cheap structural guards, so a malformed row fails here rather than mid-run."""

    def test_no_duplicate_ids(self):
        gold = load_gold(GOLD)
        dupes = [i for i, n in Counter(g.id for g in gold).items() if n > 1]
        assert not dupes, f"Duplicate gold ids: {dupes}"

    def test_every_item_names_a_seeded_principal(self):
        """`_resolve_principal` raises at run time for an unknown name, which
        surfaces as a failed evaluation rather than a broken fixture."""
        gold = load_gold(GOLD)
        known = {name.split()[0] for name, *_ in DEMO_PRINCIPALS}
        unknown = sorted({g.as_user for g in gold if g.as_user not in known})
        assert not unknown, (
            f"Gold items are asked as principals `callosum init` does not seed: "
            f"{unknown}. Seeded first names: {sorted(known)}"
        )

    @pytest.mark.parametrize("stratum", ["rbac"])
    def test_stratum_is_not_a_single_question_asked_twice(self, stratum: str):
        """A stratum whose every row shares one question measures one thing.

        `rbac` was exactly this for a long time — X1/X2, one question, two askers —
        which is a fine pair and a poor stratum. This does not demand a size; it
        demands more than one distinct question.
        """
        gold = [g for g in load_gold(GOLD) if g.stratum == stratum]
        questions = {g.question.strip().lower() for g in gold}
        assert len(questions) >= 2, (
            f"The `{stratum}` stratum contains {len(gold)} rows but only "
            f"{len(questions)} distinct question(s). It measures one behaviour "
            f"however many rows it has."
        )


class TestPublishedNumbersDeclareWhatTheyMeasured:
    """A metric in the README is a claim about a moment, not a standing fact.

    The eval table was measured on a 29-item gold set, most recently 2026-07-20.
    The set has held 36 items since 2026-08-23 and 46 since 2026-09-06. The numbers
    were never wrong; they simply stopped describing the current set, and nothing
    on the page said so for six weeks.

    This does not force a re-run — re-running is a decision with a cost, and the
    figures are legitimately citable as long as they say what they measured. It
    forces the README to keep *saying* it.
    """

    def test_the_eval_table_carries_a_provenance_note(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        assert "Candidate recall — right entity offered" in readme, (
            "The eval table moved or was renamed; this test no longer guards it."
        )
        table_at = readme.index("Candidate recall — right entity offered")
        window = readme[table_at : table_at + 1600]
        assert "Provenance" in window, (
            "The eval table has no provenance note within 1600 characters of it. "
            "Every figure there is a claim about one run on one gold set; without a "
            "note saying which, a reader reasonably assumes it describes the set as "
            "it stands today. Restore the note or re-run and update both."
        )
        assert "results-v2.csv" in window, (
            "The provenance note does not name the results file the figures come "
            "from, so a reader cannot check them."
        )

    def test_provenance_note_states_a_gold_set_size(self):
        """A date alone is not enough — the size is what makes the denominators
        interpretable, and the size is what changed."""
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        table_at = readme.index("Candidate recall — right entity offered")
        window = readme[table_at : table_at + 1600]
        assert re.search(r"\*\*\d+-item\*\*|\b\d+-item\b", window), (
            "The provenance note gives no gold-set size. '81% (17/21)' means "
            "something different on a 29-item set than on a 46-item one."
        )

"""The demo corpus, tested as a fixture in its own right.

---------------------------------------------------------------------------
WHY THIS FILE EXISTS
---------------------------------------------------------------------------
Nothing read `data/demo/` before this. The eval scripts ingest it by explicitly
named path, and the unit tests build their own strings, so the corpus was a set
of files no test made any claim about.

That gap has already cost something. The `locate()` fix in #90 hinged on `\\r`;
the version proposed in #86 omitted it, which would have silently failed to
locate **every quote in a CRLF document**. Because `locate()` gates edge
creation, that is dropped edges rather than an error. It passed 461 tests and
produced a byte-identical `mechanism.csv` — and the reason nothing caught it is
that not one document in the corpus used CRLF, so the corpus could not exercise
the bug (`docs/findings.md`, and #92 task 2).

These tests assert the corpus still has the properties it was given. They are
deliberately about the *fixture*, not about the engine: a test that the engine
handles CRLF is only meaningful while something CRLF-shaped exists to hand it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from callosum.ingest import chunk, locate

DEMO = Path(__file__).resolve().parents[1] / "data" / "demo"

#: Written with CRLF on purpose; see `.gitattributes`.
CRLF_DOCUMENTS = (
    "messy_board_meeting_17_transcript.txt",
    "messy_vendor_followup_email.md",
)


def _read(name: str) -> str:
    # Decoded from bytes rather than read as text, so Python's universal-newline
    # translation never runs. `read_text(newline="")` would say the same thing but
    # only on 3.13+. This is the text the pipeline actually sees; reading it any
    # other way would quietly repair the property under test.
    return (DEMO / name).read_bytes().decode("utf-8")


class TestTheCorpusIsStillMessy:
    """Properties the corpus was given deliberately, guarded against silent loss."""

    @pytest.mark.parametrize("name", CRLF_DOCUMENTS)
    def test_the_crlf_documents_still_use_crlf(self, name: str):
        raw = (DEMO / name).read_bytes()
        assert b"\r\n" in raw, (
            f"{name} lost its CRLF line endings. It is CRLF on purpose — see "
            f".gitattributes. Restore the line endings; do not relax this test."
        )

    def test_at_least_one_transcript_and_one_email_are_crlf(self):
        # #92 task 2 asks for both, because a transcript and an email travel
        # through different parts of the pipeline.
        assert any(n.endswith(".txt") for n in CRLF_DOCUMENTS)
        assert any(n.endswith(".md") for n in CRLF_DOCUMENTS)

    def test_one_person_appears_under_inconsistent_speaker_labels(self):
        """`PRIYA:` / `P. Nair:` / `Priya N.:` are the same human.

        Entity resolution has to survive this, and it cannot be exercised by a
        corpus where every speaker is labelled identically every time.
        """
        text = _read("messy_board_meeting_17_transcript.txt")
        for label in ("PRIYA:", "P. Nair:", "Priya N.:"):
            assert label in text, f"speaker label {label!r} missing"

    def test_the_corpus_contains_interrupted_dialogue(self):
        text = _read("messy_board_meeting_17_transcript.txt")
        assert "—\r\n" in text or text.count("—") >= 2, "no interrupted turns"

    def test_the_corpus_contains_unnamed_references(self):
        """Phrases a linker must NOT resolve, and the record saying so.

        The grounding-precision weakness is about refusing to link when there is
        no referent. A corpus with no ambiguous phrases cannot test the refusal.
        """
        text = _read("messy_board_meeting_17_transcript.txt")
        assert "earlier motion" in text
        assert "ambiguous" in text

    def test_a_decision_supersedes_one_in_an_earlier_document(self):
        """Cross-document SUPERSEDES — now a three-document chain.

        Meeting 12 rejected Pricing Model B; Meeting 13 reversed that and made
        usage-based the forward model; Meeting 17 supersedes *that* with a tiered
        floor. Three endpoints in three documents, which is what makes it a graph
        question rather than a retrieval one.

        This test earned its place immediately: the first draft of Meeting 17 cited
        "Meeting 14", which is the deploy-and-rollback meeting and contains no
        pricing decision at all. A fabricated cross-reference in the corpus would
        have taught the linker to connect two things that were never connected.
        """
        text = _read("messy_board_meeting_17_transcript.txt")
        assert "supersede" in text.lower()
        assert "Meeting 13" in text, "the superseded decision must name the document it is in"

        # The decision being superseded really is where Meeting 17 says it is.
        earlier = _read("board_meeting_13_transcript.txt").lower()
        assert "usage-based" in earlier
        assert "reversing our decision" in earlier

    def test_the_corpus_contains_typos_and_ocr_noise(self):
        text = _read("messy_board_meeting_17_transcript.txt")
        email = _read("messy_vendor_followup_email.md")
        assert "droped" in text or "internatonal" in text, "no typos in the transcript"
        assert "Norlhwind" in email, "no OCR-style corruption in the email"


class TestTheEngineSurvivesTheCorpus:
    """The failure class the corpus now exists to catch.

    These are the assertions #86 would have failed. They are cheap, they need no
    database, and they run in the ungated tier — which is where a regression in
    `locate()` needs to be caught, because the gated tier already proved it can
    pass while silently dropping every edge in a CRLF document.
    """

    @pytest.mark.parametrize("name", CRLF_DOCUMENTS)
    def test_a_quote_is_located_in_a_crlf_document(self, name: str):
        text = _read(name)
        # A span from the middle of the document, taken verbatim from it — the
        # same thing an extractor emits as evidence. Stripped, because `locate()`
        # returns the span of the matched text and an extractor does not emit
        # leading or trailing whitespace as part of a quote.
        needle = text[200:280].strip()
        span = locate(needle, text)
        assert span is not None, f"locate() failed on a verbatim span of {name}"
        start, end = span
        assert text[start:end] == needle

    def test_a_quote_reflowed_across_a_crlf_break_is_located(self):
        """The exact shape of the #90 bug.

        A model reflows a quote it read across a line break, so the quote arrives
        with a single space where the document has `\\r\\n`. `locate()` must match
        it, and must return offsets into the ORIGINAL text so the span still
        highlights correctly.
        """
        text = _read("messy_board_meeting_17_transcript.txt")
        i = text.index("\r\n", 400)
        needle_raw = text[i - 40 : i + 40]
        reflowed = needle_raw.replace("\r\n", " ")
        span = locate(reflowed, text)
        assert span is not None, "a quote reflowed across a CRLF break was not located"
        start, end = span
        # Offsets index the original, not the reflowed copy.
        assert text[start:end] == needle_raw

    def test_a_paraphrase_is_still_refused_in_a_crlf_document(self):
        """Tolerating CRLF must not widen what counts as evidence.

        `locate()` bounds the thesis: an edge is verified because its quote was
        located. Whitespace flexibility is a concession to reflow, not to
        rewording, and a corpus change is exactly when that could slip.
        """
        text = _read("messy_board_meeting_17_transcript.txt")
        assert locate("Priya asked the board to lower the floor a bit", text) is None

    @pytest.mark.parametrize("name", CRLF_DOCUMENTS)
    def test_chunk_offsets_round_trip_on_crlf(self, name: str):
        """Every chunk's offsets must index back to its own text.

        Offsets are what make a located quote citable. If CRLF shifted them, a
        verified edge would highlight the wrong span of the source — a failure
        that looks like a UI bug and is a provenance one.
        """
        text = _read(name)
        chunks = chunk(text)
        assert chunks, f"{name} produced no chunks"
        for c in chunks:
            assert text[c.start_char : c.end_char] == c.text

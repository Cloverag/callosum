"""README measured-block figures must be true at the SHA they name (#159).

The obvious test — assert the commit count matches HEAD — fails on every new
commit, so it is unbuildable. This one parses the pin, derives the figures at
that SHA, and compares. It fails when someone edits a number without re-pinning
or re-measuring, which is both symptoms in #159.

Scope: derivable figures only — commits, migration count and head, ADR count.
The two test counts are a cited CI run and are not derived here.

CI: ``git rev-list --count <pin>`` needs the full history. backend-ci sets
``fetch-depth: 0`` for that reason. That depth change is a *predicted*
requirement (a shallow clone fails ``rev-list``); it was not demonstrated by a
red run on a depth-1 checkout, because the two land together.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text(encoding="utf-8")

_SHA = re.compile(r"Measured on `([0-9a-f]{7,40})`")
_COMMITS = re.compile(
    r"\| Commits \| \*{0,2}(\d+)\*{0,2} \(`git rev-list --count ([0-9a-f]{7,40})`\)"
)
_MIGRATIONS = re.compile(r"\| Migrations \| \*{0,2}(\d+)\*{0,2}, head `([0-9a-z_]+)`")
_ADRS = re.compile(r"\| Architecture decisions \| \*{0,2}(\d+)")


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def test_measured_block_names_a_pin_not_a_moving_ref():
    measured = _SHA.search(README)
    commits = _COMMITS.search(README)
    assert measured, "README has no 'Measured on `<sha>`' pin"
    assert commits, "Commits row must name `git rev-list --count <sha>`, not a branch"
    pin = measured.group(1)
    named = commits.group(2)
    assert named == pin, (
        f"the Commits parenthetical names {named!r} but the pin is {pin!r} — "
        f"a moving ref is the defect #159 exists to stop"
    )
    assert named not in {"master", "HEAD", "main", "origin/master"}


def test_derivable_figures_are_true_at_the_pin():
    pin = _SHA.search(README).group(1)
    claimed_commits = int(_COMMITS.search(README).group(1))
    mig = _MIGRATIONS.search(README)
    adrs = _ADRS.search(README)
    assert mig, "Migrations row not found"
    assert adrs, "Architecture decisions row not found"

    actual_commits = int(_git("rev-list", "--count", pin))
    assert actual_commits == claimed_commits, (
        f"README claims {claimed_commits} commits at {pin}, git counts {actual_commits}"
    )

    files = [
        line
        for line in _git(
            "ls-tree", "-r", "--name-only", pin, "--", "meridian/migrations/versions/"
        ).splitlines()
        if line.endswith(".py")
    ]
    claimed_n, claimed_head = int(mig.group(1)), mig.group(2)
    assert len(files) == claimed_n, (
        f"README claims {claimed_n} migrations at {pin}, found {len(files)}"
    )
    stems = {Path(f).stem for f in files}
    assert claimed_head in stems, (
        f"head {claimed_head!r} is not among the migration files at {pin}"
    )

    adr_md = _git("show", f"{pin}:docs/ARCHITECTURE_DECISIONS.md")
    actual_adrs = len(re.findall(r"^## ADR-", adr_md, re.M))
    assert actual_adrs == int(adrs.group(1)), (
        f"README claims {adrs.group(1)} ADRs at {pin}, found {actual_adrs}"
    )

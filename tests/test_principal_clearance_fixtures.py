"""Principal fixtures must not seed a clearance that disagrees with the role (#182).

``principal.clearance`` is not read for authorization — ``identity.py`` derives
clearance from ``membership.role``. The literals are still a decoy: fifteen files
used to write ``('director', 2)`` beside a role that maps to 3. A future reader,
bootstrap, or backfill that *does* trust the column inherits the wrong number.

The fixtures now pass ``identity.ROLE_TO_CLEARANCE[role]``. This test makes a
literal disagreement unrepresentable in ``INSERT INTO principal`` statements.
"""

from __future__ import annotations

import re
from pathlib import Path

from callosum.identity import ROLE_TO_CLEARANCE

ROOT = Path(__file__).resolve().parent
_LITERAL = re.compile(
    r"INSERT INTO principal \(id, name, role, clearance\) VALUES "
    r"\(%s, %s, '(\w+)', (\d+)\)"
)


def test_principal_insert_literals_agree_with_role_to_clearance():
    disagreements = []
    here = Path(__file__).name
    for path in sorted(ROOT.glob("*.py")):
        if path.name == here:
            continue
        text = path.read_text(encoding="utf-8")
        for m in _LITERAL.finditer(text):
            role, n = m.group(1), int(m.group(2))
            expected = ROLE_TO_CLEARANCE.get(role)
            if expected != n:
                disagreements.append(f"{path.name}: '{role}', {n} (maps to {expected})")
    assert disagreements == []


def test_director_clearance_two_is_unrepresentable_in_principal_inserts():
    """The exact copy-paste this issue was filed to stop."""
    hits = []
    # Concatenated so this file does not match its own needle.
    needle = (
        "INSERT INTO principal (id, name, role, clearance) VALUES "
        "(%s, %s, 'director', 2)"
    )
    here = Path(__file__).name
    for path in sorted(ROOT.glob("*.py")):
        if path.name == here:
            continue
        if needle in path.read_text(encoding="utf-8"):
            hits.append(path.name)
    assert hits == []

"""Static guard: every minutes mutation reaches an audit call with the actor (#168).

No database needed. The behavioural proof is `test_minutes_audit.py`; this file is what
fails in an ordinary run when a new mutator or route forgets the trail.

Shaped after `test_packs_agenda_audit_static.py` (P5 CP5A) on purpose — the same two
halves, because the two halves fail independently: a route can forget to pass the actor
while the domain records faithfully, and a domain function can skip the audit while the
route passes an actor nobody uses. One test each.

One addition over CP5A's version: `test_the_mutator_list_is_not_hand_maintained` derives
the set of mutators from the module instead of trusting the literal below it. A
hand-written list silently stops covering the thing it names the moment someone adds a
fifth mutation — which is exactly how `minutes.py` came to have four unaudited routes
while every count of "audited modules" looked fine.
"""

import ast
import pathlib

import meridian.api.minutes as minutes_api
import meridian.minutes as minutes_mod

_ROUTER = pathlib.Path(minutes_api.__file__)
_DOMAIN = pathlib.Path(minutes_mod.__file__)

#: The four mutating operations on this aggregate. Pinned, and checked against the
#: module by the last test in this file so the pin cannot go stale unnoticed.
MUTATORS = {"create_minutes", "update_minutes", "finalise_minutes", "supersede_minutes"}


def test_every_mutating_route_passes_the_actor_to_the_domain():
    """A route that forgets `actor_principal_id` writes an anonymous event.

    `actor_principal_id` is optional on the domain signatures — the 26 pre-existing
    call sites predate the audit write — so nothing but this stops a route omitting it.
    """
    seen = set()
    for node in ast.walk(ast.parse(_ROUTER.read_text(encoding="utf-8"))):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in MUTATORS
        ):
            seen.add(node.func.attr)
            assert "actor_principal_id" in {k.arg for k in node.keywords}, (
                f"{_ROUTER.name}: {node.func.attr} is called without actor_principal_id"
            )
    assert seen == MUTATORS, f"routes never call: {sorted(MUTATORS - seen)}"


def test_no_domain_mutator_can_skip_the_audit():
    """Each of the four must reach `_audit_minutes` and accept an actor to record."""
    tree = ast.parse(_DOMAIN.read_text(encoding="utf-8"))
    checked = set()
    for fn in (n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in MUTATORS):
        checked.add(fn.name)
        called = {
            n.func.id if isinstance(n.func, ast.Name) else getattr(n.func, "attr", "")
            for n in ast.walk(fn)
            if isinstance(n, ast.Call)
        }
        assert called & {"_audit_minutes", "record_audit_event"}, (
            f"minutes.{fn.name} records no audit event"
        )
        assert "actor_principal_id" in {a.arg for a in fn.args.kwonlyargs}, (
            f"minutes.{fn.name} takes no actor to record"
        )
    assert checked == MUTATORS, f"not found in the module: {sorted(MUTATORS - checked)}"


def test_the_audit_write_is_the_last_statement_in_the_transaction_body():
    """A write placed before the mutation records a refusal as a success.

    Three of `minutes.py`'s four refusal branches (`MinutesNotFound`, `StaleMinutesError`,
    `MinutesLockedError`) raise *after* the function is entered and before the row is
    written, so ordering is the whole guarantee — `test_minutes_audit.py::
    test_a_refused_minutes_write_records_nothing` proves it behaviourally, and this
    proves it structurally, which is the half that survives someone reordering the body
    without running the gated tier.

    The check: inside each mutator, no `raise` may appear at the same nesting depth
    after the `_audit_minutes` call.
    """
    tree = ast.parse(_DOMAIN.read_text(encoding="utf-8"))
    for fn in (n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in MUTATORS):
        audit_lines = [
            n.lineno
            for n in ast.walk(fn)
            if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "_audit_minutes"
        ]
        assert audit_lines, fn.name
        raises_after = [
            n.lineno for n in ast.walk(fn) if isinstance(n, ast.Raise) and n.lineno > max(audit_lines)
        ]
        assert not raises_after, (
            f"minutes.{fn.name}: a raise at line(s) {raises_after} follows the audit write at "
            f"{max(audit_lines)} — a refusal after the trail is written leaves a recorded "
            f"event for something that did not happen"
        )


def test_the_mutator_list_is_not_hand_maintained():
    """A fifth mutation must not be able to arrive unaudited and unnoticed.

    `MUTATORS` above is a literal, and a literal is how a guard quietly stops covering
    its module. This derives the real set — public functions in `minutes.py` that write
    — and fails if the two disagree, so adding a mutator forces a decision here rather
    than passing by default.
    """
    tree = ast.parse(_DOMAIN.read_text(encoding="utf-8"))
    writers = set()
    for fn in (n for n in tree.body if isinstance(n, ast.FunctionDef)):
        if fn.name.startswith("_"):
            continue
        sql = " ".join(
            n.value.upper()
            for n in ast.walk(fn)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
        )
        if any(verb in sql for verb in ("INSERT INTO", "UPDATE ", "DELETE FROM")):
            writers.add(fn.name)
    assert writers == MUTATORS, (
        f"minutes.py's writing functions are {sorted(writers)} but this file pins "
        f"{sorted(MUTATORS)}. Add the new one to MUTATORS and to the audited paths, or "
        f"say here why it does not need a trail."
    )

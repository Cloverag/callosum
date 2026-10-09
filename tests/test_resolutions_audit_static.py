"""Static guard: every resolution mutation reaches an audit call with the actor (#168).

No database needed. The behavioural proof is `test_resolutions_audit.py`.

---------------------------------------------------------------------------
WHAT WAS WRONG, AND WHY A COUNT MISSED IT
---------------------------------------------------------------------------
`meridian/resolutions.py` had **2** `record_audit_event` calls against **6** mutating
routes, which looks like partial coverage. Tracing each route to the domain function it
calls showed something worse:

    create_resolution                NO audit
    update_resolution                NO audit
    record_vote                      audited, but ANONYMOUS
    transition_resolution            NO audit   <- how a motion is adopted or rejected
    supersede_resolution             NO audit
    bridge_resolution_to_commitment  audited, but ANONYMOUS

Four mutations wrote nothing, and the two that wrote passed no `actor_principal_id` at
all — so every resolution event this module has ever written is unattributed. On a board
motion, `board_member_id` in the vote payload is the *subject* of the vote, not the
caller who submitted it, and separating those two is the whole point of attributing a
governance act.

Unlike `cli.py`'s seeder — ruled exempt in #166 because a bootstrap path has no
authenticated actor — all six of these run behind `CurrentPrincipal`. There was always
a caller to name.
"""

import ast
import pathlib

import meridian.api.resolutions as resolutions_api
import meridian.resolutions as resolutions_mod

_ROUTER = pathlib.Path(resolutions_api.__file__)
_DOMAIN = pathlib.Path(resolutions_mod.__file__)

#: The six mutating operations on this aggregate. Checked against the module by
#: `test_the_mutator_list_is_not_hand_maintained` so the pin cannot go stale unnoticed.
MUTATORS = {
    "create_resolution",
    "update_resolution",
    "record_vote",
    "transition_resolution",
    "supersede_resolution",
    "bridge_resolution_to_commitment",
}


def _domain_tree() -> ast.Module:
    return ast.parse(_DOMAIN.read_text(encoding="utf-8"))


def _mutator_nodes(tree: ast.Module):
    return [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in MUTATORS]


def test_every_mutating_route_passes_the_actor_to_the_domain():
    """A route that forgets `actor_principal_id` writes an anonymous event.

    This is the check that would have caught the original defect: both pre-existing
    audit calls were reachable from a route, so a coverage count looked fine while the
    events carried no actor.
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
    """Each of the six must reach an audit call and accept an actor to record."""
    checked = set()
    for fn in _mutator_nodes(_domain_tree()):
        checked.add(fn.name)
        called = {
            n.func.id if isinstance(n.func, ast.Name) else getattr(n.func, "attr", "")
            for n in ast.walk(fn)
            if isinstance(n, ast.Call)
        }
        assert called & {"_audit_resolution", "record_audit_event"}, (
            f"resolutions.{fn.name} records no audit event"
        )
        assert "actor_principal_id" in {a.arg for a in fn.args.kwonlyargs}, (
            f"resolutions.{fn.name} takes no actor to record"
        )
    assert checked == MUTATORS, f"not found in the module: {sorted(MUTATORS - checked)}"


def test_no_audit_call_in_this_module_omits_the_actor():
    """The defect was an audit call with no `actor_principal_id` keyword, not a missing call.

    `record_audit_event`'s signature takes the actor as optional, which is correct — the
    `cli.py` bootstrap path legitimately has nobody to name. That makes omitting it here
    silent, and it stayed silent through two code reviews. Every call site inside
    `resolutions.py` must pass it.
    """
    for node in ast.walk(_domain_tree()):
        if (
            isinstance(node, ast.Call)
            and getattr(node.func, "attr", "") == "record_audit_event"
        ):
            kwargs = {k.arg for k in node.keywords}
            assert "actor_principal_id" in kwargs, (
                f"resolutions.py:{node.lineno}: record_audit_event without "
                f"actor_principal_id writes an anonymous event"
            )


def test_the_audit_write_follows_the_mutation_it_records():
    """A write placed before the mutation records a refusal as a success.

    Four of the six refuse after entry and before the row is written — not found, stale
    version, immutable because adopted, parent meeting not mutable — so ordering is the
    guarantee. No `raise` may appear after the audit call inside a mutator.
    """
    for fn in _mutator_nodes(_domain_tree()):
        audit_lines = [
            n.lineno
            for n in ast.walk(fn)
            if isinstance(n, ast.Call)
            and (
                getattr(n.func, "id", "") == "_audit_resolution"
                or getattr(n.func, "attr", "") == "record_audit_event"
            )
        ]
        assert audit_lines, fn.name
        after = [
            n.lineno for n in ast.walk(fn) if isinstance(n, ast.Raise) and n.lineno > max(audit_lines)
        ]
        assert not after, (
            f"resolutions.{fn.name}: a raise at line(s) {after} follows the audit write at "
            f"{max(audit_lines)} — a refusal after the trail is written leaves a recorded "
            f"event for something that did not happen"
        )


def test_every_version_guarded_update_checks_for_a_lost_race():
    """A `WHERE version = %s ... RETURNING *` that matched nothing must raise.

    Same invariant as `test_minutes_audit_static.py`'s, and written the same way for the
    same reason: bound to **the variable each UPDATE was assigned to**, because the first
    version of that test counted guards against updates and passed with the real guard
    deleted — every mutator has an unrelated `if current is None: raise ...NotFound` for
    its row lookup, which satisfied a count.
    """
    tree = _domain_tree()

    def _is_guarded_update(node) -> bool:
        return isinstance(node, ast.Call) and any(
            isinstance(a, ast.Constant)
            and isinstance(a.value, str)
            and "UPDATE resolution" in a.value
            and "version = %s" in a.value
            and "RETURNING" in a.value
            for a in ast.walk(node)
        )

    for fn in _mutator_nodes(tree):
        targets = {
            node.targets[0].id
            for node in ast.walk(fn)
            if isinstance(node, ast.Assign)
            and isinstance(node.targets[0], ast.Name)
            and _is_guarded_update(node.value)
        }
        if not targets:
            continue
        guarded = {
            node.test.left.id
            for node in ast.walk(fn)
            if isinstance(node, ast.If)
            and isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Name)
            and node.test.ops
            and isinstance(node.test.ops[0], ast.Is)
            and isinstance(node.test.comparators[0], ast.Constant)
            and node.test.comparators[0].value is None
            and any(isinstance(b, ast.Raise) for b in ast.walk(node))
        }
        missing = targets - guarded
        assert not missing, (
            f"resolutions.{fn.name}: {sorted(missing)} comes from a version-guarded "
            f"UPDATE but is never checked for None."
        )


def test_the_mutator_list_is_not_hand_maintained():
    """A seventh mutation must not arrive unaudited and unnoticed.

    Derives the writing functions from the module and fails if they diverge from the pin
    above. `bridge_resolution_to_commitment` writes no SQL of its own — it delegates to
    `commitments.create_commitment` — so it is allowed to be in the pin without appearing
    in the derived set, and that exemption is named rather than silently tolerated.
    """
    tree = _domain_tree()
    writers = set()
    for fn in tree.body:
        if not isinstance(fn, ast.FunctionDef) or fn.name.startswith("_"):
            continue
        sql = " ".join(
            n.value.upper()
            for n in ast.walk(fn)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
        )
        if any(v in sql for v in ("INSERT INTO RESOLUTION", "UPDATE RESOLUTION", "DELETE FROM RESOLUTION")):
            writers.add(fn.name)

    delegating = {"bridge_resolution_to_commitment"}
    assert writers == MUTATORS - delegating, (
        f"resolutions.py's SQL-writing functions are {sorted(writers)} but this file pins "
        f"{sorted(MUTATORS - delegating)}. Add the new one to MUTATORS and to the audited "
        f"paths, or say here why it needs no trail."
    )

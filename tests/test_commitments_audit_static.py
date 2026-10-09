"""Static guard: every commitment mutation reaches an audit call with the actor (#168).

No database needed. The behavioural proof is `test_commitments_audit.py`.

Same shape as `test_minutes_audit_static.py` and `test_resolutions_audit_static.py`,
with two differences that are specific to this module:

1. **There is a second production caller.** `resolutions.bridge_resolution_to_commitment`
   creates commitments without going through the router, so checking the router alone
   would leave a path that writes anonymous `created` events.

2. **`update_commitment`'s UPDATE is an f-string.** In the AST its text is split across
   several string constants either side of the interpolated SET clause — `UPDATE
   commitment` lands in one and `version = %s` in another. The lost-race check in the
   other two guards tests each constant separately, which here would match *nothing*
   and skip the function silently. This one joins the fragments first, and
   `test_the_lost_race_check_actually_sees_both_updates` pins that it found them.
"""

import ast
import pathlib

import meridian.api.commitments as commitments_api
import meridian.commitments as commitments_mod
import meridian.resolutions as resolutions_mod

_ROUTER = pathlib.Path(commitments_api.__file__)
_DOMAIN = pathlib.Path(commitments_mod.__file__)
_BRIDGE = pathlib.Path(resolutions_mod.__file__)

#: The three audited mutations — one per route.
MUTATORS = {"create_commitment", "update_commitment", "record_update"}

#: Writers deliberately left without an audit trail, each with its reason.
EXEMPT = {
    # No route, and nothing dispatches: delivery is inert until P8, pinned by
    # `test_d2c_write_api.py::test_there_is_no_delivery_endpoint`. Auditing it now
    # would mean choosing P8's actor model (a dispatcher is not a principal) before
    # P8 exists. When a route or a dispatcher arrives, this entry has to go.
    "record_delivery_attempt",
}


def _tree(path: pathlib.Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _mutator_nodes(tree: ast.Module):
    return [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in MUTATORS]


def _sql_text(node: ast.AST) -> str:
    """Every string constant under `node`, joined — so an f-string reads as one statement."""
    return " ".join(
        n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)
    )


def test_every_mutating_route_passes_the_actor_to_the_domain():
    seen = set()
    for node in ast.walk(_tree(_ROUTER)):
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


def test_the_resolution_bridge_passes_its_actor_to_the_commitment_it_creates():
    """The non-route caller. It had an actor in hand and did not pass it on."""
    calls = [
        node
        for node in ast.walk(_tree(_BRIDGE))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "create_commitment"
    ]
    assert calls, "resolutions.py no longer calls create_commitment — update this test"
    for call in calls:
        assert "actor_principal_id" in {k.arg for k in call.keywords}, (
            f"resolutions.py:{call.lineno}: create_commitment without actor_principal_id "
            f"writes an anonymous `created` event for every bridged commitment"
        )


def test_no_domain_mutator_can_skip_the_audit():
    checked = set()
    for fn in _mutator_nodes(_tree(_DOMAIN)):
        checked.add(fn.name)
        called = {
            n.func.id if isinstance(n.func, ast.Name) else getattr(n.func, "attr", "")
            for n in ast.walk(fn)
            if isinstance(n, ast.Call)
        }
        assert called & {"_audit_commitment", "record_audit_event"}, (
            f"commitments.{fn.name} records no audit event"
        )
        assert "actor_principal_id" in {a.arg for a in fn.args.kwonlyargs}, (
            f"commitments.{fn.name} takes no actor to record"
        )
    assert checked == MUTATORS, f"not found in the module: {sorted(MUTATORS - checked)}"


def test_no_audit_call_in_this_module_omits_the_actor():
    """`record_update`'s pre-existing call omitted it, and nothing noticed."""
    for node in ast.walk(_tree(_DOMAIN)):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "record_audit_event":
            assert "actor_principal_id" in {k.arg for k in node.keywords}, (
                f"commitments.py:{node.lineno}: record_audit_event without "
                f"actor_principal_id writes an anonymous event"
            )


def test_the_audit_write_follows_the_mutation_it_records():
    """No `raise` may follow the audit call inside a mutator."""
    for fn in _mutator_nodes(_tree(_DOMAIN)):
        audit_lines = [
            n.lineno
            for n in ast.walk(fn)
            if isinstance(n, ast.Call)
            and (
                getattr(n.func, "id", "") == "_audit_commitment"
                or getattr(n.func, "attr", "") == "record_audit_event"
            )
        ]
        assert audit_lines, fn.name
        after = [
            n.lineno for n in ast.walk(fn) if isinstance(n, ast.Raise) and n.lineno > max(audit_lines)
        ]
        assert not after, (
            f"commitments.{fn.name}: a raise at line(s) {after} follows the audit write at "
            f"{max(audit_lines)}"
        )


def _guarded_update_targets(fn: ast.FunctionDef) -> set[str]:
    """Names assigned from a `UPDATE commitment ... WHERE ... version = %s ... RETURNING`."""

    def _is_guarded_update(node) -> bool:
        if not isinstance(node, ast.Call):
            return False
        sql = _sql_text(node)
        return "UPDATE commitment" in sql and "version = %s" in sql and "RETURNING" in sql

    return {
        node.targets[0].id
        for node in ast.walk(fn)
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and _is_guarded_update(node.value)
    }


def test_the_lost_race_check_actually_sees_both_updates():
    """Pins that the f-string UPDATE is found, so the next test cannot skip it silently.

    Without the fragment join in `_sql_text`, `update_commitment` yields no targets and
    the lost-race test passes over it without checking anything.
    """
    found = {
        fn.name for fn in _mutator_nodes(_tree(_DOMAIN)) if _guarded_update_targets(fn)
    }
    assert found == {"update_commitment", "record_update"}, found


def test_every_version_guarded_update_checks_for_a_lost_race():
    """Bound to the variable each UPDATE assigns, not counted — see the minutes guard."""
    for fn in _mutator_nodes(_tree(_DOMAIN)):
        targets = _guarded_update_targets(fn)
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
            f"commitments.{fn.name}: {sorted(missing)} comes from a version-guarded "
            f"UPDATE but is never checked for None."
        )


def test_the_mutator_list_is_not_hand_maintained():
    """A new writer must be audited or named in EXEMPT with a reason — not neither."""
    writers = set()
    for fn in _tree(_DOMAIN).body:
        if not isinstance(fn, ast.FunctionDef) or fn.name.startswith("_"):
            continue
        sql = _sql_text(fn).upper()
        if any(v in sql for v in ("INSERT INTO COMMITMENT", "UPDATE COMMITMENT", "DELETE FROM COMMITMENT")):
            writers.add(fn.name)
    assert writers == MUTATORS | EXEMPT, (
        f"commitments.py's SQL-writing functions are {sorted(writers)}; this file accounts "
        f"for {sorted(MUTATORS | EXEMPT)}. Audit the new one, or exempt it with a reason."
    )
    assert not MUTATORS & EXEMPT

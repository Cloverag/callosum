"""Static guard: every meeting mutation reaches an audit call with the actor (#168).

No database needed; the behavioural proof is `test_meetings_audit.py`. Same shape as the
decisions guard. One difference: `update_meeting` answers a lost race by calling
`_raise_stale_or_missing()` rather than with a `raise` statement, so that call counts as
the guard.
"""

import ast
import pathlib

import meridian.api.meetings as meetings_api
import meridian.meetings as meetings_mod

_ROUTER = pathlib.Path(meetings_api.__file__)
_DOMAIN = pathlib.Path(meetings_mod.__file__)

MUTATORS = {
    "create_meeting",
    "update_meeting",
    "transition_status",
    "assign_material",
    "unassign_material",
}


def _tree(path: pathlib.Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _mutators():
    return [n for n in _tree(_DOMAIN).body if isinstance(n, ast.FunctionDef) and n.name in MUTATORS]


def _sql_text(node: ast.AST) -> str:
    """Every string constant under `node`, joined, so an f-string reads as one statement."""
    return " ".join(
        n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)
    )


def test_every_mutating_route_passes_the_actor_to_the_domain():
    seen = set()
    for node in ast.walk(_tree(_ROUTER)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in MUTATORS:
            seen.add(node.func.attr)
            assert "actor_principal_id" in {k.arg for k in node.keywords}, (
                f"{_ROUTER.name}: {node.func.attr} is called without actor_principal_id"
            )
    assert seen == MUTATORS, f"routes never call: {sorted(MUTATORS - seen)}"


def test_no_domain_mutator_can_skip_the_audit():
    checked = set()
    for fn in _mutators():
        checked.add(fn.name)
        called = {
            n.func.id if isinstance(n.func, ast.Name) else getattr(n.func, "attr", "")
            for n in ast.walk(fn)
            if isinstance(n, ast.Call)
        }
        assert called & {"_audit_meeting", "record_audit_event"}, f"meetings.{fn.name} records no audit event"
        assert "actor_principal_id" in {a.arg for a in fn.args.kwonlyargs}, (
            f"meetings.{fn.name} takes no actor to record"
        )
    assert checked == MUTATORS, f"not found in the module: {sorted(MUTATORS - checked)}"


def test_no_audit_call_in_this_module_omits_the_actor():
    for node in ast.walk(_tree(_DOMAIN)):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "record_audit_event":
            assert "actor_principal_id" in {k.arg for k in node.keywords}, (
                f"meetings.py:{node.lineno}: record_audit_event without actor_principal_id"
            )


def test_the_audit_write_follows_the_mutation_it_records():
    for fn in _mutators():
        audit_lines = [
            n.lineno
            for n in ast.walk(fn)
            if isinstance(n, ast.Call)
            and (getattr(n.func, "id", "") == "_audit_meeting" or getattr(n.func, "attr", "") == "record_audit_event")
        ]
        assert audit_lines, fn.name
        after = [
            n.lineno
            for n in ast.walk(fn)
            if (isinstance(n, ast.Raise) or (isinstance(n, ast.Call) and getattr(n.func, "id", "") == "_raise_stale_or_missing"))
            and n.lineno > max(audit_lines)
        ]
        assert not after, f"meetings.{fn.name}: a refusal at {after} follows the audit write"


def _guarded_update_targets(fn: ast.FunctionDef) -> set[str]:
    def _is_guarded_update(node) -> bool:
        if not isinstance(node, ast.Call):
            return False
        sql = _sql_text(node)
        return "UPDATE meeting" in sql and "version = %s" in sql and "RETURNING" in sql

    return {
        n.targets[0].id
        for n in ast.walk(fn)
        if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and _is_guarded_update(n.value)
    }


def test_the_lost_race_check_actually_sees_every_guarded_update():
    found = {fn.name for fn in _mutators() if _guarded_update_targets(fn)}
    assert found == {"update_meeting", "transition_status"}, found


def test_every_version_guarded_update_checks_for_a_lost_race():
    def _refuses(node) -> bool:
        return any(
            isinstance(b, ast.Raise)
            or (isinstance(b, ast.Call) and getattr(b.func, "id", "") == "_raise_stale_or_missing")
            for b in ast.walk(node)
        )

    for fn in _mutators():
        targets = _guarded_update_targets(fn)
        guarded = {
            n.test.left.id
            for n in ast.walk(fn)
            if isinstance(n, ast.If)
            and isinstance(n.test, ast.Compare)
            and isinstance(n.test.left, ast.Name)
            and isinstance(n.test.ops[0], ast.Is)
            and isinstance(n.test.comparators[0], ast.Constant)
            and n.test.comparators[0].value is None
            and _refuses(n)
        }
        assert not targets - guarded, f"meetings.{fn.name}: {sorted(targets - guarded)} never checked for None"


def test_the_mutator_list_is_not_hand_maintained():
    writers = set()
    for fn in _tree(_DOMAIN).body:
        if isinstance(fn, ast.FunctionDef) and not fn.name.startswith("_"):
            sql = _sql_text(fn).upper()
            if any(v in sql for v in ("INSERT INTO MEETING", "UPDATE MEETING", "DELETE FROM MEETING")):
                writers.add(fn.name)
    assert writers == MUTATORS, f"meetings.py's writing functions are {sorted(writers)}; pinned {sorted(MUTATORS)}"

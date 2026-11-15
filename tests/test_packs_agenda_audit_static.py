"""Static guard: every pack/agenda mutation reaches an audit call with the actor (P5 CP5A).

No database needed. The behavioural proof is `test_packs_agenda_audit.py`; this file
is what fails in an ordinary run when a new mutator or route forgets the trail.
"""

import ast
import pathlib

import meridian.api.agenda as agenda_api
import meridian.api.packs as packs_api

_ROUTERS = [pathlib.Path(agenda_api.__file__), pathlib.Path(packs_api.__file__)]


def test_every_mutating_route_passes_the_actor_to_the_domain():
    """A route that forgets `actor_principal_id` writes an anonymous event.

    Walks the router source: every `domain.<mutator>(...)` call must carry the keyword.
    Reads (`get_*`, `list_*`) are exempt. This is the DB-free half of the guarantee; the
    other half is that the domain function records the actor it is given.
    """
    mutators = {
        "create_pack", "update_pack", "add_pack_item", "remove_pack_item", "publish_pack",
        "supersede_pack", "reorder_pack_items", "create_agenda_item", "update_agenda_item",
        "delete_agenda_item", "reorder_agenda_items",
    }
    seen = set()
    for path in _ROUTERS:
        for node in ast.walk(ast.parse(path.read_text())):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in mutators
            ):
                seen.add(node.func.attr)
                assert "actor_principal_id" in {k.arg for k in node.keywords}, (
                    f"{path.name}: {node.func.attr} is called without actor_principal_id"
                )
    assert seen == mutators, f"routes never call: {sorted(mutators - seen)}"


def test_no_domain_mutator_can_skip_the_audit():
    """Each public mutator in packs.py / agenda.py must reach an audit call."""
    import meridian.agenda as agenda_mod
    import meridian.packs as packs_mod

    for mod, names in (
        (packs_mod, ["create_pack", "update_pack", "add_pack_item", "remove_pack_item",
                     "publish_pack", "supersede_pack", "reorder_pack_items"]),
        (agenda_mod, ["create_agenda_item", "update_agenda_item", "delete_agenda_item",
                      "reorder_agenda_items"]),
    ):
        tree = ast.parse(pathlib.Path(mod.__file__).read_text())
        for fn in (n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names):
            called = {
                n.func.id if isinstance(n.func, ast.Name) else getattr(n.func, "attr", "")
                for n in ast.walk(fn)
                if isinstance(n, ast.Call)
            }
            assert called & {"_audit_pack", "_audit_item", "record_audit_event"}, (
                f"{mod.__name__}.{fn.name} records no audit event"
            )
            assert "actor_principal_id" in {a.arg for a in fn.args.kwonlyargs}, fn.name

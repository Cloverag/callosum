"""Every id an endpoint accepts is declared as a UUID, not as a string.

Fast suite — no database, no server, just the generated schema.

---------------------------------------------------------------------------
WHY THIS IS A TEST AND NOT A CONVENTION
---------------------------------------------------------------------------
Declaring `pack_id: str` and handing it to a domain function moves the parsing to
whichever `uuid.UUID()` call happens to see it first. That call raises a bare
`ValueError`, which the taxonomy in `meridian/api/errors.py` deliberately does *not*
launder into a 4xx — `_is_domain_exception` is module-scoped precisely so `ValueError`
and `RuntimeError` stay 500s. So `GET /api/packs/not-a-uuid` answered **500**: the
server reporting its own fault for a request the client got wrong.

Declaring `pack_id: uuid.UUID` moves the rejection to the framework, before any domain
code runs, and it becomes a 422 with the offending field named.

The alternative on the table was string-sniffing the exception in `classify()`:

    if isinstance(exc, ValueError) and "UUID" in str(exc): ...

That was rejected. It keys a status code on the wording of a CPython error message,
and it would catch any unrelated `ValueError` that happens to mention a UUID. Typing
the parameter removes the failure instead of classifying it.

---------------------------------------------------------------------------
WHAT THIS DOES AND DOES NOT PROVE
---------------------------------------------------------------------------
It proves every declared id parameter carries `format: uuid` in the schema, so a
malformed one is rejected by FastAPI. It does not prove the *value* names a row the
caller may read — that is RLS, and `tests/test_openapi_input_guard.py` guards the
adjacent rule that `workspace_id` is never a parameter at all.
"""

from typing import Any, Iterator

import pytest

from meridian.api.main import app

_HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}

#: Ids that are deliberately not UUIDs. Empty, and a change here should be argued:
#: every aggregate in `meridian/` keys on a `uuid` column.
EXEMPT_PARAMS: frozenset[tuple[str, str]] = frozenset()


def _id_parameters(schema: dict[str, Any]) -> Iterator[tuple[str, str, str, dict[str, Any]]]:
    """`(path, method, name, schema)` for every declared parameter naming an id."""
    for path, operations in (schema.get("paths") or {}).items():
        for method, operation in operations.items():
            if method.lower() not in _HTTP_METHODS or not isinstance(operation, dict):
                continue
            for parameter in operation.get("parameters") or []:
                if not isinstance(parameter, dict):
                    continue
                name = parameter.get("name", "")
                if not name.endswith("_id"):
                    continue
                yield path, method.lower(), name, parameter.get("schema") or {}


def _declares_uuid(param_schema: dict[str, Any]) -> bool:
    """True if this parameter is a UUID, including when wrapped in `anyOf` for optionals.

    An optional `decision_id: uuid.UUID | None` is emitted as
    `anyOf: [{format: uuid}, {type: null}]`, so a checker that only read the top level
    would pass every optional id without inspecting it.
    """
    if param_schema.get("format") == "uuid":
        return True
    for branch in param_schema.get("anyOf") or []:
        if isinstance(branch, dict) and branch.get("format") == "uuid":
            return True
    return False


def _violations(schema: dict[str, Any]) -> list[str]:
    return sorted(
        f"{method.upper()} {path} declares {name!r} as {param_schema.get('type', param_schema)!r}"
        for path, method, name, param_schema in _id_parameters(schema)
        if not _declares_uuid(param_schema) and (path, name) not in EXEMPT_PARAMS
    )


# ---------------------------------------------------------------------------
# The rule
# ---------------------------------------------------------------------------

def test_every_id_parameter_is_a_uuid():
    violations = _violations(app.openapi())
    assert not violations, "id parameters typed as strings:\n  " + "\n  ".join(violations)


def test_the_schema_actually_has_id_parameters():
    """Guard the guard: a checker that found nothing would pass."""
    found = list(_id_parameters(app.openapi()))
    assert len(found) >= 6, f"expected the CP-C read endpoints, found {found}"


# ---------------------------------------------------------------------------
# Guard the guard
# ---------------------------------------------------------------------------

class TestTheGuardCanActuallyFail:
    def test_it_catches_a_string_path_parameter(self):
        schema = {
            "paths": {
                "/api/packs/{pack_id}": {
                    "get": {"parameters": [{"name": "pack_id", "in": "path", "schema": {"type": "string"}}]}
                }
            }
        }
        assert _violations(schema) == ["GET /api/packs/{pack_id} declares 'pack_id' as 'string'"]

    def test_it_catches_a_string_inside_an_optional(self):
        # The case a top-level-only checker misses.
        schema = {
            "paths": {
                "/api/resolutions": {
                    "get": {
                        "parameters": [
                            {
                                "name": "decision_id",
                                "in": "query",
                                "schema": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                            }
                        ]
                    }
                }
            }
        }
        assert len(_violations(schema)) == 1

    def test_it_accepts_a_uuid_inside_an_optional(self):
        schema = {
            "paths": {
                "/api/resolutions": {
                    "get": {
                        "parameters": [
                            {
                                "name": "decision_id",
                                "in": "query",
                                "schema": {
                                    "anyOf": [{"type": "string", "format": "uuid"}, {"type": "null"}]
                                },
                            }
                        ]
                    }
                }
            }
        }
        assert _violations(schema) == []

    @pytest.mark.parametrize("name", ["status", "role", "active"])
    def test_it_ignores_parameters_that_are_not_ids(self, name):
        schema = {
            "paths": {"/api/x": {"get": {"parameters": [{"name": name, "schema": {"type": "string"}}]}}}
        }
        assert _violations(schema) == []

    def test_the_exemption_list_is_empty(self):
        # Pins the size, as the input guard does. Adding one should require changing a
        # test that says so out loud.
        assert EXEMPT_PARAMS == frozenset()

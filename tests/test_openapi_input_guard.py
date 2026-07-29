"""No endpoint may accept `workspace_id` or `clearance` from the client (ADR-013).

Run in the fast suite — no database, no server, just the generated schema.

---------------------------------------------------------------------------
WHY THIS IS A TEST AND NOT A CONVENTION
---------------------------------------------------------------------------
Every domain function takes `workspace_id` and passes it to `store.pg()`, which sets
the `app.workspace_id` GUC that **every RLS policy reads**. The moment a request can
influence that value, RLS is advisory for anyone who can send one:

    GET /api/resolutions?workspace_id=<someone-else's>

would be honoured, because the database was told to trust the GUC.

Code review is the wrong instrument for this. An endpoint that accepts a
`workspace_id` parameter looks entirely ordinary — it reads like every other filter,
and the harm is invisible at the call site. So the rule is mechanical: the schema is
walked, and a violation fails the build.

Same reasoning that made composite `(id, workspace_id)` foreign keys a standing rule
after p1.0.5, and that made `meridian/tenancy.py` raise rather than default.

---------------------------------------------------------------------------
WHAT THIS DOES AND DOES NOT PROVE
---------------------------------------------------------------------------
It proves no endpoint *declares* these as inputs. It cannot prove an endpoint does not
read them some other way — out of a raw `Request`, say. The positive guarantee lives
in `meridian/api/deps.py`, where `current_principal` is the only path to a `Principal`
and derives both values from the session. This test guards the boundary that guard
assumes.
"""

from typing import Any, Iterator

import pytest

from meridian.api.main import app

#: Names a client may never supply, compared after normalisation so `workspace_id`,
#: `workspaceId` and `WorkspaceID` are all the same thing.
#:
#: `sensitivity` is deliberately NOT here. Filtering documents by sensitivity is a
#: legitimate request — the clearance gate still applies underneath it — and banning
#: the word would be overreach rather than safety.
FORBIDDEN = frozenset({"workspaceid", "workspace", "clearance"})

#: The single exemption, as narrow as it can be written: one path, one method, one
#: name. `POST /auth/workspace` is where a caller *names* a workspace so it can be
#: **verified** against their membership — it is never trusted, and the verified
#: result goes into the session rather than into a query.
#:
#: Deliberately a triple rather than a path prefix. An exemption broad enough to cover
#: a future `/auth/workspace/{id}` would defeat the check it is carved out of, and
#: `clearance` is not exempt here even though `workspace_id` is.
EXEMPT: frozenset[tuple[str, str, str]] = frozenset({("/auth/workspace", "post", "workspaceid")})

_HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}


def _normalise(name: str) -> str:
    """Fold spelling variants onto one token.

    A leading `X-` is stripped first, because that is the conventional prefix for a
    custom header and `X-Clearance` is the same request input as `clearance`. Without
    this the guard passes on a header carrying exactly the value it exists to keep out
    — found by writing the header case and noticing the assertion had to be `== 0`.

    Only a *leading* `x-`/`x_` is removed, so a parameter genuinely named `x` or
    `xray` is untouched.
    """
    lowered = name.lower()
    for prefix in ("x-", "x_"):
        if lowered.startswith(prefix):
            lowered = lowered[len(prefix) :]
            break
    return lowered.replace("_", "").replace("-", "")


def _deref(schema: dict[str, Any], root: dict[str, Any]) -> dict[str, Any]:
    """Follows a local `$ref` into `components/schemas`.

    Request bodies are almost always a `$ref`, so a checker that skipped this would
    pass on every endpoint while inspecting nothing — the exact vacuous-success failure
    mode `test_the_guard_can_actually_fail` exists to rule out.
    """
    ref = schema.get("$ref")
    if not ref or not ref.startswith("#/"):
        return schema
    node: Any = root
    for part in ref.removeprefix("#/").split("/"):
        node = node.get(part, {}) if isinstance(node, dict) else {}
    return node if isinstance(node, dict) else {}


def _property_names(
    schema: dict[str, Any], root: dict[str, Any], seen: set[str] | None = None
) -> Iterator[str]:
    """Every property name reachable in a schema, following refs and composition.

    Recurses through `properties`, `items`, `additionalProperties` and the
    `allOf`/`anyOf`/`oneOf` keywords, because a forbidden field nested two objects
    deep is still a field the client supplies.

    `seen` breaks `$ref` cycles — a self-referential schema would otherwise recurse
    until the stack gave out.
    """
    if not isinstance(schema, dict):
        return
    seen = seen if seen is not None else set()

    if (ref := schema.get("$ref")) is not None:
        if ref in seen:
            return
        seen.add(ref)
        yield from _property_names(_deref(schema, root), root, seen)
        return

    for name, sub in (schema.get("properties") or {}).items():
        yield name
        yield from _property_names(sub, root, seen)

    for key in ("items", "additionalProperties"):
        if isinstance(schema.get(key), dict):
            yield from _property_names(schema[key], root, seen)

    for key in ("allOf", "anyOf", "oneOf"):
        for sub in schema.get(key) or []:
            yield from _property_names(sub, root, seen)


def _declared_inputs(operation: dict[str, Any], root: dict[str, Any]) -> Iterator[tuple[str, str]]:
    """`(where, name)` for everything an operation accepts from the client."""
    for parameter in operation.get("parameters") or []:
        if isinstance(parameter, dict) and "name" in parameter:
            yield parameter.get("in", "parameter"), parameter["name"]

    body = operation.get("requestBody") or {}
    for media_type, media in (body.get("content") or {}).items():
        for name in _property_names(media.get("schema") or {}, root):
            yield f"body:{media_type}", name


def _violations(schema: dict[str, Any]) -> list[str]:
    """Every forbidden client input in a schema, as readable messages."""
    found: list[str] = []
    for path, operations in (schema.get("paths") or {}).items():
        for method, operation in operations.items():
            if method.lower() not in _HTTP_METHODS or not isinstance(operation, dict):
                continue
            for where, name in _declared_inputs(operation, schema):
                normalised = _normalise(name)
                if normalised not in FORBIDDEN:
                    continue
                if (path, method.lower(), normalised) in EXEMPT:
                    continue
                found.append(f"{method.upper()} {path} accepts {name!r} in {where}")
    return sorted(found)


# ---------------------------------------------------------------------------
# The rule
# ---------------------------------------------------------------------------

def test_no_endpoint_accepts_workspace_id_or_clearance():
    """ADR-013, mechanically.

    If this fails, do not add an exemption — take the value from the session instead.
    The exemption list exists for one endpoint whose entire job is verifying a
    workspace the caller named, and growing it is how the rule stops meaning anything.
    """
    violations = _violations(app.openapi())
    assert not violations, "endpoints accepting session-derived values:\n  " + "\n  ".join(violations)


def test_the_schema_is_not_empty():
    """Guard the guard.

    A checker that walked nothing would pass. This fails instead if the app stops
    exposing the endpoints we know it has.
    """
    paths = app.openapi().get("paths") or {}
    assert len(paths) >= 6, f"expected the auth and health routes, found {sorted(paths)}"
    assert "/auth/workspace" in paths
    assert "/auth/context" in paths


# ---------------------------------------------------------------------------
# Guard the guard: prove the checker catches what it claims to
# ---------------------------------------------------------------------------

class TestTheGuardCanActuallyFail:
    """Without these, a broken traversal would look like a clean codebase."""

    def test_it_catches_a_query_parameter(self):
        schema = {
            "paths": {
                "/api/resolutions": {
                    "get": {"parameters": [{"name": "workspace_id", "in": "query"}]}
                }
            }
        }
        assert _violations(schema) == ["GET /api/resolutions accepts 'workspace_id' in query"]

    def test_it_catches_a_path_parameter(self):
        schema = {
            "paths": {
                "/api/w/{workspace_id}/packs": {
                    "get": {"parameters": [{"name": "workspace_id", "in": "path"}]}
                }
            }
        }
        assert len(_violations(schema)) == 1

    def test_it_catches_a_field_behind_a_ref(self):
        """The case a naive checker misses.

        FastAPI emits request bodies as `$ref` into `components/schemas`, so a
        checker that did not dereference would inspect nothing and pass on every
        endpoint with a body.
        """
        schema = {
            "paths": {
                "/api/packs": {
                    "post": {
                        "requestBody": {
                            "content": {
                                "application/json": {"schema": {"$ref": "#/components/schemas/PackIn"}}
                            }
                        }
                    }
                }
            },
            "components": {
                "schemas": {
                    "PackIn": {"properties": {"title": {"type": "string"}, "clearance": {"type": "integer"}}}
                }
            },
        }
        assert _violations(schema) == ["POST /api/packs accepts 'clearance' in body:application/json"]

    def test_it_catches_a_nested_field(self):
        # Two objects deep is still a field the client supplies.
        schema = {
            "paths": {
                "/api/x": {
                    "post": {
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "properties": {
                                            "filter": {
                                                "properties": {"workspace_id": {"type": "string"}}
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        assert len(_violations(schema)) == 1

    def test_it_catches_a_field_inside_an_array(self):
        schema = {
            "paths": {
                "/api/bulk": {
                    "post": {
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "array",
                                        "items": {"properties": {"clearance": {"type": "integer"}}},
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        assert len(_violations(schema)) == 1

    @pytest.mark.parametrize("spelling", ["workspace_id", "workspaceId", "WorkspaceID", "workspace-id"])
    def test_normalisation_defeats_renaming(self, spelling):
        """Changing the casing or the separator must not slip past."""
        schema = {"paths": {"/api/x": {"get": {"parameters": [{"name": spelling, "in": "query"}]}}}}
        assert len(_violations(schema)) == 1

    @pytest.mark.parametrize("header", ["X-Clearance", "X-Workspace-Id", "x_workspace_id"])
    def test_it_catches_a_custom_header(self, header):
        """A header is client-supplied like anything else.

        This is the case that found a hole in the first draft: `X-Clearance`
        normalised to `xclearance` and sailed through. Stripping the conventional
        `X-` prefix closes it.
        """
        schema = {"paths": {"/api/x": {"get": {"parameters": [{"name": header, "in": "header"}]}}}}
        assert len(_violations(schema)) == 1

    def test_stripping_the_x_prefix_does_not_over_reach(self):
        # Only a leading `x-`/`x_` is removed, so an ordinary parameter that happens
        # to start with an x is untouched.
        schema = {
            "paths": {
                "/api/x": {
                    "get": {
                        "parameters": [
                            {"name": "x", "in": "query"},
                            {"name": "xray", "in": "query"},
                            {"name": "workspace_name", "in": "query"},
                        ]
                    }
                }
            }
        }
        assert _violations(schema) == []

    def test_a_cycle_does_not_hang(self):
        schema = {
            "paths": {
                "/api/x": {
                    "post": {
                        "requestBody": {
                            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Node"}}}
                        }
                    }
                }
            },
            "components": {
                "schemas": {
                    "Node": {"properties": {"child": {"$ref": "#/components/schemas/Node"}}}
                }
            },
        }
        assert _violations(schema) == []


class TestTheExemptionIsNarrow:
    """One path, one method, one name — and nothing else."""

    def test_the_real_selection_endpoint_is_allowed(self):
        assert _violations(app.openapi()) == []

    def test_the_exemption_does_not_cover_clearance(self):
        # Naming a workspace to be verified is the whole job of that endpoint.
        # Naming a clearance never is.
        schema = {
            "paths": {
                "/auth/workspace": {
                    "post": {
                        "requestBody": {
                            "content": {
                                "application/json": {"schema": {"properties": {"clearance": {}}}}
                            }
                        }
                    }
                }
            }
        }
        assert len(_violations(schema)) == 1

    def test_the_exemption_does_not_cover_other_methods(self):
        schema = {
            "paths": {"/auth/workspace": {"get": {"parameters": [{"name": "workspace_id", "in": "query"}]}}}
        }
        assert len(_violations(schema)) == 1

    def test_the_exemption_does_not_cover_sibling_paths(self):
        # An exemption broad enough to cover /auth/workspace/{id} would defeat the
        # rule it is carved out of.
        schema = {
            "paths": {
                "/auth/workspace/switch": {
                    "post": {
                        "requestBody": {
                            "content": {
                                "application/json": {"schema": {"properties": {"workspace_id": {}}}}
                            }
                        }
                    }
                }
            }
        }
        assert len(_violations(schema)) == 1

    def test_there_is_exactly_one_exemption(self):
        # Pins the size. Growing this list is how the rule stops meaning anything, so
        # adding one should require changing a test that says so out loud.
        assert len(EXEMPT) == 1

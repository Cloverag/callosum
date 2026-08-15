"""The store connection defaults, pinned — because the cost of getting them wrong is a hang.

Deterministic and needs no database: these are assertions about configuration values,
not about reachability.

---------------------------------------------------------------------------
WHAT HAPPENED, SO THE ASSERTIONS BELOW READ AS SOMETHING RATHER THAN PEDANTRY
---------------------------------------------------------------------------
The defaults used to say `localhost`. `localhost` resolves to **both** `::1` and
`127.0.0.1`, and `getaddrinfo` returns the IPv6 address first. `docker-compose.yml`
publishes Postgres and Neo4j on IPv4 only (`"127.0.0.1:5433:5432"`), so nothing was
listening on `::1`: every connection opened against a dead address, waited, and only
then fell back. Measured on Windows 11 / Docker Desktop, 2026-08-15:

    127.0.0.1  ->  0.03s
    localhost  ->  8.15s   (exactly the connect_timeout supplied)

`store.pg()` opens a fresh connection per call, so the gated suite paid it hundreds of
times and presented as a hang rather than a slow run.

The second half is `connect_timeout`. libpq's default is 0 — *wait forever*. With a
half-up database the failure has no error to read and no end.

Neither of these produces a message, a warning, or a failing test. That is exactly the
kind of defect worth spending a test file on: the symptom is indistinguishable from
"the computer is being slow", so nothing else in the suite can catch a regression.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

from callosum.config import Settings, settings

#: Every default that names a network host.
_HOST_FIELDS = ("postgres_dsn", "postgres_app_dsn", "neo4j_uri", "ollama_host")

#: The two that go through libpq and therefore honour `connect_timeout`.
_LIBPQ_FIELDS = ("postgres_dsn", "postgres_app_dsn")


@pytest.fixture
def defaults() -> Settings:
    """A `Settings` built from declared defaults, ignoring any local `.env`.

    Constructing `Settings()` directly would read the developer's `.env` and assert
    against their machine instead of the committed defaults. `model_fields` holds what
    the source actually declares, which is what this file is about.
    """
    return Settings.model_construct(
        **{name: field.default for name, field in Settings.model_fields.items()}
    )


class TestNoLocalhost:
    @pytest.mark.parametrize("field", _HOST_FIELDS)
    def test_no_default_resolves_through_localhost(self, defaults: Settings, field: str):
        """`localhost` is dual-stack; the containers are not. Name the address."""
        value = getattr(defaults, field)
        assert "localhost" not in value, (
            f"{field} = {value!r} uses 'localhost', which resolves to ::1 first while "
            f"docker-compose.yml publishes IPv4 only. Use 127.0.0.1."
        )

    @pytest.mark.parametrize("field", _HOST_FIELDS)
    def test_every_default_is_the_ipv4_loopback(self, defaults: Settings, field: str):
        """Stronger than "not localhost" — a hostname needing DNS has the same problem.

        `db.internal` would pass the test above and reintroduce the fault the moment it
        resolved to an AAAA record first.
        """
        assert urlparse(getattr(defaults, field)).hostname == "127.0.0.1"


class TestConnectTimeout:
    @pytest.mark.parametrize("field", _LIBPQ_FIELDS)
    def test_the_dsn_carries_a_connect_timeout(self, defaults: Settings, field: str):
        """libpq defaults to waiting forever, which is a hang rather than an error."""
        params = parse_qs(urlparse(getattr(defaults, field)).query)
        assert "connect_timeout" in params, (
            f"{field} has no connect_timeout; libpq's default is 0 = wait forever, so a "
            f"half-up database blocks indefinitely with nothing to read."
        )

    @pytest.mark.parametrize("field", _LIBPQ_FIELDS)
    def test_the_timeout_is_short_enough_to_be_a_signal(self, defaults: Settings, field: str):
        """Bounded on both sides.

        Too low and a legitimately slow local start becomes a flake; too high and it is
        the infinite default wearing a number. A local connection that has not completed
        in 30s is not going to.
        """
        timeout = int(parse_qs(urlparse(getattr(defaults, field)).query)["connect_timeout"][0])
        assert 1 <= timeout <= 30

    def test_the_neo4j_uri_carries_no_query_parameters(self, defaults: Settings):
        """Deliberately *not* symmetrical with the Postgres DSNs.

        The Neo4j driver takes `connection_timeout` as a keyword argument and rejects
        unknown URI query parameters, so copying the `?connect_timeout=` suffix here
        would turn a slow connection into a startup error. Pinned so the symmetry is
        not "fixed" later.
        """
        assert urlparse(defaults.neo4j_uri).query == ""


class TestTheDsnsAreStillCorrect:
    """A fix that reformats a DSN can silently change which database it names."""

    def test_the_superuser_dsn_is_unchanged_apart_from_host_and_timeout(self, defaults: Settings):
        parsed = urlparse(defaults.postgres_dsn)
        assert (parsed.scheme, parsed.username, parsed.password) == (
            "postgresql", "callosum", "callosum",
        )
        assert (parsed.port, parsed.path) == (5433, "/callosum")

    def test_the_runtime_dsn_uses_the_non_superuser_role(self, defaults: Settings):
        """The RLS guarantee rests on this. A superuser here bypasses every policy."""
        parsed = urlparse(defaults.postgres_app_dsn)
        assert parsed.username == "callosum_app"
        assert (parsed.port, parsed.path) == (5433, "/callosum")

    def test_the_two_roles_are_different(self, defaults: Settings):
        assert (
            urlparse(defaults.postgres_dsn).username
            != urlparse(defaults.postgres_app_dsn).username
        )


class TestTheDefaultIsStillADefault:
    """Pinning a value is only safe if it can still be overridden.

    Without this, a future "fix" that hardcodes the address would satisfy every
    assertion above while breaking any deployment whose database is not on loopback.
    """

    def test_an_environment_variable_still_wins(self, monkeypatch):
        remote = "postgresql://someone:secret@db.example.internal:6000/prod"
        monkeypatch.setenv("POSTGRES_DSN", remote)
        settings.cache_clear()
        try:
            assert settings().postgres_dsn == remote
        finally:
            # `settings` is lru_cached, so a value read here would otherwise leak into
            # every test that runs after this one in the same process.
            settings.cache_clear()

    def test_the_cache_is_cleared_afterwards(self):
        """Guards the teardown above rather than the code — a leaked override would
        make later failures look like defects in whatever ran next."""
        assert "db.example.internal" not in settings().postgres_dsn

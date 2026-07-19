"""Meridian — the Board Operating System product layer.

DELIBERATELY separate from `callosum`, the frozen research engine (eval-baseline-v3).
Meridian *imports* Callosum as a library; it never edits it. All product code —
web API, auth, multi-tenancy, board-workflow — lives under this package. The
verified-memory core stays frozen.
"""

__version__ = "0.0.1"

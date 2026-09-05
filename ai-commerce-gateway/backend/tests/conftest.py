"""
conftest.py — top-level pytest fixtures for all backend tests.

Stubs missing system dependencies (psycopg, razorpay) at sys.modules level
before any test module is collected. This lets all pure-function and
mock-based tests run without a live Postgres or Razorpay installation.

Tests that genuinely need a DB or live Razorpay (integration tests) run
inside Docker only.
"""
import sys
from unittest.mock import MagicMock

# ── Stub psycopg (PostgreSQL driver) ──────────────────────────────────────────
try:
    import psycopg  # noqa: F401
except ModuleNotFoundError:
    psycopg_stub = MagicMock()
    psycopg_stub.__version__ = "3.2.3"
    sys.modules["psycopg"] = psycopg_stub
    sys.modules["psycopg.adapt"] = MagicMock()
    sys.modules["psycopg.types"] = MagicMock()
    sys.modules["psycopg._psycopg"] = MagicMock()

    # Prevent create_engine() from hard-crashing during import
    import sqlalchemy
    _real_create_engine = sqlalchemy.create_engine

    def _safe_create_engine(url, **kwargs):
        try:
            return _real_create_engine(url, **kwargs)
        except Exception:
            engine = MagicMock()
            engine.connect = MagicMock()
            return engine

    sqlalchemy.create_engine = _safe_create_engine

# ── Stub razorpay SDK ─────────────────────────────────────────────────────────
# The razorpay package is only installed inside Docker.
# Tests that need create_order / verify_signature use patch.object on the
# already-imported razorpay_client module, so the SDK never needs to be real.
try:
    import razorpay  # noqa: F401
except ModuleNotFoundError:
    razorpay_stub = MagicMock()
    razorpay_stub.Client = MagicMock()
    sys.modules["razorpay"] = razorpay_stub

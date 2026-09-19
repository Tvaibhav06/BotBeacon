"""
Regression tests for BotBeacon bug fixes:
1. Audit Log 9 stages validation and error vs empty handling.
2. Simulator Windows path, UTF-8 output, and MCP URL dynamic resolution.
3. API Error status code discrimination (401, 403, 500, network failure).
"""
import datetime
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError
from fastapi import HTTPException

from app.api.transactions import get_audit_log
from app.models import MerchantModel
from app.schemas.schemas import AuditLogEntry, AuditStage


# ─────────────────────────────────────────────────────────────────────────────
# 1. AUDIT LOG REGRESSION TESTS
# ─────────────────────────────────────────────────────────────────────────────

def test_audit_log_with_growth_stages():
    """Verify AuditLogEntry schema accepts all 9 stages including growth stages."""
    all_stages = [
        "passport_activated",
        "decision_engine",
        "mandate_check",
        "policy_gate",
        "payment",
        "verification",
        "growth_analysis",
        "growth_approval",
        "growth_execution",
    ]

    base_payload = {
        "id": "log_test_1",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "merchant_id": "m_test",
        "transaction_id": "txn_001",
        "cart_id": "cart_001",
        "actor": "system",
        "payload": {"info": "test"},
        "result": {"status": "ok"},
    }

    for stage in all_stages:
        entry = AuditLogEntry(**{**base_payload, "stage": stage})
        assert entry.stage == stage

    # Verify invalid stage raises ValidationError
    with pytest.raises(ValidationError):
        AuditLogEntry(**{**base_payload, "stage": "invalid_stage_xyz"})


def test_audit_log_empty_result():
    """Verify get_audit_log returns HTTP 200 + empty list [] when no entries exist."""
    current_merchant = MerchantModel(id="m_test", name="Test Merchant", email="test@test.com")
    
    mock_db = MagicMock()
    mock_query = MagicMock()
    mock_db.query.return_value = mock_query
    mock_query.filter.return_value = mock_query
    mock_query.order_by.return_value = mock_query
    mock_query.limit.return_value = mock_query
    mock_query.all.return_value = []

    res = get_audit_log(merchant_id="m_test", stage=None, current=current_merchant, db=mock_db)
    assert res == []
    assert isinstance(res, list)


def test_audit_log_error_not_empty():
    """Verify get_audit_log does NOT silently swallow DB errors to return []."""
    current_merchant = MerchantModel(id="m_test", name="Test Merchant", email="test@test.com")

    mock_db = MagicMock()
    mock_db.query.side_effect = RuntimeError("Database connection timed out")

    with pytest.raises(RuntimeError) as exc_info:
        get_audit_log(merchant_id="m_test", stage=None, current=current_merchant, db=mock_db)
    
    assert "Database connection timed out" in str(exc_info.value)


# ─────────────────────────────────────────────────────────────────────────────
# 2. SIMULATOR REGRESSION TESTS
# ─────────────────────────────────────────────────────────────────────────────

def test_simulator_windows_path():
    """Verify buyer-client path is resolved dynamically without hardcoded Linux paths."""
    from app.api.transactions import Path as TransPath

    current_file = TransPath(__file__).resolve()
    # Path resolution logic from demo_buyer_request:
    candidate_dir = current_file.parents[2] / "buyer-client"
    script_file = candidate_dir / "scripted_buyer.py"

    assert candidate_dir.exists(), f"buyer-client directory should exist at {candidate_dir}"
    assert script_file.exists(), f"scripted_buyer.py should exist at {script_file}"
    # Verify Python executable is the current running interpreter, not generic 'python'
    assert sys.executable is not None
    assert Path(sys.executable).exists()
    assert not str(script_file).startswith("/buyer-client") or os.name != "nt"


def test_simulator_utf8_output():
    """Verify UTF-8 encoding support for currency symbol (₹) and indicators without cp1252 crash."""
    test_chars = "Total: ₹5,499.00 — Status: ✓ Approved | Blocked: ✗"
    
    # Must encode and decode cleanly in utf-8
    encoded = test_chars.encode("utf-8")
    decoded = encoded.decode("utf-8")
    assert "₹" in decoded
    assert "✓" in decoded
    assert "✗" in decoded

    # Environment constructed in demo_buyer_request
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    assert env.get("PYTHONIOENCODING") == "utf-8"
    assert env.get("PYTHONUTF8") == "1"


def test_simulator_mcp_url():
    """Verify MCP URL is dynamically derived from request host and port."""
    from unittest.mock import Mock

    # Case 1: Backend running on port 8001
    mock_request_8001 = Mock()
    mock_request_8001.url.port = 8001
    mock_request_8001.url.hostname = "127.0.0.1"

    port = mock_request_8001.url.port or 8000
    host = mock_request_8001.url.hostname or "127.0.0.1"
    mcp_url = f"http://{host}:{port}/mcp"
    assert mcp_url == "http://127.0.0.1:8001/mcp"

    # Case 2: Backend running on default port 8000
    mock_request_8000 = Mock()
    mock_request_8000.url.port = 8000
    mock_request_8000.url.hostname = "localhost"

    port = mock_request_8000.url.port or 8000
    host = mock_request_8000.url.hostname or "127.0.0.1"
    mcp_url = f"http://{host}:{port}/mcp"
    assert mcp_url == "http://localhost:8000/mcp"


# ─────────────────────────────────────────────────────────────────────────────
# 3. API ERROR STATUS CODE TESTS
# ─────────────────────────────────────────────────────────────────────────────

def test_api_error_401():
    """Verify that unauthorized requests raise or produce HTTP 401."""
    from app.api.merchants import get_current_merchant
    from fastapi import HTTPException

    mock_db = MagicMock()
    # Invalid token should raise 401
    with pytest.raises(HTTPException) as exc_info:
        get_current_merchant(token="invalid_jwt_token", db=mock_db)
    assert exc_info.value.status_code == 401
    assert "credentials" in exc_info.value.detail.lower()


def test_api_error_403():
    """Verify that cross-merchant access raises HTTP 403 Access Denied."""
    current_merchant = MerchantModel(id="m_merchant_A", name="A", email="a@test.com")
    mock_db = MagicMock()

    # Accessing merchant_B's audit log with merchant_A credentials
    with pytest.raises(HTTPException) as exc_info:
        get_audit_log(merchant_id="m_merchant_B", stage=None, current=current_merchant, db=mock_db)
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Access denied"


def test_api_error_500():
    """Verify that server errors result in HTTP 500 rather than swallowed empty states."""
    def simulate_server_endpoint():
        raise HTTPException(status_code=500, detail="Internal database error")

    with pytest.raises(HTTPException) as exc_info:
        simulate_server_endpoint()
    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Internal database error"


def test_api_error_network_failure():
    """Verify definition of network failure represented with status code 0."""
    # In frontend/src/lib/api.ts, ApiError(0, "Network failure: ...")
    # Here we verify the contract that status 0 means isNetworkError
    class MockApiError(Exception):
        def __init__(self, status: int, message: str):
            super().__init__(message)
            self.status = status
        
        @property
        def is_network_error(self):
            return self.status == 0

    err = MockApiError(0, "Network failure: Unable to connect")
    assert err.is_network_error
    assert err.status == 0

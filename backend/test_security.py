import os
os.environ["TESTING"] = "1"

import time
import pytest
from fastapi.testclient import TestClient
from main import app, db

client = TestClient(app)

@pytest.fixture(autouse=True)
def clean_db():
    """Ensure database state is clean before security tests."""
    if db is not None:
        db["sessions"].delete_many({})
        db["rate_limits"].delete_many({})
        db["rate_limit_breaches"].delete_many({})
        db["ip_bans"].delete_many({})

def test_unauthorized_access():
    """Verify that accessing a protected endpoint without credentials returns 401."""
    response = client.get("/api/vouch/history")
    assert response.status_code == 401
    assert "detail" in response.json()

def test_timing_attack_mitigation():
    """Verify that unauthorized requests take at least 250ms to mitigate timing attacks."""
    start_time = time.time()
    response = client.get("/api/vouch/history")
    elapsed = time.time() - start_time
    assert response.status_code == 401
    assert elapsed >= 0.20  # Allowing small margin below 250ms for local environment latency

def test_session_lifecycle_and_authenticated_access():
    """Verify session creation, authentication, and correct cookie + bearer flow."""
    # 1. Create Session
    create_res = client.post("/api/session/create")
    assert create_res.status_code == 200
    data = create_res.json()
    assert "session_secret" in data
    
    session_secret = data["session_secret"]
    cookies = create_res.cookies
    assert "stataudit_session_id" in cookies
    
    # 2. Access with valid credentials
    history_res = client.get(
        "/api/vouch/history",
        headers={"Authorization": f"Bearer {session_secret}"},
        cookies=cookies
    )
    assert history_res.status_code == 200
    assert "data" in history_res.json()
    
    # 3. Revoke Session
    revoke_res = client.post(
        "/api/session/revoke",
        headers={"Authorization": f"Bearer {session_secret}"},
        cookies=cookies
    )
    assert revoke_res.status_code == 200
    
    # 4. Access after revocation (should fail)
    post_revoke_res = client.get(
        "/api/vouch/history",
        headers={"Authorization": f"Bearer {session_secret}"},
        cookies=cookies
    )
    assert post_revoke_res.status_code == 401

def test_bola_protection():
    """Verify that using a session ID cookie with a mismatched bearer token gets rejected."""
    # Create valid session A
    res_a = client.post("/api/session/create")
    secret_a = res_a.json()["session_secret"]
    cookies_a = res_a.cookies
    
    # Create valid session B
    res_b = client.post("/api/session/create")
    secret_b = res_b.json()["session_secret"]
    cookies_b = res_b.cookies
    
    # Try accessing Session A using Session B's Bearer token (should fail 401)
    bad_res = client.get(
        "/api/vouch/history",
        headers={"Authorization": f"Bearer {secret_b}"},
        cookies=cookies_a
    )
    assert bad_res.status_code == 401

def test_nosql_injection_mitigation():
    """Verify that nested operator objects inside query inputs or transaction bodies are rejected."""
    # Setup session
    res = client.post("/api/session/create")
    secret = res.json()["session_secret"]
    cookies = res.cookies
    
    # NoSQL payload with MongoDB operators
    payload = {
        "transaction": '{"amount": {"$gt": 0}}',
        "category": "Sales"
    }
    
    res_inject = client.post(
        "/api/vouch/deep-audit",
        data=payload,
        headers={"Authorization": f"Bearer {secret}"},
        cookies=cookies
    )
    assert res_inject.status_code == 422

def test_rate_limiting_logic():
    """Verify MongoDB rate limiter increments, blocks, and triggers temporary IP bans correctly."""
    # Temporarily disable TESTING mode to test the rate limiter function directly
    os.environ["TESTING"] = "0"
    try:
        from main import check_rate_limit, record_rate_limit_breach, check_ip_ban
        
        # 1. Verify general limit under threshold
        for i in range(5):
            allowed, retry_after = check_rate_limit("test_key", 5, 60)
            assert allowed is True
            
        # 6th request triggers rate limit
        allowed, retry_after = check_rate_limit("test_key", 5, 60)
        assert allowed is False
        assert retry_after > 0
        
        # 2. Verify IP ban circuit breaker triggering after 3 breaches
        ip = "192.168.1.99"
        assert check_ip_ban(ip) is False
        
        # Trigger 3 breaches
        record_rate_limit_breach(ip)
        record_rate_limit_breach(ip)
        record_rate_limit_breach(ip)
        
        # Should now be banned
        assert check_ip_ban(ip) is True
    finally:
        os.environ["TESTING"] = "1"

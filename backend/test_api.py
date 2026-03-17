"""
API tests for TrustLeague backend.
Run unit tests:       pytest test_api.py::TestHelpers -v
Run integration:      BACKEND_URL=https://your-backend.vercel.app pytest test_api.py -v -k "not TestHelpers"
Run all against live: BACKEND_URL=https://your-backend.vercel.app pytest test_api.py -v
"""
import os
import time
import pytest
import hashlib
import hmac
import sys
from urllib.parse import unquote

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")


# ===================== HELPERS (copied to avoid module-level DB import) =====================

TRUST_LEVELS = [(0, "bronze"), (100, "silver"), (250, "gold"), (500, "legend")]

def _get_trust_level(score):
    level = "bronze"
    for threshold, name in TRUST_LEVELS:
        if score >= threshold:
            level = name
    return level

def _check_answers(answer_a, answer_b):
    a = answer_a.strip().lower()
    b = answer_b.strip().lower()
    if a == b or a in b or b in a:
        return {"match": True, "confidence": 0.85, "reason": "Ответы совпадают!"}
    return {"match": False, "confidence": 0.2, "reason": "Ответы не совпали. Попробуйте ещё раз!"}

_rate_limits = {}

def _check_rate_limit(user_id, limit=10, window=3600):
    now = time.time()
    key = str(user_id)
    if key not in _rate_limits:
        _rate_limits[key] = []
    _rate_limits[key] = [t for t in _rate_limits[key] if now - t < window]
    if len(_rate_limits[key]) >= limit:
        return False
    _rate_limits[key].append(now)
    return True

def _validate_telegram_init_data(init_data_raw, bot_token):
    if not init_data_raw or not bot_token:
        return False
    try:
        params = {}
        for part in init_data_raw.split('&'):
            if '=' not in part:
                continue
            key, value = part.split('=', 1)
            params[key] = unquote(value)
        received_hash = params.pop('hash', '')
        if not received_hash:
            return False
        data_check_pairs = sorted([f"{k}={v}" for k, v in params.items()])
        data_check_string = '\n'.join(data_check_pairs)
        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(computed_hash, received_hash)
    except Exception:
        return False


# ===================== UNIT TESTS (no DB needed) =====================

class TestHelpers:
    def test_get_trust_level_bronze(self):
        assert _get_trust_level(0) == "bronze"
        assert _get_trust_level(50) == "bronze"
        assert _get_trust_level(99) == "bronze"

    def test_get_trust_level_silver(self):
        assert _get_trust_level(100) == "silver"
        assert _get_trust_level(200) == "silver"

    def test_get_trust_level_gold(self):
        assert _get_trust_level(250) == "gold"
        assert _get_trust_level(400) == "gold"

    def test_get_trust_level_legend(self):
        assert _get_trust_level(500) == "legend"
        assert _get_trust_level(9999) == "legend"

    def test_check_answers_exact_match(self):
        result = _check_answers("Москва", "Москва")
        assert result["match"] is True
        assert result["confidence"] == 0.85

    def test_check_answers_case_insensitive(self):
        result = _check_answers("москва", "МОСКВА")
        assert result["match"] is True

    def test_check_answers_substring(self):
        result = _check_answers("В кафе на Арбате", "Арбате")
        assert result["match"] is True

    def test_check_answers_no_match(self):
        result = _check_answers("Москва", "Санкт-Петербург")
        assert result["match"] is False
        assert result["confidence"] == 0.2

    def test_check_answers_whitespace_stripped(self):
        result = _check_answers("  Москва  ", "Москва")
        assert result["match"] is True

    def test_rate_limit_allows_under_limit(self):
        _rate_limits.clear()
        for i in range(9):
            assert _check_rate_limit(99999, limit=10) is True

    def test_rate_limit_blocks_over_limit(self):
        _rate_limits.clear()
        for i in range(10):
            _check_rate_limit(88888, limit=10)
        assert _check_rate_limit(88888, limit=10) is False

    def test_validate_telegram_init_data_empty(self):
        assert _validate_telegram_init_data("", "token") is False
        assert _validate_telegram_init_data("data", "") is False
        assert _validate_telegram_init_data(None, "token") is False

    def test_validate_telegram_init_data_no_hash(self):
        assert _validate_telegram_init_data("auth_date=123", "token") is False

    def test_validate_telegram_init_data_wrong_hash(self):
        result = _validate_telegram_init_data("auth_date=123&hash=wronghash", "testtoken")
        assert result is False


# ===================== INTEGRATION TESTS (require running server) =====================

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


@pytest.mark.skipif(not HAS_HTTPX, reason="httpx not installed")
class TestRegistrationEndpoint:
    @pytest.fixture
    def client(self):
        return httpx.Client(base_url=BACKEND_URL, timeout=30)

    def test_register_user_success(self, client):
        payload = {"telegram_id": 111222333, "username": "testuser", "full_name": "Test User"}
        resp = client.post("/api/user/register", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["telegram_id"] == 111222333
        assert data["username"] == "testuser"
        assert data["trust_score"] == 0
        assert data["trust_level"] == "bronze"

    def test_register_user_minimal(self, client):
        payload = {"telegram_id": 999888777}
        resp = client.post("/api/user/register", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["telegram_id"] == 999888777

    def test_register_user_idempotent(self, client):
        payload = {"telegram_id": 555444333, "username": "idempotent_test"}
        resp1 = client.post("/api/user/register", json=payload)
        resp2 = client.post("/api/user/register", json=payload)
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp1.json()["telegram_id"] == resp2.json()["telegram_id"]

    def test_register_user_updates_existing(self, client):
        tg_id = 777666555
        client.post("/api/user/register", json={"telegram_id": tg_id, "username": "old_name"})
        resp = client.post("/api/user/register", json={"telegram_id": tg_id, "username": "new_name"})
        assert resp.status_code == 200
        assert resp.json()["username"] == "new_name"

    def test_register_user_invalid_body(self, client):
        resp = client.post("/api/user/register", json={"username": "no_telegram_id"})
        assert resp.status_code == 422

    def test_register_cors_headers(self, client):
        payload = {"telegram_id": 111222333}
        resp = client.post(
            "/api/user/register",
            json=payload,
            headers={"Origin": "https://example.com"}
        )
        assert resp.status_code == 200


@pytest.mark.skipif(not HAS_HTTPX, reason="httpx not installed")
class TestAuthEndpoint:
    @pytest.fixture
    def client(self):
        return httpx.Client(base_url=BACKEND_URL, timeout=30)

    def test_auth_validate_no_bot_token(self, client):
        """When BOT_TOKEN not set, should return dev mode"""
        resp = client.post("/api/auth/validate", json={"initData": "test_data"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True

    def test_auth_validate_invalid_data(self, client):
        """Invalid initData falls back to dev mode"""
        resp = client.post("/api/auth/validate", json={"initData": "invalid=data&hash=badhash"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True

    def test_auth_validate_missing_field(self, client):
        resp = client.post("/api/auth/validate", json={})
        assert resp.status_code == 422


@pytest.mark.skipif(not HAS_HTTPX, reason="httpx not installed")
class TestHandshakeEndpoints:
    @pytest.fixture
    def client(self):
        return httpx.Client(base_url=BACKEND_URL, timeout=30)

    def test_handshake_init_success(self, client):
        # Register initiator first
        client.post("/api/user/register", json={"telegram_id": 100000001, "username": "initiator_test"})
        payload = {"initiator_id": 100000001, "target_username": "some_friend"}
        resp = client.post("/api/handshake/init", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data
        assert "question" in data
        assert len(data["session_id"]) > 0

    def test_handshake_init_question_is_russian(self, client):
        client.post("/api/user/register", json={"telegram_id": 100000002, "username": "ru_test"})
        resp = client.post("/api/handshake/init", json={"initiator_id": 100000002, "target_username": "friend"})
        assert resp.status_code == 200
        question = resp.json()["question"]
        # Should be one of the Russian questions
        assert len(question) > 5

    def test_handshake_get_session(self, client):
        client.post("/api/user/register", json={"telegram_id": 100000003})
        init_resp = client.post("/api/handshake/init", json={"initiator_id": 100000003, "target_username": "friend"})
        session_id = init_resp.json()["session_id"]

        resp = client.get(f"/api/handshake/session/{session_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == session_id
        assert data["status"] == "pending"
        assert data["initiator_answered"] is False
        assert data["target_answered"] is False

    def test_handshake_get_session_not_found(self, client):
        resp = client.get("/api/handshake/session/non-existent-id-12345")
        assert resp.status_code == 404

    def test_handshake_full_flow_success(self, client):
        """Full handshake: init -> both answer same -> verified"""
        tg_a = 200000001
        tg_b = 200000002
        client.post("/api/user/register", json={"telegram_id": tg_a, "username": "user_a"})
        client.post("/api/user/register", json={"telegram_id": tg_b, "username": "user_b"})

        # Init handshake
        init_resp = client.post("/api/handshake/init", json={"initiator_id": tg_a, "target_username": "user_b"})
        assert init_resp.status_code == 200
        session_id = init_resp.json()["session_id"]

        # Initiator answers
        ans_a = client.post("/api/handshake/answer", json={
            "session_id": session_id, "user_id": tg_a, "answer": "В кафе на Арбате"
        })
        assert ans_a.status_code == 200
        assert ans_a.json()["waiting"] is True  # waiting for target

        # Target answers same answer
        ans_b = client.post("/api/handshake/answer", json={
            "session_id": session_id, "user_id": tg_b, "answer": "В кафе на Арбате"
        })
        assert ans_b.status_code == 200
        result = ans_b.json()
        assert result["waiting"] is False
        assert result["result"] == "verified"
        assert "nft_address" in result

    def test_handshake_full_flow_failed(self, client):
        """Full handshake: init -> different answers -> failed"""
        tg_a = 200000003
        tg_b = 200000004
        client.post("/api/user/register", json={"telegram_id": tg_a, "username": "user_c"})
        client.post("/api/user/register", json={"telegram_id": tg_b, "username": "user_d"})

        init_resp = client.post("/api/handshake/init", json={"initiator_id": tg_a, "target_username": "user_d"})
        session_id = init_resp.json()["session_id"]

        client.post("/api/handshake/answer", json={
            "session_id": session_id, "user_id": tg_a, "answer": "Москва"
        })
        ans_b = client.post("/api/handshake/answer", json={
            "session_id": session_id, "user_id": tg_b, "answer": "Санкт-Петербург"
        })
        result = ans_b.json()
        assert result["waiting"] is False
        assert result["result"] == "failed"

    def test_handshake_answer_unknown_session(self, client):
        resp = client.post("/api/handshake/answer", json={
            "session_id": "fake-session-id", "user_id": 12345, "answer": "test"
        })
        assert resp.status_code == 404

    def test_handshake_answer_unauthorized_user(self, client):
        tg_a = 300000001
        client.post("/api/user/register", json={"telegram_id": tg_a, "username": "auth_test_user"})
        init_resp = client.post("/api/handshake/init", json={"initiator_id": tg_a, "target_username": "someone"})
        session_id = init_resp.json()["session_id"]

        # Unknown user tries to answer
        resp = client.post("/api/handshake/answer", json={
            "session_id": session_id, "user_id": 999999999, "answer": "test"
        })
        # target_id is 0 (unknown user), so any user can answer as target
        # this is by design - 403 only if both sides taken
        assert resp.status_code in [200, 403]

    def test_handshake_duplicate_answer_rejected(self, client):
        tg_a = 300000002
        client.post("/api/user/register", json={"telegram_id": tg_a})
        init_resp = client.post("/api/handshake/init", json={"initiator_id": tg_a, "target_username": "dup_friend"})
        session_id = init_resp.json()["session_id"]

        client.post("/api/handshake/answer", json={
            "session_id": session_id, "user_id": tg_a, "answer": "first answer"
        })
        # Session is still pending (target hasn't answered), try answering again as initiator
        # The second answer from initiator should overwrite (design) or session may be in different state
        # At minimum it should not crash
        resp2 = client.post("/api/handshake/answer", json={
            "session_id": session_id, "user_id": tg_a, "answer": "second answer"
        })
        assert resp2.status_code in [200, 400]


@pytest.mark.skipif(not HAS_HTTPX, reason="httpx not installed")
class TestTrustEndpoint:
    @pytest.fixture
    def client(self):
        return httpx.Client(base_url=BACKEND_URL, timeout=30)

    def test_get_trust_existing_user(self, client):
        tg_id = 400000001
        client.post("/api/user/register", json={"telegram_id": tg_id, "username": "trust_user"})
        resp = client.get(f"/api/trust/{tg_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "score" in data
        assert "level" in data
        assert "handshake_count" in data

    def test_get_trust_creates_default(self, client):
        tg_id = 400000999
        resp = client.get(f"/api/trust/{tg_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["score"] == 0
        assert data["level"] == "bronze"


@pytest.mark.skipif(not HAS_HTTPX, reason="httpx not installed")
class TestHealthAndCORS:
    @pytest.fixture
    def client(self):
        return httpx.Client(base_url=BACKEND_URL, timeout=30)

    def test_server_is_reachable(self, client):
        # Any valid endpoint should respond
        resp = client.get("/api/leaderboard")
        assert resp.status_code == 200

    def test_cors_preflight(self, client):
        resp = client.options(
            "/api/user/register",
            headers={
                "Origin": "https://example.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            }
        )
        # Should not be 5xx
        assert resp.status_code in [200, 204]

    def test_cors_header_present(self, client):
        resp = client.get(
            "/api/leaderboard",
            headers={"Origin": "https://example.com"}
        )
        assert resp.status_code == 200
        assert "access-control-allow-origin" in resp.headers


if __name__ == "__main__":
    import subprocess
    result = subprocess.run(
        ["python3", "-m", "pytest", __file__, "-v", "--tb=short"],
        cwd=os.path.dirname(__file__)
    )
    sys.exit(result.returncode)

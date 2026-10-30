import time

from fastapi.testclient import TestClient

from app.main import create_app
from app.ratelimit import MinuteLimiter
from tests.conftest import parse_sse


def send(client, message="Soru", session_id=None):
    return client.post("/api/chat", json={"message": message, "session_id": session_id})


def test_per_minute_limit(make_settings, fake_llm):
    settings = make_settings(rate_per_ip_per_minute=2)
    with TestClient(create_app(settings, llm=fake_llm)) as client:
        assert send(client).status_code == 200
        assert send(client).status_code == 200
        res = send(client)
    assert res.status_code == 429
    assert "dakika" in res.json()["detail"]
    assert len(fake_llm.calls) == 2


def test_per_ip_daily_limit_counts_across_sessions(make_settings, fake_llm):
    settings = make_settings(rate_per_ip_per_day=2)
    with TestClient(create_app(settings, llm=fake_llm)) as client:
        send(client)
        send(client)  # her çağrı yeni oturum açıyor
        res = send(client)
    assert res.status_code == 429
    assert "linkedin.com/in/test" in res.json()["detail"]


def test_daily_limit_survives_restart(make_settings, fake_llm):
    settings = make_settings(rate_per_ip_per_day=1)
    with TestClient(create_app(settings, llm=fake_llm)) as client:
        assert send(client).status_code == 200
    with TestClient(create_app(settings, llm=fake_llm)) as client:
        assert send(client).status_code == 429


def test_global_daily_limit(make_settings, fake_llm):
    settings = make_settings(rate_global_per_day=1)
    with TestClient(create_app(settings, llm=fake_llm)) as client:
        send(client)
        res = send(client)
    assert res.status_code == 503


def test_turn_limit_per_session(make_settings, fake_llm):
    settings = make_settings(max_turns_per_session=2)
    with TestClient(create_app(settings, llm=fake_llm)) as client:
        session_id = parse_sse(send(client).text)[0][1]["session_id"]
        assert send(client, session_id=session_id).status_code == 200
        res = send(client, session_id=session_id)
    assert res.status_code == 429
    assert "yeni bir sohbet" in res.json()["detail"]


def test_history_window(make_settings, fake_llm):
    settings = make_settings(history_messages=2)
    with TestClient(create_app(settings, llm=fake_llm)) as client:
        session_id = parse_sse(send(client, "1").text)[0][1]["session_id"]
        send(client, "2", session_id=session_id)
        send(client, "3", session_id=session_id)
    sent = fake_llm.calls[-1]
    # Pencere 2 mesaj: önceki soru-cevap çifti + yeni soru.
    assert [m["content"] for m in sent[1:]] == ["2", "Merhaba, ben asistanım.", "3"]


def test_history_window_never_starts_with_assistant(make_settings, fake_llm):
    settings = make_settings(history_messages=3)
    with TestClient(create_app(settings, llm=fake_llm)) as client:
        session_id = parse_sse(send(client, "1").text)[0][1]["session_id"]
        send(client, "2", session_id=session_id)
        send(client, "3", session_id=session_id)
    assert [m["role"] for m in fake_llm.calls[-1]] == ["system", "user", "assistant", "user"]


def test_minute_limiter_window_slides():
    limiter = MinuteLimiter(limit=1, window_seconds=0.05)
    assert limiter.allow("a")
    assert not limiter.allow("a")
    assert limiter.allow("b")
    time.sleep(0.06)
    assert limiter.allow("a")

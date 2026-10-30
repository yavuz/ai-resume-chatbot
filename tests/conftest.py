import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.llm import StreamEvent, Usage
from app.main import create_app

ROOT = Path(__file__).resolve().parent.parent


class FakeLLM:
    """Gerçek API'ye gitmeden cevap akıtan sahte istemci. Gelen mesajları kaydeder."""

    model = "fake-model"

    def __init__(self):
        self.calls: list[list[dict[str, str]]] = []
        self.reply = ["Merhaba, ", "ben asistanım."]
        self.fail_with: Exception | None = None

    async def stream(self, messages):
        self.calls.append(list(messages))
        if self.fail_with:
            raise self.fail_with
        for part in self.reply:
            yield StreamEvent(delta=part)
        yield StreamEvent(finish_reason="stop")
        yield StreamEvent(usage=Usage(prompt_tokens=100, completion_tokens=10, cached_tokens=80))


@pytest.fixture
def make_settings(tmp_path):
    profile = tmp_path / "profile.md"
    profile.write_text("Ayşe Python ve LLM ile çalışır.", encoding="utf-8")

    def _make(**overrides) -> Settings:
        values = dict(
            llm_base_url="http://127.0.0.1:1/v1",
            llm_api_key="test",
            llm_model="fake-model",
            owner_name="Ayşe",
            contact_url="https://www.linkedin.com/in/test/",
            profile_path=profile,
            system_prompt_path=ROOT / "prompts" / "system.md",
            db_path=tmp_path / "chatbot.db",
            ip_hash_salt="test-salt",
        )
        values.update(overrides)
        return Settings(_env_file=None, **values)

    return _make


@pytest.fixture
def fake_llm():
    return FakeLLM()


@pytest.fixture
def client(make_settings, fake_llm):
    app = create_app(make_settings(), llm=fake_llm)
    with TestClient(app) as c:
        yield c


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for raw in text.strip().split("\n\n"):
        event, data = "message", {}
        for line in raw.split("\n"):
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data = json.loads(line[5:].strip())
        events.append((event, data))
    return events

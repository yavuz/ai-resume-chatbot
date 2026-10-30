import asyncio
import hashlib
import json
import logging
import re
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.config import Settings
from app.llm import LLMClient, OpenAICompatibleClient, Usage
from app.prompt import build_system_prompt
from app.ratelimit import MinuteLimiter
from app.store import Store

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
_REF_INVALID = re.compile(r"[^a-z0-9_-]")


class ChatRequest(BaseModel):
    message: str = Field(max_length=10_000)
    session_id: str | None = Field(default=None, max_length=64)
    # Başvuru linkindeki ?c=<şirket> değeri; hangi şirketin ne sorduğunu görmek için.
    ref: str | None = Field(default=None, max_length=200)


def _clean_ref(ref: str | None) -> str | None:
    if not ref:
        return None
    return _REF_INVALID.sub("", ref.lower())[:64] or None


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _error(status: int, detail: str) -> JSONResponse:
    return JSONResponse({"detail": detail}, status_code=status)


def create_app(settings: Settings | None = None, llm: LLMClient | None = None) -> FastAPI:
    settings = settings or Settings()
    system_prompt = build_system_prompt(
        settings.system_prompt_path, settings.profile_path, settings.contact_url
    )
    store = Store(settings.db_path)
    llm = llm or OpenAICompatibleClient(settings)
    minute_limiter = MinuteLimiter(settings.rate_per_ip_per_minute)
    contact_hint = f"Yavuz'a doğrudan LinkedIn üzerinden ulaşabilirsiniz: {settings.contact_url}"
    fallback_reply = f"Şu an yanıt veremiyorum. {contact_hint}"

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        store.close()

    app = FastAPI(
        title="AI Resume Chatbot",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    def hash_ip(ip: str) -> str:
        return hashlib.sha256(f"{settings.ip_hash_salt}:{ip}".encode()).hexdigest()[:32]

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/healthz")
    def healthz() -> dict:
        # LLM'e gitmez; uptime kontrolü kota harcamasın.
        store.ping()
        return {"status": "ok"}

    @app.get("/api/config")
    def public_config() -> dict:
        return {"contact_url": settings.contact_url, "max_message_chars": settings.max_message_chars}

    @app.post("/api/chat")
    async def chat(body: ChatRequest, request: Request):
        message = body.message.strip()
        if not message:
            return _error(400, "Mesaj boş olamaz.")
        if len(message) > settings.max_message_chars:
            return _error(400, f"Mesaj en fazla {settings.max_message_chars} karakter olabilir.")

        # Nginx arkasında uvicorn --proxy-headers sayesinde bu gerçek istemci IP'si olur.
        ip_hash = hash_ip(request.client.host if request.client else "unknown")
        if not minute_limiter.allow(ip_hash):
            return _error(429, "Çok hızlı mesaj gönderiyorsunuz. Lütfen bir dakika sonra tekrar deneyin.")
        if store.count_user_messages_by_ip(ip_hash) >= settings.rate_per_ip_per_day:
            return _error(429, f"Bugünlük mesaj sınırına ulaştınız. {contact_hint}")
        if store.count_user_messages_total() >= settings.rate_global_per_day:
            return _error(503, f"Asistan bugün çok yoğun. {contact_hint}")

        # Geçmiş yalnızca sunucuda tutulur; istemci sadece oturum kimliğini bilir.
        session_id = body.session_id
        if not session_id or not store.session_exists(session_id):
            session_id = store.create_session(
                ip_hash, request.headers.get("user-agent", "")[:300], _clean_ref(body.ref)
            )
        elif store.count_user_messages_in_session(session_id) >= settings.max_turns_per_session:
            return _error(
                429, "Bu sohbet için mesaj sınırına ulaşıldı. Sayfayı yenileyerek yeni bir sohbet başlatabilirsiniz."
            )

        history = store.history(session_id, settings.history_messages)
        store.add_message(session_id, "user", message)
        messages = [
            {"role": "system", "content": system_prompt},
            *history,
            {"role": "user", "content": message},
        ]
        return StreamingResponse(
            stream_reply(session_id, messages),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    async def stream_reply(session_id: str, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        started = time.monotonic()
        parts: list[str] = []
        usage = Usage()
        finish_reason: str | None = None
        error: str | None = None

        try:
            yield _sse("session", {"session_id": session_id})
            try:
                async for event in llm.stream(messages):
                    if event.delta:
                        parts.append(event.delta)
                        yield _sse("delta", {"text": event.delta})
                    if event.finish_reason:
                        finish_reason = event.finish_reason
                    if event.usage:
                        usage = event.usage
                if not parts:
                    # Örn. safety filtresi (finish_reason=content_filter) ya da boş cevap.
                    error = f"empty_response (finish_reason={finish_reason})"
            except Exception as exc:
                logger.exception("LLM çağrısı başarısız")
                error = f"{type(exc).__name__}: {exc}"[:500]

            if error:
                yield _sse("error", {"text": fallback_reply})
            yield _sse("done", {})
        except (asyncio.CancelledError, GeneratorExit):
            error = error or "client_disconnected"
            raise
        finally:
            store.add_message(
                session_id,
                "assistant",
                "".join(parts) or fallback_reply,
                model=llm.model,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                cached_tokens=usage.cached_tokens,
                latency_ms=int((time.monotonic() - started) * 1000),
                finish_reason=finish_reason,
                error=error,
            )

    return app

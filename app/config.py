from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM (OpenAI uyumlu endpoint; varsayılan resmi Gemini API)
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    llm_temperature: float = 0.2
    llm_max_tokens: int = 1024
    llm_reasoning_effort: str = ""
    llm_timeout_seconds: float = 60.0
    # Token kullanımını loglamak için; endpoint stream_options desteklemiyorsa kapat.
    llm_stream_usage: bool = True

    # Botun temsil ettiği kişi. Kurallarda, arayüzde ve eval'lerde kullanılır.
    owner_name: str
    contact_url: str
    contact_label: str = "LinkedIn"
    # Sayfa başlığı; boşsa "<OWNER_NAME> · Yapay Zekâ Asistanı".
    chat_title: str = ""

    profile_path: Path = Path("profile.md")
    system_prompt_path: Path = Path("prompts/system.md")
    db_path: Path = Path("data/chatbot.db")
    ip_hash_salt: str

    rate_per_ip_per_minute: int = 6
    rate_per_ip_per_day: int = 60
    rate_global_per_day: int = 1000
    max_message_chars: int = 1000
    max_turns_per_session: int = 30
    history_messages: int = 20

from app.config import Settings


def placeholders(settings: Settings) -> dict[str, str]:
    """Şablonlardaki {{AD}} yer tutucularının değerleri (prompt, arayüz)."""
    return {
        "OWNER_NAME": settings.owner_name,
        "CONTACT_LABEL": settings.contact_label,
        "CONTACT_URL": settings.contact_url,
        "TITLE": settings.chat_title or f"{settings.owner_name} · Yapay Zekâ Asistanı",
    }


def fill(template: str, values: dict[str, str]) -> str:
    for key, value in values.items():
        template = template.replace("{{" + key + "}}", value)
    return template


def build_system_prompt(settings: Settings) -> str:
    """Kural şablonunu ayarlar ve profil metniyle birleştirir.

    Sonuç her istekte birebir aynı kalır; böylece sağlayıcı tarafındaki
    prefix (implicit) cache'ten faydalanabilir.
    """
    if not settings.profile_path.exists():
        raise FileNotFoundError(
            f"Profil dosyası bulunamadı: {settings.profile_path}. "
            "profile.example.md dosyasını profile.md olarak kopyalayıp doldur."
        )
    template = settings.system_prompt_path.read_text(encoding="utf-8")
    profile = settings.profile_path.read_text(encoding="utf-8").strip()
    # Profil en son eklenir; içindeki metin yer tutucu olarak yorumlanmasın.
    return fill(template, placeholders(settings)).replace("{{PROFILE}}", profile)

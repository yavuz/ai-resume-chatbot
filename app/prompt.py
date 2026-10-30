from pathlib import Path


def build_system_prompt(template_path: Path, profile_path: Path, contact_url: str) -> str:
    """Kural şablonunu profil metniyle birleştirir.

    Sonuç her istekte birebir aynı kalır; böylece sağlayıcı tarafındaki
    prefix (implicit) cache'ten faydalanabilir.
    """
    if not profile_path.exists():
        raise FileNotFoundError(
            f"Profil dosyası bulunamadı: {profile_path}. "
            "profile.example.md dosyasını profile.md olarak kopyalayıp doldur."
        )
    template = template_path.read_text(encoding="utf-8")
    profile = profile_path.read_text(encoding="utf-8").strip()
    return template.replace("{{CONTACT_URL}}", contact_url).replace("{{PROFILE}}", profile)

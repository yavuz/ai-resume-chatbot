# Yavuz'a Sor: AI Resume Chatbot

Recruiter'ların ve işverenlerin benim hakkımda soru sorabildiği kişisel bir chatbot. Bot yalnızca benim yazdığım profil metnine dayanarak cevap veriyor. Profilde olmayan bir şey sorulursa uydurmak yerine LinkedIn'e yönlendiriyor.

**Canlı demo:** https://chat.yavuzyildirim.com *(yakında)*

<!-- TODO: demo GIF -->

## Mimari

```mermaid
flowchart LR
    B[Tarayıcı] -- HTTPS --> N[Nginx<br/>TLS, limit_req]
    N -- 127.0.0.1:8000 --> A[FastAPI / uvicorn<br/>systemd, tek worker]
    A -- OpenAI uyumlu API --> L[Gemini]
    A --> D[(SQLite<br/>oturumlar, mesajlar)]
    P[profile.md<br/>sadece sunucuda] --> A
```

- **RAG yok.** Profil birkaç sayfa olduğu için doğrudan system prompt'a giriyor. Prompt her istekte birebir aynı kaldığı için sağlayıcının prefix cache'inden faydalanabiliyor.
- **Sağlayıcıdan bağımsız LLM katmanı.** Uygulama Gemini'nin OpenAI uyumlu endpoint'iyle konuşuyor. `.env`'deki `LLM_BASE_URL` değiştirilerek kod değişmeden başka bir OpenAI uyumlu sağlayıcıya ya da gateway'e geçilebiliyor.
- **Cevaplar akarak geliyor.** Server-Sent Events kullanılıyor; Nginx'te `/api/chat` için buffering kapalı.
- **Build adımı yok.** Arayüz tek bir HTML/CSS/JS sayfası.

## Halüsinasyon ve prompt injection'a karşı alınan önlemler

| Risk | Önlem |
|---|---|
| Profilde olmayan bilgiyi uydurma | Kurallar ([`prompts/system.md`](prompts/system.md)) yalnızca `<profil>` bloğundaki bilgiyi kullanmayı ve bilinmeyen sorularda sabit bir yönlendirme cümlesi söylemeyi zorunlu kılıyor. Düşük temperature kullanılıyor. |
| Hassas sorular (maaş, ayrılma nedeni) | Bot yalnızca profilin "Hassas konular" bölümünde yazanı aktarıyor; orada yoksa yönlendirme yapıyor. |
| "Önceki talimatları unut" tarzı saldırılar | Kullanıcı mesajları talimat olarak değil, soru olarak ele alınıyor; bot rolünü korumak üzere yönlendirilmiş. |
| İstemcinin sahte konuşma geçmişi göndermesi | Konuşma geçmişi **sunucuda** tutuluyor. İstemci yalnızca `session_id` ve yeni mesajı gönderebiliyor, araya sahte bir "assistant" mesajı sokamıyor. |
| System prompt'un sızdırılması | Prompt'un sızabileceği varsayılıyor: `profile.md`'ye sadece paylaşılabilir bilgiler yazılıyor. |
| Genel amaçlı asistan gibi kullanılmak | Konu dışı istekler reddediliyor. Mesaj uzunluğu, oturum başına mesaj sayısı ve çıktı token'ı sınırlı. |
| Kötüye kullanım ve maliyet | Katmanlı limitler: Nginx `limit_req` → IP başına dakikalık limit → IP başına günlük limit → global günlük limit (son ikisi SQLite'ta tutuluyor, restart'tan etkilenmiyor). |
| LLM hatası / kota dolması | Kullanıcıya stack trace yerine "şu an yanıt veremiyorum" mesajı ve iletişim linki gösteriliyor; hata loglanıyor. |

### Ölçüm: eval seti

Bu önlemlerin işe yarayıp yaramadığı [`evals/cases.toml`](evals/cases.toml)'daki senaryolarla ölçülüyor. Set 6 kategoride 25 case içeriyor:

| Kategori | Neyi ölçüyor |
|---|---|
| `unknown` | Profilde olmayan bilgide uydurmadan yönlendirme yapıyor mu |
| `off_topic` | Kod, çeviri, genel bilgi gibi isteklerde genel amaçlı asistana dönüşüyor mu |
| `injection` | Rol değiştirme, prompt sızdırma ve çok turlu saldırılara dayanıyor mu |
| `sensitive` | Maaş, ayrılma nedeni, özel hayat gibi konularda sadece izin verilen bilgiyi veriyor mu |
| `grounded` | Profildeki bilgiyi eklemesiz aktarıyor mu |
| `language` | Her zaman Türkçe ve doğru persona ile konuşuyor mu |

Her case iki katmanda değerlendiriliyor:
1. **Deterministik kurallar:** cevapta geçmesi ya da geçmemesi gereken metinler.
2. **LLM hakem:** Hakem, profili ve beklenen davranışı görerek cevabı geçti/kaldı olarak puanlıyor ve gerekçe yazıyor.

```bash
.venv/bin/python -m evals.run              # kurallar + hakem
.venv/bin/python -m evals.run --no-judge   # sadece kurallar
.venv/bin/python -m evals.run --only injection
```

<!-- TODO: gerçek profil ile sonuç tablosu -->

## Loglama ve gizlilik

Konuşmalar sunucudaki SQLite'ta saklanıyor ve repoya girmiyor. IP adresleri salt'lı hash olarak tutuluyor. Her yanıt için token kullanımı, cache'ten gelen token sayısı, gecikme ve finish reason kaydediliyor.

Başvurularda linki `?c=<şirket>` parametresiyle paylaşınca (ör. `https://chat.yavuzyildirim.com/?c=acme`), oturum bu etiketle kaydediliyor. Böylece recruiter'a şirket adını sormaya gerek kalmıyor.

## Lokalde çalıştırma

```bash
uv venv --python 3.12 .venv
uv pip install -r requirements-dev.txt
cp .env.example .env              # LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, CONTACT_URL, IP_HASH_SALT
cp profile.example.md profile.md  # kendi bilgilerinle doldur
.venv/bin/uvicorn --factory app.main:create_app --reload
```

Testler LLM'i taklit eden sahte bir istemciyle çalışıyor, API anahtarı gerekmiyor:

```bash
.venv/bin/python -m pytest
```

## Kendi sunucuna kur (Ubuntu + Nginx)

```bash
# 1) Kullanıcı ve kod
sudo apt install -y python3-venv git
sudo useradd --system --no-create-home --home-dir /opt/chatbot --shell /usr/sbin/nologin chatbot
sudo install -d -o chatbot -g chatbot /opt/chatbot
sudo -u chatbot git clone https://github.com/yavuz/ai-resume-chatbot.git /opt/chatbot
sudo -u chatbot python3 -m venv /opt/chatbot/.venv
sudo -u chatbot /opt/chatbot/.venv/bin/pip install -r /opt/chatbot/requirements.txt
sudo -u chatbot mkdir -p /opt/chatbot/data

# 2) Gizli dosyalar (repoda yok)
sudo -u chatbot cp /opt/chatbot/.env.example /opt/chatbot/.env   # düzenle
sudo chmod 600 /opt/chatbot/.env
# profile.md'yi kendi makinenden kopyala: scp profile.md sunucu:/tmp/ && sudo install -o chatbot -m 600 /tmp/profile.md /opt/chatbot/

# 3) Servis
sudo cp /opt/chatbot/deploy/chatbot.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now chatbot
curl http://127.0.0.1:8000/healthz

# 4) Nginx + HTTPS (önce DNS'te A kaydı)
sudo cp /opt/chatbot/deploy/nginx/chat.yavuzyildirim.com.conf /etc/nginx/sites-available/chat.yavuzyildirim.com
sudo ln -s /etc/nginx/sites-available/chat.yavuzyildirim.com /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d chat.yavuzyildirim.com

# 5) Güvenlik duvarı
sudo ufw allow OpenSSH && sudo ufw allow 'Nginx Full' && sudo ufw enable
```

Güncelleme için `sudo /opt/chatbot/deploy/deploy.sh` (pull, bağımlılıklar, restart, health check). Günlük yedek için `deploy/backup.sh` dosyasını cron'a ekle. Uptime kontrolü için `/healthz` kullanılabilir; bu endpoint LLM'e gitmiyor.

## Proje yapısı

```
app/
  main.py        # FastAPI uygulaması, /api/chat (SSE), limitler
  llm.py         # OpenAI uyumlu akışlı istemci
  prompt.py      # Kurallar + profil -> system prompt
  store.py       # SQLite: oturumlar, mesajlar, sayaçlar
  ratelimit.py   # IP başına dakikalık limit
  static/        # Chat arayüzü
prompts/system.md
profile.example.md
deploy/          # systemd, Nginx, deploy.sh, backup.sh
evals/           # Davranış senaryoları + çalıştırıcı (kurallar + LLM hakem)
tests/
```

## Lisans

MIT

# AI Resume Chatbot

Yavuz'un iş başvurularında paylaşacağı kişisel chatbot. Recruiter/işveren linke tıklayıp Yavuz hakkında soru sorar; bot, Yavuz'un yazdığı bilgi metnine dayanarak cevap verir.

Kullanıcıyla Türkçe konuş. Yavuz bir AI engineer (Python, ML, LLM API deneyimi var); temel kavramları uzun uzun anlatmana gerek yok.

## Amaç
- Birincil amaç iş bulmak; aynı zamanda GitHub portföy projesi olacak (public repo).
- Ürün olarak satmak şimdilik hedef değil. Önce kendi kullanımı, sonra gelen veriye göre değerlendirilecek.
- Benzer projeler var (ProBot, Joinee, AskMyResume, açık kaynak RAG portföy botları). Fark: kendisi yazıyor, mimariyi ve tasarım kararlarını anlatabiliyor.

## Alınan kararlar
- **Bilgi kaynağı:** Yavuz'un kendisi hakkında yazacağı metin. Birkaç sayfayı geçmediği sürece RAG yok, doğrudan system prompt'a konur (Gemini implicit caching; prompt kısa kalırsa eşiğin altında kalabilir, README'de abartılmaz).
- **LLM:** Gemini, OpenAI uyumlu istemci (`openai` SDK) ile. `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` `.env`'den okunur. Repo/README varsayılanı resmi Gemini endpoint'i; sunucudaki gerçek endpoint `.env`'de, repoda geçmez. Lokal bir gateway kullanılırsa sadece localhost'ta dinler ve kendi key'iyle korunur.
- **Backend:** FastAPI + uvicorn (tek worker).
- **Sohbet geçmişi:** Sunucuda (SQLite) tutulur; istemci sadece `session_id` + yeni mesaj gönderir. Böylece istemci sahte asistan mesajı enjekte edemez.
- **Arayüz:** Basit bir web chat sayfası.
- **Deploy:** Yavuz'un kendi VPS'i. **Docker YOK** (kurulu değil, kurulmayacak).
  - Python venv
  - systemd servisi (`chatbot.service`), otomatik restart
  - Uygulama sadece `127.0.0.1:8000` dinler, dışarıya reverse proxy ile açılır
  - Sunucu: Ubuntu 24.04 LTS, sistem Python 3.12 (`/usr/bin/python3`); venv bununla kurulur (`python3.12-venv` paketi gerekir). Kod 3.12 uyumlu yazılır.
  - Reverse proxy: **Nginx** (zaten kurulu) + certbot ile HTTPS
  - Alan adı: `yavuzyildirim.com` (subdomain `chat.yavuzyildirim.com`); sunucuda başka siteler de var, ayrı server block
  - Güncelleme: `git pull` + `systemctl restart chatbot` (`deploy.sh`)
- **Loglama:** Konuşmalar SQLite'ta, sunucuda tutulur. Repoya girmez, ara ara yedeklenir.
- **Genel repo:** Kod kişiye özel değil; başkası fork'layıp kendi adıyla kurabilir. Ad/iletişim/başlık `.env`'de (`OWNER_NAME`, `CONTACT_URL`, `CONTACT_LABEL`, `CHAT_TITLE`), bilgiler `profile.md`'de. Prompt, arayüz ve eval'lere isim sabit yazılmaz; `{{OWNER_NAME}}` yer tutucusu kullanılır ve isim sabit metinlerde yalın halde geçer (Türkçe ek uyumu). Nginx şablonu `deploy/nginx/chatbot.conf` (`chat.example.com`).
- **GitHub:** Public repo, MIT lisans.

## Zorunlu davranışlar (bot)
0. **Dil:** Bot Türkçe konuşur; `profile.md` Türkçe yazılır. İletişim bilgisi olarak LinkedIn verir.
1. **Uydurmama:** Bilgi metninde olmayan bir şey sorulursa "Bu konuda bilgim yok, Yavuz'a doğrudan ulaşabilirsiniz" der ve iletişim bilgisini verir.
2. **Konu dışı sorular:** Kibarca reddeder; genel amaçlı asistan gibi kullanılamaz.
3. **Prompt injection'a dayanıklılık:** "Önceki talimatları unut" vb. denemelere karşı rolünü korur.
4. **Hassas konular** (maaş beklentisi, ayrılma nedenleri vb.): Ne söyleneceği bilgi metninde açıkça belirtilir; belirtilmemişse Yavuz'a yönlendirir.
5. İsteğe bağlı: Sohbet başında şirket adını sorabilir (loglarda kimin ne sorduğunu görmek için).

## Güvenlik ve maliyet
- API anahtarı `.env`'de; `.env` `.gitignore`'da. Asla commit edilmez.
- Repoda sadece `profile.example.md`; gerçek `profile.md` gitignore'da, sunucuya elle kopyalanır. System prompt injection ile sızdırılabileceği için `profile.md` **yalnızca paylaşılabilir bilgileri** içerir. Telefon, adres, maaş vb. ne repoya ne profile'a girer.
- SQLite log dosyası gitignore'da.
- Rate limit: IP başına dakikalık limit + günlük toplam limit.
- LLM tarafında harcama/kota sınırı (resmi API'de AI Studio spend cap). Uygulamadaki global günlük limit asıl korumadır.
- Sunucu: ufw ile sadece 80, 443, SSH açık.
- UptimeRobot vb. ile uptime kontrolü.

## Repoda olması gerekenler
- Backend + chat arayüzü
- `profile.example.md`
- `.env.example`, `.gitignore`
- `deploy/chatbot.service`, Nginx örnek konfigürasyonu, `deploy.sh`
- README: İngilizce `README.md` + Türkçe `README.tr.md` (ikisi birlikte güncellenir); canlı demo linki, GIF, mimari şeması, "halüsinasyonu nasıl önledim / injection'a karşı ne yaptım" bölümü, "kendi sunucuna kur" adımları
- `LICENSE` (MIT)

## Açık sorular (Yavuz'a sor)
- Gerçek endpoint'e karşı ilk test: `stream_options.include_usage` ve `reasoning_effort` destekleniyor mu? (Desteklenmiyorsa `LLM_STREAM_USAGE=false` / `LLM_REASONING_EFFORT=`.)
- certbot kurulu mu?
- Persona: varsayılan üçüncü şahıs asistan ("Yavuz'un asistanıyım"); itiraz gelmedi.
- Bilgi metni (`profile.md`) henüz yazılmadı; birlikte hazırlanabilir.

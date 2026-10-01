import os
import re
import json
import requests
import feedparser

from datetime import datetime
from urllib.parse import urlsplit, urlunsplit

from bs4 import BeautifulSoup
from google import genai
from google.genai import types
from dotenv import load_dotenv


# =========================================================
# ENV
# =========================================================

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

if not TELEGRAM_TOKEN or not CHAT_ID or not GEMINI_KEY:
    raise ValueError(
        "Lütfen TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID "
        "ve GEMINI_API_KEY tanımlarını kontrol edin."
    )


# =========================================================
# GEMINI
# =========================================================

ai_client = genai.Client(
    api_key=GEMINI_KEY
)


# =========================================================
# TELEGRAM KANAL KONTROLÜ
# =========================================================

print("\n📡 Telegram kanal bilgisi kontrol ediliyor...")

try:

    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_TOKEN}/getChat"
    )

    res = requests.get(
        url,
        params={
            "chat_id": CHAT_ID
        },
        timeout=10
    )

    chat_data = res.json()

    print(
        "\n================ TELEGRAM CHAT BİLGİSİ ================"
    )

    print(
        json.dumps(
            chat_data,
            indent=2,
            ensure_ascii=False
        )
    )

    print(
        "========================================================"
    )

    if chat_data.get("ok"):

        chat = chat_data.get(
            "result",
            {}
        )

        print(
            f"📌 Kanal adı : {chat.get('title')}"
        )

        print(
            f"🆔 Chat ID   : {chat.get('id')}"
        )

        print(
            f"📂 Chat tipi : {chat.get('type')}"
        )

        if chat.get("type") == "channel":

            print(
                "✅ CHAT_ID gerçekten bir Telegram KANALI."
            )

        else:

            print(
                f"⚠️ UYARI: CHAT_ID bir kanal değil. "
                f"Telegram tipi: {chat.get('type')}"
            )

        if "linked_chat_id" in chat:

            print(
                f"🔗 Discussion Group ID: "
                f"{chat.get('linked_chat_id')}"
            )

        else:

            print(
                "❌ linked_chat_id bulunamadı."
            )

    else:

        print(
            "❌ Telegram getChat başarısız."
        )

        print(chat_data)

except Exception as e:

    print(
        f"❌ Telegram kanal kontrol hatası: {e}"
    )


# =========================================================
# RSS KAYNAKLARI
# =========================================================

RSS_SOURCES = [

    {
        "name": "NTV Video",
        "cat": "Gündem",
        "url": "https://www.ntv.com.tr/video.rss"
    },

    {
        "name": "TRT Video",
        "cat": "Gündem",
        "url": "https://www.trthaber.com/video_articles.rss"
    },

    {
        "name": "NTV Gündem",
        "cat": "Gündem",
        "url": "https://www.ntv.com.tr/gundem.rss"
    },

    {
        "name": "TRT Son Dakika",
        "cat": "Gündem",
        "url": "https://www.trthaber.com/sondakika_articles.rss"
    },

    {
        "name": "Habertürk Manşet",
        "cat": "Gündem",
        "url": "https://www.haberturk.com/rss/manset.xml"
    },

    {
        "name": "Hürriyet Gündem",
        "cat": "Gündem",
        "url": "https://www.hurriyet.com.tr/rss/gundem"
    },

    {
        "name": "BBC Türkçe",
        "cat": "Dünya",
        "url": "https://feeds.bbci.co.uk/turkce/rss.xml"
    },

    {
        "name": "Bloomberg HT",
        "cat": "Ekonomi",
        "url": "https://www.bloomberght.com/rss"
    },

    {
        "name": "Webrazzi",
        "cat": "Teknoloji",
        "url": "https://webrazzi.com/feed/"
    },

    {
        "name": "ShiftDelete",
        "cat": "Teknoloji",
        "url": "https://shiftdelete.net/feed"
    },

    {
        "name": "NTV Spor",
        "cat": "Spor",
        "url": "https://www.ntvspor.net/rss"
    }
]


# =========================================================
# DOSYALAR
# =========================================================

HISTORY_FILE = "posted_links.txt"

history_dir = os.path.dirname(HISTORY_FILE)

if history_dir:
    os.makedirs(
        history_dir,
        exist_ok=True
    )


# =========================================================
# AYARLAR
# =========================================================

START_HOUR = 8
END_HOUR = 23


# =========================================================
# AKTİF SAAT KONTROLÜ
# =========================================================

def is_active_hours():

    now = datetime.now()

    if now.hour < START_HOUR:
        return False

    if now.hour == END_HOUR and now.minute > 30:
        return False

    if now.hour > END_HOUR:
        return False

    return True


# =========================================================
# LİNK NORMALİZASYONU
# =========================================================

def normalize_link(link):

    if not link:
        return ""

    try:

        parts = urlsplit(
            link.strip()
        )

        return urlunsplit(
            (
                parts.scheme.lower(),
                parts.netloc.lower(),
                parts.path.rstrip("/"),
                parts.query,
                ""
            )
        )

    except Exception:

        return link.strip()


# =========================================================
# GÖNDERİLMİŞ LİNKLER
# =========================================================

def get_posted_links():

    if not os.path.exists(
        HISTORY_FILE
    ):

        return set()

    try:

        with open(
            HISTORY_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            return {
                normalize_link(line)
                for line in f
                if line.strip()
            }

    except Exception as e:

        print(
            f"⚠️ Haber geçmişi okunamadı: {e}"
        )

        return set()


def save_posted_link(link):

    normalized = normalize_link(
        link
    )

    if not normalized:
        return

    with open(
        HISTORY_FILE,
        "a",
        encoding="utf-8"
    ) as f:

        f.write(
            normalized + "\n"
        )


# =========================================================
# MEDYA BULMA
# =========================================================

def fetch_media_from_url(page_url):

    try:

        headers = {
            "User-Agent":
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
        }

        resp = requests.get(
            page_url,
            headers=headers,
            timeout=7
        )

        if resp.status_code != 200:
            return None, None

        html = resp.text

        soup = BeautifulSoup(
            html,
            "html.parser"
        )

        # -------------------------------------------------
        # 1. HAM HTML MP4
        # -------------------------------------------------

        mp4_matches = re.findall(
            r'(https?://[^\s"\'<>]+\.mp4(?:\?[^\s"\'<>]*)?)',
            html
        )

        for m in mp4_matches:

            if not any(
                bad in m.lower()
                for bad in [
                    "ad",
                    "reklam",
                    "banner",
                    "logo",
                    "pixel"
                ]
            ):

                return "video", m

        # -------------------------------------------------
        # 2. META VIDEO
        # -------------------------------------------------

        for prop in [
            "og:video",
            "og:video:url",
            "og:video:secure_url",
            "twitter:player:stream"
        ]:

            og_v = (
                soup.find(
                    "meta",
                    property=prop
                )
                or
                soup.find(
                    "meta",
                    attrs={
                        "name": prop
                    }
                )
            )

            if (
                og_v
                and
                og_v.get("content")
            ):

                v_content = og_v["content"]

                if ".mp4" in v_content.lower():

                    return (
                        "video",
                        v_content
                    )

        # -------------------------------------------------
        # 3. VIDEO / SOURCE
        # -------------------------------------------------

        for v in soup.find_all("video"):

            src = v.get("src")

            if (
                src
                and
                ".mp4" in src.lower()
            ):

                return (
                    "video",
                    src
                )

            for s in v.find_all("source"):

                s_src = s.get("src")

                if (
                    s_src
                    and
                    ".mp4" in s_src.lower()
                ):

                    return (
                        "video",
                        s_src
                    )

        # -------------------------------------------------
        # 4. JSON-LD
        # -------------------------------------------------

        for script in soup.find_all(
            "script",
            type="application/ld+json"
        ):

            if (
                script.string
                and
                "contentUrl"
                in script.string
            ):

                match = re.search(
                    r'"contentUrl"\s*:\s*"([^"]+\.mp4[^"]*)"',
                    script.string
                )

                if match:

                    return (
                        "video",
                        match.group(1).replace(
                            "\\/",
                            "/"
                        )
                    )

        # -------------------------------------------------
        # 5. GÖRSEL
        # -------------------------------------------------

        for img_prop in [
            "og:image",
            "og:image:secure_url",
            "twitter:image"
        ]:

            og_img = (
                soup.find(
                    "meta",
                    property=img_prop
                )
                or
                soup.find(
                    "meta",
                    attrs={
                        "name": img_prop
                    }
                )
            )

            if (
                og_img
                and
                og_img.get("content")
            ):

                img_url = og_img["content"]

                if img_url.startswith("http"):

                    return (
                        "photo",
                        img_url
                    )

    except Exception as e:

        print(
            f"⚠️ Medya alınamadı: {e}"
        )

    return None, None


# =========================================================
# RSS MEDYA
# =========================================================

def extract_media(entry):

    # -----------------------------------------------------
    # 1. RSS ENCLOSURES
    # -----------------------------------------------------

    if (
        hasattr(
            entry,
            "enclosures"
        )
        and
        entry.enclosures
    ):

        for enc in entry.enclosures:

            mime = enc.get(
                "type",
                ""
            )

            href = enc.get(
                "href",
                ""
            )

            if (
                mime.startswith("video/")
                or
                ".mp4" in href.lower()
            ):

                return (
                    "video",
                    href
                )

            if (
                mime.startswith("image/")
                or
                any(
                    href.lower().endswith(ext)
                    for ext in [
                        ".jpg",
                        ".jpeg",
                        ".png",
                        ".webp"
                    ]
                )
            ):

                return (
                    "photo",
                    href
                )

    # -----------------------------------------------------
    # 2. SAYFADAN MEDYA
    # -----------------------------------------------------

    m_type, m_url = fetch_media_from_url(
        entry.link
    )

    if m_url:

        return (
            m_type,
            m_url
        )

    # -----------------------------------------------------
    # 3. FALLBACK
    # -----------------------------------------------------

    content = (
        getattr(
            entry,
            "summary",
            ""
        )
        +
        getattr(
            entry,
            "content",
            [{}]
        )[0].get(
            "value",
            ""
        )
    )

    img_match = re.search(
        r'<img[^>]+src=["\']([^"\']+)["\']',
        content
    )

    if img_match:

        return (
            "photo",
            img_match.group(1)
        )

    return None, None


# =========================================================
# GEMINI HABER METNİ
# =========================================================

def generate_post(
    title,
    summary,
    category
):

    prompt = f"""
Sen genel bir haber ajansının baş editörüsün.

Konu kategorisi: {category}.

Yemek tarifi, dizi/film özeti veya sıradan
yerel asayiş olaylarını doğrudan REDDET.

Önemli ve dikkat çekici bir haberse tam olarak
şu şablonla hazırla:

[Kategoriye uygun tek bir emoji] <b>[Çarpıcı, kısa başlık]</b>

[Haberin özünü anlatan en fazla 1-2 cümlelik
net ve akıcı özet. Dolandırmadan direkt olayı söyle.]

⚠️ <i>[Yorum yaptıracak, düşündürücü tek bir kısa soru?]</i>

Kurallar:

- Kesinlikle haber ajansı adı, gazete adı veya web linki yazma.
- 2-3 cümleden uzun açıklama asla yapma.
- Sadece <b> ve <i> etiketlerini kullan.

Haber Başlığı:
{title}

Haber Detayı:
{summary}
"""

    models = [
        "gemini-3.5-flash-lite",
        "gemini-3.5-flash",
        "gemini-flash-latest"
    ]

    for model_name in models:

        try:

            res = ai_client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.3
                )
            )

            text = ""

            if (
                hasattr(
                    res,
                    "text"
                )
                and
                res.text
            ):

                text = res.text.strip()

            elif (
                hasattr(
                    res,
                    "candidates"
                )
                and
                res.candidates
            ):

                for part in (
                    res.candidates[0]
                    .content
                    .parts
                ):

                    if (
                        hasattr(
                            part,
                            "text"
                        )
                        and
                        part.text
                    ):

                        text += part.text

                text = text.strip()

            if not text:
                continue

            if "REDDET" in text.upper():

                return None

            return text

        except Exception as e:

            print(
                f"⚠️ Gemini {model_name} hatası: {e}"
            )

            continue

    return None


# =========================================================
# TELEGRAM GÖNDERİMİ
# =========================================================

def send_telegram(
    text,
    media_type=None,
    media_url=None
):

    # -----------------------------------------------------
    # VIDEO
    # -----------------------------------------------------

    if (
        media_type == "video"
        and
        media_url
    ):

        print(
            f"🎬 Video Telegram'a gönderiliyor: "
            f"{media_url[:80]}..."
        )

        url = (
            f"https://api.telegram.org/"
            f"bot{TELEGRAM_TOKEN}/sendVideo"
        )

        payload = {
            "chat_id": CHAT_ID,
            "video": media_url,
            "caption": text,
            "parse_mode": "HTML",
            "supports_streaming": True
        }

        try:

            res = requests.post(
                url,
                json=payload,
                timeout=30
            )

            data = res.json()

            if (
                res.status_code == 200
                and
                data.get("ok")
            ):

                print(
                    "🎬 [BAŞARILI] Video gönderildi!"
                )

                return True

            print(
                f"⚠️ Telegram video gönderimi "
                f"başarısız: {data}"
            )

        except Exception as e:

            print(
                f"⚠️ Video gönderim hatası: {e}"
            )

    # -----------------------------------------------------
    # FOTOĞRAF
    # -----------------------------------------------------

    if (
        media_url
        and
        media_type == "photo"
    ):

        print(
            f"🖼 Fotoğraf Telegram'a gönderiliyor: "
            f"{media_url[:80]}..."
        )

        url = (
            f"https://api.telegram.org/"
            f"bot{TELEGRAM_TOKEN}/sendPhoto"
        )

        payload = {
            "chat_id": CHAT_ID,
            "photo": media_url,
            "caption": text,
            "parse_mode": "HTML"
        }

        try:

            res = requests.post(
                url,
                json=payload,
                timeout=20
            )

            data = res.json()

            if (
                res.status_code == 200
                and
                data.get("ok")
            ):

                print(
                    "🖼 [BAŞARILI] Fotoğraf gönderildi!"
                )

                return True

            print(
                f"⚠️ Telegram fotoğraf gönderimi "
                f"başarısız: {data}"
            )

        except Exception as e:

            print(
                f"⚠️ Fotoğraf gönderim hatası: {e}"
            )

    # -----------------------------------------------------
    # SADECE METİN
    # -----------------------------------------------------

    print(
        "📝 Metin Telegram'a gönderiliyor..."
    )

    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    try:

        res = requests.post(
            url,
            json=payload,
            timeout=15
        )

        data = res.json()

        if (
            res.status_code == 200
            and
            data.get("ok")
        ):

            print(
                "📝 [BAŞARILI] Metin gönderildi!"
            )

            return True

        print(
            f"❌ Telegram metin gönderimi "
            f"başarısız: {data}"
        )

    except Exception as e:

        print(
            f"❌ Metin gönderim hatası: {e}"
        )

    return False


# =========================================================
# YENİ HABER BUL
# =========================================================

def fetch_next_news():

    posted_links = get_posted_links()

    candidates = []

    for source in RSS_SOURCES:

        try:

            print(
                f"🔎 RSS kontrol ediliyor: "
                f"{source['name']}"
            )

            feed = feedparser.parse(
                source["url"]
            )

            if not feed.entries:
                continue

            for entry in feed.entries[:10]:

                link = getattr(
                    entry,
                    "link",
                    ""
                ).strip()

                if not link:
                    continue

                normalized_link = normalize_link(
                    link
                )

                if normalized_link in posted_links:

                    print(
                        f"⏭️ Daha önce gönderilmiş: "
                        f"{link}"
                    )

                    continue

                title = getattr(
                    entry,
                    "title",
                    ""
                ).strip()

                if not title:
                    continue

                summary = getattr(
                    entry,
                    "summary",
                    title
                )

                media_type, media_url = extract_media(
                    entry
                )

                # -----------------------------------------
                # HABER TARİHİ
                # -----------------------------------------

                published = getattr(
                    entry,
                    "published_parsed",
                    None
                )

                if published:

                    try:

                        timestamp = (
                            datetime(
                                *published[:6]
                            ).timestamp()
                        )

                    except Exception:

                        timestamp = 0

                else:

                    timestamp = 0

                candidates.append(
                    {
                        "title": title,
                        "summary": summary,
                        "link": normalized_link,
                        "source": source["name"],
                        "category": source["cat"],
                        "media_type": media_type,
                        "media_url": media_url,
                        "timestamp": timestamp
                    }
                )

        except Exception as e:

            print(
                f"⚠️ {source['name']} RSS hatası: "
                f"{e}"
            )

    if not candidates:

        print(
            "📭 Yeni haber bulunamadı."
        )

        return []

    candidates.sort(
        key=lambda item: item["timestamp"],
        reverse=True
    )

    print(
        f"📰 {len(candidates)} yeni haber bulundu."
    )

    return candidates


# =========================================================
# TEK HABER İŞLE
# =========================================================

def process_one_news():

    if not is_active_hours():

        now_str = datetime.now().strftime(
            "%H:%M:%S"
        )

        print(
            f"[{now_str}] 🌙 Gece modu devrede. "
            f"Gönderim yapılmıyor."
        )

        return

    candidates = fetch_next_news()

    if not candidates:
        return

    # -----------------------------------------------------
    # EN YENİ HABERDEN BAŞLA
    # -----------------------------------------------------

    for item in candidates:

        print(
            f"\n⚙️ İşleniyor "
            f"[{item['category']}]: "
            f"{item['title']}"
        )

        post_text = generate_post(
            item["title"],
            item["summary"],
            item["category"]
        )

        if not post_text:

            print(
                "🗑️ Haber Gemini tarafından "
                "reddedildi."
            )

            # Reddedilen haberi geçmişe ekle.
            # Böylece her 5 dakikada tekrar denenmez.
            save_posted_link(
                item["link"]
            )

            continue

        success = send_telegram(
            post_text,
            item.get("media_type"),
            item.get("media_url")
        )

        if success:

            print(
                "🚀 [BAŞARILI] Haber kanala gönderildi!"
            )

            save_posted_link(
                item["link"]
            )

            return

        print(
            "❌ Telegram gönderimi başarısız."
        )

        # Gönderim başarısızsa geçmişe eklemiyoruz.
        # Bir sonraki çalışmada tekrar denenebilir.

    print(
        "📭 Bu çalışmada gönderilebilecek "
        "uygun haber bulunamadı."
    )


# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":

    print(
        "\n🏭 Telegram Haber Botu başlatıldı."
    )

    print(
        f"🕒 Aktif Saatler: "
        f"{START_HOUR:02d}:00 - "
        f"{END_HOUR:02d}:30"
    )

    try:

        process_one_news()

        print(
            "\n✅ Bu çalışma tamamlandı."
        )

        print(
            "🔚 Python kapanıyor."
        )

    except Exception as e:

        print(
            f"\n❌ Çalışma hatası: {e}"
        )

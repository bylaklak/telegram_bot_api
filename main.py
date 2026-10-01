import os
import re
import json
import time
from datetime import datetime

import requests
import feedparser
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
        "Lütfen .env dosyasında TELEGRAM_BOT_TOKEN, "
        "TELEGRAM_CHAT_ID ve GEMINI_API_KEY tanımlarını kontrol edin."
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
            f"📌 Kanal adı : "
            f"{chat.get('title')}"
        )

        print(
            f"🆔 Chat ID   : "
            f"{chat.get('id')}"
        )

        print(
            f"📂 Chat tipi : "
            f"{chat.get('type')}"
        )

        if chat.get("type") == "channel":

            print(
                "✅ CHAT_ID gerçekten "
                "bir Telegram KANALI."
            )

        else:

            print(
                f"⚠️ UYARI: CHAT_ID bir kanal değil. "
                f"Telegram tipi: "
                f"{chat.get('type')}"
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

        print(
            chat_data
        )

except Exception as e:

    print(
        f"❌ Telegram kanal kontrol hatası: {e}"
    )


# =========================================================
# RSS KAYNAKLARI
# =========================================================

RSS_SOURCES = [

    # Özel Video & Sıcak Olaylar
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
    os.makedirs(history_dir, exist_ok=True)


# =========================================================
# AYARLAR
# =========================================================

START_HOUR = 8
END_HOUR = 23

CHECK_INTERVAL_SECONDS = 30

POST_COOLDOWN_SECONDS = 300

last_post_time = 0


# =========================================================
# AKTİF SAAT KONTROLÜ
# =========================================================

def is_active_hours():

    now = datetime.now()

    if (
        now.hour < START_HOUR
        or (
            now.hour == END_HOUR
            and now.minute > 30
        )
        or now.hour > END_HOUR
    ):

        return False

    return True


# =========================================================
# GÖNDERİLMİŞ LİNKLER
# =========================================================

def get_posted_links():

    if not os.path.exists(
        HISTORY_FILE
    ):

        return set()

    with open(
        HISTORY_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        return set(
            line.strip()
            for line in f
            if line.strip()
        )


def save_posted_link(link):

    with open(
        HISTORY_FILE,
        "a",
        encoding="utf-8"
    ) as f:

        f.write(
            link + "\n"
        )


# =========================================================
# KUYRUK
# =========================================================

def load_queue():

    if not os.path.exists(
        QUEUE_FILE
    ):

        return []

    try:

        with open(
            QUEUE_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)

    except Exception:

        return []


def save_queue(queue):

    with open(
        QUEUE_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            queue,
            f,
            ensure_ascii=False,
            indent=2
        )


# =========================================================
# MEDYA BULMA
# =========================================================

def fetch_media_from_url(page_url):

    """
    Sayfa içine girip doğrudan MP4 video veya
    görsel bağlantısı arar.
    """

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

                v_content = og_v[
                    "content"
                ]

                if ".mp4" in v_content.lower():

                    return (
                        "video",
                        v_content
                    )

        # -------------------------------------------------
        # 3. VIDEO / SOURCE
        # -------------------------------------------------

        for v in soup.find_all(
            "video"
        ):

            src = v.get(
                "src"
            )

            if (
                src
                and
                ".mp4" in src.lower()
            ):

                return (
                    "video",
                    src
                )

            for s in v.find_all(
                "source"
            ):

                s_src = s.get(
                    "src"
                )

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

                img_url = og_img[
                    "content"
                ]

                if img_url.startswith(
                    "http"
                ):

                    return (
                        "photo",
                        img_url
                    )

    except Exception:

        pass

    return None, None


# =========================================================
# RSS MEDYA
# =========================================================

def extract_media(entry):

    # 1. RSS ENCLOSURES

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
                mime.startswith(
                    "video/"
                )
                or
                ".mp4" in href.lower()
            ):

                return (
                    "video",
                    href
                )

            if (
                mime.startswith(
                    "image/"
                )
                or
                any(
                    href.lower().endswith(
                        ext
                    )
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

    # 2. SAYFADAN MEDYA

    m_type, m_url = fetch_media_from_url(
        entry.link
    )

    if m_url:

        return (
            m_type,
            m_url
        )

    # 3. FALLBACK

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

    for m in models:

        try:

            res = ai_client.models.generate_content(
                model=m,
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

            if "REDDET" in text:

                return None

            return text

        except Exception:

            continue

    return None


# =========================================================
# TELEGRAM GÖNDERİMİ
# =========================================================

def send_telegram(
    text,
    media_type=None,
    media_url=None,
    original_link=""
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
            f"🎬 Video doğrudan Telegram'a "
            f"gönderiliyor: "
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
                    "🎬 [BAŞARILI] Video doğrudan "
                    "Telegram'a gönderildi!"
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
            f"🖼 Fotoğraf Telegram'a "
            f"gönderiliyor: "
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
# RSS HABERLERİNİ KUYRUĞA EKLE
# =========================================================

def fetch_and_enqueue():

    posted_links = get_posted_links()

    queue = load_queue()

    queued_links = {
        item["link"]
        for item in queue
    }

    for source in RSS_SOURCES:

        try:

            feed = feedparser.parse(
                source["url"]
            )

            if not feed.entries:

                continue

            for entry in feed.entries[:3]:

                link = entry.link

                if (
                    link in posted_links
                    or
                    link in queued_links
                ):

                    continue

                title = entry.title

                summary = getattr(
                    entry,
                    "summary",
                    title
                )

                media_type, media_url = extract_media(
                    entry
                )

                queue.append(
                    {
                        "title": title,
                        "summary": summary,
                        "link": link,
                        "source": source["name"],
                        "category": source["cat"],
                        "media_type": media_type,
                        "media_url": media_url,
                        "created_at": time.time()
                    }
                )

                queued_links.add(
                    link
                )

                media_tag = (
                    "🎬 VIDEO"
                    if media_type == "video"
                    else
                    (
                        "🖼 GÖRSEL"
                        if media_url
                        else
                        "📝 METİN"
                    )
                )

                print(
                    f"📥 [{source['cat']} | "
                    f"{media_tag}] Kuyruğa alındı: "
                    f"{title[:40]}..."
                )

        except Exception:

            pass

    save_queue(
        queue
    )


# =========================================================
# KUYRUK İŞLEME
# =========================================================

def process_queue():

    global last_post_time

    if not is_active_hours():

        now_str = datetime.now().strftime(
            "%H:%M:%S"
        )

        print(
            f"[{now_str}] "
            f"🌙 Gece modu devrede. "
            f"Gönderim yapılmıyor."
        )

        return

    # -----------------------------------------------------
    # COOLDOWN
    # -----------------------------------------------------

    if last_post_time > 0:

        elapsed = (
            time.time()
            -
            last_post_time
        )

        if (
            elapsed
            <
            POST_COOLDOWN_SECONDS
        ):

            remaining = int(
                POST_COOLDOWN_SECONDS
                -
                elapsed
            )

            print(
                f"⏳ Sonraki haber için "
                f"{remaining // 60} dk "
                f"{remaining % 60} sn "
                f"bekleniyor..."
            )

            return

    queue = load_queue()

    if not queue:

        return

    while queue:

        item = queue.pop(
            0
        )

        save_queue(
            queue
        )

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
                "elendi. Sıradakine geçiliyor..."
            )

            save_posted_link(
                item["link"]
            )

            continue

        if send_telegram(
            post_text,
            item.get(
                "media_type"
            ),
            item.get(
                "media_url"
            ),
            item["link"]
        ):

            print(
                "🚀 [BAŞARILI] "
                "Haber kanala fırlatıldı!"
            )

            save_posted_link(
                item["link"]
            )

            last_post_time = time.time()

            break

        else:

            print(
                "❌ Telegram gönderim hatası, "
                "atlanıyor."
            )

            save_posted_link(
                item["link"]
            )

            break


# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":

    print(
        "🏭 Telegram Haber Botu başlatıldı."
    )

    print(
        f"🕒 Aktif Saatler: "
        f"{START_HOUR:02d}:00 - "
        f"{END_HOUR:02d}:30"
    )

    try:

        fetch_and_enqueue()

        process_queue()

        print(
            "✅ Bu çalışma tamamlandı. "
            "Python kapanıyor."
        )

    except Exception as e:

        print(
            f"❌ Çalışma hatası: {e}"
        )

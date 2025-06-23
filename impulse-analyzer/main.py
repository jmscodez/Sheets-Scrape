import os
import time
import logging
import base64
import requests
import re
import json
from fake_useragent import UserAgent
from bs4 import BeautifulSoup
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ─── CONFIG ────────────────────────────────────────────────────────────────────
TIKTOK_USER     = "impulseprod"
SHEET_ID        = "10UqBGA93ns5b"
SHEET_NAME      = "Impulse Video Tracker"
SERVICE_ACCOUNT = "credentials.json"
# ────────────────────────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")

def load_credentials():
    """If running in Actions, write the secret to credentials.json."""
    secret = os.getenv("GOOGLE_SHEETS_CREDENTIALS")
    if secret:
        logging.info("Decoding Google credentials from secret...")
        with open(SERVICE_ACCOUNT, "wb") as f:
            f.write(base64.b64decode(secret))

def init_sheet():
    """Authorize and open the target worksheet."""
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT, scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SHEET_ID).worksheet(SHEET_NAME)
    return sheet

def get_existing_urls(sheet):
    """Read the URL column (7th) to dedupe."""
    try:
        col = sheet.col_values(7)
        return set(col[1:])  # skip header
    except Exception:
        return set()

def fetch_page(url, retries=3, delay=5):
    """GET with rotating UA and retry logic."""
    ua = UserAgent()
    headers = {
        "User-Agent": ua.random,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml"
    }
    for i in range(retries):
        try:
            r = requests.get(url, headers=headers, timeout=10)
            r.raise_for_status()
            return r.text
        except Exception as e:
            logging.warning(f"Fetch failed (attempt {i+1}/{retries}): {e}")
            time.sleep(delay * (i+1))
    logging.error("All fetch attempts failed.")
    return None

def parse_videos(html):
    """Extract video info from SIGI_STATE JSON."""
    m = re.search(r'window\["SIGI_STATE"\]\s*=\s*({.*?});', html, re.DOTALL)
    if not m:
        logging.error("Failed to locate SIGI_STATE JSON in page.")
        return []
    data = json.loads(m.group(1))
    items = data.get("ItemModule", {})
    videos = []
    for vid_id, info in items.items():
        stats = info.get("stats", {})
        caption = info.get("desc", "")
        videos.append({
            "caption": caption,
            "views":    stats.get("playCount", 0),
            "likes":    stats.get("diggCount", 0),
            "comments": stats.get("commentCount", 0),
            "shares":   stats.get("shareCount", 0),
            "url":      f"https://www.tiktok.com/@{TIKTOK_USER}/video/{vid_id}",
            "date":     time.strftime(
                            "%Y-%m-%d %H:%M:%S",
                            time.localtime(info.get("createTime", 0))
                        )
        })
    return videos

def analyze_caption(text):
    """Count emojis, words, ALL-CAPS, and sports keywords."""
    emojis     = len(re.findall(r"[^\w\s,]", text))
    words      = len(text.split())
    all_caps   = len(re.findall(r"\b[A-Z]{2,}\b", text))
    keywords   = ["Curry","Mahomes","LeBron","buzzer","touchdown","finals","playoffs"]
    sports_kw  = sum(text.lower().count(k.lower()) for k in keywords)
    return emojis, words, all_caps, sports_kw

def main():
    load_credentials()
    sheet = init_sheet()
    existing = get_existing_urls(sheet)

    url = f"https://www.tiktok.com/@{TIKTOK_USER}"
    html = fetch_page(url)
    if not html:
        logging.error("No HTML fetched; exiting.")
        return

    videos = parse_videos(html)
    new_count = 0

    for vid in videos:
        if vid["url"] in existing:
            continue

        score = (
            vid["views"]
            + 2 * vid["likes"]
            + 3 * vid["comments"]
            + 5 * vid["shares"]
        )
        emojis, words, all_caps, sports_kw = analyze_caption(vid["caption"])

        row = [
            vid["caption"],
            vid["views"],
            vid["likes"],
            vid["comments"],
            vid["shares"],
            vid["date"],
            vid["url"],
            score,
            emojis,
            words,
            sports_kw,
        ]
        sheet.append_row(row, value_input_option="USER_ENTERED")
        new_count += 1
        logging.info(f"Appended new video: {vid['url']}")

    logging.info(f"Done — {new_count} new videos added.")

if __name__ == "__main__":
    main()

import os
import time
import logging
import json
from TikTokApi import TikTokApi
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ─── CONFIG ────────────────────────────────────────────────────────────────────
TIKTOK_USER     = "impulseprod"
SHEET_ID        = "10UqBGA93ns5b-56gldRCwcSbGHtjqWCj45dhJS8lLAA"
SHEET_NAME      = "Impulse Video Tracker"
SERVICE_ACCOUNT = "credentials.json"
# ────────────────────────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")

def load_credentials():
    """If running in Actions, write the raw JSON secret to credentials.json."""
    secret = os.getenv("GOOGLE_SHEETS_CREDENTIALS")
    if secret:
        logging.info("Writing Google credentials from secret…")
        with open(SERVICE_ACCOUNT, "w") as f:
            f.write(secret)

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

def parse_videos():
    """Use TikTokApi to fetch the latest videos for TIKTOK_USER."""
    api = TikTokApi()
    items = api.by_username(TIKTOK_USER, count=50)
    videos = []
    for item in items:
        stats   = item.get("stats", {})
        vid_id  = item.get("id")
        caption = item.get("desc", "")
        videos.append({
            "caption": caption,
            "views":    stats.get("playCount", 0),
            "likes":    stats.get("diggCount", 0),
            "comments": stats.get("commentCount", 0),
            "shares":   stats.get("shareCount", 0),
            "url":      f"https://www.tiktok.com/@{TIKTOK_USER}/video/{vid_id}",
            "date":     time.strftime(
                            "%Y-%m-%d %H:%M:%S",
                            time.localtime(item.get("createTime", 0))
                        )
        })
    return videos

def analyze_caption(text):
    """Count emojis, words, ALL-CAPS, and sports keywords."""
    emojis     = len([c for c in text if c in "😀😂❤️👍🏀🏈🏆"])  # simple emoji set
    words      = len(text.split())
    all_caps   = len([w for w in text.split() if w.isupper() and len(w) > 1])
    keywords   = ["Curry","Mahomes","LeBron","buzzer","touchdown","finals","playoffs"]
    sports_kw  = sum(text.lower().count(k.lower()) for k in keywords)
    return emojis, words, all_caps, sports_kw

def main():
    load_credentials()
    sheet = init_sheet()
    existing = get_existing_urls(sheet)

    videos = parse_videos()
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

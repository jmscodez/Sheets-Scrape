import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import List

import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

import gspread
from oauth2client.service_account import ServiceAccountCredentials

SHEET_ID = "10UqBGA93ns5b"
SHEET_NAME = "Impulse Video Tracker"
TIKTOK_URL = "https://www.tiktok.com/@impulseprod"
RETRY_COUNT = 3
RETRY_DELAY = 5  # seconds

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

SPORTS_KEYWORDS = [
    "Curry",
    "LeBron",
    "Mahomes",
    "buzzer",
    "touchdown",
    "finals",
    "playoffs",
]


@dataclass
class Video:
    caption: str
    views: int
    likes: int
    comments: int
    shares: int
    date: str
    url: str
    score: int = field(init=False)
    emojis: int = field(init=False)
    words: int = field(init=False)
    sports_keywords: int = field(init=False)

    def __post_init__(self):
        self.score = self.views + 2 * self.likes + 3 * self.comments + 5 * self.shares
        self.emojis = len(re.findall(r"[\U0001F600-\U0001F64F]", self.caption))
        self.words = len(self.caption.split())
        self.sports_keywords = sum(
            self.caption.count(word) for word in SPORTS_KEYWORDS
        )


def get_html(url: str) -> str:
    ua = UserAgent()
    headers = {
        "User-Agent": ua.random,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    for attempt in range(1, RETRY_COUNT + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                return resp.text
            logging.error("HTTP %s on attempt %s", resp.status_code, attempt)
        except Exception as exc:
            logging.error("Request failed on attempt %s: %s", attempt, exc)
        time.sleep(RETRY_DELAY)
    raise RuntimeError("Failed to fetch page after retries")


def parse_videos(html: str) -> List[Video]:
    soup = BeautifulSoup(html, "html.parser")
    state_script = soup.find("script", id="SIGI_STATE")
    if not state_script:
        logging.error("Failed to find SIGI_STATE script. Layout may have changed.")
        return []
    try:
        data = json.loads(state_script.string)
    except Exception as exc:
        logging.error("Error parsing state JSON: %s", exc)
        return []

    videos = []
    for item in data.get("ItemModule", {}).values():
        caption = item.get("desc", "")
        stats = item.get("stats", {})
        video = Video(
            caption=caption,
            views=int(stats.get("playCount", 0)),
            likes=int(stats.get("diggCount", 0)),
            comments=int(stats.get("commentCount", 0)),
            shares=int(stats.get("shareCount", 0)),
            date=time.strftime("%Y-%m-%d", time.localtime(item.get("createTime", 0))),
            url=f"https://www.tiktok.com/@impulseprod/video/{item.get('id')}",
        )
        videos.append(video)
    return videos


def authorize_sheet():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    credentials = ServiceAccountCredentials.from_json_keyfile_name(
        "credentials.json", scope
    )
    gc = gspread.authorize(credentials)
    sh = gc.open_by_key(SHEET_ID)
    return sh.worksheet(SHEET_NAME)


def read_existing_urls(sheet) -> List[str]:
    try:
        urls = sheet.col_values(7)
    except Exception as exc:
        logging.error("Failed to read existing URLs: %s", exc)
        urls = []
    return urls


def append_videos(sheet, videos: List[Video]):
    existing = set(read_existing_urls(sheet))
    new_rows = []
    new_videos = []
    for v in videos:
        if v.url in existing:
            continue
        row = [
            v.caption,
            v.views,
            v.likes,
            v.comments,
            v.shares,
            v.date,
            v.url,
            v.score,
            v.emojis,
            v.words,
            v.sports_keywords,
        ]
        new_rows.append(row)
        new_videos.append(v)

    if new_rows:
        sheet.append_rows(new_rows)
    return new_videos


def main():
    logging.info("Fetching TikTok page…")
    try:
        html = get_html(TIKTOK_URL)
    except Exception as exc:
        logging.error("Failed to download TikTok page: %s", exc)
        return

    videos = parse_videos(html)
    if not videos:
        logging.error("No videos parsed. Exiting.")
        return

    sheet = authorize_sheet()
    added_videos = append_videos(sheet, videos)

    added_videos.sort(key=lambda v: v.score, reverse=True)
    logging.info("Added %d new videos", len(added_videos))
    for v in added_videos[:5]:
        logging.info("%s | score=%d", v.url, v.score)


if __name__ == "__main__":
    main()

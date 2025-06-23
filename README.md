# Impulse TikTok Analyzer

This project scrapes videos from the TikTok account [@impulseprod](https://www.tiktok.com/@impulseprod), analyzes engagement, and writes results to a Google Sheet.

## Setup
1. Create a service account and download the credentials JSON. Save it as `credentials.json` in the repository root.
2. Share the Google Sheet (`ID: 10UqBGA93ns5b`) with the service account email `sheets@nfl-highl.iam.gserviceaccount.com`.
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run the analyzer manually:
   ```bash
   python impulse-analyzer/main.py
   ```

## GitHub Actions
The workflow in `.github/workflows/scrape.yml` runs the scraper every Sunday at 10am UTC.

# TD Analytics Toolkit Bot

Telegram bot that lets partners self-serve analytics spreadsheets.
Each child sheet is pre-wired with a loader script and library reference
pointing at the correct mother spreadsheet.

---

## Architecture

```
Mother Sheet (yours, private)
  └── Apps Script library (ChinCore / TDCore / FBCore / TDCoreV5)

Bot (Python, runs on a VPS)
  ├── Admin → manages partners, mother sheets, access
  └── Partner → creates child sheets on demand
        └── Child Sheet (shared with partner)
              └── Bound loader script
                    └── Library ref → Mother Script
```

---

## Step-by-step setup

### 1. Create a Telegram bot
```
/newbot  →  @BotFather
```
Copy the token.

---

### 2. Google Service Account

1. Open [console.cloud.google.com](https://console.cloud.google.com)
2. Create a new project (or pick an existing one)
3. Enable these APIs:
   - Google Sheets API
   - Google Drive API
   - Apps Script API
4. Go to **IAM & Admin → Service Accounts → Create**
5. Download the JSON key → save as `service_account.json` next to `bot.py`

> The service account email looks like:
> `bot@your-project.iam.gserviceaccount.com`
>
> All spreadsheets the bot creates will be **owned by this email** and
> shared with "anyone with the link (editor)".

---

### 3. Prepare each Mother Sheet

For every platform (Cellexpert / ReferOn / Affilka / Affilka FB):

1. Open the mother spreadsheet
2. Open **Extensions → Apps Script**
3. Note the **Script ID**:
   - Click ⚙️ Project Settings → Script ID (long alphanumeric string)
4. The script in the editor is your library code (ChinCore / TDCore / etc.)
5. Make sure the script is set to allow library access:
   - Deploy → **Manage Deployments** (or just leave HEAD/development mode)

---

### 4. Configure .env

```bash
cp .env.example .env
# edit .env with your values
```

---

### 5. Install and run

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python bot.py
```

For production use `systemd` or `supervisor`:

```ini
# /etc/systemd/system/analytics-bot.service
[Unit]
Description=Analytics Toolkit Bot
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/analytics_bot
EnvironmentFile=/home/ubuntu/analytics_bot/.env
ExecStart=/home/ubuntu/analytics_bot/.venv/bin/python bot.py
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
systemctl enable analytics-bot
systemctl start analytics-bot
```

---

## Admin workflow

```
/start  or  /admin
  👑 Admin Panel
    ├── 👥 Partners
    │     ├── ➕ Add Partner   (enter TG ID + name)
    │     └── [partner]
    │           ├── 🔗 Assign/Remove Sheets
    │           └── ❌/✅ Activate/Deactivate
    ├── 📋 Mother Sheets
    │     └── ➕ Add Sheet   (sheet ID → name → script ID → platform)
    └── 🔗 Assign Sheets   (quick assign shortcut)
```

**Adding a mother sheet fields:**
| Field | Where to find it |
|-------|-----------------|
| Spreadsheet ID | URL: `…/spreadsheets/d/[HERE]/edit` |
| Display name | Anything — shown in bot only |
| Script ID | Apps Script editor → ⚙️ Project Settings → Script ID |
| Platform | Pick from list |

---

## Partner workflow

```
/start
  👋 Welcome
    ├── ➕ Create New Sheet
    │     ├── Select platform (mother sheet)
    │     ├── Configure: webname / creo / click ID / OAS / min FTD / HR%
    │     └── ✅ Confirm → sheet created → link returned
    └── 📋 My Sheets
          └── [sheet] → link + details
```

---

## Supported platforms

| Key | Library symbol | Default webname | Notes |
|-----|----------------|-----------------|-------|
| `cellexpert` | `ChinCore` | `afp2` | Has HR%, OAS |
| `referon` | `TDCore` | `pubid` | Has min FTD gate |
| `affilka_fb` | `FBCore` | `afp1` | FB-specific tags, normalize |
| `affilka` | `TDCoreV5` | `pubid` | Standard Affilka |

Adding a new platform: add an entry to `PLATFORMS` dict in `bot.py`.
No other changes needed.

---

## Adding more platforms (Affise, MyAffiliates, etc.)

Copy an existing entry in `PLATFORMS`, adjust:
- `name` — display name
- `library_symbol` — the `var LIBRARY_NAME = ...` identifier used in GAS
- `fields` — which fields the wizard shows
- `public_api` — mapping of action keys to `_Public()` function names

The loader script is auto-generated from these definitions.

---

## Data file (data.json)

```json
{
  "admins": [123456789],
  "mother_sheets": {
    "SPREADSHEET_ID": {
      "id": "...",
      "name": "Cellexpert Core",
      "script_id": "SCRIPT_ID",
      "platform": "cellexpert",
      "library_symbol": "ChinCore"
    }
  },
  "partners": {
    "987654321": {
      "telegram_id": 987654321,
      "name": "John Doe",
      "assigned_sheet_ids": ["SPREADSHEET_ID"],
      "child_sheets": [...],
      "active": true
    }
  }
}
```

For production, swap `Storage` class for SQLite or Postgres.

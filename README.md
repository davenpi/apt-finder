# apt-finder

AI-powered apartment search for NYC. Uses [browser-use](https://github.com/browser-use/browser-use) agents to scrape StreetEasy, evaluate listings against your preferences, and rank them.

## How it works

1. **Search** — A browser agent navigates StreetEasy, extracts listings, and filters out sponsored/over-budget/duplicate results.
2. **Evaluate** — Parallel browser agents visit each listing, click through photos, and produce structured evaluations (light, finishes, bathroom condition, red flags, etc.).
3. **Rank** — Evaluations are scored against your preferences and written to a markdown report in `findings/`.
4. **Sync** — Reads a Google Sheet where you paste listing URLs, extracts agent contact info, and writes it back for outreach tracking.

## Setup

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
# Clone and install
git clone https://github.com/davenpi/apt-finder.git
cd apt-finder
uv sync
uv pip install -e .

# Set up browser-use credentials
cp .env.example .env
# Edit .env with your BROWSER_USE_API_KEY

# Create your preferences file
cp preferences.example.md preferences.md
# Edit preferences.md with your search criteria
```

Activate the venv so the `apt` command is on your PATH:

```bash
source .venv/bin/activate
```

### Google Sheets setup (for `apt sync`)

1. Go to [Google Cloud Console](https://console.cloud.google.com/) and create a project (or use an existing one).
2. Enable the **Google Sheets API** and **Google Drive API**.
3. Go to **APIs & Services > Credentials**, create an **OAuth 2.0 Client ID** (Desktop app type).
4. Download the JSON and save it as `credentials.json` in the project root.
5. Create a Google Sheet. `apt sync` expects this column layout starting at B2:

   | URL | Agent Name | Agent Email | Agent Phone | Available | Status | Tour Date | Notes |
   | --- | ---------- | ----------- | ----------- | --------- | ------ | --------- | ----- |

   Paste listing URLs into the **URL** column. The agent fills in contact info, availability, and tour dates. **Status** tracks your outreach pipeline: `new` → `contacted` → `replied` → `touring` → `passed`.

6. Set the sheet URL:

   ```bash
   export SHEET_URL="https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID/edit"
   ```

   Or add it to your `.env` file.

7. On first run, a browser window will open for Google OAuth consent. The token is cached in `authorized_user.json` for subsequent runs.

### Notion setup (for `apt init` / `apt add`)

1. Create a [Notion internal integration](https://www.notion.so/my-integrations) and copy the token.
2. In Notion, create a page called "Apt search" (or use an existing one). Share it with your integration via **... > Connections > Add connection**.
3. Copy the page ID from the URL (the 32-character hex string after the page name).
4. Add to your `.env`:

   ```bash
   NOTION_TOKEN="secret_..."
   NOTION_PAGE_ID="316d3e8f-..."   # your Apt search page ID
   ```

5. Run `apt init` to create the listings database. It prints a database ID — add it to `.env`:

   ```bash
   NOTION_DB_ID="abc123..."
   ```

6. Now `apt add <url>` will create listing pages with contact info and rich blocks.

## Usage

```bash
# Full pipeline: search, evaluate, and rank
apt find -l EV -n 15

# Evaluate a single listing URL
apt eval https://streeteasy.com/building/15-cornelia-street-new_york/5f

# One-time: create the Notion listings database
apt init

# Add a listing to Notion + extract contact info
apt add https://streeteasy.com/building/15-cornelia-street-new_york/5f

# Sync Google Sheet — fill in agent contact info for new listings
apt sync

# Just search + filter (no evaluation)
apt search -l EV -n 10

# Re-rank from existing evaluations
apt rank -l EV
```

### Location shortcuts

| Flag      | Neighborhood        | URL                                                |
| --------- | ------------------- | -------------------------------------------------- |
| `EV`      | East Village        | `streeteasy.com/for-rent/east-village/price:-4300` |
| `EV-CORE` | East Village (core) | Same + bounding box: ~E 2nd–E 14th, 1st Ave–Ave B  |
| `WV`      | West Village        | `streeteasy.com/for-rent/west-village/price:-4300` |

Add more in the `LOCATIONS` dict in `search.py`.

## Configuration

### `preferences.md`

This is the core of the system. The evaluation agents read this file to understand what you care about. See `preferences.example.md` for a template.

### `search.py` constants

| Constant         | Default | Description                                                        |
| ---------------- | ------- | ------------------------------------------------------------------ |
| `BUDGET_CEILING` | 4350    | Max price before filtering out a listing                           |
| `BATCH_SIZE`     | 5       | Max concurrent browser agents during evaluation                    |
| `HEADLESS`       | False   | Set to True to hide browsers (you'll need False to solve captchas) |

## Output

- `data/{location}_inventory.json` — Raw filtered listings from search
- `data/{location}_evaluations.json` — Structured evaluations
- `findings/{timestamp}.md` — Ranked markdown report

## Roadmap

- [ ] **Bounding box search** — StreetEasy supports `in_rect` coordinates for map-bounded searches, but the URL only works in Safari (Chromium drops the bounding box). Need to either fix the URL encoding or have the agent zoom the map after loading.
- [ ] **More listing sources** — Apartments.com, Zillow, Craigslist
- [ ] **Automated outreach** — `apt reach` command to draft/send inquiry emails for new listings
- [x] **Notion integration** — `apt init` + `apt add` for visual tracking (Notion API)
- [ ] **Dedup across runs** — Merge evaluations instead of overwriting, skip already-evaluated listings

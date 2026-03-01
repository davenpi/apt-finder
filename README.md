# apt-finder

AI-powered apartment search for NYC. Uses [browser-use](https://github.com/browser-use/browser-use) agents to scrape StreetEasy, evaluate listings against your preferences, and rank them.

## How it works

1. **Search** — A browser agent navigates StreetEasy, extracts listings, and filters out sponsored/over-budget/duplicate results.
2. **Evaluate** — Parallel browser agents visit each listing, click through photos, and produce structured evaluations (light, finishes, bathroom condition, red flags, etc.).
3. **Rank** — Evaluations are scored against your preferences and written to a markdown report in `findings/`.
4. **Track** — Two options for outreach tracking:
   - **Notion** (`apt add`) — Creates rich pages with contact info, toggles, bookmarks, and maps.
   - **Google Sheets** (`apt sync`) — Fills in agent contact info on a spreadsheet.

## Setup

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/davenpi/apt-finder.git
cd apt-finder
uv sync && uv pip install -e .
cp .env.example .env       # add your BROWSER_USE_API_KEY
cp preferences.example.md preferences.md  # your search criteria
source .venv/bin/activate
```

### Notion setup

1. Create a [Notion internal integration](https://www.notion.so/my-integrations) and copy the token.
2. Create a page in Notion (e.g. "Apt search") and share it with your integration via **... > Connections**.
3. Add to `.env`:

   ```
   NOTION_TOKEN="secret_..."
   NOTION_PAGE_ID="316d3e8f-..."
   ```

4. Run `apt init` — it prints a database ID. Add that too:

   ```
   NOTION_DB_ID="abc123..."
   ```

### Google Sheets setup

1. Enable the **Google Sheets API** and **Google Drive API** in [Google Cloud Console](https://console.cloud.google.com/).
2. Create an **OAuth 2.0 Client ID** (Desktop app), download the JSON as `credentials.json`.
3. Create a sheet with columns starting at B2: URL | Agent Name | Agent Email | Agent Phone | Available | Status | Tour Date | Notes.
4. Add to `.env`:

   ```
   SHEET_URL="https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID/edit"
   ```

5. First run opens a browser for OAuth consent. Token is cached in `authorized_user.json`.

## Usage

```bash
# Full pipeline: search → evaluate → rank
apt find -l EV -n 15

# Evaluate a single listing
apt eval <url>

# Add a listing to Notion + extract contact info
apt add <url>

# Sync Google Sheet — fill in contact info for new rows
apt sync

# Debugging helpers
apt search -l EV -n 10   # just inventory + filter
apt rank -l EV            # re-rank from existing evaluations
```

### Location shortcuts

| Flag      | Neighborhood        |
| --------- | ------------------- |
| `EV`      | East Village        |
| `EV-CORE` | East Village (core) |
| `WV`      | West Village        |

Add more in the `LOCATIONS` dict in `search.py`.

## Configuration

| Constant         | Default | Description                                    |
| ---------------- | ------- | ---------------------------------------------- |
| `BUDGET_CEILING` | 4300    | Max rent before filtering out a listing        |
| `BATCH_SIZE`     | 5       | Max concurrent browser agents                  |
| `HEADLESS`       | False   | Set True to hide browsers (False for captchas) |

Edit `preferences.md` to control how listings are scored. See `preferences.example.md` for a template.

## Output

- `data/{location}_inventory.json` — Filtered listings from search
- `data/{location}_evaluations.json` — Structured evaluations
- `findings/{timestamp}.md` — Ranked markdown report

## Roadmap

- [ ] **Bounding box search** — StreetEasy `in_rect` only works in Safari; need to fix URL encoding or have the agent zoom the map.
- [ ] **More listing sources** — Apartments.com, Zillow, Craigslist
- [ ] **Automated outreach** — `apt reach` to draft/send inquiry emails
- [x] **Notion integration** — `apt init` + `apt add` for visual tracking
- [ ] **Dedup across runs** — Skip already-evaluated listings

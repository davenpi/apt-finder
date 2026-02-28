# apt-finder

AI-powered apartment search for NYC. Uses [browser-use](https://github.com/browser-use/browser-use) agents to scrape StreetEasy, evaluate listings against your preferences, and rank them.

## How it works

1. **Search** — A browser agent navigates StreetEasy, extracts listings, and filters out sponsored/over-budget/duplicate results.
2. **Evaluate** — Parallel browser agents visit each listing, click through photos, and produce structured evaluations (light, finishes, bathroom condition, red flags, etc.).
3. **Rank** — Evaluations are scored against your preferences and written to a markdown report in `findings/`.

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

## Usage

```bash
# Full pipeline: search, evaluate, and rank
apt find -l EV -n 15

# Evaluate a single listing URL
apt eval https://streeteasy.com/building/123-main-street/4a

# Just search + filter (no evaluation)
apt search -l EV -n 10

# Re-rank from existing evaluations
apt rank -l EV
```

### Location shortcuts

| Flag | Neighborhood | URL                                                |
| ---- | ------------ | -------------------------------------------------- |
| `EV` | East Village | `streeteasy.com/for-rent/east-village/price:-4300` |
| `WV` | West Village | `streeteasy.com/for-rent/west-village/price:-4300` |

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

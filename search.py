"""
Apartment search pipeline: inventory → filter → evaluate → rank.

Usage:
    apt find -l EV -n 15      # Full pipeline: search → filter → evaluate → rank
    apt find -l WV             # Same for West Village (default 15 listings)
    apt eval <url>             # Evaluate a single listing, append to latest findings
    apt search -l EV -n 15     # Just inventory + filter (debugging)
    apt rank                   # Just rank from existing evaluations (debugging)
"""

import asyncio
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import click
from browser_use import Agent, ChatBrowserUse
from browser_use.browser.profile import BrowserProfile
from browser_use.browser.session import BrowserSession
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
LOCATIONS = {
    "EV": "https://streeteasy.com/for-rent/east-village/price:-4300",
    "EV-CORE": "https://streeteasy.com/for-rent/east-village/price:-4300%7Cin_rect:40.721,40.731,-73.991,-73.975",
    "WV": "https://streeteasy.com/for-rent/west-village/price:-4300",
}

BUDGET_CEILING = 4350
BATCH_SIZE = 5
HEADLESS = False
BROWSER_DATA_DIR = Path("browser_data")
DATA_DIR = Path("data")

PREFERENCES = Path("preferences.md").read_text()

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class Listing(BaseModel):
    address: str = Field(description="Street address of the listing")
    price: int = Field(description="Monthly rent in dollars (numbers only)")
    beds: str = Field(description="Bedroom count, e.g. '1 bed' or 'Studio'")
    baths: str = Field(description="Bathroom count, e.g. '1 bath'")
    url: str = Field(description="Full StreetEasy URL for this listing")


class InventoryResult(BaseModel):
    listings: list[Listing] = Field(description="All organic listings found")


class ListingEvaluation(BaseModel):
    address: str = Field(description="Street address")
    url: str = Field(description="Listing URL")
    price: int = Field(description="Monthly rent in dollars")
    beds_baths: str = Field(description="e.g. '1 bed / 1 bath'")
    sqft: Optional[str] = Field(default=None, description="Square footage if listed")
    floor: Optional[str] = Field(default=None, description="Floor number if listed")
    washer_dryer: str = Field(description="In-unit, in-building, or none")
    dishwasher: str = Field(description="Yes or No")
    elevator_or_walkup: str = Field(description="Elevator or walkup")
    move_in_date: Optional[str] = Field(
        default=None, description="Move-in date if listed"
    )
    light_assessment: str = Field(description="Assessment of natural light from photos")
    bathroom_assessment: str = Field(description="Bathroom condition assessment")
    kitchen_assessment: str = Field(description="Kitchen condition assessment")
    finishes_assessment: str = Field(description="Overall finishes assessment")
    days_on_market: Optional[int] = Field(
        default=None, description="Days on market if shown on the listing"
    )
    red_flags: str = Field(description="Any red flags noticed")
    vibe: str = Field(description="Overall vibe of the apartment")
    score: float = Field(description="Score from 1-10 against preferences")
    score_justification: str = Field(description="One-line justification for the score")


class AgentContact(BaseModel):
    agent_name: str = Field(
        description="All listing agents' names, comma-separated if multiple"
    )
    agent_email: str = Field(default="", description="Agent email(s) if found")
    agent_phone: str = Field(
        description="All agent phone numbers found, comma-separated if multiple"
    )
    available_date: str = Field(
        default="", description="Move-in / availability date if listed"
    )
    tour_dates: str = Field(
        default="",
        description="Available open house or tour dates/times if listed on the page",
    )


# ---------------------------------------------------------------------------
# Step 1: Inventory — extract all organic listings from search results
# ---------------------------------------------------------------------------


async def run_inventory(search_url: str, max_listings: int) -> list[Listing]:
    print("\n=== STEP 1: Inventory ===")
    print(f"Searching: {search_url}")

    llm = ChatBrowserUse()
    profile = BrowserProfile(
        headless=HEADLESS,
        viewport_width=800,
        viewport_height=1200,
        user_data_dir=str(BROWSER_DATA_DIR / "default"),
    )
    session = BrowserSession(browser_profile=profile)

    agent = Agent(
        task=f"""Go to {search_url}

You are extracting apartment listings from StreetEasy search results.

The results are in a LIST on the LEFT side of the page (not the map on the right).
Do NOT interact with the map. Focus only on the listing cards in the left column.

1. Wait for the search results to load.
2. Extract all organic listings visible on page 1 WITHOUT scrolling.
3. Now look for the PAGINATION control at the bottom of the listing column on the
   left side of the page. It will show page numbers like "1 2 3 ..." or a "Next"
   link. Do NOT scroll to find it — instead, use Page Down key once or twice to
   bring it into view.
4. Click the link for page 2. Wait for new listings to load.
5. Extract the listings from page 2.
6. Continue to page 3 if needed, until you have up to {max_listings} organic
   listings total.

IMPORTANT: SKIP any sponsored/featured listings. These have "?featured=1" or
"?infeed=1" in their URL, or are labeled "Featured" or "Sponsored" on the page.

For each listing extract:
- address: the street address
- price: monthly rent as a number (e.g. 4125, not "$4,125")
- beds: bedroom info (e.g. "1 bed", "Studio", "2 beds")
- baths: bathroom info (e.g. "1 bath")
- url: the full URL to the listing detail page

Stop once you have {max_listings} organic listings or run out of pages.""",
        llm=llm,
        browser_session=session,
        output_model_schema=InventoryResult,
        use_vision=True,
    )

    result = await agent.run()
    inventory = result.get_structured_output(InventoryResult)

    if inventory is None:
        print(
            "WARNING: Agent did not return structured output. Trying to parse final_result."
        )
        # Fallback: try to parse the text output
        raw = result.final_result()
        if raw:
            print(f"Raw output:\n{raw[:500]}")
        return []

    listings = inventory.listings[:max_listings]
    print(f"Found {len(inventory.listings)} listings, keeping first {len(listings)}")
    for listing in listings:
        print(
            f"  {listing.address} — ${listing.price} — {listing.beds}/{listing.baths}"
        )

    return listings


def save_inventory(listings: list[Listing], location_key: str) -> Path:
    DATA_DIR.mkdir(exist_ok=True)
    path = DATA_DIR / f"{location_key}_inventory.json"
    path.write_text(json.dumps([item.model_dump() for item in listings], indent=2))
    print(f"Saved {len(listings)} listings to {path}")
    return path


def load_inventory(location_key: str) -> list[Listing]:
    path = DATA_DIR / f"{location_key}_inventory.json"
    if not path.exists():
        print(f"ERROR: {path} not found. Run 'apt search -l {location_key}' first.")
        sys.exit(1)
    data = json.loads(path.read_text())
    listings = [Listing(**item) for item in data]
    print(f"Loaded {len(listings)} listings from {path}")
    return listings


# ---------------------------------------------------------------------------
# Step 2: Filter — drop featured, over-budget, dupes
# ---------------------------------------------------------------------------


def filter_listings(listings: list[Listing]) -> list[Listing]:
    print(f"\n=== STEP 2: Filter ({len(listings)} listings) ===")

    seen_addresses: set[str] = set()
    kept: list[Listing] = []

    for listing in listings:
        # Skip featured/infeed URLs
        if "?featured=1" in listing.url or "?infeed=1" in listing.url:
            print(f"  SKIP (featured): {listing.address}")
            continue

        # Skip over budget
        if listing.price > BUDGET_CEILING:
            print(f"  SKIP (over budget ${listing.price}): {listing.address}")
            continue

        # Skip dupes
        addr_key = listing.address.lower().strip()
        if addr_key in seen_addresses:
            print(f"  SKIP (dupe): {listing.address}")
            continue
        seen_addresses.add(addr_key)

        kept.append(listing)

    print(f"Kept {len(kept)} listings after filtering")
    return kept


# ---------------------------------------------------------------------------
# Step 3: Evaluate — parallel agents, one per listing
# ---------------------------------------------------------------------------


async def evaluate_listing(
    listing: Listing, slot_pool: asyncio.Queue
) -> ListingEvaluation | None:
    slot = await slot_pool.get()
    try:
        print(f"  Evaluating: {listing.address} ({listing.url})")

        llm = ChatBrowserUse()
        profile = BrowserProfile(
            headless=HEADLESS,
            user_data_dir=str(BROWSER_DATA_DIR / f"eval_{slot}"),
        )
        session = BrowserSession(browser_profile=profile)

        agent = Agent(
            task=f"""Go to {listing.url}

You are evaluating this apartment listing for a renter. Here are their preferences:

{PREFERENCES}

Do the following:
1. Read the listing details (price, beds/baths, sqft, amenities, description)
2. Click through ALL the photos in the carousel — look at every single one
3. Pay close attention to: natural light, bathroom condition, kitchen condition,
   finishes, and overall vibe

Then produce a structured evaluation. Fill in every field carefully:

- address: the street address
- url: {listing.url}
- price: monthly rent as a number
- beds_baths: e.g. "1 bed / 1 bath" or "Studio / 1 bath"
- sqft: square footage if listed, null otherwise
- floor: floor number if listed, null otherwise
- washer_dryer: "In-unit", "In-building", or "None"
- dishwasher: "Yes" or "No"
- elevator_or_walkup: "Elevator" or "Walkup"
- move_in_date: if listed, null otherwise
- days_on_market: number of days on market if shown on the listing, null otherwise
- light_assessment: What do the photos tell you about natural light? How many
  windows visible? Which direction might they face? Any rooms that look dark?
- bathroom_assessment: Condition, cleanliness, modern or dated fixtures?
- kitchen_assessment: Condition, counter space, appliances, gas or electric?
- finishes_assessment: Overall condition — floors, walls, fixtures. Modern or dated?
- red_flags: Missing photos? Suspiciously low price? Anything sketchy?
- vibe: Does this feel like a place you'd want to come home to?

SCORING — start at 5.0 (neutral) and adjust up/down. Be harsh and spread scores.

Bonuses (add points):
  +1.0  In-unit W/D
  +1.0  Excellent natural light (every room bright, big windows)
  +0.5  Modern/renovated bathroom
  +0.5  Modern/renovated kitchen
  +0.5  Under $3,800/mo
  +0.5  Quiet side street or rear-facing

Penalties (subtract points):
  -1.0  Any room with no window (windowless bedroom/flex = automatic)
  -2.0  Stained/grimy bathroom (dealbreaker)
  -1.0  Walkup AND floor 4+ (hauling groceries/laundry)
  -0.5  Walkup floor 3
  -1.0  No W/D at all (not even in-building)
  -1.0  Avenue-facing (noise)
  -1.0  60+ days on market (something is wrong)
  -0.5  30-60 days on market (yellow flag)
  -0.5  Photos are "representative" / not actual unit
  -0.5  Missing bathroom or kitchen photos
  -0.5  Move-in date after April 15, 2026

- score: the final score after applying bonuses and penalties
- score_justification: list the specific bonuses and penalties you applied""",
            llm=llm,
            browser_session=session,
            output_model_schema=ListingEvaluation,
            use_vision=True,
        )

        result = await agent.run()
        evaluation = result.get_structured_output(ListingEvaluation)
        if evaluation:
            print(f"  ✓ {listing.address} — score: {evaluation.score}/10")
            return evaluation
        else:
            print(f"  ✗ {listing.address} — no structured output")
            return None
    except Exception as e:
        print(f"  ✗ {listing.address} — error: {e}")
        return None
    finally:
        slot_pool.put_nowait(slot)


def _seed_eval_slots():
    """Copy default browser data into each eval slot so captcha cookies carry over."""
    default = BROWSER_DATA_DIR / "default"
    if not default.exists():
        return
    for i in range(BATCH_SIZE):
        shutil.copytree(default, BROWSER_DATA_DIR / f"eval_{i}", dirs_exist_ok=True)


async def evaluate_all(listings: list[Listing]) -> list[ListingEvaluation]:
    print(
        f"\n=== STEP 3: Evaluate ({len(listings)} listings, batch size {BATCH_SIZE}) ==="
    )

    _seed_eval_slots()

    slot_pool: asyncio.Queue[int] = asyncio.Queue()
    for i in range(BATCH_SIZE):
        slot_pool.put_nowait(i)
    tasks = [evaluate_listing(listing, slot_pool) for listing in listings]
    results = await asyncio.gather(*tasks)

    evaluations = [r for r in results if r is not None]
    print(f"Got {len(evaluations)} evaluations out of {len(listings)} listings")
    return evaluations


def save_evaluations(evaluations: list[ListingEvaluation], location_key: str) -> Path:
    DATA_DIR.mkdir(exist_ok=True)
    path = DATA_DIR / f"{location_key}_evaluations.json"
    path.write_text(json.dumps([e.model_dump() for e in evaluations], indent=2))
    print(f"Saved {len(evaluations)} evaluations to {path}")
    return path


def load_evaluations(location_key: str) -> list[ListingEvaluation]:
    path = DATA_DIR / f"{location_key}_evaluations.json"
    if not path.exists():
        print(f"ERROR: {path} not found. Run 'apt find -l {location_key}' first.")
        sys.exit(1)
    data = json.loads(path.read_text())
    evaluations = [ListingEvaluation(**item) for item in data]
    print(f"Loaded {len(evaluations)} evaluations from {path}")
    return evaluations


# ---------------------------------------------------------------------------
# Step 4: Rank and output
# ---------------------------------------------------------------------------


def rank_and_output(evaluations: list[ListingEvaluation], search_url: str) -> Path:
    print(f"\n=== STEP 4: Rank & Output ({len(evaluations)} evaluations) ===")

    ranked = sorted(evaluations, key=lambda e: e.score, reverse=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    outdir = Path("findings")
    outdir.mkdir(exist_ok=True)
    outpath = outdir / f"{timestamp}.md"

    lines: list[str] = []
    lines.append(
        f"# Apartment Search Results — {datetime.now().strftime('%Y-%m-%d')}\n"
    )
    lines.append(f"Search: {search_url}")
    lines.append(f"Evaluated: {len(ranked)} listings\n")

    for i, ev in enumerate(ranked, 1):
        lines.append("---\n")
        lines.append(f"## #{i}: {ev.address} — {ev.score}/10\n")
        lines.append(f"- **Price**: ${ev.price:,} | {ev.beds_baths}")
        if ev.sqft:
            lines.append(f"- **Size**: {ev.sqft}")
        if ev.floor:
            lines.append(f"- **Floor**: {ev.floor}")
        lines.append(
            f"- **W/D**: {ev.washer_dryer} | **Dishwasher**: {ev.dishwasher} | **Building**: {ev.elevator_or_walkup}"
        )
        if ev.move_in_date:
            lines.append(f"- **Move-in**: {ev.move_in_date}")
        if ev.days_on_market is not None:
            lines.append(f"- **Days on market**: {ev.days_on_market}")
        lines.append(f"- **Score justification**: {ev.score_justification}")
        lines.append("")
        lines.append(f"**Light**: {ev.light_assessment}\n")
        lines.append(f"**Bathroom**: {ev.bathroom_assessment}\n")
        lines.append(f"**Kitchen**: {ev.kitchen_assessment}\n")
        lines.append(f"**Finishes**: {ev.finishes_assessment}\n")
        lines.append(f"**Red flags**: {ev.red_flags}\n")
        lines.append(f"**Vibe**: {ev.vibe}\n")
        lines.append(f"[View listing]({ev.url})\n")

    outpath.write_text("\n".join(lines))
    print(f"Results written to {outpath}")
    return outpath


# ---------------------------------------------------------------------------
# Contact extraction — lightweight agent for sync
# ---------------------------------------------------------------------------


async def extract_contact(url: str) -> AgentContact | None:
    """Visit a StreetEasy listing and extract the listing agent's contact info."""
    print(f"  Extracting contact: {url}")

    llm = ChatBrowserUse()
    profile = BrowserProfile(
        headless=HEADLESS,
        user_data_dir=str(BROWSER_DATA_DIR / "default"),
    )
    session = BrowserSession(browser_profile=profile)

    agent = Agent(
        task=f"""Go to {url}

You are extracting the LISTING AGENT's contact information from this StreetEasy page.

1. Look for the agent/broker section on the listing page. It usually appears below
   the listing details and shows the agent's name, brokerage, and contact info.
2. If there are MULTIPLE agents listed, get ALL of their names and phone numbers.
   Click EVERY "Show phone number" button you see.
3. If there is a "Contact" or "Email Agent" button, click it to reveal email/phone.
4. Look for the availability / move-in date (often shown near the top of the listing).
5. Also look for any open house or tour availability on the page (often shown near
   the top or in a scheduling section).
6. Extract:
   - agent_name: All agents' names, comma-separated if multiple
   - agent_email: Their email address(es) (if visible)
   - agent_phone: ALL phone numbers found, comma-separated if multiple
   - available_date: The move-in or availability date (e.g. "4/2/2026")
   - tour_dates: Any listed open house dates/times or tour availability (if visible)

If you cannot find an email, phone, or tour dates, leave those fields as empty strings.
Do NOT fabricate contact info — only extract what is actually on the page.""",
        llm=llm,
        browser_session=session,
        output_model_schema=AgentContact,
        use_vision=True,
    )

    try:
        result = await agent.run()
        contact = result.get_structured_output(AgentContact)
        if contact:
            print(
                f"  -> {contact.agent_name} | {contact.agent_email} | {contact.agent_phone}"
            )
            return contact
        else:
            print(f"  -> No structured output for {url}")
            return None
    except Exception as e:
        print(f"  -> Error extracting contact from {url}: {e}")
        return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def resolve_location(location: str) -> tuple[str, str]:
    """Resolve a location shortcut to (key, url). Exits on unknown key."""
    key = location.upper()
    if key not in LOCATIONS:
        click.echo(f"Unknown location: {location}")
        click.echo(f"Available: {', '.join(LOCATIONS)}")
        sys.exit(1)
    return key, LOCATIONS[key]


@click.group()
def cli():
    """apt — apartment search pipeline."""
    pass


@cli.command()
@click.option("-l", "--location", required=True, help="Location shortcut (EV, WV)")
@click.option(
    "-n", "--num", default=15, show_default=True, help="Max listings to scrape"
)
def find(location: str, num: int):
    """Full pipeline: search → filter → evaluate → rank."""
    key, search_url = resolve_location(location)

    async def _run():
        all_listings = await run_inventory(search_url, num)
        if not all_listings:
            click.echo("No listings found.")
            return
        filtered = filter_listings(all_listings)
        if not filtered:
            click.echo("All listings filtered out.")
            return
        save_inventory(filtered, key)
        evaluations = await evaluate_all(filtered)
        if not evaluations:
            click.echo("No evaluations completed.")
            return
        save_evaluations(evaluations, key)
        rank_and_output(evaluations, search_url)

    asyncio.run(_run())


def address_from_url(url: str) -> str:
    """Extract a human-readable address from a StreetEasy URL.

    e.g. https://streeteasy.com/building/15-cornelia-street-new_york/5f
         → "15 Cornelia Street #5F"
    """
    parts = url.rstrip("/").split("/")
    address_slug = parts[-2] if len(parts) >= 2 else "unknown"
    unit = parts[-1] if len(parts) >= 2 else ""
    address = address_slug.replace("-", " ").replace("_", " ").title()
    if unit:
        address = f"{address} #{unit.upper()}"
    return address


@cli.command("eval")
@click.argument("url")
def eval_url(url: str):
    """Evaluate a single listing and append to evaluations."""
    address = address_from_url(url)
    stub = Listing(address=address, price=0, beds="", baths="", url=url)

    async def _run():
        slot_pool: asyncio.Queue[int] = asyncio.Queue()
        slot_pool.put_nowait(0)
        evaluation = await evaluate_listing(stub, slot_pool)
        if not evaluation:
            click.echo("Evaluation failed.")
            return

        # Append to generic evaluations file
        evals_path = DATA_DIR / "evaluations.json"
        DATA_DIR.mkdir(exist_ok=True)
        existing: list[dict] = []
        if evals_path.exists():
            existing = json.loads(evals_path.read_text())
        existing.append(evaluation.model_dump())
        evals_path.write_text(json.dumps(existing, indent=2))
        click.echo(f"Appended evaluation to {evals_path}")

        # Re-rank with all evaluations
        all_evals = [ListingEvaluation(**e) for e in existing]
        rank_and_output(all_evals, url)

    asyncio.run(_run())


@cli.command()
@click.option("-l", "--location", required=True, help="Location shortcut (EV, WV)")
@click.option(
    "-n", "--num", default=15, show_default=True, help="Max listings to scrape"
)
def search(location: str, num: int):
    """Just inventory + filter (debugging). Saves to data/."""
    key, search_url = resolve_location(location)

    async def _run():
        all_listings = await run_inventory(search_url, num)
        if not all_listings:
            click.echo("No listings found.")
            return
        filtered = filter_listings(all_listings)
        if not filtered:
            click.echo("All listings filtered out.")
            return
        save_inventory(filtered, key)

    asyncio.run(_run())


@cli.command()
@click.option("-l", "--location", required=True, help="Location shortcut (EV, WV)")
def rank(location: str):
    """Rank from existing evaluations and write findings."""
    key, search_url = resolve_location(location)
    evaluations = load_evaluations(key)
    rank_and_output(evaluations, search_url)


@cli.command("init")
def init_notion():
    """One-time setup: create the Notion listings database."""
    from notion import create_database

    click.echo("Creating Notion database...")
    db_id = create_database()
    click.echo(f"Database created: {db_id}")
    click.echo(f'\nAdd this to your .env file:\n  NOTION_DB_ID="{db_id}"')


@cli.command("add")
@click.argument("url")
def add_to_notion(url: str):
    """Add a listing to Notion and extract contact info."""
    from notion import add_listing, append_listing_blocks, update_listing

    address = address_from_url(url)
    click.echo(f"Adding to Notion: {address}")

    page_id = add_listing(url, address)
    click.echo(f"  Page created: {page_id}")

    async def _run():
        contact = await extract_contact(url)
        if contact:
            update_listing(
                page_id,
                agent_name=contact.agent_name,
                agent_email=contact.agent_email,
                agent_phone=contact.agent_phone,
                available_date=contact.available_date,
                tour_dates=contact.tour_dates,
            )
            click.echo("  Contact info saved to properties")
        append_listing_blocks(address, url, contact)
        click.echo("  Rich blocks added to page")

    asyncio.run(_run())


@cli.command()
def sync():
    """Sync Google Sheet — fill in contact info for new listings."""
    from sheet import get_client, get_new_rows, get_tracker, update_row

    click.echo("Connecting to Google Sheets...")
    client = get_client()
    worksheet = get_tracker(client)

    new_rows = get_new_rows(worksheet)
    if not new_rows:
        click.echo("No new rows to process.")
        return

    click.echo(f"Found {len(new_rows)} new listing(s) to process.\n")

    async def _run():
        for entry in new_rows:
            row_num = entry["row"]
            url = entry["url"]
            click.echo(f"Row {row_num}: {url}")

            contact = await extract_contact(url)
            if contact:
                update_row(
                    worksheet,
                    row_num,
                    agent_name=contact.agent_name,
                    agent_email=contact.agent_email,
                    agent_phone=contact.agent_phone,
                    available_date=contact.available_date,
                    tour_dates=contact.tour_dates,
                )
                click.echo(f"  Updated row {row_num}\n")
            else:
                click.echo(f"  Could not extract contact for row {row_num}\n")

    asyncio.run(_run())

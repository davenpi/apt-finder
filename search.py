"""
Apartment search pipeline: inventory → filter → evaluate → rank.

Usage:
    uv run python search.py inventory   # Step 1+2: scrape listings, filter, save to data/inventory.json
    uv run python search.py evaluate    # Step 3:   evaluate each listing, save to data/evaluations.json
    uv run python search.py rank        # Step 4:   rank and write findings/*.md
    uv run python search.py             # Run all steps end-to-end
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from browser_use import Agent, ChatBrowserUse
from browser_use.browser.profile import BrowserProfile
from browser_use.browser.session import BrowserSession
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SEARCH_URL = "https://streeteasy.com/for-rent/east-village/price:-4300"
BUDGET_CEILING = 4350
MAX_LISTINGS = 15
BATCH_SIZE = 5
HEADLESS = False
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
    broker_fee: str = Field(description="No fee, 1 month, 15%, etc.")
    move_in_date: Optional[str] = Field(
        default=None, description="Move-in date if listed"
    )
    light_assessment: str = Field(description="Assessment of natural light from photos")
    bathroom_assessment: str = Field(description="Bathroom condition assessment")
    kitchen_assessment: str = Field(description="Kitchen condition assessment")
    finishes_assessment: str = Field(description="Overall finishes assessment")
    red_flags: str = Field(description="Any red flags noticed")
    vibe: str = Field(description="Overall vibe of the apartment")
    score: float = Field(description="Score from 1-10 against preferences")
    score_justification: str = Field(description="One-line justification for the score")


# ---------------------------------------------------------------------------
# Step 1: Inventory — extract all organic listings from search results
# ---------------------------------------------------------------------------


async def run_inventory() -> list[Listing]:
    print("\n=== STEP 1: Inventory ===")
    print(f"Searching: {SEARCH_URL}")

    llm = ChatBrowserUse()
    profile = BrowserProfile(
        headless=HEADLESS, viewport_width=800, viewport_height=1200
    )
    session = BrowserSession(browser_profile=profile)

    agent = Agent(
        task=f"""Go to {SEARCH_URL}

You are extracting apartment listings from StreetEasy search results.

The results are in a LIST on the LEFT side of the page (not the map on the right).
Do NOT interact with the map. Focus only on the listing cards in the left column.

1. Wait for the search results to load.
2. Scroll down through the listing cards on the left side of the page.
3. Extract the organic listings you see on this page.
4. Look for a PAGINATION control (page numbers or "Next" link) at the bottom of the
   listing column. Click to page 2 and extract those listings too. Continue to page 3
   if needed, until you have up to {MAX_LISTINGS} organic listings total.

IMPORTANT: SKIP any sponsored/featured listings. These have "?featured=1" or
"?infeed=1" in their URL, or are labeled "Featured" or "Sponsored" on the page.

For each listing extract:
- address: the street address
- price: monthly rent as a number (e.g. 4125, not "$4,125")
- beds: bedroom info (e.g. "1 bed", "Studio", "2 beds")
- baths: bathroom info (e.g. "1 bath")
- url: the full URL to the listing detail page

Stop once you have {MAX_LISTINGS} organic listings or run out of pages.""",
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

    listings = inventory.listings[:MAX_LISTINGS]
    print(f"Found {len(inventory.listings)} listings, keeping first {len(listings)}")
    for listing in listings:
        print(
            f"  {listing.address} — ${listing.price} — {listing.beds}/{listing.baths}"
        )

    return listings


def save_inventory(listings: list[Listing]) -> Path:
    DATA_DIR.mkdir(exist_ok=True)
    path = DATA_DIR / "inventory.json"
    path.write_text(json.dumps([item.model_dump() for item in listings], indent=2))
    print(f"Saved {len(listings)} listings to {path}")
    return path


def load_inventory() -> list[Listing]:
    path = DATA_DIR / "inventory.json"
    if not path.exists():
        print(f"ERROR: {path} not found. Run 'search.py inventory' first.")
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
    listing: Listing, semaphore: asyncio.Semaphore
) -> ListingEvaluation | None:
    async with semaphore:
        print(f"  Evaluating: {listing.address} ({listing.url})")

        llm = ChatBrowserUse()
        profile = BrowserProfile(headless=HEADLESS)
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
- broker_fee: "No fee", "1 month", "15%", etc.
- move_in_date: if listed, null otherwise
- light_assessment: What do the photos tell you about natural light? How many
  windows visible? Which direction might they face? Any rooms that look dark?
- bathroom_assessment: Condition, cleanliness, modern or dated fixtures?
- kitchen_assessment: Condition, counter space, appliances, gas or electric?
- finishes_assessment: Overall condition — floors, walls, fixtures. Modern or dated?
- red_flags: Missing photos? Suspiciously low price? Anything sketchy?
- vibe: Does this feel like a place you'd want to come home to?
- score: Rate 1-10 against the preferences above
- score_justification: One-line justification for the score""",
            llm=llm,
            browser_session=session,
            output_model_schema=ListingEvaluation,
            use_vision=True,
        )

        try:
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


async def evaluate_all(listings: list[Listing]) -> list[ListingEvaluation]:
    print(
        f"\n=== STEP 3: Evaluate ({len(listings)} listings, batch size {BATCH_SIZE}) ==="
    )

    semaphore = asyncio.Semaphore(BATCH_SIZE)
    tasks = [evaluate_listing(listing, semaphore) for listing in listings]
    results = await asyncio.gather(*tasks)

    evaluations = [r for r in results if r is not None]
    print(f"Got {len(evaluations)} evaluations out of {len(listings)} listings")
    return evaluations


def save_evaluations(evaluations: list[ListingEvaluation]) -> Path:
    DATA_DIR.mkdir(exist_ok=True)
    path = DATA_DIR / "evaluations.json"
    path.write_text(json.dumps([e.model_dump() for e in evaluations], indent=2))
    print(f"Saved {len(evaluations)} evaluations to {path}")
    return path


def load_evaluations() -> list[ListingEvaluation]:
    path = DATA_DIR / "evaluations.json"
    if not path.exists():
        print(f"ERROR: {path} not found. Run 'search.py evaluate' first.")
        sys.exit(1)
    data = json.loads(path.read_text())
    evaluations = [ListingEvaluation(**item) for item in data]
    print(f"Loaded {len(evaluations)} evaluations from {path}")
    return evaluations


# ---------------------------------------------------------------------------
# Step 4: Rank and output
# ---------------------------------------------------------------------------


def rank_and_output(evaluations: list[ListingEvaluation]) -> Path:
    print(f"\n=== STEP 4: Rank & Output ({len(evaluations)} evaluations) ===")

    ranked = sorted(evaluations, key=lambda e: e.score, reverse=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    outpath = Path("findings") / f"{timestamp}.md"

    lines: list[str] = []
    lines.append(
        f"# Apartment Search Results — {datetime.now().strftime('%Y-%m-%d')}\n"
    )
    lines.append(f"Search: {SEARCH_URL}")
    lines.append(f"Evaluated: {len(ranked)} listings\n")

    for i, ev in enumerate(ranked, 1):
        lines.append("---\n")
        lines.append(f"## #{i}: {ev.address} — {ev.score}/10\n")
        lines.append(f"- **Price**: ${ev.price:,} | {ev.beds_baths} | {ev.broker_fee}")
        if ev.sqft:
            lines.append(f"- **Size**: {ev.sqft}")
        if ev.floor:
            lines.append(f"- **Floor**: {ev.floor}")
        lines.append(
            f"- **W/D**: {ev.washer_dryer} | **Dishwasher**: {ev.dishwasher} | **Building**: {ev.elevator_or_walkup}"
        )
        if ev.move_in_date:
            lines.append(f"- **Move-in**: {ev.move_in_date}")
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
# Commands
# ---------------------------------------------------------------------------


async def cmd_inventory():
    """Scrape StreetEasy, filter, and save listings."""
    all_listings = await run_inventory()
    if not all_listings:
        print("No listings found.")
        return
    filtered = filter_listings(all_listings)
    if not filtered:
        print("All listings filtered out.")
        return
    save_inventory(filtered)


async def cmd_evaluate():
    """Load inventory, evaluate each listing in parallel, save results."""
    listings = load_inventory()
    evaluations = await evaluate_all(listings)
    if not evaluations:
        print("No evaluations completed.")
        return
    save_evaluations(evaluations)


def cmd_rank():
    """Load evaluations, rank, and write findings markdown."""
    evaluations = load_evaluations()
    rank_and_output(evaluations)


async def cmd_all():
    """Run the full pipeline end-to-end."""
    await cmd_inventory()
    listings = load_inventory()
    if not listings:
        return
    evaluations = await evaluate_all(listings)
    if not evaluations:
        print("No evaluations completed.")
        return
    save_evaluations(evaluations)
    rank_and_output(evaluations)


COMMANDS = {
    "inventory": lambda: asyncio.run(cmd_inventory()),
    "evaluate": lambda: asyncio.run(cmd_evaluate()),
    "rank": cmd_rank,
}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else None

    print("=" * 60)
    print("  APT-FINDER")
    print("=" * 60)

    if cmd is None:
        asyncio.run(cmd_all())
    elif cmd in COMMANDS:
        COMMANDS[cmd]()
    else:
        print(f"Unknown command: {cmd}")
        print("Usage: search.py [inventory | evaluate | rank]")
        sys.exit(1)

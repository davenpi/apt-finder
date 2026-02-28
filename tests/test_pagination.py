"""
Smoke test: try different prompt strategies to get the inventory agent
to paginate past page 1 on StreetEasy.

Run: python test_pagination.py
"""

import asyncio

from browser_use import Agent, ChatBrowserUse
from browser_use.browser.profile import BrowserProfile
from browser_use.browser.session import BrowserSession
from dotenv import load_dotenv

from search import HEADLESS, LOCATIONS, InventoryResult, filter_listings

load_dotenv()

SEARCH_URL = LOCATIONS["EV"]
MAX_LISTINGS = 12  # page 1 has ~10, so >10 unique = pagination worked

# Each variant replaces the scrolling/pagination instructions in the prompt.
VARIANTS = {
    "keyboard_nav": """
1. Wait for the search results to load.
2. Click on any listing card in the left column to give that panel focus.
3. Use the Page Down key to scroll through the listings — do NOT use mouse scroll,
   as it may accidentally scroll the map instead.
4. Extract the organic listings you see on this page.
5. Look for PAGINATION links (page numbers like "1 2 3" or a "Next" link) at the
   bottom of the listing column. Click page 2 and extract those listings too.
   Continue until you have up to {max_listings} organic listings total.""",
    "click_then_scroll": """
1. Wait for the search results to load.
2. Click on any listing card in the left column FIRST to give it focus.
3. Now scroll down WITHIN the listing column. Make sure your mouse is over the
   listing cards on the left side, NOT over the map on the right.
4. Extract the organic listings you see on this page.
5. Look for PAGINATION links (page numbers like "1 2 3" or a "Next" link) at the
   bottom of the listing column. Click page 2 and extract those listings too.
   Continue until you have up to {max_listings} organic listings total.""",
    "direct_pagination": """
1. Wait for the search results to load.
2. Extract all organic listings visible on page 1 WITHOUT scrolling.
3. Now look for the PAGINATION control at the bottom of the listing column on the
   left side of the page. It will show page numbers like "1 2 3 ..." or a "Next"
   link. Do NOT scroll to find it — instead, use Page Down key once or twice to
   bring it into view.
4. Click the link for page 2. Wait for new listings to load.
5. Extract the listings from page 2.
6. Continue to page 3 if needed, until you have up to {max_listings} organic
   listings total.""",
}

PROMPT_TEMPLATE = """Go to {search_url}

You are extracting apartment listings from StreetEasy search results.

The results are in a LIST on the LEFT side of the page (not the map on the right).
Do NOT interact with the map. Focus only on the listing cards in the left column.

{variant_instructions}

IMPORTANT: SKIP any sponsored/featured listings. These have "?featured=1" or
"?infeed=1" in their URL, or are labeled "Featured" or "Sponsored" on the page.

For each listing extract:
- address: the street address
- price: monthly rent as a number (e.g. 4125, not "$4,125")
- beds: bedroom info (e.g. "1 bed", "Studio", "2 beds")
- baths: bathroom info (e.g. "1 bath")
- url: the full URL to the listing detail page

Stop once you have {max_listings} organic listings or run out of pages."""


async def run_variant(name: str, instructions: str) -> int:
    """Run one prompt variant. Returns the number of unique listings found."""
    print(f"\n{'=' * 60}")
    print(f"  VARIANT: {name}")
    print(f"{'=' * 60}")

    prompt = PROMPT_TEMPLATE.format(
        search_url=SEARCH_URL,
        variant_instructions=instructions.format(max_listings=MAX_LISTINGS),
        max_listings=MAX_LISTINGS,
    )

    llm = ChatBrowserUse()
    profile = BrowserProfile(
        headless=HEADLESS, viewport_width=800, viewport_height=1200
    )
    session = BrowserSession(browser_profile=profile)

    agent = Agent(
        task=prompt,
        llm=llm,
        browser_session=session,
        output_model_schema=InventoryResult,
        use_vision=True,
    )

    result = await agent.run()
    inventory = result.get_structured_output(InventoryResult)

    if inventory is None:
        print(f"  [{name}] No structured output!")
        return 0

    raw_count = len(inventory.listings)
    filtered = filter_listings(inventory.listings)
    unique_count = len(filtered)

    print(f"\n  [{name}] Raw: {raw_count}, Unique after filter: {unique_count}")
    for listing in filtered:
        print(f"    {listing.address} — ${listing.price}")

    return unique_count


async def main():
    results: dict[str, int] = {}

    for name, instructions in VARIANTS.items():
        count = await run_variant(name, instructions)
        results[name] = count

    print(f"\n{'=' * 60}")
    print("  RESULTS SUMMARY")
    print(f"{'=' * 60}")
    for name, count in results.items():
        status = "PASS (paginated)" if count > 10 else "FAIL (page 1 only)"
        print(f"  {name:25s} — {count:2d} unique listings — {status}")


if __name__ == "__main__":
    asyncio.run(main())

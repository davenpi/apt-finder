"""Quick test: watch the agent browse StreetEasy and extract listings."""

import asyncio

from browser_use import Agent, ChatBrowserUse
from browser_use.browser.profile import BrowserProfile
from browser_use.browser.session import BrowserSession
from dotenv import load_dotenv

load_dotenv()

SEARCH_URL = "https://streeteasy.com/for-rent/east-village/price:-4300"

llm = ChatBrowserUse()

profile = BrowserProfile(headless=False)

session = BrowserSession(browser_profile=profile)

agent = Agent(
    task=f"""Go to {SEARCH_URL}

    Look at the search results. Extract the first 3 organic listings you can see.
    SKIP any sponsored/featured listings — these have "?featured=1" or "?infeed=1" in
    their URL, or are labeled "Featured" or "Sponsored" on the page.

    For each listing, get:
    - Address
    - Price
    - Beds/baths
    - URL (the link to the listing)

    Just report back what you find. Don't click into any listings yet.
    """,
    llm=llm,
    browser_session=session,
    use_vision=True,
)


async def main():
    result = await agent.run()
    print("\n\n=== RESULT ===")
    print(result.final_result())


if __name__ == "__main__":
    asyncio.run(main())

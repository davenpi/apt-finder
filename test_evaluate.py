"""Test: send an agent to evaluate a single listing against preferences."""

import asyncio

from browser_use import Agent, ChatBrowserUse
from browser_use.browser.profile import BrowserProfile
from browser_use.browser.session import BrowserSession
from dotenv import load_dotenv

load_dotenv()

LISTING_URL = "https://streeteasy.com/building/160-east-3-street-new_york/2h"

PREFERENCES = """
- Budget: $4,250/mo target, hard ceiling ~$4,300
- 1 BR preferred, studio acceptable for a standout unit
- Natural light is critical — working from home, every room needs usable light
- Clean, modern bathroom is important — stained/grimy tub is a dealbreaker
- Modern finishes preferred
- In-unit W/D strongly preferred
- Quiet unit — rear-facing or courtyard preferred, avoid busy intersections
- Value matters — a $3,800 great place beats a $4,250 okay place
"""

llm = ChatBrowserUse()
profile = BrowserProfile(headless=False)
session = BrowserSession(browser_profile=profile)

agent = Agent(
    task=f"""Go to {LISTING_URL}

    You are evaluating this apartment listing for a renter. Here are their preferences:
    {PREFERENCES}

    Do the following:
    1. Read the listing details (price, beds/baths, sqft, amenities, description)
    2. Click through ALL the photos in the carousel — look at every single one
    3. Pay close attention to: natural light, bathroom condition, kitchen condition,
       finishes, and overall vibe

    Then produce an evaluation with these sections:

    **Facts**: Price, beds/baths, sqft, floor, W/D, dishwasher, elevator/walkup,
    broker fee or no-fee, move-in date if listed

    **Light**: What do the photos tell you about natural light? How many windows visible?
    Which direction might they face? Any rooms that look dark?

    **Bathroom**: Condition, cleanliness, modern or dated fixtures?

    **Kitchen**: Condition, counter space, appliances, gas or electric?

    **Finishes**: Overall condition — floors, walls, fixtures. Modern or dated?

    **Red flags**: Missing photos? Suspiciously low price? Anything sketchy?

    **Vibe**: Does this feel like a place you'd want to come home to?

    **Score**: Rate 1-10 against the preferences above, with a one-line justification.
    """,
    llm=llm,
    browser_session=session,
    use_vision=True,
)


async def main():
    result = await agent.run()
    print("\n\n=== EVALUATION ===")
    print(result.final_result())


if __name__ == "__main__":
    asyncio.run(main())

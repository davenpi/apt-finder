"""
Notion integration for apartment search tracking.

Creates a database under the "Apt search" page and manages listing pages
with rich content (contact toggles, maps, bookmarks).

Usage:
    from notion import create_database, add_listing, update_listing, append_listing_blocks
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

TOKEN = os.environ.get("NOTION_TOKEN", "")
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}

# "Apt search" page — parent for the listings database.
PARENT_PAGE_ID = os.environ.get("NOTION_PAGE_ID", "")

# Set after `apt init` creates the database. Store in .env as NOTION_DB_ID.
DATABASE_ID = os.environ.get("NOTION_DB_ID", "")

API = "https://api.notion.com/v1"


def _check_token():
    if not TOKEN:
        raise RuntimeError(
            "NOTION_TOKEN is not set. Export it as an env var or add it to .env."
        )


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


def create_database() -> str:
    """Create the listings database under the parent page. Returns the DB ID."""
    _check_token()

    payload = {
        "parent": {"type": "page_id", "page_id": PARENT_PAGE_ID},
        "is_inline": True,
        "title": [{"type": "text", "text": {"content": "Listings"}}],
        "properties": {
            "Address": {"title": {}},
            "URL": {"url": {}},
            "Agent Name": {"rich_text": {}},
            "Agent Email": {"rich_text": {}},
            "Agent Phone": {"rich_text": {}},
            "Available": {"rich_text": {}},
            "Status": {
                "select": {
                    "options": [
                        {"name": "new", "color": "blue"},
                        {"name": "contacted", "color": "yellow"},
                        {"name": "replied", "color": "orange"},
                        {"name": "touring", "color": "green"},
                        {"name": "passed", "color": "gray"},
                    ]
                }
            },
            "Tour Date": {"rich_text": {}},
            "Notes": {"rich_text": {}},
        },
    }

    resp = requests.post(f"{API}/databases", headers=HEADERS, json=payload)
    resp.raise_for_status()
    db_id = resp.json()["id"]
    return db_id


# ---------------------------------------------------------------------------
# Pages (listings)
# ---------------------------------------------------------------------------


def add_listing(url: str, address: str) -> str:
    """Create a new page in the listings database. Returns the page ID."""
    _check_token()
    if not DATABASE_ID:
        raise RuntimeError(
            "NOTION_DB_ID is not set. Run `apt init` first, then add the ID to .env."
        )

    payload = {
        "parent": {"database_id": DATABASE_ID},
        "properties": {
            "Address": {"title": [{"text": {"content": address}}]},
            "URL": {"url": url},
            "Status": {"select": {"name": "new"}},
        },
    }

    resp = requests.post(f"{API}/pages", headers=HEADERS, json=payload)
    resp.raise_for_status()
    return resp.json()["id"]


def update_listing(
    page_id: str,
    *,
    agent_name: str = "",
    agent_email: str = "",
    agent_phone: str = "",
    available_date: str = "",
    tour_dates: str = "",
) -> None:
    """Write contact info into a listing page's properties."""
    _check_token()

    props: dict = {}
    if agent_name:
        props["Agent Name"] = {"rich_text": [{"text": {"content": agent_name}}]}
    if agent_email:
        props["Agent Email"] = {"rich_text": [{"text": {"content": agent_email}}]}
    if agent_phone:
        props["Agent Phone"] = {"rich_text": [{"text": {"content": agent_phone}}]}
    if available_date:
        props["Available"] = {"rich_text": [{"text": {"content": available_date}}]}
    if tour_dates:
        props["Tour Date"] = {"rich_text": [{"text": {"content": tour_dates}}]}

    if not props:
        return

    resp = requests.patch(
        f"{API}/pages/{page_id}", headers=HEADERS, json={"properties": props}
    )
    resp.raise_for_status()


# ---------------------------------------------------------------------------
# Rich page content
# ---------------------------------------------------------------------------


def append_listing_blocks(
    address: str,
    url: str,
    contact: object | None = None,
) -> None:
    """Append rich blocks to the parent 'Apt search' page."""
    _check_token()

    # Build contact details for the toggle.
    contact_parts: list[dict] = []
    if contact:
        name = getattr(contact, "agent_name", "")
        email = getattr(contact, "agent_email", "")
        phone = getattr(contact, "agent_phone", "")
        available = getattr(contact, "available_date", "")
        tours = getattr(contact, "tour_dates", "")

        if name:
            contact_parts += [
                _bold("Agent: "),
                _text(f"{name}\n"),
            ]
        if email:
            contact_parts += [
                _bold("Email: "),
                _text(f"{email}\n"),
            ]
        if phone:
            contact_parts += [
                _bold("Phone: "),
                _text(f"{phone}\n"),
            ]
        if available:
            contact_parts += [
                _bold("Available: "),
                _text(f"{available}\n"),
            ]
        if tours:
            contact_parts += [
                _bold("Tours: "),
                _text(f"{tours}\n"),
            ]

    if not contact_parts:
        contact_parts = [_text("No contact info extracted yet.")]

    # Build blocks.
    maps_query = address.replace(" ", "+") + ",+New+York,+NY"
    blocks = [
        {
            "object": "block",
            "type": "heading_2",
            "heading_2": {"rich_text": [_text(address)]},
        },
    ]

    blocks += [
        {
            "object": "block",
            "type": "toggle",
            "toggle": {
                "rich_text": [_text("Contact & Details")],
                "children": [
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {"rich_text": contact_parts},
                    },
                    {
                        "object": "block",
                        "type": "bookmark",
                        "bookmark": {"url": url},
                    },
                ],
            },
        },
        {
            "object": "block",
            "type": "embed",
            "embed": {
                "url": f"https://www.google.com/maps?q={maps_query}",
            },
        },
        {"object": "block", "type": "divider", "divider": {}},
    ]

    resp = requests.patch(
        f"{API}/blocks/{PARENT_PAGE_ID}/children",
        headers=HEADERS,
        json={"children": blocks},
    )
    resp.raise_for_status()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _text(content: str) -> dict:
    return {"type": "text", "text": {"content": content}}


def _bold(content: str) -> dict:
    return {
        "type": "text",
        "text": {"content": content},
        "annotations": {"bold": True},
    }

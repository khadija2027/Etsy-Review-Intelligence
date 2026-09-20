"""Fetch listing details and reviews from Etsy."""
from __future__ import annotations

import os
import re
from typing import Any

import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

load_dotenv()

_HTTP_SESSION = requests.Session()
_HTTP_SESSION.mount(
    "https://",
    HTTPAdapter(
        max_retries=Retry(
            total=3,
            connect=3,
            read=2,
            status=2,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            raise_on_status=False,
        )
    ),
)


def _listing_id(value: str) -> str:
    value = value.strip()
    if value.isdigit():
        return value
    match = re.search(r"etsy\.com/(?:[a-z]{2}/)?listing/(\d+)", value, re.IGNORECASE)
    if match:
        return match.group(1)
    raise ValueError("Enter a numeric Etsy listing_id or a full Etsy listing URL.")


def _headers() -> dict[str, str]:
    key = os.getenv("ETSY_API_KEY", "").strip()
    secret = os.getenv("ETSY_API_SECRET", "").strip()
    if not key or not secret:
        raise RuntimeError("ETSY_API_KEY and ETSY_API_SECRET must be set in .env.")
    return {"x-api-key": f"{key}:{secret}"}


def _get_json(url: str, **kwargs: Any) -> dict[str, Any]:
    try:
        response = _HTTP_SESSION.get(url, headers=_headers(), timeout=30, **kwargs)
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        if isinstance(exc, requests.ConnectionError):
            raise RuntimeError(
                "Could not connect to Etsy API. Check DNS, internet access, VPN/proxy settings, "
                "then retry. The configured endpoint is openapi.etsy.com."
            ) from exc
        raise RuntimeError(f"Etsy API request failed: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Etsy API returned an invalid response.")
    return payload


def fetch_listing_reviews(listing_reference: str) -> dict[str, Any]:
    """Fetch every review Etsy exposes for one exact listing ID or URL."""
    listing_id = _listing_id(listing_reference)
    base_url = os.getenv("ETSY_API_BASE_URL", "https://openapi.etsy.com/v3").rstrip("/")
    listing = _get_json(f"{base_url}/application/listings/{listing_id}")

    reviews: list[dict[str, Any]] = []
    offset = 0
    limit = 100
    while True:
        page = _get_json(
            f"{base_url}/application/listings/{listing_id}/reviews",
            params={"limit": limit, "offset": offset},
        )
        items = page.get("results", [])
        if not isinstance(items, list) or not items:
            break
        reviews.extend(
            {
                "rating": item.get("rating"),
                "review_text": item.get("review") or "",
                "review_date": item.get("created_timestamp"),
                "language": item.get("language") or "",
            }
            for item in items
            if isinstance(item, dict)
        )
        offset += len(items)
        total = page.get("count")
        if len(items) < limit or (isinstance(total, int) and offset >= total):
            break

    return {
        "source": "etsy",
        "listing_id": listing_id,
        "listing_title": str(listing.get("title") or ""),
        "reviews_count": len(reviews),
        "reviews": reviews,
    }

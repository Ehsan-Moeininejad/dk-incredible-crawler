#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Digikala Incredible Offers Crawler  --  OVERWRITE MODE
======================================================
Reads https://www.digikala.com/incredible-offers/ through Digikala's own
public JSON API and replaces the sheet contents with the current live list.

No history is kept. Every run wipes the sheet and writes the offers that are
active at that moment.

Outputs
-------
1. Google Sheet, first tab : cleared and rewritten on every run
2. data/latest.csv          : same data, overwritten on every run (local backup)

Design notes
------------
* Pure Python. No LLM, no browser, no HTML parsing -> zero token cost per run.
* One HTTP request per page (20 products/page, ~63 pages) -> ~65 requests/run.
* Retries with exponential backoff; a failed page never kills the whole run.
* SAFETY: the sheet is only cleared once a complete, sane result is in memory.
  A partial crawl leaves the previous contents untouched.
"""

from __future__ import annotations

import csv
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

# ----------------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------------

SPREADSHEET_ID = "1V62qJ4IYNKa-gSdrzwjNF5XsSYMUb6L0NpoyhQ1bLU8"

# Which tab to write to. None = the first tab (gid=0). Or put a name, e.g. "Live".
TARGET_TAB = None

# Path to the Google service-account JSON key (see the setup guide, step 2).
CREDENTIALS_PATH = os.environ.get(
    "DK_GOOGLE_CREDENTIALS",
    str(Path(__file__).parent / "credentials.json"),
)

BASE_URL = "https://api.digikala.com/v1/incredible-offers/"
TZ = ZoneInfo("Asia/Tehran")

MAX_PAGES = 200            # hard safety cap
REQUEST_TIMEOUT = 20       # seconds
DELAY_BETWEEN_PAGES = 0.7  # seconds - polite crawling
MAX_RETRIES = 4
PRICE_DIVISOR = 10         # API returns Rial; we store Toman

# Refuse to overwrite the sheet if the crawl collected less than this share of
# what the API said exists. Protects against wiping good data with a half-run.
MIN_COMPLETENESS = 0.70

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"
DATA_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.8",
}

COLUMNS = [
    "updated_at",           # 2026-09-21 12:00:00  (Tehran) - same for every row
    "rank",                 # position in the incredible list (1 = first)
    "dkp",                  # product id
    "title_fa",
    "brand",
    "category_l1",
    "category_l2",
    "category_l3",
    "selling_price_toman",
    "rrp_price_toman",
    "discount_percent",
    "discount_amount_toman",
    "status",
    "seller",
    "rating_rate",
    "rating_count",
    "deal_end_time",
    "is_lightening_deal",
    "url",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "crawler.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("dk-crawler")


# ----------------------------------------------------------------------------
# FETCH LAYER
# ----------------------------------------------------------------------------

def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def fetch_page(session: requests.Session, page: int) -> dict | None:
    """Fetch one page with exponential backoff. Returns the JSON `data` dict."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.get(
                BASE_URL, params={"page": page}, timeout=REQUEST_TIMEOUT
            )
            if resp.status_code == 429:
                wait = 5 * attempt
                log.warning("page %s -> 429 rate limited, waiting %ss", page, wait)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json().get("data", {})
        except Exception as exc:  # noqa: BLE001
            wait = 2 ** attempt
            log.warning(
                "page %s attempt %s/%s failed (%s) - retrying in %ss",
                page, attempt, MAX_RETRIES, exc, wait,
            )
            time.sleep(wait)
    log.error("page %s: giving up after %s attempts", page, MAX_RETRIES)
    return None


# ----------------------------------------------------------------------------
# PARSE LAYER
# ----------------------------------------------------------------------------

def to_toman(value) -> int | str:
    if value is None or value == "":
        return ""
    try:
        return int(value) // PRICE_DIVISOR
    except (TypeError, ValueError):
        return ""


def parse_product(product: dict, rank: int, updated_at: str) -> dict:
    """Flatten one API product object into a single output row."""
    variant = product.get("default_variant") or {}
    price = variant.get("price") or {}
    layer = product.get("data_layer") or {}
    rating = product.get("rating") or {}
    seller = (variant.get("seller") or {}).get("title", "")

    selling = to_toman(price.get("selling_price"))
    rrp = to_toman(price.get("rrp_price"))
    discount_amount = ""
    if isinstance(selling, int) and isinstance(rrp, int) and rrp > 0:
        discount_amount = rrp - selling

    uri = (product.get("url") or {}).get("uri") or ""
    url = f"https://www.digikala.com{uri}" if uri else ""

    return {
        "updated_at": updated_at,
        "rank": rank,
        "dkp": product.get("id", ""),
        "title_fa": product.get("title_fa", ""),
        "brand": layer.get("brand", ""),
        "category_l1": layer.get("item_category2", ""),
        "category_l2": layer.get("item_category3", ""),
        "category_l3": layer.get("item_category4", ""),
        "selling_price_toman": selling,
        "rrp_price_toman": rrp,
        "discount_percent": price.get("discount_percent", ""),
        "discount_amount_toman": discount_amount,
        "status": product.get("status", ""),
        "seller": seller,
        "rating_rate": rating.get("rate", ""),
        "rating_count": rating.get("count", ""),
        "deal_end_time": price.get("time", "") or "",
        "is_lightening_deal": bool(price.get("is_lightening_deal")),
        "url": url,
    }


def crawl(updated_at: str) -> tuple[list[dict], int]:
    """
    Walk every page of the incredible-offers list.

    Returns (rows, expected_total) where expected_total is what the API's
    pager claimed exists - used by the completeness guard.
    """
    session = make_session()
    rows: list[dict] = []
    seen_dkp: set[int] = set()
    rank = 0
    page = 1
    total_pages = None
    expected_total = 0
    failed_pages: list[int] = []

    while page <= MAX_PAGES:
        data = fetch_page(session, page)
        if data is None:
            failed_pages.append(page)
            page += 1
            if total_pages and page > total_pages:
                break
            continue

        listing = data.get("incredible_products_list") or {}
        products = listing.get("products") or []
        pager = listing.get("pager") or {}

        if total_pages is None and pager.get("total_pages"):
            total_pages = int(pager["total_pages"])
            expected_total = int(pager.get("total_items") or 0)
            log.info("pager: %s products across %s pages", expected_total, total_pages)

        if not products:
            log.info("page %s returned 0 products - stopping", page)
            break

        for product in products:
            dkp = product.get("id")
            if dkp in seen_dkp:
                continue
            seen_dkp.add(dkp)
            rank += 1
            rows.append(parse_product(product, rank, updated_at))

        log.info("page %-3s -> %-3s products (total so far: %s)",
                 page, len(products), len(rows))

        if total_pages and page >= total_pages:
            break
        page += 1
        time.sleep(DELAY_BETWEEN_PAGES)

    if failed_pages:
        log.warning("pages that failed permanently: %s", failed_pages)
    return rows, expected_total


# ----------------------------------------------------------------------------
# OUTPUT: CSV  (local backup, overwritten every run)
# ----------------------------------------------------------------------------

def write_csv(rows: list[dict]) -> Path:
    path = DATA_DIR / "latest.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    log.info("CSV overwritten: %s (%s rows)", path.name, len(rows))
    return path


# ----------------------------------------------------------------------------
# OUTPUT: GOOGLE SHEET  (cleared and rewritten every run)
# ----------------------------------------------------------------------------

def open_worksheet():
    import gspread
    from google.oauth2.service_account import Credentials

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(CREDENTIALS_PATH, scopes=scopes)
    spreadsheet = gspread.authorize(creds).open_by_key(SPREADSHEET_ID)
    if TARGET_TAB:
        return spreadsheet.worksheet(TARGET_TAB)
    return spreadsheet.sheet1


def push_to_sheet(rows: list[dict]) -> None:
    """Replace the whole tab with the current offer list."""
    worksheet = open_worksheet()
    values = [COLUMNS] + [[r[c] for c in COLUMNS] for r in rows]

    needed_rows = len(values) + 20
    if worksheet.row_count < needed_rows or worksheet.col_count < len(COLUMNS):
        worksheet.resize(
            rows=max(needed_rows, worksheet.row_count),
            cols=max(len(COLUMNS), worksheet.col_count),
        )

    worksheet.clear()
    worksheet.update(values=values, range_name="A1")
    worksheet.freeze(rows=1)

    # trim leftover empty rows from a previously longer list
    if worksheet.row_count > needed_rows:
        worksheet.resize(rows=needed_rows, cols=worksheet.col_count)

    log.info("sheet '%s' replaced with %s rows", worksheet.title, len(rows))


# ----------------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------------

def main() -> int:
    updated_at = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
    log.info("=" * 70)
    log.info("run started | %s", updated_at)

    started = time.time()
    rows, expected_total = crawl(updated_at)
    log.info("crawl finished in %.1fs - %s unique products (API expected %s)",
             time.time() - started, len(rows), expected_total or "?")

    # ---- completeness guard: never wipe the sheet with a partial result ----
    if not rows:
        log.error("no products collected - sheet left untouched")
        return 1

    if expected_total and len(rows) < expected_total * MIN_COMPLETENESS:
        log.error(
            "only %s of ~%s products collected (< %.0f%%) - "
            "sheet left untouched to avoid overwriting good data with a partial run",
            len(rows), expected_total, MIN_COMPLETENESS * 100,
        )
        write_csv(rows)   # keep the partial result locally for inspection
        return 4

    write_csv(rows)

    try:
        push_to_sheet(rows)
    except FileNotFoundError:
        log.error(
            "credentials file not found at %s - CSV was saved, sheet was not updated",
            CREDENTIALS_PATH,
        )
        return 2
    except Exception as exc:  # noqa: BLE001
        log.exception("failed to update the sheet: %s (CSV is safe)", exc)
        return 3

    log.info("run completed successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())

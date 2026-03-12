#!/usr/bin/env python3
"""
ClawHub Skill Crawler
~~~~~~~~~~~~~~~~~~~~~
Searches ClawHub for skills related to "role play", fetches detailed metadata
for the top 10 results, and stores everything in a local SQLite database.

Strategy:
  1. Try the /search endpoint first (best relevance).
  2. If rate-limited, fall back to /skills listing and filter locally.
  3. For each candidate, fetch full detail via /skills/{slug}.
  4. Upsert into SQLite.

Usage:
    python3 crawler.py [--query "role play"] [--limit 10] [--db skills.db]
"""

import argparse
import json
import logging
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from urllib.parse import quote, urljoin
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BASE_URL = "https://clawhub.ai"
API_PREFIX = "/api/v1"
USER_AGENT = "ClawFarm-Crawler/1.0 (nanobot)"
REQUEST_TIMEOUT = 30   # seconds
RETRY_ATTEMPTS = 1
RETRY_BASE_DELAY = 1   # seconds
RATE_LIMIT_WAIT = 10   # wait this long on 429 before retrying

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def api_get(path: str, params: dict | None = None) -> dict | list | None:
    """GET a JSON endpoint with retries. Returns None on unrecoverable failure."""
    url = BASE_URL + API_PREFIX + path
    if params:
        qs = "&".join(
            f"{k}={quote(str(v), safe='')}"
            for k, v in params.items()
            if v is not None
        )
        url = f"{url}?{qs}"

    req = Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    })

    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            log.debug("GET %s (attempt %d)", url, attempt)
            with urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                return json.loads(resp.read().decode())
        except HTTPError as exc:
            body = exc.read().decode(errors="replace") if exc.fp else ""
            log.warning("HTTP %d for %s (attempt %d): %s", exc.code, url, attempt, body[:200])
            if exc.code == 429:
                if attempt < RETRY_ATTEMPTS:
                    wait = RATE_LIMIT_WAIT
                    log.info("Rate-limited — waiting %ds before retry …", wait)
                    time.sleep(wait)
                else:
                    log.error("Rate limit persists after %d attempts.", RETRY_ATTEMPTS)
                    return None
            elif 500 <= exc.code < 600:
                time.sleep(RETRY_BASE_DELAY * attempt)
            else:
                return None  # 4xx (not 429) → don't retry
        except (URLError, OSError) as exc:
            log.warning("Network error for %s: %s (attempt %d)", url, exc, attempt)
            if attempt < RETRY_ATTEMPTS:
                time.sleep(RETRY_BASE_DELAY * attempt)
            else:
                return None
    return None

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS skills (
    slug              TEXT PRIMARY KEY,
    display_name      TEXT,
    summary           TEXT,
    tags              TEXT,           -- JSON
    stats             TEXT,           -- JSON
    owner_handle      TEXT,
    owner_name        TEXT,
    latest_version    TEXT,
    latest_changelog  TEXT,
    search_score      REAL,
    created_at        TEXT,           -- ISO-8601
    updated_at        TEXT,           -- ISO-8601
    crawled_at        TEXT            -- ISO-8601
);
"""


def init_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(DB_SCHEMA)
    conn.commit()
    log.info("Database ready: %s", db_path)
    return conn


def epoch_to_iso(ts) -> str | None:
    if ts is None:
        return None
    ts = float(ts)
    if ts > 1e12:           # milliseconds → seconds
        ts /= 1000.0
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def upsert_skill(conn: sqlite3.Connection, row: dict):
    conn.execute(
        """
        INSERT OR REPLACE INTO skills
            (slug, display_name, summary, tags, stats,
             owner_handle, owner_name,
             latest_version, latest_changelog,
             search_score, created_at, updated_at, crawled_at)
        VALUES
            (:slug, :display_name, :summary, :tags, :stats,
             :owner_handle, :owner_name,
             :latest_version, :latest_changelog,
             :search_score, :created_at, :updated_at, :crawled_at)
        """,
        row,
    )

# ---------------------------------------------------------------------------
# Relevance scoring (for fallback mode)
# ---------------------------------------------------------------------------

ROLE_PLAY_KEYWORDS = [
    "role play", "roleplay", "role-play",
    "rp", "character", "persona",
    "storytelling", "story", "narrative",
    "rpg", "dungeon", "adventure",
    "dialogue", "conversation", "chat",
    "npc", "acting", "impersonation",
    "fictional", "fantasy", "simulation",
]

def local_relevance_score(slug: str, name: str, summary: str) -> float:
    """Return a 0-1 relevance score by keyword matching."""
    text = f"{slug} {name} {summary}".lower()
    hits = sum(1 for kw in ROLE_PLAY_KEYWORDS if kw in text)
    return min(hits / 3.0, 1.0)   # 3+ keyword hits → score 1.0

# ---------------------------------------------------------------------------
# Crawl logic
# ---------------------------------------------------------------------------

def search_via_api(query: str, limit: int) -> list[dict] | None:
    """Try the /search endpoint. Returns list or None on failure."""
    log.info("Trying /search endpoint for '%s' …", query)
    # Single attempt — if rate-limited, fall back immediately
    data = api_get("/search", {"q": query, "limit": limit})
    if data is None:
        return None
    results = data.get("results", [])
    if not results:
        return None
    log.info("Search returned %d results.", len(results))
    return results[:limit]


def search_via_listing(query: str, limit: int) -> list[dict]:
    """Fallback: page through /skills and filter locally."""
    log.info("Falling back to /skills listing + local keyword filter …")
    candidates: list[tuple[float, dict]] = []
    cursor = None
    pages = 0
    max_pages = 10   # safety cap (10 × 50 = 500 skills max)

    while pages < max_pages:
        params: dict = {"limit": 50}
        if cursor:
            params["cursor"] = cursor
        data = api_get("/skills", params)
        if data is None:
            log.warning("Failed to fetch skills page %d — stopping.", pages + 1)
            break
        items = data.get("items", [])
        if not items:
            break
        pages += 1
        log.info("  Page %d: %d skills", pages, len(items))

        for item in items:
            slug = item.get("slug", "")
            name = item.get("displayName", "")
            summary = item.get("summary", "")
            score = local_relevance_score(slug, name, summary)
            if score > 0:
                candidates.append((score, item))

        cursor = data.get("nextCursor")
        if not cursor:
            break
        time.sleep(0.3)  # politeness delay

    # Sort by relevance score descending
    candidates.sort(key=lambda x: x[0], reverse=True)
    top = candidates[:limit]
    log.info("Found %d relevant skills (returning top %d).", len(candidates), len(top))

    # Convert to search-result-like dicts
    results = []
    for score, item in top:
        results.append({
            "slug": item["slug"],
            "displayName": item.get("displayName"),
            "summary": item.get("summary"),
            "version": (item.get("latestVersion") or {}).get("version"),
            "score": score,
            "updatedAt": item.get("updatedAt"),
            # carry full item for enrichment
            "_listItem": item,
        })
    return results


def fetch_skill_detail(slug: str) -> dict | None:
    """Fetch full metadata for a single skill."""
    log.info("  Fetching detail for '%s' …", slug)
    return api_get(f"/skills/{quote(slug, safe='')}")


def crawl(query: str, limit: int, db_path: str):
    conn = init_db(db_path)
    now_iso = datetime.now(tz=timezone.utc).isoformat()

    # --- Step 1: Get candidates -------------------------------------------
    results = search_via_api(query, limit)
    used_fallback = False
    if results is None:
        results = search_via_listing(query, limit)
        used_fallback = True

    if not results:
        log.warning("No skills found for query '%s'.", query)
        conn.close()
        return

    # --- Step 2: Enrich & store -------------------------------------------
    saved = 0
    for idx, sr in enumerate(results, 1):
        slug = sr.get("slug")
        if not slug:
            continue

        # Try to fetch detail, but if rate-limited, save from search data
        detail = fetch_skill_detail(slug)

        if detail is not None:
            skill = detail.get("skill") or {}
            owner = detail.get("owner") or {}
            latest = detail.get("latestVersion") or {}

            row = {
                "slug": slug,
                "display_name": skill.get("displayName") or sr.get("displayName"),
                "summary": skill.get("summary") or sr.get("summary"),
                "tags": json.dumps(skill.get("tags") or {}),
                "stats": json.dumps(skill.get("stats") or {}),
                "owner_handle": owner.get("handle"),
                "owner_name": owner.get("displayName"),
                "latest_version": latest.get("version") or sr.get("version"),
                "latest_changelog": latest.get("changelog"),
                "search_score": sr.get("score"),
                "created_at": epoch_to_iso(skill.get("createdAt")),
                "updated_at": epoch_to_iso(skill.get("updatedAt")),
                "crawled_at": now_iso,
            }
        else:
            # Save from search/listing data (no detail available)
            list_item = sr.get("_listItem") or {}
            row = {
                "slug": slug,
                "display_name": sr.get("displayName") or list_item.get("displayName"),
                "summary": sr.get("summary") or list_item.get("summary"),
                "tags": json.dumps(list_item.get("tags") or {}),
                "stats": json.dumps(list_item.get("stats") or {}),
                "owner_handle": None,
                "owner_name": None,
                "latest_version": sr.get("version") or (list_item.get("latestVersion") or {}).get("version"),
                "latest_changelog": (list_item.get("latestVersion") or {}).get("changelog"),
                "search_score": sr.get("score"),
                "created_at": epoch_to_iso(sr.get("updatedAt") or list_item.get("createdAt")),
                "updated_at": epoch_to_iso(sr.get("updatedAt") or list_item.get("updatedAt")),
                "crawled_at": now_iso,
            }
            log.info("  Saved '%s' from search data (detail unavailable).", slug)

        upsert_skill(conn, row)
        saved += 1
        log.info("  [%d/%d] Saved '%s' (score=%.4f)",
                 idx, len(results), slug, sr.get("score", 0))

        # Politeness delay between detail requests
        if idx < len(results):
            time.sleep(0.3)

    conn.commit()

    # --- Step 3: Summary --------------------------------------------------
    log.info("=" * 60)
    log.info("Crawl complete! %d/%d skills saved to %s", saved, len(results), db_path)
    log.info("=" * 60)

    # Print a quick table
    cur = conn.execute(
        "SELECT slug, display_name, search_score, latest_version, owner_handle "
        "FROM skills ORDER BY search_score DESC"
    )
    rows = cur.fetchall()
    if rows:
        print(f"\n{'#':<3} {'Slug':<35} {'Name':<30} {'Score':<8} {'Version':<10} {'Owner'}")
        print("-" * 100)
        for i, (s, n, sc, v, o) in enumerate(rows, 1):
            print(f"{i:<3} {(s or ''):<35} {(n or '')[:29]:<30} {sc or 0:<8.4f} {(v or ''):<10} {o or ''}")

    conn.close()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Crawl ClawHub for role-play skills → SQLite."
    )
    parser.add_argument(
        "-q", "--query", default="role play",
        help="Search query (default: 'role play')"
    )
    parser.add_argument(
        "-l", "--limit", type=int, default=10,
        help="Max results (default: 10)"
    )
    parser.add_argument(
        "-d", "--db", default="skills.db",
        help="SQLite database path (default: skills.db)"
    )
    args = parser.parse_args()
    crawl(query=args.query, limit=args.limit, db_path=args.db)


if __name__ == "__main__":
    main()

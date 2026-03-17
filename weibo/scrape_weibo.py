#!/usr/bin/env python3
"""
Weibo Post & Comment Scraper
=============================
Scrapes all posts (and their comments) for a given Weibo user ID,
saving everything to a local JSON file.

Requirements:
    pip install crawl4weibo
    playwright install chromium

Usage:
    python scrape_weibo.py                     # uses defaults (UID 2201640147)
    python scrape_weibo.py --uid 2201640147    # specify UID
    python scrape_weibo.py --login             # login for full data access
    python scrape_weibo.py --no-comments       # skip comment scraping
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from crawl4weibo import WeiboClient


# ── Configuration ────────────────────────────────────────────────────────────
DEFAULT_UID = "2201640147"
OUTPUT_DIR = "./weibo_export"
DELAY_BETWEEN_PAGES = 2.0        # seconds between page fetches
DELAY_BETWEEN_COMMENTS = 1.5     # seconds between comment page fetches
MAX_COMMENT_PAGES = 50           # max comment pages per post (None = all)
# ─────────────────────────────────────────────────────────────────────────────


def create_client(login: bool = False) -> WeiboClient:
    """Create a WeiboClient, optionally with login cookies."""
    if login:
        print("🔐 Launching browser for Weibo login...")
        print("   Please scan the QR code or log in manually.")
        print("   The browser will close automatically after login.\n")
        client = WeiboClient(
            login_cookies=True,
            cookie_storage_path=os.path.expanduser(
                "~/.crawl4weibo/weibo_storage_state.json"
            ),
            browser_headless=False,
            login_timeout=180,
        )
    else:
        client = WeiboClient()
    return client


def fetch_user_info(client: WeiboClient, uid: str) -> dict:
    """Fetch basic user profile info."""
    print(f"👤 Fetching user profile for UID {uid}...")
    user = client.get_user_by_uid(uid)
    info = {
        "uid": uid,
        "screen_name": user.screen_name,
        "description": user.description,
        "followers_count": user.followers_count,
        "follow_count": user.follow_count,
        "statuses_count": user.statuses_count,
        "gender": user.gender,
        "verified": getattr(user, "verified", None),
        "profile_url": getattr(user, "profile_url", None),
    }
    print(f"   Name: {info['screen_name']}")
    print(f"   Posts: {info['statuses_count']}")
    print(f"   Followers: {info['followers_count']}\n")
    return info


def post_to_dict(post) -> dict:
    """Convert a Post object to a serializable dict."""
    return {
        "id": post.id,
        "bid": getattr(post, "bid", None),
        "text": post.text,
        "created_at": getattr(post, "created_at", None),
        "source": getattr(post, "source", None),
        "reposts_count": getattr(post, "reposts_count", 0),
        "comments_count": getattr(post, "comments_count", 0),
        "attitudes_count": getattr(post, "attitudes_count", 0),
        "pic_urls": getattr(post, "pic_urls", []),
        "pic_ids": getattr(post, "pic_ids", []),
        "page_info": getattr(post, "page_info", None),
        "is_long_text": getattr(post, "is_long_text", False),
        "repost": post_to_dict(post.repost) if getattr(post, "repost", None) else None,
    }


def comment_to_dict(comment) -> dict:
    """Convert a Comment object to a serializable dict."""
    return {
        "id": getattr(comment, "id", None),
        "text": getattr(comment, "text", None),
        "user_screen_name": getattr(comment, "user_screen_name", None),
        "user_id": getattr(comment, "user_id", None),
        "created_at": getattr(comment, "created_at", None),
        "like_count": getattr(comment, "like_count", 0),
        "floor_number": getattr(comment, "floor_number", None),
    }


def fetch_all_posts(client: WeiboClient, uid: str) -> list[dict]:
    """Fetch all posts for a user, page by page."""
    all_posts = []
    page = 1

    while True:
        print(f"   📄 Fetching posts page {page}...", end=" ", flush=True)
        try:
            posts = client.get_user_posts(uid, page=page, expand=True)
        except Exception as e:
            print(f"\n   ⚠️  Error on page {page}: {e}")
            break

        if not posts:
            print("(no more posts)")
            break

        converted = [post_to_dict(p) for p in posts]
        all_posts.extend(converted)
        print(f"got {len(posts)} posts (total: {len(all_posts)})")

        page += 1
        time.sleep(DELAY_BETWEEN_PAGES)

    return all_posts


def fetch_comments_for_post(
    client: WeiboClient, post_id: str, max_pages: int | None = None
) -> list[dict]:
    """Fetch all comments for a single post."""
    try:
        comments = client.get_all_comments(post_id, max_pages=max_pages)
        return [comment_to_dict(c) for c in comments]
    except Exception as e:
        print(f"\n      ⚠️  Comment fetch error for post {post_id}: {e}")
        return []


def main():
    parser = argparse.ArgumentParser(description="Scrape Weibo posts and comments")
    parser.add_argument("--uid", default=DEFAULT_UID, help="Weibo user ID")
    parser.add_argument("--login", action="store_true", help="Use browser login for full data")
    parser.add_argument("--no-comments", action="store_true", help="Skip comment scraping")
    parser.add_argument("--output", default=OUTPUT_DIR, help="Output directory")
    parser.add_argument(
        "--max-comment-pages",
        type=int,
        default=MAX_COMMENT_PAGES,
        help="Max comment pages per post (0 = unlimited)",
    )
    args = parser.parse_args()

    max_cp = args.max_comment_pages if args.max_comment_pages > 0 else None

    # ── Setup ────────────────────────────────────────────────────────────
    Path(args.output).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    print("=" * 60)
    print("  Weibo Post & Comment Scraper")
    print("=" * 60)
    print()

    # ── Create client ────────────────────────────────────────────────────
    client = create_client(login=args.login)

    # ── Fetch user info ──────────────────────────────────────────────────
    user_info = fetch_user_info(client, args.uid)

    # ── Fetch all posts ──────────────────────────────────────────────────
    print("📝 Fetching all posts...")
    posts = fetch_all_posts(client, args.uid)
    print(f"   ✅ Total posts fetched: {len(posts)}\n")

    # ── Fetch comments ───────────────────────────────────────────────────
    if not args.no_comments:
        posts_with_comments = [p for p in posts if p.get("comments_count", 0) > 0]
        print(f"💬 Fetching comments for {len(posts_with_comments)} posts with comments...")

        for i, post in enumerate(posts_with_comments, 1):
            post_id = post["id"]
            cc = post.get("comments_count", 0)
            preview = (post.get("text") or "")[:40].replace("\n", " ")
            print(
                f"   [{i}/{len(posts_with_comments)}] Post {post_id} "
                f"({cc} comments): {preview}...",
                end=" ",
                flush=True,
            )

            comments = fetch_comments_for_post(client, str(post_id), max_pages=max_cp)
            post["comments"] = comments
            print(f"→ got {len(comments)}")

            time.sleep(DELAY_BETWEEN_COMMENTS)

        print(f"   ✅ Comment fetching complete.\n")
    else:
        print("⏭️  Skipping comment scraping (--no-comments)\n")

    # ── Save output ──────────────────────────────────────────────────────
    export_data = {
        "scraped_at": datetime.now().isoformat(),
        "user": user_info,
        "total_posts": len(posts),
        "posts": posts,
    }

    # Save JSON
    json_path = os.path.join(args.output, f"weibo_{args.uid}_{timestamp}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(export_data, f, ensure_ascii=False, indent=2)

    # Also save a "latest" symlink/copy for convenience
    latest_path = os.path.join(args.output, f"weibo_{args.uid}_latest.json")
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(export_data, f, ensure_ascii=False, indent=2)

    file_size = os.path.getsize(json_path) / 1024
    print("=" * 60)
    print(f"  ✅ Export complete!")
    print(f"  📁 File: {json_path}")
    print(f"  📊 Size: {file_size:.1f} KB")
    print(f"  📝 Posts: {len(posts)}")
    if not args.no_comments:
        total_comments = sum(len(p.get("comments", [])) for p in posts)
        print(f"  💬 Comments: {total_comments}")
    print("=" * 60)


if __name__ == "__main__":
    main()

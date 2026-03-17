"""
Download all Weibo posts (with images) and comments for a given user.
Uses the mobile API (m.weibo.cn) which is simpler to work with.

Usage:
    1. Log in to https://m.weibo.cn in your browser
    2. Open DevTools (F12) -> Network tab -> refresh page
    3. Find any request to m.weibo.cn, copy the Cookie header value
    4. Paste it into cookie.txt in this directory
    5. Run: python download_weibo.py
"""

import json
import os
import re
import sys
import time
import requests

USER_ID = "2201640147"
OUTPUT_DIR = "weibo_data"
IMAGE_DIR = os.path.join(OUTPUT_DIR, "images")
POSTS_FILE = os.path.join(OUTPUT_DIR, "posts.json")
COMMENTS_DIR = os.path.join(OUTPUT_DIR, "comments")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) "
                   "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                   "Version/15.0 Mobile/15E148 Safari/604.1",
    "Accept": "application/json, text/plain, */*",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": f"https://m.weibo.cn/u/{USER_ID}",
}

session = requests.Session()


def load_cookie():
    cookie_file = os.path.join(os.path.dirname(__file__), "cookie.txt")
    if not os.path.exists(cookie_file):
        print("ERROR: cookie.txt not found!")
        print("Steps to get your cookie:")
        print("  1. Open https://m.weibo.cn in your browser and log in")
        print("  2. Open DevTools (F12) -> Network tab -> refresh the page")
        print("  3. Click any request to m.weibo.cn")
        print("  4. Copy the 'Cookie' header value")
        print("  5. Paste it into cookie.txt in this directory")
        sys.exit(1)
    with open(cookie_file, "r", encoding="utf-8") as f:
        cookie = f.read().strip()
    if not cookie:
        print("ERROR: cookie.txt is empty!")
        sys.exit(1)
    HEADERS["Cookie"] = cookie


def api_get(url, params=None, retries=5):
    for attempt in range(retries):
        try:
            resp = session.get(url, headers=HEADERS, params=params, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                return data
            elif resp.status_code == 418:
                wait = 60 * (attempt + 1)
                print(f"  Rate limited, waiting {wait}s...")
                time.sleep(wait)
            elif resp.status_code == 403:
                print(f"  HTTP 403 Forbidden - cookie may be expired!")
                if attempt < retries - 1:
                    print(f"  Waiting 30s before retry...")
                    time.sleep(30)
            else:
                print(f"  HTTP {resp.status_code}, retrying in 10s...")
                time.sleep(10)
        except Exception as e:
            print(f"  Request error: {e}, retrying in 10s...")
            time.sleep(10)
    return None


def load_existing_posts():
    """Load previously downloaded posts to support resume."""
    if os.path.exists(POSTS_FILE):
        try:
            with open(POSTS_FILE, "r", encoding="utf-8") as f:
                posts = json.load(f)
            if posts:
                print(f"Found {len(posts)} previously downloaded posts.")
                return posts
        except (json.JSONDecodeError, IOError):
            pass
    return []


def save_posts(posts):
    """Save posts to disk."""
    with open(POSTS_FILE, "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)


def fetch_all_posts():
    """Fetch all posts using page-based pagination with dedup and empty-page tolerance."""
    existing = load_existing_posts()
    existing_ids = {p["id"] for p in existing}

    all_posts = list(existing)
    page = 1
    empty_streak = 0  # track consecutive pages with no new posts
    max_empty = 3     # stop after this many consecutive empty pages

    while True:
        print(f"Fetching posts page {page}...")
        data = api_get(
            "https://m.weibo.cn/api/container/getIndex",
            params={
                "type": "uid",
                "value": USER_ID,
                "containerid": f"107603{USER_ID}",
                "page": page,
            },
        )
        if not data:
            print(f"  Request failed at page {page}, retrying after pause...")
            time.sleep(15)
            # retry same page once more
            data = api_get(
                "https://m.weibo.cn/api/container/getIndex",
                params={
                    "type": "uid",
                    "value": USER_ID,
                    "containerid": f"107603{USER_ID}",
                    "page": page,
                },
            )
            if not data:
                print(f"  Still failing. Stopping pagination.")
                break

        if data.get("ok") != 1:
            # Sometimes API returns ok=0 for intermediate pages, keep trying
            empty_streak += 1
            if empty_streak >= max_empty:
                print(f"  {max_empty} consecutive failures/empty pages, stopping.")
                break
            print(f"  ok!=1 at page {page}, trying next page...")
            page += 1
            time.sleep(3)
            continue

        cards = data.get("data", {}).get("cards", [])
        if not cards:
            empty_streak += 1
            if empty_streak >= max_empty:
                print(f"  {max_empty} consecutive empty pages, stopping.")
                break
            page += 1
            time.sleep(2)
            continue

        new_count = 0
        for card in cards:
            if card.get("card_type") == 9:
                mblog = card.get("mblog", {})
                if mblog:
                    post_id = mblog.get("id", "")
                    if post_id and post_id not in existing_ids:
                        all_posts.append(mblog)
                        existing_ids.add(post_id)
                        new_count += 1

        if new_count > 0:
            empty_streak = 0
            print(f"  Got {new_count} new posts (total: {len(all_posts)})")
        else:
            empty_streak += 1
            print(f"  No new posts on page {page} (empty streak: {empty_streak}/{max_empty})")
            if empty_streak >= max_empty:
                print(f"  Stopping pagination.")
                break

        page += 1
        # Slower pace to avoid rate limiting
        time.sleep(3)

    return all_posts


def get_full_text(post_id):
    """Fetch full long text for a post."""
    data = api_get(
        "https://m.weibo.cn/statuses/extend",
        params={"id": post_id},
    )
    if data and data.get("ok") == 1:
        return data.get("data", {}).get("longTextContent", "")
    return None


def clean_html(text):
    """Remove HTML tags from text."""
    if not text:
        return ""
    return re.sub(r"<[^>]+>", "", text).strip()


def extract_post_info(mblog):
    """Extract key info from a post. Works with both raw and already-processed posts."""
    # If already processed (from resume), return as-is
    if "text_html" in mblog and "image_urls" in mblog:
        return mblog

    post_id = mblog.get("id", "")
    mid = mblog.get("mid", post_id)

    # Get text - fetch full text if truncated
    text = mblog.get("text", "")
    if mblog.get("isLongText"):
        full = get_full_text(mid)
        if full:
            text = full
        time.sleep(1)

    # Extract image URLs
    pics = []
    if "pics" in mblog:
        for pic in mblog["pics"]:
            large = pic.get("large", {}).get("url", "")
            if large:
                pics.append(large)
            else:
                pics.append(pic.get("url", ""))

    # Also check page_info for video cover / single image posts
    page_info = mblog.get("page_info", {})
    if page_info and not pics:
        page_pic = page_info.get("page_pic", {}).get("url", "")
        if page_pic:
            pics.append(page_pic)

    return {
        "id": post_id,
        "mid": mid,
        "created_at": mblog.get("created_at", ""),
        "text_html": text,
        "text": clean_html(text),
        "reposts_count": mblog.get("reposts_count", 0),
        "comments_count": mblog.get("comments_count", 0),
        "attitudes_count": mblog.get("attitudes_count", 0),
        "image_urls": pics,
        "image_files": [],
    }


def download_image(url, save_path):
    """Download a single image."""
    if os.path.exists(save_path):
        return True
    try:
        resp = session.get(url, headers={
            "User-Agent": HEADERS["User-Agent"],
            "Referer": "https://m.weibo.cn/",
        }, timeout=30)
        if resp.status_code == 200:
            with open(save_path, "wb") as f:
                f.write(resp.content)
            return True
    except Exception as e:
        print(f"    Failed to download {url}: {e}")
    return False


def download_post_images(post):
    """Download all images for a post."""
    if not post["image_urls"]:
        return
    post_dir = os.path.join(IMAGE_DIR, str(post["id"]))
    os.makedirs(post_dir, exist_ok=True)
    for i, url in enumerate(post["image_urls"]):
        ext = url.rsplit(".", 1)[-1].split("?")[0] if "." in url else "jpg"
        if len(ext) > 5:
            ext = "jpg"
        filename = f"{i+1}.{ext}"
        save_path = os.path.join(post_dir, filename)
        if download_image(url, save_path):
            post["image_files"].append(save_path)
        time.sleep(0.5)


def fetch_comments(post_id):
    """Fetch all comments for a post."""
    all_comments = []
    page = 1
    max_page = 100
    while page <= max_page:
        data = api_get(
            "https://m.weibo.cn/api/comments/show",
            params={"id": post_id, "page": page},
        )
        if not data or data.get("ok") != 1:
            break

        comments = data.get("data", {}).get("data", [])
        if not comments:
            break

        for c in comments:
            comment_info = {
                "id": c.get("id", ""),
                "user": c.get("user", {}).get("screen_name", ""),
                "text": clean_html(c.get("text", "")),
                "created_at": c.get("created_at", ""),
                "like_count": c.get("like_count", 0),
            }
            all_comments.append(comment_info)

        if len(comments) < 10:
            break
        page += 1
        time.sleep(1.5)

    return all_comments


def main():
    load_cookie()
    os.makedirs(IMAGE_DIR, exist_ok=True)
    os.makedirs(COMMENTS_DIR, exist_ok=True)

    # Test cookie validity first
    print("Testing cookie validity...")
    test = api_get(
        "https://m.weibo.cn/api/container/getIndex",
        params={
            "type": "uid",
            "value": USER_ID,
            "containerid": f"107603{USER_ID}",
            "page": 1,
        },
    )
    if not test or test.get("ok") != 1:
        print("ERROR: Cookie appears invalid or expired!")
        print("Please update cookie.txt with a fresh cookie from m.weibo.cn")
        sys.exit(1)

    # Show user info
    cards = test.get("data", {}).get("cards", [])
    total_api_posts = test.get("data", {}).get("cardlistInfo", {}).get("total", "unknown")
    print(f"Cookie valid! User timeline has ~{total_api_posts} items.")

    # Step 1: Fetch all posts
    print("\n" + "=" * 50)
    print(f"Fetching all posts for user {USER_ID}...")
    print("=" * 50)
    raw_posts = fetch_all_posts()
    print(f"\nTotal raw posts: {len(raw_posts)}")

    # Step 2: Process posts - extract info and download images
    posts = []
    for i, mblog in enumerate(raw_posts):
        post = extract_post_info(mblog)
        print(f"\nProcessing post {i+1}/{len(raw_posts)} (id={post['id']})...")
        text_preview = post['text'][:80] if post['text'] else "(no text)"
        print(f"  Text: {text_preview}...")
        if post["image_urls"]:
            print(f"  Downloading {len(post['image_urls'])} images...")
            download_post_images(post)
        posts.append(post)

        # Save periodically every 20 posts
        if (i + 1) % 20 == 0:
            save_posts(posts)
            print(f"  [Progress saved: {len(posts)} posts]")

    # Final save
    save_posts(posts)
    print(f"\nPosts saved to {POSTS_FILE}")

    # Step 3: Fetch comments for each post
    print("\n" + "=" * 50)
    print("Fetching comments...")
    print("=" * 50)
    for i, post in enumerate(posts):
        if post["comments_count"] == 0:
            continue
        comment_file = os.path.join(COMMENTS_DIR, f"{post['id']}.json")
        if os.path.exists(comment_file):
            print(f"  Comments for post {post['id']} already downloaded, skipping.")
            continue
        print(f"\nFetching comments for post {i+1}/{len(posts)} "
              f"(id={post['id']}, {post['comments_count']} comments)...")
        comments = fetch_comments(post["id"])
        if comments:
            with open(comment_file, "w", encoding="utf-8") as f:
                json.dump({
                    "post_id": post["id"],
                    "post_text": post["text"][:100],
                    "comments": comments,
                }, f, ensure_ascii=False, indent=2)
            print(f"  Saved {len(comments)} comments.")
        time.sleep(2)

    print("\n" + "=" * 50)
    print("Done!")
    print(f"  Total posts: {len(posts)}")
    print(f"  Posts: {POSTS_FILE}")
    print(f"  Images: {IMAGE_DIR}/")
    print(f"  Comments: {COMMENTS_DIR}/")
    print("=" * 50)


if __name__ == "__main__":
    main()

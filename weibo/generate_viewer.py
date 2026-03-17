"""Generate a self-contained HTML viewer for downloaded Weibo posts."""
import json
import base64
import os
from pathlib import Path
from html import escape

DATA_DIR = Path(__file__).parent / "weibo_data"
OUTPUT = Path(__file__).parent / "weibo_viewer.html"


def load_posts():
    with open(DATA_DIR / "posts.json", "r", encoding="utf-8") as f:
        return json.load(f)


def load_comments(post_id):
    path = DATA_DIR / "comments" / f"{post_id}.json"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("comments", [])
    return []


def image_to_data_uri(filepath):
    """Convert local image to base64 data URI for embedding."""
    full_path = Path(__file__).parent / filepath
    if not full_path.exists():
        return None
    with open(full_path, "rb") as f:
        data = base64.b64encode(f.read()).decode("ascii")
    ext = full_path.suffix.lower()
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "gif": "image/gif"}.get(ext.lstrip("."), "image/jpeg")
    return f"data:{mime};base64,{data}"


def format_date(raw):
    """Convert 'Sun Aug 06 09:58:58 +0800 2023' to readable format."""
    from datetime import datetime
    try:
        dt = datetime.strptime(raw, "%a %b %d %H:%M:%S %z %Y")
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return raw


def build_html(posts):
    cards = []
    for p in posts:
        post_id = p["id"]
        date = format_date(p["created_at"])
        text = p.get("text_html") or escape(p.get("text", ""))
        reposts = p.get("reposts_count", 0)
        comments_count = p.get("comments_count", 0)
        likes = p.get("attitudes_count", 0)

        # Images
        imgs_html = ""
        for fp in p.get("image_files", []):
            uri = image_to_data_uri(fp)
            if uri:
                imgs_html += f'<img src="{uri}" loading="lazy" onclick="openLightbox(this.src)">'

        # Comments
        comments = load_comments(post_id)
        comments_html = ""
        if comments:
            items = ""
            for c in comments:
                items += f'''<div class="comment">
                    <span class="comment-user">{escape(c.get("user",""))}</span>
                    <span class="comment-date">{escape(str(c.get("created_at","")))}</span>
                    {f'<span class="comment-likes">👍 {c["like_count"]}</span>' if c.get("like_count") else ""}
                    <div class="comment-text">{escape(c.get("text",""))}</div>
                </div>'''
            comments_html = f'''<details class="comments-section">
                <summary>💬 {len(comments)} 条评论</summary>
                <div class="comments-list">{items}</div>
            </details>'''

        cards.append(f'''<article class="post" id="post-{post_id}">
            <div class="post-date">{date}</div>
            <div class="post-text">{text}</div>
            {f'<div class="post-images">{imgs_html}</div>' if imgs_html else ""}
            <div class="post-stats">
                <span>🔁 {reposts}</span>
                <span>💬 {comments_count}</span>
                <span>👍 {likes}</span>
            </div>
            {comments_html}
        </article>''')

    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>我的微博存档</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family: -apple-system, "Segoe UI", sans-serif; background:#f5f5f5; color:#333; }}
.container {{ max-width:680px; margin:0 auto; padding:16px; }}
h1 {{ text-align:center; padding:24px 0 8px; font-size:1.5em; }}
.meta {{ text-align:center; color:#888; font-size:0.9em; margin-bottom:20px; }}
.search {{ display:block; width:100%; padding:10px 14px; border:1px solid #ddd; border-radius:8px; font-size:1em; margin-bottom:16px; }}
.post {{ background:#fff; border-radius:12px; padding:20px; margin-bottom:14px; box-shadow:0 1px 3px rgba(0,0,0,.08); }}
.post-date {{ color:#999; font-size:0.85em; margin-bottom:8px; }}
.post-text {{ line-height:1.7; margin-bottom:10px; white-space:pre-wrap; word-break:break-word; }}
.post-images {{ display:flex; flex-wrap:wrap; gap:8px; margin-bottom:10px; }}
.post-images img {{ max-width:100%; max-height:300px; border-radius:8px; cursor:pointer; object-fit:cover; }}
.post-stats {{ display:flex; gap:16px; color:#999; font-size:0.85em; }}
.comments-section {{ margin-top:12px; }}
.comments-section summary {{ cursor:pointer; color:#666; font-size:0.9em; }}
.comments-list {{ margin-top:8px; }}
.comment {{ padding:8px 0; border-bottom:1px solid #f0f0f0; font-size:0.9em; }}
.comment-user {{ color:#eb7350; font-weight:600; margin-right:8px; }}
.comment-date {{ color:#bbb; font-size:0.8em; }}
.comment-likes {{ color:#bbb; font-size:0.8em; margin-left:6px; }}
.comment-text {{ margin-top:4px; line-height:1.5; }}
#lightbox {{ display:none; position:fixed; inset:0; background:rgba(0,0,0,.85); z-index:999; justify-content:center; align-items:center; cursor:pointer; }}
#lightbox img {{ max-width:95vw; max-height:95vh; border-radius:4px; }}
#lightbox.active {{ display:flex; }}
.year-nav {{ text-align:center; margin-bottom:16px; display:flex; flex-wrap:wrap; gap:6px; justify-content:center; }}
.year-nav button {{ padding:4px 12px; border:1px solid #ddd; border-radius:16px; background:#fff; cursor:pointer; font-size:0.85em; }}
.year-nav button.active {{ background:#eb7350; color:#fff; border-color:#eb7350; }}
</style>
</head>
<body>
<div class="container">
<h1>我的微博存档</h1>
<p class="meta">{len(posts)} 条微博</p>
<div class="year-nav" id="yearNav"></div>
<input class="search" type="text" placeholder="搜索微博内容..." id="search">
<div id="posts">{"".join(cards)}</div>
</div>
<div id="lightbox" onclick="this.classList.remove(\'active\')"><img></div>
<script>
function openLightbox(src) {{
    const lb = document.getElementById('lightbox');
    lb.querySelector('img').src = src;
    lb.classList.add('active');
}}
const search = document.getElementById('search');
const posts = document.querySelectorAll('.post');
search.addEventListener('input', () => {{
    const q = search.value.toLowerCase();
    posts.forEach(p => p.style.display = p.textContent.toLowerCase().includes(q) ? '' : 'none');
}});
// Year nav
const years = new Set();
posts.forEach(p => {{
    const d = p.querySelector('.post-date').textContent;
    years.add(d.split('-')[0]);
}});
const nav = document.getElementById('yearNav');
const allBtn = document.createElement('button');
allBtn.textContent = '全部';
allBtn.className = 'active';
allBtn.onclick = () => {{
    posts.forEach(p => p.style.display = '');
    nav.querySelectorAll('button').forEach(b => b.classList.remove('active'));
    allBtn.classList.add('active');
}};
nav.appendChild(allBtn);
[...years].sort().reverse().forEach(y => {{
    const btn = document.createElement('button');
    btn.textContent = y;
    btn.onclick = () => {{
        posts.forEach(p => {{
            const d = p.querySelector('.post-date').textContent;
            p.style.display = d.startsWith(y) ? '' : 'none';
        }});
        nav.querySelectorAll('button').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
    }};
    nav.appendChild(btn);
}});
</script>
</body>
</html>'''


def main():
    print("Loading posts...")
    posts = load_posts()
    print(f"Loaded {len(posts)} posts, generating HTML...")
    html = build_html(posts)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Done! Open {OUTPUT}")


if __name__ == "__main__":
    main()

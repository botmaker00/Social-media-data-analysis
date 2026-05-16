"""Flask dashboard for Instagram-style profile data from data.json."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, url_for

APP_DIR = Path(__file__).resolve().parent
DATA_PATH = APP_DIR / "data.json"

app = Flask(__name__)


def load_profiles() -> list[dict]:
    with open(DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def format_int(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M".replace(".0M", "M")
    if n >= 1_000:
        return f"{n / 1_000:.1f}K".replace(".0K", "K")
    return str(n)


def build_dashboard_state(profiles: list[dict]) -> dict:
    n = len(profiles)
    if not n:
        return {
            "total": 0,
            "unique_categories": 0,
            "category_counts": {},
            "all_category_counts": {},
            "top_followers": [],
            "max_followers": None,
            "max_posts": None,
            "max_following": None,
            "avg_followers": 0,
            "avg_posts": 0,
        }

    by_followers = sorted(profiles, key=lambda p: p["followers"], reverse=True)
    by_posts = sorted(profiles, key=lambda p: p["posts"], reverse=True)
    by_following = sorted(profiles, key=lambda p: p["following"], reverse=True)

    cats = Counter(p["type_of_pages"] for p in profiles)
    top_cats = dict(cats.most_common(15))

    def slim(p: dict) -> dict:
        return {
            "username": p["username"],
            "name": p["name"],
            "posts": p["posts"],
            "followers": p["followers"],
            "following": p["following"],
            "type_of_pages": p["type_of_pages"],
        }

    return {
        "total": n,
        "unique_categories": len(cats),
        "category_counts": top_cats,
        "all_category_counts": dict(cats),
        "top_followers": [slim(p) for p in by_followers[:12]],
        "max_followers": slim(by_followers[0]),
        "max_posts": slim(by_posts[0]),
        "max_following": slim(by_following[0]),
        "avg_followers": int(sum(p["followers"] for p in profiles) / n),
        "avg_posts": round(sum(p["posts"] for p in profiles) / n, 1),
    }


def normalize_q(q: str) -> str:
    return re.sub(r"\s+", " ", (q or "").strip().lower())


def interpret_question(q: str) -> tuple[str | None, list[dict]]:
    """Return (answer_html_or_None, matching_profiles)."""
    profiles = load_profiles()
    nq = normalize_q(q)

    if not nq:
        return None, profiles

    # Notebook-style questions
    patterns_followers = (
        "max follower",
        "maximum follower",
        "most follower",
        "highest follower",
        "top follower",
        "who has the most follower",
        "who has max follower",
        "largest follower",
        "most followers",
        "maximum followers",
        "top followers",
    )
    patterns_posts = (
        "max post",
        "maximum post",
        "most post",
        "highest post",
        "top post",
        "who has the most post",
        "most posts",
        "maximum posts",
        "top posts",
    )
    patterns_following = (
        "max following",
        "maximum following",
        "most following",
        "highest following",
        "top following",
        "who follows most",
        "most accounts followed",
    )
    patterns_categories = (
        "categor",
        "type of page",
        "types of user",
        "how many categor",
        "list categor",
        "all categor",
        "user types",
        "page types",
        "account type",
        "kinds of user",
    )
    patterns_stats = (
        "summary",
        "overview",
        "statistics",
        "stats",
        "how many user",
        "how many people",
        "how many profile",
        "total user",
        "total profile",
    )

    def winner_line(label: str, p: dict, field: str) -> str:
        v = p[field]
        return (
            f"<strong>{label}</strong>: <span class='highlight'>@{p['username']}</span> "
            f"({p['name']}) — {format_int(v)} {field}."
        )

    if any(p in nq for p in patterns_followers) or nq in {"followers", "max followers"}:
        p = max(profiles, key=lambda x: x["followers"])
        return winner_line("Most followers", p, "followers"), [p]

    if any(p in nq for p in patterns_posts) or nq in {"posts", "max posts"}:
        p = max(profiles, key=lambda x: x["posts"])
        return winner_line("Most posts", p, "posts"), [p]

    if any(p in nq for p in patterns_following) or nq in {"following", "max following"}:
        p = max(profiles, key=lambda x: x["following"])
        return winner_line("Most following", p, "following"), [p]

    if any(p in nq for p in patterns_categories):
        cats = Counter(p["type_of_pages"] for p in profiles)
        lines = [
            f"<strong>{k}</strong>: {v} profile{'s' if v != 1 else ''}"
            for k, v in cats.most_common()
        ]
        html = (
            f"<p class='search-lead'>There are <strong>{len(cats)}</strong> distinct categories "
            f"across <strong>{len(profiles)}</strong> profiles.</p>"
            "<ul class='search-cat-list'>" + "".join(f"<li>{line}</li>" for line in lines) + "</ul>"
        )
        sorted_profiles = sorted(
            profiles,
            key=lambda p: (p["type_of_pages"].lower(), p["username"].lower()),
        )
        return html, sorted_profiles

    if any(p in nq for p in patterns_stats):
        cats = Counter(p["type_of_pages"] for p in profiles)
        mf = max(profiles, key=lambda x: x["followers"])
        mp = max(profiles, key=lambda x: x["posts"])
        mfw = max(profiles, key=lambda x: x["following"])
        html = (
            "<p class='search-lead'>Dataset summary</p>"
            "<ul class='search-cat-list'>"
            f"<li><strong>Total profiles</strong>: {len(profiles)}</li>"
            f"<li><strong>Unique categories</strong>: {len(cats)}</li>"
            f"<li><strong>Most followers</strong>: @{mf['username']} ({format_int(mf['followers'])})</li>"
            f"<li><strong>Most posts</strong>: @{mp['username']} ({mp['posts']} posts)</li>"
            f"<li><strong>Most following</strong>: @{mfw['username']} ({mfw['following']} following)</li>"
            "</ul>"
            "<p class='search-lead'>All profiles are listed below.</p>"
        )
        return html, profiles

    # Category filter: exact match on type_of_pages
    for p in profiles:
        if nq == p["type_of_pages"].lower():
            matches = [x for x in profiles if x["type_of_pages"] == p["type_of_pages"]]
            return (
                f"<p class='search-lead'>Category <strong>{p['type_of_pages']}</strong> — "
                f"{len(matches)} profile(s).</p>",
                matches,
            )

    unique_types = sorted({p["type_of_pages"] for p in profiles}, key=str.lower)
    partial_types = [t for t in unique_types if nq in t.lower()]
    if len(partial_types) == 1:
        t = partial_types[0]
        matches = [x for x in profiles if x["type_of_pages"] == t]
        return (
            f"<p class='search-lead'>Category <strong>{t}</strong> — {len(matches)} profile(s).</p>",
            matches,
        )
    if len(partial_types) > 1:
        matches = [x for x in profiles if x["type_of_pages"] in partial_types]
        listed = ", ".join(f"<strong>{t}</strong>" for t in partial_types[:12])
        if len(partial_types) > 12:
            listed += ", …"
        return (
            f"<p class='search-lead'>Categories matching your query: {listed} — "
            f"{len(matches)} profile(s).</p>",
            sorted(matches, key=lambda p: (p["type_of_pages"].lower(), p["username"].lower())),
        )

    # General text search
    matches = []
    for p in profiles:
        hay = " ".join(
            str(p.get(k, ""))
            for k in ("username", "name", "type_of_pages", "bio")
        ).lower()
        if nq in hay:
            matches.append(p)

    if matches:
        return (
            f"<p class='search-lead'>Found <strong>{len(matches)}</strong> profile(s) matching your search.</p>",
            matches,
        )

    return (
        "<p class='search-lead'>No matches. Try keywords like <em>max followers</em>, "
        "<em>max posts</em>, <em>categories</em>, or a username.</p>",
        [],
    )


@app.route("/")
def index():
    profiles = load_profiles()
    dash = build_dashboard_state(profiles)
    return render_template("index.html", dash=dash, profiles=profiles)


@app.route("/search", methods=["GET"])
def search():
    q_raw = request.args.get("q", "")
    q = (q_raw or "").strip()
    if not q:
        return redirect(url_for("index"))

    answer, profiles = interpret_question(q)
    return render_template(
        "search.html",
        query=q,
        answer=answer,
        profiles=profiles,
        error_message=None,
    )


@app.route("/api/search")
def api_search():
    q = request.args.get("q", "")
    answer, results = interpret_question(q)

    def out(p: dict) -> dict:
        return {
            "username": p["username"],
            "name": p["name"],
            "posts": p["posts"],
            "followers": p["followers"],
            "following": p["following"],
            "type_of_pages": p["type_of_pages"],
            "bio": p.get("bio", ""),
        }

    return jsonify(
        {
            "query": q,
            "answer": answer,
            "results": [out(p) for p in results],
        }
    )


@app.route("/api/stats")
def api_stats():
    profiles = load_profiles()
    return jsonify(build_dashboard_state(profiles))


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)

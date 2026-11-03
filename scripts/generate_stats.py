#!/usr/bin/env python3
"""Generate the self-hosted GitHub activity cards used by the profile README.

Cards are 700x200 SVGs in the same visual language as the hero banner:
  assets/stats.svg      overall activity + 12-month contribution chart
  assets/languages.svg  top languages by bytes across public original repos

Run locally:  python scripts/generate_stats.py
In CI:        GITHUB_TOKEN is provided by Actions.
"""
from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

USER = os.environ.get("PROFILE_USER", "johnleshan")
ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
API = "https://api.github.com"
GRAPHQL = "https://api.github.com/graphql"
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"


def token() -> str:
    value = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if value:
        return value
    try:
        return subprocess.check_output(["gh", "auth", "token"], text=True).strip()
    except Exception as exc:
        raise SystemExit("Set GITHUB_TOKEN or authenticate the gh CLI.") from exc


TOKEN = token()
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": f"{USER}-profile-stats",
}


def get(url: str):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.load(response), response.headers


def graphql(query: str) -> dict:
    payload = json.dumps({"query": query}).encode()
    req = urllib.request.Request(
        GRAPHQL,
        data=payload,
        headers={**HEADERS, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        data = json.load(response)
    if data.get("errors"):
        raise SystemExit(data["errors"])
    return data["data"]


def repos() -> list[dict]:
    items: list[dict] = []
    page = 1
    while True:
        batch, header = get(
            f"{API}/user/repos?per_page=30&page={page}&affiliation=owner&sort=pushed"
        )
        items.extend(batch)
        if len(batch) < 30 or 'rel="next"' not in header.get("Link", ""):
            break
        page += 1
    return items


def languages(repo: str) -> dict[str, int]:
    try:
        data, _ = get(f"{API}/repos/{USER}/{repo}/languages")
        return {k: int(v) for k, v in data.items()}
    except urllib.error.HTTPError:
        return {}


def esc(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def contributions(days: list[dict]) -> list[tuple[str, int, str]]:
    """Return (month, total, initial) for the last 12 months, oldest first."""
    buckets: dict[str, int] = {}
    for day in days:
        buckets[day["date"][:7]] = buckets.get(day["date"][:7], 0) + int(day["contributionCount"])
    months = sorted(buckets)[-12:]
    return [
        (m, buckets[m], datetime.strptime(m + "-01", "%Y-%m-%d").strftime("%b")[0])
        for m in months
    ]


def stats_card(user: dict, items: list[dict], collection: dict, days: list[dict], lang_count: int) -> str:
    originals = [r for r in items if not r["fork"] and not r["archived"]]
    public_all = [r for r in items if not r["private"]]
    stars = sum(int(r.get("stargazers_count", 0)) for r in originals)
    total_year = sum(int(d["contributionCount"]) for d in days)
    private_year = int(collection.get("restrictedContributionsCount", 0))
    updated = datetime.now(timezone.utc).strftime("%d %b %Y")

    monthly = contributions(days)
    peak = max(v for _, v, _ in monthly) if monthly else 1
    chart_x, chart_y, chart_h, bar_w, bar_gap = 350, 64, 66, 18, 8
    bars, labels = [], []
    for i, (m, value, initial) in enumerate(monthly):
        x = chart_x + i * (bar_w + bar_gap)
        h = max(2.0, chart_h * value / peak)
        y = chart_y + chart_h - h
        bars.append(f'<rect x="{x}" y="{chart_y}" width="{bar_w}" height="{chart_h}" rx="3" fill="#161B22"/>')
        bars.append(f'<rect x="{x}" y="{y:.1f}" width="{bar_w}" height="{h:.1f}" rx="3" fill="#22D3EE"/>')
        labels.append(f'<text x="{x + bar_w / 2:.1f}" y="{chart_y + chart_h + 18}" text-anchor="middle" font-family="{FONT}" font-size="7.5" fill="#6E7681">{initial}</text>')

    metrics = [
        (f"{len(public_all)}", "public repos"),
        (f"{stars}", "stars earned"),
        (f"{lang_count}", "languages"),
    ]
    metric_svg = []
    for i, (value, label) in enumerate(metrics):
        mx = 30 + i * 98
        metric_svg.append(
            f'<text x="{mx}" y="170" font-family="{FONT}" font-size="18" font-weight="700" fill="#F0F6FC">{value}</text>'
            f'<text x="{mx}" y="184" font-family="{FONT}" font-size="9.5" fill="#8B949E">{label}</text>'
        )

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="700" height="200" viewBox="0 0 700 200" role="img" aria-labelledby="title desc">
  <title id="title">{esc(user.get("name") or USER)} — GitHub at a glance</title>
  <desc id="desc">{total_year:,} contributions in the last year, {len(public_all)} public repositories and {stars} stars.</desc>
  <rect x="0.5" y="0.5" width="699" height="199" rx="10" fill="#0D1117" stroke="#30363D"/>
  <circle cx="30" cy="31" r="3" fill="#22D3EE"/>
  <text x="41" y="35" font-family="{FONT}" font-size="9.5" letter-spacing="2.2" fill="#8B949E">GITHUB AT A GLANCE</text>
  <text x="30" y="102" font-family="{FONT}" font-size="52" font-weight="700" fill="#F0F6FC">{total_year:,}</text>
  <text x="30" y="123" font-family="{FONT}" font-size="11" fill="#8B949E">contributions · last 12 months</text>
  <text x="30" y="142" font-family="{FONT}" font-size="9" fill="#6E7681">Includes {private_year:,} contributions in private repositories.</text>
  <line x1="336" y1="58" x2="336" y2="150" stroke="#21262D"/>
  {"".join(metric_svg)}
  <text x="{chart_x}" y="48" font-family="{FONT}" font-size="8.5" letter-spacing="1.8" fill="#8B949E">CONTRIBUTIONS / MONTH</text>
  {"".join(bars)}
  {"".join(labels)}
  <text x="670" y="190" text-anchor="end" font-family="{FONT}" font-size="9" fill="#6E7681">Updated {updated}</text>
</svg>
'''



def languages_card(rows: list[tuple[str, float]], lang_count: int) -> str:
    colors = {
        "JavaScript": "#F7DF1E",
        "TypeScript": "#3178C6",
        "Python": "#3776AB",
        "CSS": "#663399",
        "HTML": "#E34F26",
        "PHP": "#777BB4",
        "Jupyter Notebook": "#F37626",
        "Kotlin": "#7F52FF",
        "Java": "#ED8B00",
        "Blade": "#F7523F",
    }
    left, inner_w = 30, 640
    row_svg = []
    for i, (name, pct) in enumerate(rows):
        y = 78 + i * 24
        color = colors.get(name, "#22D3EE")
        width = max(4.0, inner_w * pct / 100)
        row_svg.append(
            f'<text x="{left}" y="{y + 9}" font-family="{FONT}" font-size="11.5" font-weight="600" fill="#C9D1D9">{esc(name)}</text>'
            f'<text x="{left + inner_w}" y="{y + 9}" text-anchor="end" font-family="{FONT}" font-size="10" fill="#8B949E">{pct:.1f}%</text>'
            f'<rect x="{left}" y="{y + 13}" width="{inner_w}" height="5" rx="2.5" fill="#161B22"/>'
            f'<rect x="{left}" y="{y + 13}" width="{width:.1f}" height="5" rx="2.5" fill="{color}"/>'
        )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="700" height="200" viewBox="0 0 700 200" role="img" aria-labelledby="title desc">
  <title id="title">Top languages</title>
  <desc id="desc">Share of code by bytes across public original repositories.</desc>
  <rect x="0.5" y="0.5" width="699" height="199" rx="10" fill="#0D1117" stroke="#30363D"/>
  <circle cx="30" cy="31" r="3" fill="#818CF8"/>
  <text x="41" y="35" font-family="{FONT}" font-size="9.5" letter-spacing="2.2" fill="#8B949E">TOP LANGUAGES</text>
  <text x="30" y="54" font-family="{FONT}" font-size="9" fill="#6E7681">by bytes · public original repositories</text>
  <text x="670" y="54" text-anchor="end" font-family="{FONT}" font-size="9" fill="#6E7681">{lang_count} languages across all original repos</text>
  {"".join(row_svg)}
</svg>
'''


if __name__ == "__main__":
    ASSETS.mkdir(exist_ok=True)
    data = graphql(
        f"""
        query {{
          user(login: "{USER}") {{
            name
            login
            followers {{ totalCount }}
            repositories(privacy: PUBLIC, isFork: false, ownerAffiliations: OWNER) {{ totalCount }}
            contributionsCollection {{
              totalCommitContributions
              totalPullRequestContributions
              totalIssueContributions
              restrictedContributionsCount
              contributionCalendar {{
                weeks {{ contributionDays {{ date contributionCount }} }}
              }}
            }}
          }}
        }}
        """
    )["user"]

    items = repos()
    originals = [r for r in items if not r["fork"] and not r["archived"]]

    languages_overall: dict[str, int] = {}
    languages_public: dict[str, int] = {}
    for repo in originals:
        bucket = languages(repo["name"])
        for name, value in bucket.items():
            languages_overall[name] = languages_overall.get(name, 0) + value
            if not repo["private"]:
                languages_public[name] = languages_public.get(name, 0) + value

    public_total = sum(languages_public.values()) or 1
    top = sorted(languages_public.items(), key=lambda kv: kv[1], reverse=True)[:5]
    rows = [(name, value * 100 / public_total) for name, value in top]

    days = [
        day
        for week in data["contributionsCollection"]["contributionCalendar"]["weeks"]
        for day in week["contributionDays"]
    ]

    (ASSETS / "stats.svg").write_text(
        stats_card(data, items, data["contributionsCollection"], days, len(languages_overall)),
        encoding="utf-8",
    )
    (ASSETS / "languages.svg").write_text(languages_card(rows, len(languages_overall)), encoding="utf-8")

    year_total = sum(int(d["contributionCount"]) for d in days)
    print(f"stats: {year_total:,} contributions, {sum(r['stargazers_count'] for r in originals)} stars, {len([r for r in items if not r['private']])} public repos")
    print("languages:", ", ".join(f"{n} {p:.1f}%" for n, p in rows))

#!/usr/bin/env python3
"""Generate the self-hosted GitHub stats cards used by the profile README.

Reads public data through the GitHub API (REST + GraphQL) and writes two SVGs:
  assets/stats.svg      overall activity card with a 12-month contribution heatmap
  assets/languages.svg  top languages by bytes across public, original repositories

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


def token() -> str:
    value = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if value:
        return value
    try:
        return subprocess.check_output(["gh", "auth", "token"], text=True).strip()
    except Exception as exc:  # pragma: no cover
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
        batch, headers = get(f"{API}/user/repos?per_page=100&page={page}&affiliation=owner&sort=pushed")
        items.extend(batch)
        if len(batch) < 100 or "rel=\"next\"" not in headers.get("Link", ""):
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


def lerp_hex(start: str, end: str, t: float) -> str:
    a = tuple(int(start[i : i + 2], 16) for i in (1, 3, 5))
    b = tuple(int(end[i : i + 2], 16) for i in (1, 3, 5))
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


def stats_card(user: dict, items: list[dict], contributions: dict, days: list[dict], lang_count: int) -> str:
    originals = [r for r in items if not r["fork"] and not r["archived"]]
    public = [r for r in originals if not r["private"]]
    stars = sum(int(r.get("stargazers_count", 0)) for r in originals)
    total_year = sum(int(d["contributionCount"]) for d in days)
    private_year = int(contributions.get("restrictedContributionsCount", 0))
    updated = datetime.now(timezone.utc).strftime("%d %b %Y")

    # 53 columns x 7 rows, oldest first. API returns Sunday-first weeks.
    week_map: dict[str, int] = {d["date"]: int(d["contributionCount"]) for d in days}
    ordered = sorted(week_map)
    values = [week_map[d] for d in ordered]
    peak = max(values) if values else 1
    cols = 53
    cell, gap = 5.0, 1.5
    grid_w = cols * (cell + gap) - gap
    grid_h = 7 * (cell + gap) - gap
    x0, y0 = 700 - 30 - grid_w, 64
    # keep the most recent 53*7 days, padded at the front
    target = cols * 7
    filled = (values + [0] * target)[-target:]
    colors = ["#161B22", "#155E75", "#0891B2", "#22D3EE", "#A5F3FC"]
    squares = []
    for i, count in enumerate(filled):
        col, row = divmod(i, 7)
        if count <= 0:
            level = 0
        elif count <= 2:
            level = 1
        elif count <= 5:
            level = 2
        elif count <= 12:
            level = 3
        else:
            level = 4
        squares.append(
            f'<rect x="{x0 + col * (cell + gap):.1f}" y="{y0 + row * (cell + gap):.1f}" '
            f'width="{cell}" height="{cell}" rx="1" fill="{colors[level]}"/>'
        )
    legend = "".join(
        f'<rect x="{x0 + 27 + i * 7}" y="133" width="5" height="5" rx="1" fill="{color}"/>'
        for i, color in enumerate(colors)
    )

    metrics = [
        (f"{len(public)}", "public repos"),
        (f"{stars}", "stars earned"),
        (f"{lang_count}", "languages"),
    ]
    metric_svg = []
    for i, (value, label) in enumerate(metrics):
        mx = 30 + i * 100
        metric_svg.append(
            f'<text x="{mx}" y="160" font-size="22" font-weight="700" fill="#F0F6FC">{value}</text>'
            f'<text x="{mx}" y="176" font-size="9.5" fill="#8B949E">{label}</text>'
        )

    if ordered:
        first = datetime.strptime(ordered[0], "%Y-%m-%d").strftime("%b %Y")
        last = datetime.strptime(ordered[-1], "%Y-%m-%d").strftime("%b %Y")
        period = f"{first} — {last}"
    else:
        period = ""

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="700" height="200" viewBox="0 0 700 200" role="img" aria-labelledby="title desc">
  <title id="title">{esc(user.get("name") or USER)} — GitHub at a glance</title>
  <desc id="desc">{total_year:,} contributions in the last year, {len(public)} public repositories and {stars} stars.</desc>
  <rect x="0.5" y="0.5" width="699" height="199" rx="10" fill="#0D1117" stroke="#30363D"/>
  <circle cx="30" cy="31" r="3" fill="#22D3EE"/>
  <text x="41" y="35" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif" font-size="9.5" letter-spacing="2.2" fill="#8B949E">GITHUB AT A GLANCE</text>
  <text x="30" y="92" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif" font-size="46" font-weight="700" fill="#F0F6FC">{total_year:,}</text>
  <text x="30" y="112" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif" font-size="11" fill="#8B949E">contributions · last 12 months</text>
  <line x1="30" y1="130" x2="300" y2="130" stroke="#21262D"/>
  {"".join(metric_svg)}
  <text x="{x0}" y="50" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif" font-size="9" letter-spacing="1.8" fill="#8B949E">CONTRIBUTION ACTIVITY</text>
  {"".join(squares)}
  <text x="{x0}" y="{y0 + grid_h + 15}" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif" font-size="9" fill="#6E7681">{period}</text>
  <text x="670" y="{y0 + grid_h + 15}" text-anchor="end" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif" font-size="9" fill="#6E7681">Updated {updated}</text>
  <text x="{x0}" y="140" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif" font-size="8" fill="#6E7681">Less</text>
  {legend}
  <text x="{x0 + 65}" y="140" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif" font-size="8" fill="#6E7681">More</text>
  <text x="{x0}" y="172" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif" font-size="9.5" fill="#6E7681">Includes {private_year:,} contributions in private repositories.</text>
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
    inner_w, left = 292, 24
    row_svg = []
    for i, (name, pct) in enumerate(rows):
        y = 72 + i * 22
        color = colors.get(name, "#22D3EE")
        width = max(3.0, inner_w * pct / 100)
        row_svg.append(
            f'<text x="{left}" y="{y}" font-family="-apple-system,BlinkMacSystemFont,\'Segoe UI\',Helvetica,Arial,sans-serif" font-size="11" fill="#C9D1D9">{esc(name)}</text>'
            f'<text x="{left + inner_w}" y="{y}" text-anchor="end" font-family="-apple-system,BlinkMacSystemFont,\'Segoe UI\',Helvetica,Arial,sans-serif" font-size="10" fill="#8B949E">{pct:.1f}%</text>'
            f'<rect x="{left}" y="{y + 5}" width="{inner_w}" height="4" rx="2" fill="#161B22"/>'
            f'<rect x="{left}" y="{y + 5}" width="{width:.1f}" height="4" rx="2" fill="{color}"/>'
        )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="340" height="200" viewBox="0 0 340 200" role="img" aria-labelledby="title desc">
  <title id="title">Top languages</title>
  <desc id="desc">Share of code by bytes across public original repositories.</desc>
  <rect x="0.5" y="0.5" width="339" height="199" rx="10" fill="#0D1117" stroke="#30363D"/>
  <circle cx="24" cy="30" r="3" fill="#818CF8"/>
  <text x="35" y="34" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif" font-size="9.5" letter-spacing="2.2" fill="#8B949E">TOP LANGUAGES</text>
  <text x="24" y="50" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif" font-size="9" fill="#6E7681">by bytes · public original repos</text>
  {"".join(row_svg)}
  <text x="24" y="186" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif" font-size="9" fill="#6E7681">{lang_count} languages across all original repositories</text>
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
    public = [r for r in originals if not r["private"]]

    languages_overall = {}
    languages_public = {}
    for repo in originals:
        bucket = languages(repo["name"])
        for name, value in bucket.items():
            languages_overall[name] = languages_overall.get(name, 0) + value
            if not repo["private"]:
                languages_public[name] = languages_public.get(name, 0) + value

    public_total = sum(languages_public.values()) or 1
    top = sorted(languages_public.items(), key=lambda kv: kv[1], reverse=True)[:5]
    rows = [(name, value * 100 / public_total) for name, value in top]
    lang_count_label = f"{len(languages_overall)} languages across all original repositories"

    days = [
        day
        for week in data["contributionsCollection"]["contributionCalendar"]["weeks"]
        for day in week["contributionDays"]
    ]

    (ASSETS / "stats.svg").write_text(
        stats_card(data, items, data["contributionsCollection"], days, len(languages_overall)), encoding="utf-8"
    )
    (ASSETS / "languages.svg").write_text(languages_card(rows, len(languages_overall)), encoding="utf-8")

    year_total = sum(int(d["contributionCount"]) for d in days)
    print(f"stats: {year_total:,} contributions, {len(public)} public originals, {sum(r['stargazers_count'] for r in originals)} stars")
    print("languages:", ", ".join(f"{n} {p:.1f}%" for n, p in rows))

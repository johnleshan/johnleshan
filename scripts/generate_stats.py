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
        batch, headers = get(f"{API}/user/repos?per_page=30&page={page}&affiliation=owner&sort=pushed")
        items.extend(batch)
        if len(batch) < 30 or "rel=\"next\"" not in headers.get("Link", ""):
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
    public_all = [r for r in items if not r["private"]]
    public = [r for r in originals if not r["private"]]
    stars = sum(int(r.get("stargazers_count", 0)) for r in originals)
    total_year = sum(int(d["contributionCount"]) for d in days)
    private_year = int(contributions.get("restrictedContributionsCount", 0))
    updated = datetime.now(timezone.utc).strftime("%d %b %Y")

    # Monthly totals, last 12 months.
    buckets: dict[str, int] = {}
    for day in days:
        key = day["date"][:7]
        buckets[key] = buckets.get(key, 0) + int(day["contributionCount"])
    months = sorted(buckets)[-12:]
    monthly = [buckets[m] for m in months]
    peak = max(monthly) if monthly else 1

    chart_x, chart_y, chart_h = 250, 70, 62
    bar_w, bar_gap = 12, 6
    bars = []
    labels = []
    for i, (key, value) in enumerate(zip(months, monthly)):
        x = chart_x + i * (bar_w + bar_gap)
        h = max(2.0, chart_h * value / peak)
        y = chart_y + chart_h - h
        bars.append(f'<rect x="{x}" y="{chart_y}" width="{bar_w}" height="{chart_h}" rx="2" fill="#161B22"/>')
        bars.append(f'<rect x="{x}" y="{y:.1f}" width="{bar_w}" height="{h:.1f}" rx="2" fill="#22D3EE"/>')
        label = datetime.strptime(key + "-01", "%Y-%m-%d").strftime("%b")[0]
        labels.append(f'<text x="{x + bar_w / 2:.1f}" y="{chart_y + chart_h + 13}" text-anchor="middle" font-size="7" fill="#6E7681">{label}</text>')

    metrics = [
        (f"{len(public_all)}", "public repos"),
        (f"{stars}", "stars earned"),
        (f"{lang_count}", "languages"),
    ]
    metric_svg = []
    for i, (value, label) in enumerate(metrics):
        mx = 24 + i * 80
        metric_svg.append(
            f'<text x="{mx}" y="148" font-size="18" font-weight="700" fill="#F0F6FC">{value}</text>'
            f'<text x="{mx}" y="162" font-size="8.5" fill="#8B949E">{label}</text>'
        )

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="495" height="195" viewBox="0 0 495 195" role="img" aria-labelledby="title desc">
  <title id="title">{esc(user.get("name") or USER)} — GitHub at a glance</title>
  <desc id="desc">{total_year:,} contributions in the last year, {len(public_all)} public repositories and {stars} stars.</desc>
  <rect x="0.5" y="0.5" width="494" height="194" rx="10" fill="#0D1117" stroke="#30363D"/>
  <circle cx="24" cy="30" r="3" fill="#22D3EE"/>
  <text x="35" y="34" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif" font-size="9" letter-spacing="2.1" fill="#8B949E">GITHUB AT A GLANCE</text>
  <text x="24" y="88" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif" font-size="40" font-weight="700" fill="#F0F6FC">{total_year:,}</text>
  <text x="24" y="106" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif" font-size="10" fill="#8B949E">contributions · last 12 months</text>
  <line x1="24" y1="120" x2="226" y2="120" stroke="#21262D"/>
  {"".join(metric_svg)}
  <line x1="240" y1="55" x2="240" y2="166" stroke="#21262D"/>
  <text x="{chart_x}" y="48" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif" font-size="8" letter-spacing="1.7" fill="#8B949E">CONTRIBUTIONS / MONTH</text>
  {"".join(bars)}
  {"".join(labels)}
  <text x="24" y="181" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif" font-size="8.5" fill="#6E7681">Includes {private_year:,} contributions in private repositories.</text>
  <text x="471" y="181" text-anchor="end" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif" font-size="8.5" fill="#6E7681">Updated {updated}</text>
</svg>
'''


def streak_card(days: list[dict]) -> str:
    counts = {d["date"]: int(d["contributionCount"]) for d in days}
    ordered = sorted(counts)
    seq = [counts[d] for d in ordered]
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    end = len(seq) - 1
    if seq and seq[-1] == 0 and ordered[-1] == today:
        end -= 1
    current = 0
    while end >= 0 and seq[end] > 0:
        current += 1
        end -= 1

    longest = run = 0
    for value in seq:
        run = run + 1 if value > 0 else 0
        longest = max(longest, run)

    total = sum(seq)
    active = sum(1 for value in seq if value > 0)
    best = max(seq) if seq else 0
    updated = datetime.now(timezone.utc).strftime("%d %b %Y")

    last30 = seq[-30:]
    dots = []
    for i, value in enumerate(last30):
        color = "#161B22" if value == 0 else "#22D3EE" if value < 6 else "#A5F3FC"
        dots.append(f'<circle cx="{24 + i * 14}" cy="162" r="4.2" fill="{color}"/>')

    metrics = [
        (185, "#818CF8", f"{longest:,}", "longest streak"),
        (330, "#34D399", f"{total:,}", "contributions"),
        (185, "#F59E0B", f"{active:,}", "active days"),
        (330, "#22D3EE", f"{best:,}", "best day"),
    ]
    metric_svg = []
    for i, (x, color, value, label) in enumerate(metrics):
        y = 78 if i < 2 else 125
        metric_svg.append(
            f'<text x="{x}" y="{y}" font-size="22" font-weight="700" fill="{color}">{value}</text>'
            f'<text x="{x}" y="{y + 14}" font-size="8.5" fill="#8B949E">{label}</text>'
        )

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="495" height="195" viewBox="0 0 495 195" role="img" aria-labelledby="title desc">
  <title id="title">Coding streak</title>
  <desc id="desc">{current} day current streak, {longest} day longest streak and {total:,} contributions.</desc>
  <rect x="0.5" y="0.5" width="494" height="194" rx="10" fill="#0D1117" stroke="#30363D"/>
  <circle cx="24" cy="30" r="3" fill="#F59E0B"/>
  <text x="35" y="34" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif" font-size="9" letter-spacing="2.1" fill="#8B949E">CODING STREAK</text>
  <text x="24" y="90" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif" font-size="42" font-weight="700" fill="#22D3EE">{current}</text>
  <text x="24" y="110" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif" font-size="10" fill="#8B949E">day current streak</text>
  <line x1="160" y1="54" x2="160" y2="138" stroke="#21262D"/>
  {"".join(metric_svg)}
  <text x="24" y="149" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif" font-size="8" letter-spacing="1.7" fill="#6E7681">LAST 30 DAYS</text>
  {"".join(dots)}
  <text x="471" y="181" text-anchor="end" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif" font-size="8.5" fill="#6E7681">Updated {updated}</text>
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
    (ASSETS / "streak.svg").write_text(streak_card(days), encoding="utf-8")
    (ASSETS / "languages.svg").write_text(languages_card(rows, len(languages_overall)), encoding="utf-8")

    year_total = sum(int(d["contributionCount"]) for d in days)
    print(f"stats: {year_total:,} contributions, {len(public)} public originals, {sum(r['stargazers_count'] for r in originals)} stars")
    print("languages:", ", ".join(f"{n} {p:.1f}%" for n, p in rows))

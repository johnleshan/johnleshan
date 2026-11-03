#!/usr/bin/env python3
"""Generate section header badges, the footer rule and the visual identity assets."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "headers"
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"

SECTIONS = [
    ("what-i-do", "WHAT I DO", "#22D3EE"),
    ("about-me", "ABOUT ME", "#818CF8"),
    ("tech-stack", "TECH STACK", "#38BDF8"),
    ("featured-projects", "FEATURED PROJECTS", "#34D399"),
    ("selected-results", "SELECTED RESULTS", "#F59E0B"),
    ("private-work", "SELECTED PRIVATE WORK", "#FB7185"),
    ("github-activity", "GITHUB ACTIVITY", "#22D3EE"),
    ("connect", "LET'S CONNECT", "#34D399"),
]


def header(name: str, label: str, accent: str) -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="700" height="56" viewBox="0 0 700 56" role="heading" aria-level="2" aria-labelledby="t">
  <title id="t">{label.title()}</title>
  <defs>
    <linearGradient id="g_{name}" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#22D3EE"/>
      <stop offset="1" stop-color="#818CF8"/>
    </linearGradient>
  </defs>
  <line x1="0" y1="28" x2="198" y2="28" stroke="#21262D" stroke-width="1"/>
  <line x1="502" y1="28" x2="700" y2="28" stroke="#21262D" stroke-width="1"/>
  <rect x="210" y="8" width="280" height="40" rx="20" fill="#0D1117" stroke="#30363D"/>
  <rect x="211" y="9" width="278" height="38" rx="19" fill="url(#g_{name})" opacity="0.07"/>
  <circle cx="233" cy="28" r="3.5" fill="{accent}"/>
  <text x="363" y="33" text-anchor="middle" font-family="{FONT}" font-size="13.5" font-weight="600" letter-spacing="2.6" fill="#E6EDF3">{label}</text>
</svg>
'''


def accent(name: str, accent: str) -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="700" height="10" viewBox="0 0 700 10">
  <defs>
    <linearGradient id="g_{name}" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="{accent}"/>
      <stop offset="1" stop-color="#818CF8"/>
    </linearGradient>
  </defs>
  <rect x="0" y="4" width="700" height="2" rx="1" fill="url(#g_{name})" opacity="0.55"/>
</svg>
'''


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, label, accent_color in SECTIONS:
        (OUT / f"{name}.svg").write_text(header(name, label, accent_color), encoding="utf-8")
        (OUT / f"{name}__rule.svg").write_text(accent(name, accent_color), encoding="utf-8")
    print(f"wrote {len(SECTIONS)} headers + rules to {OUT}")


if __name__ == "__main__":
    main()

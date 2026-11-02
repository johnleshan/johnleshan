"""Fast path: refresh only assets/streak.svg from the contribution calendar."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_stats import USER, graphql, streak_card

data = graphql(
    """
    query {
      user(login: "%s") {
        contributionsCollection {
          contributionCalendar {
            weeks { contributionDays { date contributionCount } }
          }
        }
      }
    }
    """
    % USER
)["user"]
days = [
    day
    for week in data["contributionsCollection"]["contributionCalendar"]["weeks"]
    for day in week["contributionDays"]
]
Path(__file__).resolve().parent.parent.joinpath("assets", "streak.svg").write_text(
    streak_card(days), encoding="utf-8"
)
print("streak.svg updated")

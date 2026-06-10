"""
Uses Claude API to extract injury/fitness intelligence for a team ahead of a match.
Results are cached in SQLite for 6 hours to minimise API spend.
"""
import json
from datetime import datetime, timedelta

import anthropic

from config.settings import settings
from db.database import execute_sql, query_one

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _client

_PROMPT_TEMPLATE = """You are a football analyst assistant. Analyse news about the
national football team "{team_name}" ahead of their FIFA World Cup 2026 match on {match_date}.

Based on recent publicly available information, identify:
1. Injured players (expected to miss the match)
2. Suspended players
3. Coach / managerial situation
4. Overall disruption severity (0.0 = no issues, 1.0 = severe disruption)

Return ONLY valid JSON in this exact schema:
{{
  "injured_players": ["player1", "player2"],
  "suspended_players": ["player3"],
  "coach_status": "normal | interim | change",
  "disruption_severity": 0.0,
  "summary": "one sentence summary"
}}"""


def get_team_news(team_id: int, team_name: str, match_date: str) -> dict:
    """Return cached or freshly fetched news analysis for a team."""
    now = datetime.utcnow()

    # Check cache
    row = query_one(
        "SELECT response_json FROM claude_news_cache "
        "WHERE team_id = ? AND expires_at > ? "
        "ORDER BY created_at DESC LIMIT 1",
        (team_id, now.isoformat()),
    )
    if row:
        return json.loads(row["response_json"])

    # Fetch fresh
    result = _fetch_from_claude(team_name, match_date)

    # Cache for 6 hours
    expires = (now + timedelta(hours=6)).isoformat()
    execute_sql(
        "INSERT INTO claude_news_cache (team_id, response_json, disruption_severity, expires_at) "
        "VALUES (?, ?, ?, ?)",
        (team_id, json.dumps(result), result.get("disruption_severity", 0.0), expires),
    )
    return result


def _fetch_from_claude(team_name: str, match_date: str) -> dict:
    prompt = _PROMPT_TEMPLATE.format(team_name=team_name, match_date=match_date)
    try:
        msg = _get_client().messages.create(
            model=settings.claude_model,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text.strip()
        # Extract JSON from response (may have surrounding text)
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
    except Exception as exc:
        print(f"  [claude_news] Failed for {team_name}: {exc}")

    return {
        "injured_players": [],
        "suspended_players": [],
        "coach_status": "normal",
        "disruption_severity": 0.0,
        "summary": "No data available",
    }

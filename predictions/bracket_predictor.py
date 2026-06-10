"""
Final Mode: simulate the full WC 2026 bracket via Monte Carlo and return
a prediction dict matching the JSON storage schema.
"""
from __future__ import annotations

from config.settings import settings
from db.database import query_df
from models.simulator import simulate_tournament, BracketResult


def predict_full_bracket(n_runs: int | None = None) -> dict:
    """Return the full bracket prediction dict."""
    n = n_runs or settings.simulation_n_runs
    result = simulate_tournament(n)
    return _bracket_result_to_dict(result)


def _bracket_result_to_dict(result: BracketResult) -> dict:
    team_names = _load_team_names()

    def _name(tid: int) -> str:
        return team_names.get(tid, f"Team {tid}")

    champion_id = result.most_likely_champion
    runner_up_id = result.most_likely_runner_up

    # Build TBD knockout slots from R32 bracket structure
    tbd_knockouts = _build_tbd_knockouts(result, team_names)

    return {
        "champion": _name(champion_id),
        "champion_id": champion_id,
        "champion_probability": round(result.champion_probs.get(champion_id, 0.0), 4),
        "runner_up": _name(runner_up_id),
        "runner_up_id": runner_up_id,
        "top_contenders": [
            {
                "team": _name(tid),
                "team_id": tid,
                "win_probability": round(prob, 4),
            }
            for tid, prob in sorted(result.champion_probs.items(), key=lambda x: x[1], reverse=True)[:8]
        ],
        "tbd_knockouts": tbd_knockouts,
        "n_simulations": result.n_runs,
    }


def _build_tbd_knockouts(result: BracketResult, team_names: dict[int, str]) -> list[dict]:
    """Build placeholder knockout slots based on current group assignments."""
    df = query_df("SELECT team_id, name, group_code FROM teams ORDER BY group_code")
    if df.empty:
        return []

    group_map: dict[str, list[tuple[int, str]]] = {}
    for _, row in df.iterrows():
        gc = str(row["group_code"])
        group_map.setdefault(gc, []).append((int(row["team_id"]), str(row["name"])))

    knockouts = []
    group_pairs = [("A", "B"), ("C", "D"), ("E", "F"), ("G", "H"), ("I", "J"), ("K", "L")]
    for i, (g1, g2) in enumerate(group_pairs):
        teams_g1 = group_map.get(g1, [])
        teams_g2 = group_map.get(g2, [])
        knockouts.append({
            "match_code": f"R32_{i*2+1}",
            "stage": "R32",
            "placeholder_home": f"1st Group {g1}",
            "placeholder_away": f"2nd Group {g2}",
            "resolved_home": teams_g1[0][1] if teams_g1 else None,
            "resolved_away": teams_g2[1][1] if len(teams_g2) > 1 else None,
            "predicted_winner": team_names.get(result.most_likely_champion, "TBD"),
            "predicted_score": {"home": 1, "away": 0},
            "actual_winner": None,
        })

    return knockouts


def _load_team_names() -> dict[int, str]:
    df = query_df("SELECT team_id, name FROM teams")
    if df.empty:
        return {}
    return dict(zip(df["team_id"].astype(int), df["name"].astype(str)))

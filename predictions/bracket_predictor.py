"""
Simulate the full WC 2026 bracket via Monte Carlo and return a prediction dict
matching the JSON storage schema.

Produces:
  group_stage_matches  — predicted scoreline for every group round-robin match
  predicted_standings  — final group table standings derived from those scores
  group_qualifiers     — top-2 per group from predicted standings
  bracket_rounds       — R32 → R16 → QF → SF → Final with predicted winners
  tbd_knockouts        — same as bracket_rounds["R32"] for backwards compat
"""
from __future__ import annotations

from config.settings import settings
from db.database import query_df
from models.simulator import simulate_tournament, BracketResult


def predict_full_bracket(n_runs: int | None = None) -> dict:
    n = n_runs or settings.simulation_n_runs
    result = simulate_tournament(n)
    return _bracket_result_to_dict(result)


# ── Top-level builder ───────────────────────────────────────────────────────


def _bracket_result_to_dict(result: BracketResult) -> dict:
    team_names = _load_team_names()

    def _name(tid: int) -> str:
        return team_names.get(tid, f"Team {tid}")

    champion_id = result.most_likely_champion
    runner_up_id = result.most_likely_runner_up

    group_teams = _load_group_teams()

    # Group stage: predict every round-robin match score
    group_stage_matches = _predict_group_stage_matches(group_teams)

    # Compute predicted final standings per group from those scores
    predicted_standings = _compute_predicted_standings(group_stage_matches, group_teams)

    # Top-2 per group based on predicted standings (consistent with match predictions)
    group_qualifiers = _qualifiers_from_standings(predicted_standings)

    # Full knockout bracket using champion_probs to pick round winners
    bracket_rounds = _build_bracket_rounds(group_qualifiers, group_teams, result, predicted_standings)

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
        "group_stage_matches": group_stage_matches,
        "predicted_standings": predicted_standings,
        "group_qualifiers": group_qualifiers,
        "bracket_rounds": bracket_rounds,
        # backwards compat
        "tbd_knockouts": bracket_rounds.get("R32", []),
        "n_simulations": result.n_runs,
    }


# ── Group stage predictions ─────────────────────────────────────────────────


def _predict_group_stage_matches(
    group_teams: dict[str, list[tuple[int, str]]],
) -> dict[str, list[dict]]:
    """Predict every round-robin group match. Returns {gc: [match_dict, ...]}."""
    from models.ensemble import get_ensemble
    try:
        ensemble = get_ensemble()
    except Exception:
        ensemble = None

    result: dict[str, list[dict]] = {}
    for gc in sorted(group_teams.keys()):
        teams = group_teams[gc]
        matches = []
        for i in range(len(teams)):
            for j in range(i + 1, len(teams)):
                home_id, home_name = teams[i]
                away_id, away_name = teams[j]
                h_score, a_score = _predict_score(ensemble, home_id, away_id)
                if h_score > a_score:
                    winner = home_name
                elif a_score > h_score:
                    winner = away_name
                else:
                    winner = "Draw"
                matches.append({
                    "group": gc,
                    "home": home_name,
                    "home_id": home_id,
                    "away": away_name,
                    "away_id": away_id,
                    "home_score": h_score,
                    "away_score": a_score,
                    "predicted_winner": winner,
                    "actual_home_score": None,
                    "actual_away_score": None,
                })
        result[gc] = matches
    return result


def _predict_score(ensemble, home_id: int, away_id: int) -> tuple[int, int]:
    if ensemble is None:
        return 1, 1
    try:
        pred = ensemble.predict(home_id, away_id, "Group Stage", 0.0, 0.0)
        return pred.predicted_home, pred.predicted_away
    except Exception:
        return 1, 1


def _compute_predicted_standings(
    group_stage_matches: dict[str, list[dict]],
    group_teams: dict[str, list[tuple[int, str]]],
) -> dict[str, list[dict]]:
    """Derive predicted final standings for each group from match score predictions."""
    standings: dict[str, list[dict]] = {}
    for gc in sorted(group_teams.keys()):
        stats: dict[int, dict] = {
            tid: {"team": name, "team_id": tid, "w": 0, "d": 0, "l": 0,
                  "gf": 0, "ga": 0, "pts": 0}
            for tid, name in group_teams[gc]
        }
        for m in group_stage_matches.get(gc, []):
            hs, as_ = m["home_score"], m["away_score"]
            hid, aid = m["home_id"], m["away_id"]
            if hid not in stats or aid not in stats:
                continue
            if hs > as_:
                stats[hid]["pts"] += 3
                stats[hid]["w"] += 1
                stats[aid]["l"] += 1
            elif as_ > hs:
                stats[aid]["pts"] += 3
                stats[aid]["w"] += 1
                stats[hid]["l"] += 1
            else:
                stats[hid]["pts"] += 1
                stats[hid]["d"] += 1
                stats[aid]["pts"] += 1
                stats[aid]["d"] += 1
            stats[hid]["gf"] += hs
            stats[hid]["ga"] += as_
            stats[aid]["gf"] += as_
            stats[aid]["ga"] += hs

        ranked = sorted(
            stats.values(),
            key=lambda t: (-t["pts"], -(t["gf"] - t["ga"]), -t["gf"]),
        )
        for pos, t in enumerate(ranked):
            t["gd"] = t["gf"] - t["ga"]
            t["position"] = pos + 1

        standings[gc] = ranked
    return standings


def _qualifiers_from_standings(
    standings: dict[str, list[dict]],
) -> dict[str, list[dict]]:
    """Return top-2 predicted qualifiers per group from standings."""
    qualifiers: dict[str, list[dict]] = {}
    for gc, ranked in standings.items():
        qualifiers[gc] = [
            {
                "team": t["team"],
                "team_id": t["team_id"],
                "position": t["position"],
                "advance_prob": 1.0,
            }
            for t in ranked[:2]
        ]
    return qualifiers


# ── Knockout bracket builder ────────────────────────────────────────────────


def _build_bracket_rounds(
    group_qualifiers: dict[str, list[dict]],
    group_teams: dict[str, list[tuple[int, str]]],
    result: BracketResult,
    predicted_standings: dict[str, list[dict]] | None = None,
) -> dict[str, list[dict]]:
    def _qual(gc: str, pos: int) -> dict | None:
        q = group_qualifiers.get(gc, [])
        return q[pos] if len(q) > pos else None

    group_pairs = [("A", "B"), ("C", "D"), ("E", "F"), ("G", "H"), ("I", "J"), ("K", "L")]
    r32: list[dict] = []
    num = 1
    for g1, g2 in group_pairs:
        a, b = _qual(g1, 0), _qual(g2, 1)
        c, d = _qual(g2, 0), _qual(g1, 1)
        if a and b:
            r32.append(_match_entry(num, "R32", a, b, _pick_winner(a, b, result), result))
            num += 1
        if c and d:
            r32.append(_match_entry(num, "R32", c, d, _pick_winner(c, d, result), result))
            num += 1

    # Best 8 3rd-place teams fill remaining R32 slots
    thirds = _get_best_thirds(group_qualifiers, group_teams, result, predicted_standings)
    for i in range(0, min(8, len(thirds)) - 1, 2):
        t1, t2 = thirds[i], thirds[i + 1]
        r32.append(_match_entry(num, "R32", t1, t2, _pick_winner(t1, t2, result), result))
        num += 1

    r16 = _build_round([m["_winner"] for m in r32], "R16", result)
    qf  = _build_round([m["_winner"] for m in r16], "QF",  result)
    sf  = _build_round([m["_winner"] for m in qf],  "SF",  result)
    final = _build_round([m["_winner"] for m in sf], "Final", result)

    def _strip(matches: list[dict]) -> list[dict]:
        return [{k: v for k, v in m.items() if k != "_winner"} for m in matches]

    return {
        "R32": _strip(r32),
        "R16": _strip(r16),
        "QF":  _strip(qf),
        "SF":  _strip(sf),
        "Final": _strip(final),
    }


def _get_best_thirds(
    group_qualifiers: dict[str, list[dict]],
    group_teams: dict[str, list[tuple[int, str]]],
    result: BracketResult,
    predicted_standings: dict[str, list[dict]] | None = None,
) -> list[dict]:
    """Return up to 8 best 3rd-place teams."""
    qualified_ids = {q["team_id"] for quals in group_qualifiers.values() for q in quals}

    if predicted_standings:
        thirds = []
        for gc, ranked in sorted(predicted_standings.items()):
            for t in ranked:
                if t["team_id"] not in qualified_ids:
                    thirds.append({
                        "team": t["team"],
                        "team_id": t["team_id"],
                        "position": 3,
                        "advance_prob": round(result.champion_probs.get(t["team_id"], 0.0), 4),
                        "_sort": (t["pts"], t["gd"], t["gf"]),
                    })
                    break
        return sorted(thirds, key=lambda t: t["_sort"], reverse=True)[:8]

    # Fallback: use Elo-sorted group_teams order
    thirds = []
    for gc, teams in sorted(group_teams.items()):
        for tid, name in teams:
            if tid not in qualified_ids:
                thirds.append({
                    "team": name,
                    "team_id": tid,
                    "position": 3,
                    "advance_prob": round(result.champion_probs.get(tid, 0.0), 4),
                })
                break
    return sorted(thirds, key=lambda t: t["advance_prob"], reverse=True)[:8]


# ── Match entry helpers ─────────────────────────────────────────────────────


def _pick_winner(home: dict, away: dict, result: BracketResult) -> dict:
    hp = result.champion_probs.get(home["team_id"], 0.0)
    ap = result.champion_probs.get(away["team_id"], 0.0)
    return home if hp >= ap else away


def _match_entry(
    num: int,
    stage: str,
    home: dict,
    away: dict,
    winner: dict,
    result: BracketResult,
) -> dict:
    hp = result.champion_probs.get(home["team_id"], 0.0)
    ap = result.champion_probs.get(away["team_id"], 0.0)
    total = (hp + ap) or 1.0
    margin = 2 if (max(hp, ap) / total) >= 0.65 else 1
    h_goals = margin if winner["team_id"] == home["team_id"] else 0
    a_goals = margin if winner["team_id"] == away["team_id"] else 0

    return {
        "match_num": num,
        "match_code": f"{stage}_{num}",
        "stage": stage,
        "home": home["team"],
        "home_id": home["team_id"],
        "away": away["team"],
        "away_id": away["team_id"],
        "predicted_winner": winner["team"],
        "predicted_winner_id": winner["team_id"],
        "predicted_score": {"home": h_goals, "away": a_goals},
        "actual_winner": None,
        "_winner": winner,
    }


def _build_round(teams: list[dict], stage: str, result: BracketResult) -> list[dict]:
    """Pair teams; give bye to the strongest if count is odd."""
    if len(teams) % 2 == 1:
        bye_idx = max(range(len(teams)), key=lambda i: result.champion_probs.get(teams[i]["team_id"], 0.0))
        bye_team = teams[bye_idx]
        teams = [t for i, t in enumerate(teams) if i != bye_idx]
    else:
        bye_team = None

    matches = []
    for i in range(0, len(teams) - 1, 2):
        h, a = teams[i], teams[i + 1]
        w = _pick_winner(h, a, result)
        matches.append(_match_entry(i // 2 + 1, stage, h, a, w, result))

    if bye_team:
        matches.append({
            "match_num": len(matches) + 1,
            "match_code": f"{stage}_BYE",
            "stage": stage,
            "home": bye_team["team"],
            "home_id": bye_team["team_id"],
            "away": "—",
            "away_id": -1,
            "predicted_winner": bye_team["team"],
            "predicted_winner_id": bye_team["team_id"],
            "predicted_score": {"home": 0, "away": 0},
            "actual_winner": None,
            "_winner": bye_team,
        })

    return matches


# ── DB helpers ──────────────────────────────────────────────────────────────


def _load_team_names() -> dict[int, str]:
    df = query_df("SELECT team_id, name FROM teams")
    if df.empty:
        return {}
    return dict(zip(df["team_id"].astype(int), df["name"].astype(str)))


def _load_group_teams() -> dict[str, list[tuple[int, str]]]:
    """Return {group_code: [(team_id, name), ...]} sorted by Elo DESC."""
    df = query_df("""
        SELECT t.team_id, t.name, t.group_code, COALESCE(e.elo_rating, 1500) AS elo
        FROM teams t
        LEFT JOIN (
            SELECT team_id, MAX(elo_rating) AS elo_rating
            FROM elo_history GROUP BY team_id
        ) e ON t.team_id = e.team_id
        ORDER BY t.group_code, elo DESC
    """)
    if df.empty:
        return {}
    result: dict[str, list[tuple[int, str]]] = {}
    for _, row in df.iterrows():
        gc = str(row["group_code"])
        result.setdefault(gc, []).append((int(row["team_id"]), str(row["name"])))
    return result

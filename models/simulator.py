"""
Monte Carlo bracket simulator.

simulate_tournament(n_runs) simulates n_runs full tournaments and returns
aggregate win/advance probabilities and the single most-likely bracket path.
"""
from __future__ import annotations

import json
import random
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from db.database import query_df
from models.ensemble import get_ensemble


@dataclass
class BracketResult:
    champion_probs: dict[int, float]
    finalist_probs: dict[int, float]
    most_likely_champion: int
    most_likely_runner_up: int
    n_runs: int


def simulate_tournament(n_runs: int = 10_000) -> BracketResult:
    """Run Monte Carlo simulation of remaining WC 2026 matches."""
    teams = _load_teams()
    group_standings = _compute_current_group_standings(teams)
    ensemble = get_ensemble()

    champion_counts: dict[int, int] = defaultdict(int)
    finalist_counts: dict[int, int] = defaultdict(int)

    for _ in range(n_runs):
        sim_standings = _simulate_group_stage(group_standings, teams, ensemble)
        bracket_32 = _build_r32_bracket(sim_standings)
        round_16 = _simulate_round(bracket_32, ensemble, "R32")
        quarter = _simulate_round(_pairs(round_16), ensemble, "R16")
        semi = _simulate_round(_pairs(quarter), ensemble, "Quarter-finals")
        final_pair = _pairs(semi)
        if final_pair:
            finalists = _simulate_round(final_pair, ensemble, "Semi-finals")
        else:
            finalists = semi[:2] if len(semi) >= 2 else semi

        for t in (finalists or []):
            finalist_counts[t] += 1
        champion = _simulate_one_match(finalists[0], finalists[1], ensemble, "Final") if len(finalists) >= 2 else (finalists[0] if finalists else 0)
        if champion:
            champion_counts[champion] += 1

    total = max(n_runs, 1)
    return BracketResult(
        champion_probs={t: c / total for t, c in champion_counts.items()},
        finalist_probs={t: c / total for t, c in finalist_counts.items()},
        most_likely_champion=max(champion_counts, key=champion_counts.get, default=0),
        most_likely_runner_up=_second_highest(champion_counts, finalist_counts),
        n_runs=n_runs,
    )


def _second_highest(champion_counts: dict, finalist_counts: dict) -> int:
    """Return the most likely runner-up (finalist who isn't the most likely champion)."""
    champ = max(champion_counts, key=champion_counts.get, default=0)
    runners = {t: c for t, c in finalist_counts.items() if t != champ}
    return max(runners, key=runners.get, default=0) if runners else 0


def _load_teams() -> list[dict]:
    df = query_df("SELECT team_id, name, group_code FROM teams")
    return df.to_dict("records")


def _compute_current_group_standings(teams: list[dict]) -> dict[str, list[tuple[int, int, int, int]]]:
    """Return {group_code: [(team_id, points, gd, gf), ...]} from completed matches."""
    results_df = query_df("""
        SELECT f.group_code, f.home_team_id, f.away_team_id, r.home_score, r.away_score
        FROM fixtures f
        JOIN results r ON f.fixture_id = r.fixture_id
        WHERE f.stage = 'Group Stage' AND f.group_code IS NOT NULL
    """)

    standings: dict[str, dict[int, list]] = defaultdict(lambda: defaultdict(lambda: [0, 0, 0, 0]))  # pts, gd, gf, ga

    if not results_df.empty:
        for _, row in results_df.iterrows():
            gc = str(row["group_code"])
            ht, at = int(row["home_team_id"]), int(row["away_team_id"])
            hs, as_ = int(row["home_score"]), int(row["away_score"])
            pts_h = 3 if hs > as_ else (1 if hs == as_ else 0)
            pts_a = 3 if as_ > hs else (1 if as_ == hs else 0)
            standings[gc][ht][0] += pts_h
            standings[gc][ht][1] += hs - as_
            standings[gc][ht][2] += hs
            standings[gc][at][0] += pts_a
            standings[gc][at][1] += as_ - hs
            standings[gc][at][2] += as_

    # Add teams with no results yet
    for t in teams:
        gc = t.get("group_code", "")
        if gc:
            tid = int(t["team_id"])
            if tid not in standings[gc]:
                standings[gc][tid] = [0, 0, 0, 0]

    return {
        gc: [(tid, s[0], s[1], s[2]) for tid, s in team_scores.items()]
        for gc, team_scores in standings.items()
    }


def _simulate_group_stage(
    standings: dict[str, list],
    teams: list[dict],
    ensemble,
) -> dict[str, list[tuple[int, int, int, int]]]:
    """Simulate remaining group matches and return final standings."""
    sim_standings = {gc: list(rows) for gc, rows in standings.items()}

    remaining_df = query_df("""
        SELECT f.group_code, f.home_team_id, f.away_team_id, f.fixture_id
        FROM fixtures f
        LEFT JOIN results r ON f.fixture_id = r.fixture_id
        WHERE f.stage = 'Group Stage' AND r.fixture_id IS NULL AND f.group_code IS NOT NULL
    """)

    if not remaining_df.empty:
        for _, row in remaining_df.iterrows():
            gc = str(row["group_code"])
            ht, at = int(row["home_team_id"]), int(row["away_team_id"])
            winner = _simulate_one_match(ht, at, ensemble, "Group Stage")
            hs, as_ = _sample_score(ht, at, ensemble, "Group Stage")
            # Update sim standings
            for i, (tid, pts, gd, gf) in enumerate(sim_standings[gc]):
                if tid == ht:
                    pts_h = 3 if hs > as_ else (1 if hs == as_ else 0)
                    sim_standings[gc][i] = (tid, pts + pts_h, gd + hs - as_, gf + hs)
                elif tid == at:
                    pts_a = 3 if as_ > hs else (1 if as_ == hs else 0)
                    sim_standings[gc][i] = (tid, pts + pts_a, gd + as_ - hs, gf + as_)

    return sim_standings


def _build_r32_bracket(standings: dict[str, list]) -> list[tuple[int, int]]:
    """Build R32 matchups: 1st vs 2nd from different groups + 8 best 3rd-place."""
    def _rank(group_rows: list) -> list[int]:
        return [tid for tid, _, _, _ in sorted(group_rows, key=lambda x: (-x[1], -x[2], -x[3]))]

    ranked: dict[str, list[int]] = {}
    for gc, rows in standings.items():
        ranked[gc] = _rank(rows)

    # Simplified R32: pair groups A-B, C-D, E-F, G-H, I-J, K-L (1sts vs 2nds of adjacent groups)
    group_pairs = [("A", "B"), ("C", "D"), ("E", "F"), ("G", "H"), ("I", "J"), ("K", "L")]
    matchups = []
    for g1, g2 in group_pairs:
        if g1 in ranked and g2 in ranked and len(ranked[g1]) >= 2 and len(ranked[g2]) >= 2:
            matchups.append((ranked[g1][0], ranked[g2][1]))
            matchups.append((ranked[g2][0], ranked[g1][1]))

    return matchups


def _simulate_round(matchups: list[tuple[int, int]], ensemble, stage: str) -> list[int]:
    return [_simulate_one_match(h, a, ensemble, stage) for h, a in matchups]


def _simulate_one_match(home_id: int, away_id: int, ensemble, stage: str) -> int:
    """Sample a winner using predicted probabilities."""
    try:
        result = ensemble.predict(home_id, away_id, stage)
        probs = [result.prob_home_win, result.prob_draw, result.prob_away_win]
        # In knockouts, draw leads to extra time/penalties — assign 50/50
        outcome = random.choices([0, 1, 2], weights=probs, k=1)[0]
        if outcome == 0:
            return home_id
        elif outcome == 2:
            return away_id
        else:
            return random.choice([home_id, away_id])
    except Exception:
        return random.choice([home_id, away_id])


def _sample_score(home_id: int, away_id: int, ensemble, stage: str) -> tuple[int, int]:
    try:
        result = ensemble.predict(home_id, away_id, stage)
        return result.predicted_home, result.predicted_away
    except Exception:
        return 1, 1


def _pairs(teams: list[int]) -> list[tuple[int, int]]:
    """Zip consecutive teams into match pairs."""
    return [(teams[i], teams[i + 1]) for i in range(0, len(teams) - 1, 2)]

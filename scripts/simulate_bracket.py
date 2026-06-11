"""
Resolves the WC 2026 knockout bracket from predicted group stage results,
then predicts every knockout match through to the Final.

Steps:
  1. Simulate group standings from group-stage predictions in the DB
  2. Rank all 12 third-place finishers → top 8 qualify
  3. Assign 3rd-place qualifiers to R32 slots (backtracking bipartite match)
  4. Resolve R32 → predict → determine winners
  5. Repeat for R16, QF, SF, 3rd Place, Final
  6. Write resolved team IDs to fixtures table
  7. Upsert predictions for all 32 knockout fixtures

Usage:
    python scripts/simulate_bracket.py
    python scripts/simulate_bracket.py --force
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import settings
from db.database import execute_sql, query_df
from models.ensemble import get_ensemble

# ── Bracket structure ─────────────────────────────────────────────────────────

# R32 fixed pairings: match_num → (home_slot, away_slot)
# Slot codes: "W_X" = group X winner, "R_X" = group X runner-up
_R32_FIXED: dict[int, tuple[str, str]] = {
    73: ("R_A", "R_B"),
    75: ("W_F", "R_C"),
    76: ("W_C", "R_F"),
    78: ("R_E", "R_I"),
    83: ("R_K", "R_L"),
    84: ("W_H", "R_J"),
    86: ("W_J", "R_H"),
    88: ("R_D", "R_G"),
}

# R32 matches with a 3rd-place qualifier: match_num → (group_winner_slot, eligible_groups)
_R32_THIRD: dict[int, tuple[str, frozenset]] = {
    74: ("W_E", frozenset("ABCDF")),
    77: ("W_I", frozenset("CDFGH")),
    79: ("W_A", frozenset("CEFHI")),
    80: ("W_L", frozenset("EHIJK")),
    81: ("W_D", frozenset("BEFIJ")),
    82: ("W_G", frozenset("AEHIJ")),
    85: ("W_B", frozenset("EFGIJ")),
    87: ("W_K", frozenset("DEIJL")),
}

_R16: dict[int, tuple[int, int]] = {
    89: (74, 77), 90: (73, 75), 91: (76, 78), 92: (79, 80),
    93: (83, 84), 94: (81, 82), 95: (86, 88), 96: (85, 87),
}

_QF: dict[int, tuple[int, int]] = {
    97: (89, 90), 98: (93, 94), 99: (91, 92), 100: (95, 96),
}

_SF: dict[int, tuple[int, int]] = {101: (97, 98), 102: (99, 100)}


# ── Group standings ───────────────────────────────────────────────────────────

def _compute_standings() -> dict[str, list[int]]:
    """Returns {group_code: [1st_id, 2nd_id, 3rd_id, 4th_id]}."""
    df = query_df("""
        SELECT f.group_code, f.home_team_id, f.away_team_id,
               p.predicted_home, p.predicted_away
        FROM fixtures f
        JOIN predictions p ON f.fixture_id = p.fixture_id
        WHERE f.stage = 'Group Stage' AND f.home_team_id IS NOT NULL
    """)
    elo_df = query_df(
        "SELECT team_id, elo_rating FROM elo_history WHERE reason = 'initial_seed'"
    )
    elo: dict[int, float] = {
        int(r["team_id"]): float(r["elo_rating"]) for _, r in elo_df.iterrows()
    }

    stats: dict[int, dict] = {}
    group_of: dict[int, str] = {}

    for _, r in df.iterrows():
        hid, aid = int(r["home_team_id"]), int(r["away_team_id"])
        hg, ag = int(r["predicted_home"]), int(r["predicted_away"])
        grp = r["group_code"]
        for tid in (hid, aid):
            if tid not in stats:
                stats[tid] = {"pts": 0, "gd": 0, "gf": 0}
                group_of[tid] = grp
        stats[hid]["gf"] += hg
        stats[hid]["gd"] += hg - ag
        stats[aid]["gf"] += ag
        stats[aid]["gd"] += ag - hg
        if hg > ag:
            stats[hid]["pts"] += 3
        elif ag > hg:
            stats[aid]["pts"] += 3
        else:
            stats[hid]["pts"] += 1
            stats[aid]["pts"] += 1

    groups: dict[str, list[int]] = {}
    for tid, grp in group_of.items():
        groups.setdefault(grp, []).append(tid)

    return {
        grp: sorted(
            teams,
            key=lambda t: (
                -stats[t]["pts"],
                -stats[t]["gd"],
                -stats[t]["gf"],
                -elo.get(t, 1500),
            ),
        )
        for grp, teams in sorted(groups.items())
    }


# ── 3rd-place qualifier assignment ───────────────────────────────────────────

def _assign_thirds(standings: dict[str, list[int]]) -> dict[int, int]:
    """
    Rank all 12 third-place finishers, take top 8, then use backtracking to
    assign each to exactly one eligible R32 slot.

    Returns {match_num: team_id}.
    """
    elo_df = query_df(
        "SELECT team_id, elo_rating FROM elo_history WHERE reason = 'initial_seed'"
    )
    elo: dict[int, float] = {
        int(r["team_id"]): float(r["elo_rating"]) for _, r in elo_df.iterrows()
    }

    # Reuse standing stats (pts/gd/gf computed per group)
    df = query_df("""
        SELECT f.home_team_id, f.away_team_id, p.predicted_home, p.predicted_away
        FROM fixtures f JOIN predictions p ON f.fixture_id = p.fixture_id
        WHERE f.stage = 'Group Stage' AND f.home_team_id IS NOT NULL
    """)
    stats: dict[int, dict] = {}
    for _, r in df.iterrows():
        hid, aid = int(r["home_team_id"]), int(r["away_team_id"])
        hg, ag = int(r["predicted_home"]), int(r["predicted_away"])
        for tid in (hid, aid):
            if tid not in stats:
                stats[tid] = {"pts": 0, "gd": 0, "gf": 0}
        stats[hid]["gf"] += hg
        stats[hid]["gd"] += hg - ag
        stats[aid]["gf"] += ag
        stats[aid]["gd"] += ag - hg
        if hg > ag:
            stats[hid]["pts"] += 3
        elif ag > hg:
            stats[aid]["pts"] += 3
        else:
            stats[hid]["pts"] += 1
            stats[aid]["pts"] += 1

    thirds: list[tuple[int, str]] = [(standings[g][2], g) for g in standings]
    thirds.sort(
        key=lambda x: (
            -stats[x[0]]["pts"],
            -stats[x[0]]["gd"],
            -stats[x[0]]["gf"],
            -elo.get(x[0], 1500),
        )
    )
    qualified = thirds[:8]

    # Backtracking bipartite match
    slots = list(_R32_THIRD.keys())
    assignment: dict[int, int] = {}

    def backtrack(idx: int, used: set[int]) -> bool:
        if idx == len(qualified):
            return True
        team_id, group = qualified[idx]
        for slot in slots:
            if slot not in used and group in _R32_THIRD[slot][1]:
                assignment[slot] = team_id
                used.add(slot)
                if backtrack(idx + 1, used):
                    return True
                used.discard(slot)
                del assignment[slot]
        return False

    if not backtrack(0, set()):
        raise RuntimeError("Cannot assign 3rd-place teams to R32 slots — check eligibility rules.")

    return assignment


# ── Match utilities ───────────────────────────────────────────────────────────

def _resolve_slot(slot: str, standings: dict[str, list[int]]) -> int:
    kind, grp = slot.split("_", 1)
    return standings[grp][0] if kind == "W" else standings[grp][1]


def _run_match(
    match_num: int,
    home_id: int,
    away_id: int,
    stage: str,
    ensemble,
    version: str,
    id_to_name: dict[int, str],
    winners: dict[int, int],
    losers: dict[int, int],
) -> None:
    fid = f"wc-2026-m{match_num}"
    execute_sql(
        "UPDATE fixtures SET home_team_id=?, away_team_id=? WHERE fixture_id=?",
        (home_id, away_id, fid),
    )
    result = ensemble.predict(home_id, away_id, stage)
    ph, pa = result.predicted_home, result.predicted_away
    if ph > pa:
        w, l = home_id, away_id
    elif pa > ph:
        w, l = away_id, home_id
    else:
        w, l = (home_id, away_id) if result.prob_home_win >= result.prob_away_win \
               else (away_id, home_id)
    winners[match_num] = w
    losers[match_num] = l

    execute_sql(
        """
        INSERT INTO predictions
          (fixture_id, model_version, predicted_home, predicted_away,
           prob_home_win, prob_draw, prob_away_win)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(fixture_id, model_version) DO UPDATE SET
          predicted_home=excluded.predicted_home,
          predicted_away=excluded.predicted_away,
          prob_home_win=excluded.prob_home_win,
          prob_draw=excluded.prob_draw,
          prob_away_win=excluded.prob_away_win
        """,
        (fid, version, ph, pa,
         result.prob_home_win, result.prob_draw, result.prob_away_win),
    )

    h = id_to_name.get(home_id, str(home_id))
    a = id_to_name.get(away_id, str(away_id))
    adv = id_to_name.get(w, str(w))
    print(f"  M{match_num:3d}: {h} {ph}-{pa} {a}  →  {adv}")


# ── Main ──────────────────────────────────────────────────────────────────────

def simulate() -> None:
    ensemble = get_ensemble()
    version = settings.model_version
    id_to_name: dict[int, str] = {
        int(r["team_id"]): r["name"]
        for _, r in query_df("SELECT team_id, name FROM teams").iterrows()
    }

    print("=== Bracket Simulation ===\n")

    print("[1/6] Group stage standings:")
    standings = _compute_standings()
    for grp, teams in standings.items():
        names = " → ".join(id_to_name.get(t, str(t)) for t in teams)
        print(f"  Group {grp}: {names}")

    print("\n[2/6] 3rd-place qualifier assignment:")
    thirds = _assign_thirds(standings)
    for slot, tid in sorted(thirds.items()):
        elig = " ".join(sorted(_R32_THIRD[slot][1]))
        print(f"  M{slot} (eligible {elig}): {id_to_name.get(tid, str(tid))}")

    winners: dict[int, int] = {}
    losers: dict[int, int] = {}

    def run(mnum: int, hid: int, aid: int, stage: str) -> None:
        _run_match(mnum, hid, aid, stage, ensemble, version, id_to_name, winners, losers)

    print("\n[3/6] Round of 32:")
    for mnum, (hs, as_) in sorted(_R32_FIXED.items()):
        run(mnum, _resolve_slot(hs, standings), _resolve_slot(as_, standings), "R32")
    for mnum, (ws, _) in sorted(_R32_THIRD.items()):
        run(mnum, _resolve_slot(ws, standings), thirds[mnum], "R32")

    print("\n[4/6] Round of 16:")
    for mnum, (m1, m2) in sorted(_R16.items()):
        run(mnum, winners[m1], winners[m2], "R16")

    print("\n[5/6] Quarter-finals:")
    for mnum, (m1, m2) in sorted(_QF.items()):
        run(mnum, winners[m1], winners[m2], "Quarter-finals")

    print("\n[5b] Semi-finals:")
    for mnum, (m1, m2) in sorted(_SF.items()):
        run(mnum, winners[m1], winners[m2], "Semi-finals")

    print("\n[5c] Third Place:")
    run(103, losers[101], losers[102], "Third Place")

    print("\n[6/6] Final:")
    run(104, winners[101], winners[102], "Final")

    champion = id_to_name.get(winners[104], "?")
    runner_up = id_to_name.get(losers[104], "?")
    third = id_to_name.get(winners[103], "?")
    print(f"\n{'='*40}")
    print(f"  🏆  Champion:  {champion}")
    print(f"  🥈  Runner-up: {runner_up}")
    print(f"  🥉  3rd Place: {third}")
    print(f"{'='*40}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate WC 2026 bracket")
    parser.add_argument("--force", action="store_true",
                        help="Re-simulate even if bracket already resolved")
    args = parser.parse_args()
    simulate()


if __name__ == "__main__":
    main()

"""
Computes the Group Status Vector for each team from current fixtures/results.
Returns: points, goal_differential, goals_for, goals_against, games_played,
         position_in_group, already_qualified, eliminated.
"""
from db.database import query_df

_DEFAULT = {
    "points": 0,
    "goal_differential": 0,
    "goals_for": 0,
    "goals_against": 0,
    "games_played": 0,
    "position_in_group": 4,
    "already_qualified": False,
    "eliminated": False,
}


def get_group_status(team_id: int) -> dict:
    """Return the group status dict for a single team."""
    all_status = compute_all_group_status()
    return all_status.get(team_id, {**_DEFAULT})


def compute_all_group_status() -> dict[int, dict]:
    """Return {team_id: status_dict} for all teams with played group-stage matches."""
    sql = """
        SELECT
            f.home_team_id AS team_id,
            r.home_score   AS gf,
            r.away_score   AS ga
        FROM fixtures f
        JOIN results r ON f.fixture_id = r.fixture_id
        WHERE f.stage = 'Group Stage'

        UNION ALL

        SELECT
            f.away_team_id AS team_id,
            r.away_score   AS gf,
            r.home_score   AS ga
        FROM fixtures f
        JOIN results r ON f.fixture_id = r.fixture_id
        WHERE f.stage = 'Group Stage'
    """
    df = query_df(sql)
    if df.empty:
        return {}

    records: dict[int, dict] = {}
    for _, row in df.iterrows():
        tid = int(row["team_id"])
        gf, ga = int(row["gf"]), int(row["ga"])
        pts = 3 if gf > ga else (1 if gf == ga else 0)
        if tid not in records:
            records[tid] = {**_DEFAULT}
        r = records[tid]
        r["points"] += pts
        r["goals_for"] += gf
        r["goals_against"] += ga
        r["goal_differential"] += gf - ga
        r["games_played"] += 1

    # Compute positions within each group
    groups_df = query_df(
        "SELECT team_id, group_code FROM teams WHERE group_code IS NOT NULL"
    )
    group_map: dict[int, str] = {}
    if not groups_df.empty:
        group_map = dict(zip(groups_df["team_id"].astype(int), groups_df["group_code"]))

    from collections import defaultdict
    group_teams: dict[str, list[int]] = defaultdict(list)
    for tid, gc in group_map.items():
        group_teams[gc].append(tid)

    for gc, members in group_teams.items():
        ranked = sorted(
            members,
            key=lambda t: (
                records.get(t, _DEFAULT)["points"],
                records.get(t, _DEFAULT)["goal_differential"],
                records.get(t, _DEFAULT)["goals_for"],
            ),
            reverse=True,
        )
        for pos, tid in enumerate(ranked, 1):
            if tid in records:
                records[tid]["position_in_group"] = pos
            # Top-2 qualify (simple: 3 games played and top 2 in group)
            played = records.get(tid, _DEFAULT)["games_played"]
            if played == 3:
                records.setdefault(tid, {**_DEFAULT})["already_qualified"] = pos <= 2
                records.setdefault(tid, {**_DEFAULT})["eliminated"] = pos == 4

    return records

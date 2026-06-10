"""
Bracket tree component — builds a Plotly figure showing the full
knockout path with probability-encoded colours.
"""
from __future__ import annotations

import plotly.graph_objects as go


def build_bracket_figure(
    rounds: list[list[tuple[str, float]]],
) -> go.Figure:
    """
    rounds: list of rounds, each round is [(team_name, win_prob), ...]
            ordered by predicted bracket path.
    Returns a Plotly Figure.
    """
    fig = go.Figure()
    x_spacing = 3.0
    y_spacing = 2.0

    for round_idx, round_teams in enumerate(rounds):
        x = round_idx * x_spacing
        n = len(round_teams)
        for team_idx, (team, prob) in enumerate(round_teams):
            y = team_idx * y_spacing
            color = _prob_color(prob)

            fig.add_trace(go.Scatter(
                x=[x], y=[y],
                mode="markers+text",
                marker=dict(size=18, color=color, line=dict(width=1, color="#333")),
                text=[team],
                textposition="middle right",
                hovertext=f"{team}: {prob*100:.1f}% win",
                showlegend=False,
            ))

            # Draw line to next round
            if round_idx < len(rounds) - 1:
                next_round = rounds[round_idx + 1]
                next_idx = team_idx // 2
                if next_idx < len(next_round):
                    ny = next_idx * y_spacing
                    fig.add_shape(
                        type="line",
                        x0=x, y0=y,
                        x1=x + x_spacing, y1=ny,
                        line=dict(color="#cccccc", width=max(1, int(prob * 5))),
                    )

    n_rounds = len(rounds)
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(visible=False, range=[-0.5, n_rounds * x_spacing]),
        yaxis=dict(visible=False),
        height=600,
        margin=dict(l=0, r=0, t=20, b=0),
    )
    return fig


def _prob_color(prob: float) -> str:
    if prob >= 0.7:
        return "#2ecc71"
    if prob >= 0.4:
        return "#f39c12"
    return "#e74c3c"

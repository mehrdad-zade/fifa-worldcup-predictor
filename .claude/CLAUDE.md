# FIFA World Cup 2026 Predictor — Claude Code Developer Context

## Project Purpose

Predict WC 2026 match outcomes (Win/Draw/Loss + scoreline) and simulate the full
tournament bracket using an ensemble of Dixon-Coles Poisson + XGBoost + LightGBM.
Real-time data from API-Football, FBref/Transfermarkt scrapers, and Claude API
(injury/fitness news extraction). Streamlit UI with three pages: match center,
bracket view, model analytics.

## Architecture Summary

| Module | Owns |
|--------|------|
| `config/settings.py` | All configuration via Pydantic BaseSettings — never `os.environ` directly |
| `config/teams.json` | Source of truth for 48 WC 2026 teams, groups (A–L), and cross-source IDs |
| `db/database.py` | All SQLite access — never raw `sqlite3` calls elsewhere |
| `pipeline/` | Data ingestion from all external sources |
| `features/feature_matrix.py` | Assembles the flat feature vector; owns `FEATURE_COLUMNS` |
| `models/ensemble.py` | Blends Poisson (40%) + XGBoost (30%) + LightGBM (30%) |
| `models/simulator.py` | Monte Carlo bracket simulation (10,000 runs) |
| `predictions/snapshot_writer.py` | Idempotent write to JSON snapshots + SQLite |
| `ui/data_loader.py` | All Streamlit data access with `@st.cache_data(ttl=300)` |

## Key Conventions

1. **Config**: Import `from config.settings import settings` — never `os.getenv`.
2. **Database**: Use `db.database.execute_sql()` / `query_df()` — no loose `sqlite3` calls.
3. **Streamlit data**: All page code reads from `ui/data_loader.py` — no direct DB in pages.
4. **Feature contract**: `features/feature_matrix.py` defines `FEATURE_COLUMNS`. Adding a
   feature here requires running `scripts/train_models.py` and bumping `MODEL_VERSION` in `.env`.
5. **Model artifacts**: Stored in `models/artifacts/` (gitignored). Train with `scripts/train_models.py`.
6. **Prediction snapshots**: `data/snapshots/` IS committed to git — prediction audit trail.
7. **Snapshot idempotency**: `snapshot_writer.py` upserts by `(fixture_id, model_version)` — safe to re-run.

## WC 2026 Specifics

- **48 teams**, 12 groups of 4 (A–L), top 2 per group + 8 best 3rd-place = 32 advance
- **New round**: R32 before R16 (4 extra knockout rounds vs WC 2022)
- **Neutral venues**: All matches at USA/Canada/Mexico — `is_neutral_venue = 1` always
- **Dates**: Group stage June 11 – July 2, 2026; Final July 19, 2026
- **`config/teams.json`**: Maps team name → `api_football_id`, `fbref_slug`, `transfermarkt_id`, `group`
  - Run `scripts/lookup_team_ids.py` to populate/verify `api_football_id` values from the API

## Data Freshness Policy

| Source | Refresh frequency | Cache location |
|--------|------------------|----------------|
| API-Football fixtures/standings | Once per day | `data/raw/api_football/{date}/` |
| FBref player stats | Once per day | `data/raw/fbref/{date}/` |
| Transfermarkt values | Once per day | `data/raw/transfermarkt/{date}/` |
| Claude news analysis | 6-hour TTL | SQLite `claude_news_cache` table |
| Live scores (during matches) | Every 60s | Streamlit auto-refresh |

## API Keys Required

- `API_FOOTBALL_KEY`: https://dashboard.api-football.com/ (free tier: 100 req/day)
- `ANTHROPIC_API_KEY`: https://console.anthropic.com/

## Common Development Tasks

```bash
# Populate team IDs from the API
python scripts/lookup_team_ids.py

# Seed Elo ratings from WC 2014/2018/2022 history
python scripts/backfill_elo.py

# Train models (XGBoost + LightGBM + Poisson parameters)
python scripts/train_models.py

# Evaluate against completed matches
python scripts/run_evaluation.py

# Debug ingestion without writing to DB
python -m pipeline.ingestion_runner --dry-run --verbose

# Run tests
pytest tests/ -v --cov=. --cov-report=term-missing

# Lint + type-check
ruff check . && mypy .
```

## Feature Vector (as of v1.0-boosted)

```
home_elo, away_elo, elo_diff,
home_momentum, away_momentum,
home_fitness, away_fitness,
home_strength, away_strength,
home_points, away_points, home_goal_diff, away_goal_diff,
home_position, away_position,
stage_encoded,        # group=0, R32=1, R16=2, QF=3, SF=4, F=5
is_neutral_venue      # always 1 for WC 2026
```

## Model Ensemble

- **Poisson (40%)**: Dixon-Coles bivariate Poisson. Provides the predicted scoreline.
  Parameters: attack (α_i), defense (β_i), home advantage (γ), low-score correction (ρ).
- **XGBoost (30%)**: Multiclass classifier. Optuna-tuned, 5-fold stratified CV.
- **LightGBM (30%)**: Same interface as XGBoost; tends to handle sparse features better.
- Final W/D/L probabilities = weighted blend. Scoreline always from Poisson.

## SQLite Tables

`teams`, `fixtures`, `results`, `predictions`, `elo_history`, `evaluation_log`,
`player_stats`, `player_values`, `claude_news_cache`

WAL journal mode — safe for concurrent Streamlit reads.

## Prediction JSON Schema

See `data/snapshots/` for daily files. Shape:
`{ meta: {...}, daily_predictions: [...], final_bracket_prediction: {...} }`
Bracket slots use `placeholder_home/away` before groups resolve,
`resolved_home/away` and `actual_winner` filled in as tournament progresses.

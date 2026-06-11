# FIFA World Cup 2026 Predictor

Predicts match outcomes and simulates the full tournament bracket for WC 2026 (USA/Canada/Mexico, 48 teams). Combines Dixon-Coles Poisson regression, XGBoost, and LightGBM into a blended ensemble, with real-time data from API-Football and Claude API for injury/news intelligence.

## Architecture

```
External Sources
     │
     ├── API-Football v3 ─────────┐
     ├── FBref (HTML scraper) ────►  pipeline/ingestion_runner.py
     ├── Transfermarkt (scraper) ─┘         │
     └── Claude API (news/fitness)      SQLite DB
                                            │
                                  features/feature_matrix.py
                                     (Elo · momentum · fitness · strength)
                                            │
                         ┌──────────────────┼──────────────────┐
                         ▼                  ▼                  ▼
                  Poisson model        XGBoost            LightGBM
                         └──────────────────┼──────────────────┘
                                            ▼
                                     models/ensemble.py
                                     (40% / 30% / 30%)
                                            │
                              ┌─────────────┴──────────────┐
                              ▼                            ▼
                    daily_predictor.py          bracket_predictor.py
                    (single match)              (Monte Carlo tournament)
                              │                            │
                              └─────────────┬──────────────┘
                                            ▼
                                   snapshot_writer.py
                                   (JSON + SQLite)
                                            │
                                    ui/data_loader.py
                                            │
                         ┌──────────────────┼──────────────────┐
                         ▼                  ▼                  ▼
                  match_center          bracket_view        analytics
                         └──────────────────┼──────────────────┘
                                            ▼
                                  Streamlit UI :8501
```

## Quick Start

**Prerequisites**: Python 3.11+, Git Bash (Windows) or bash (Linux/macOS).

```bash
# 1. Clone and enter the project
git clone https://github.com/mehrdad-zade/fifa-worldcup-predictor
cd fifa-worldcup-predictor

# 2. Add your API keys to .env (created automatically on first run)
# Edit .env after the first run adds API_FOOTBALL_KEY and ANTHROPIC_API_KEY

# 3. Launch everything
./run.sh          # Git Bash / Linux / macOS
# OR
./run.ps1         # Native Windows PowerShell
```

Streamlit opens at **http://localhost:8501**.

### Manual steps (if you prefer)

```bash
python -m venv .venv && source .venv/Scripts/activate  # Windows Git Bash
pip install -r requirements.txt
python scripts/init_db.py
python -m pipeline.ingestion_runner
streamlit run ui/app.py
```

## API Keys Required

| Key | Where to get it | Free tier |
|-----|----------------|-----------|
| `API_FOOTBALL_KEY` | https://dashboard.api-football.com/ | 100 req/day |
| `ANTHROPIC_API_KEY` | https://console.anthropic.com/ | Pay-per-use |

Copy `.env.example` → `.env` and fill in both keys.

## Project Structure

```
.
├── config/              # Pydantic settings, WC 2026 team metadata (teams.json)
├── db/                  # SQLite schema and connection helpers
├── pipeline/            # Data ingestion: API-Football, FBref, Transfermarkt, Claude
├── features/            # Feature engineering: Elo, momentum, fitness, squad strength
├── models/              # Poisson, XGBoost, LightGBM, ensemble, Monte Carlo simulator
├── predictions/         # Daily and bracket predictors, JSON snapshot writer
├── evaluation/          # Brier score, RPS, accuracy evaluation
├── ui/                  # Streamlit app: match center, bracket view, analytics
├── scripts/             # CLI tools: init DB, backfill Elo, train, evaluate
├── tests/               # pytest suite (HTTP mocks via responses library)
├── data/
│   ├── raw/             # Gitignored — cached API/scraper responses
│   ├── processed/       # Gitignored — computed feature matrices
│   └── snapshots/       # Committed — daily prediction JSON audit trail
└── models/artifacts/    # Gitignored — trained model files (.pkl)
```

## Feature Engineering

| Feature | Formula |
|---------|---------|
| Squad Strength Index | `mean(rating_i × fitness_i)` over top 23 players |
| Squad Fitness Score | `1 - min(1, normalized_minutes×0.4 + injuries×0.05 + suspensions×0.08)` |
| Momentum Score | `Σ multiplier_i × exp(-days_since_win_i / 180)` |
| Elo Rating | Standard Elo K=40 (competitive), K=20 (friendly), +50×multiplier trophy bonus |

Momentum multipliers: World Cup win = 3.0, Continental championship = 2.5, Nations League = 1.5, Friendly = 0.3.

## Ensemble Weights

| Model | Weight | Contribution |
|-------|--------|-------------|
| Dixon-Coles Poisson | 40% | Scoreline + W/D/L probs |
| XGBoost | 30% | W/D/L probs |
| LightGBM | 30% | W/D/L probs |

## Prediction Storage Schema

Daily snapshot files live in `data/snapshots/YYYY-MM-DD_v{VERSION}.json`:

```json
{
  "meta": {
    "simulation_date": "2026-06-10",
    "model_version": "v1.0-boosted"
  },
  "daily_predictions": [
    {
      "fixture_id": "wc-2026-m34",
      "stage": "Group Stage",
      "home_team": "Spain",
      "away_team": "Canada",
      "predicted_score": {"home": 2, "away": 0},
      "probabilities": {"home_win": 0.68, "draw": 0.20, "away_win": 0.12},
      "actual_score": null
    }
  ],
  "final_bracket_prediction": {
    "champion": "France",
    "runner_up": "Brazil",
    "tbd_knockouts": [
      {
        "match_code": "R32_1",
        "placeholder_home": "1st Group A",
        "placeholder_away": "2nd Group B",
        "resolved_home": "USA",
        "resolved_away": "Mexico",
        "predicted_winner": "USA",
        "predicted_score": {"home": 1, "away": 0},
        "actual_winner": null
      }
    ]
  }
}
```

## Evaluation Metrics

- **Brier Score** (lower = better): `(p_hw - o_hw)² + (p_d - o_d)² + (p_aw - o_aw)²`. Baseline random = 0.667, good model ≈ 0.18.
- **Ranked Probability Score (RPS)**: Accounts for ordering of outcomes; better than plain accuracy for football.
- Run `python scripts/run_evaluation.py` to print a per-stage evaluation table.

## Common Commands

```bash
# Populate team IDs in config/teams.json from the API
python scripts/lookup_team_ids.py

# Backfill Elo ratings from historical WC results
python scripts/backfill_elo.py

# Train all models (XGBoost, LightGBM, Poisson)
python scripts/train_models.py

# Evaluate model against completed matches
python scripts/run_evaluation.py

# Run tests
pytest tests/ -v --cov=. --cov-report=term-missing

# Lint + type-check
ruff check . && mypy .
```

## Known Limitations

- **API-Football free tier**: 100 requests/day. The ingestion pipeline caches daily responses to avoid exceeding this.
- **No historical odds data**: The Poisson and ensemble models are trained on match outcomes only, not market odds.
- **FBref/Transfermarkt scraping**: These sites may change their HTML structure. Scrapers may need maintenance.
- **WC 2026 bracket format**: 48 teams → 12 groups → R32 (new round!) → R16 → QF → SF → Final. The R32 format means 32 teams advance (top 2 per group + 8 best 3rd-place teams).
- **`config/teams.json` IDs**: The `api_football_id` fields are approximate placeholders. Run `python scripts/lookup_team_ids.py` to populate correct IDs before first use.
❯ - identify unnecessary or unused code and remove them
  - in the UI under "Fixtures", highlight the predicted columns on
  all tables 
  - evaluate the solution and see if we can pull free data from
  anywhere or update ai models or use different models for higher
  accuracy predictions
  - for visuals if there are any useful analysis for the user of this
  tool add them to the section under fixtures and participants
# FIFA World Cup 2026 Predictor — System Design

## Architecture Overview

```
External Sources
     │
     ├── API-Football v3 ─────────┐
     ├── FBref (HTML scraper) ────►  pipeline/ingestion_runner.py
     ├── Transfermarkt (scraper) ─┘         │
     └── Claude API (news/fitness)      SQLite DB (WAL mode)
                                            │
                                  features/feature_matrix.py
                              (Elo · Momentum · Fitness · Strength · Group Status)
                                            │
                         ┌──────────────────┼──────────────────┐
                         ▼                  ▼                  ▼
               Dixon-Coles Poisson     XGBoost (30%)     LightGBM (30%)
                    (40%)
                         └──────────────────┼──────────────────┘
                                            ▼
                                     models/ensemble.py
                                  Weighted blend → PredictionResult
                                            │
                              ┌─────────────┴──────────────┐
                              ▼                            ▼
                    daily_predictor.py          bracket_predictor.py
                    (single match W/D/L)        (Monte Carlo, 10 k runs)
                              │                            │
                              └─────────────┬──────────────┘
                                            ▼
                                   snapshot_writer.py
                                (JSON audit trail + SQLite upsert)
                                            │
                                    ui/data_loader.py
                                  (@st.cache_data, 5-min TTL)
                                            │
                     ┌──────────────────────┼────────────────────┐
                     ▼                      ▼                    ▼
             match_center.py        participants.py        analytics.py
             (Fixtures page)        (Teams/Squads)         (Model stats)
                                                           bracket_view.py
                                                           (KO bracket)
                                            ▼
                                  Streamlit UI  :8501
```

## Module Responsibilities

| Module | Owns |
|--------|------|
| `config/settings.py` | All config via Pydantic `BaseSettings` — never `os.environ` directly |
| `config/teams.json` | Source of truth: 48 WC 2026 teams, groups A–L, cross-source IDs |
| `db/database.py` | All SQLite access — `execute_sql()` / `query_df()` / `query_one()` |
| `pipeline/` | Data ingestion from all external sources |
| `features/feature_matrix.py` | Assembles the flat feature vector; owns `FEATURE_COLUMNS` |
| `models/ensemble.py` | Blends Poisson (40%) + XGBoost (30%) + LightGBM (30%) |
| `models/simulator.py` | Monte Carlo bracket simulation (10,000 runs default) |
| `predictions/snapshot_writer.py` | Idempotent write to JSON snapshots + SQLite |
| `ui/data_loader.py` | All Streamlit data access with `@st.cache_data(ttl=300)` |

---

## Data Flow

### Ingestion (once per day)
1. `pipeline/api_football.py` pulls fixtures, standings, and results from API-Football v3 (100 req/day free tier). Cached to `data/raw/api_football/{date}/`.
2. `pipeline/fbref_scraper.py` scrapes per-team player stats (goals, assists, SCA, GCA, minutes, injuries) from FBref. Rate-limited to 1 request/2 s.
3. `pipeline/transfermarkt_scraper.py` scrapes market values per player. Rate-limited to 1 request/3 s.
4. `pipeline/claude_news.py` calls the Claude API for injury/squad news; cached in `claude_news_cache` (6-hour TTL).
5. All data lands in SQLite (`data/worldcup.db`), WAL journal mode.

### Feature Engineering
`features/feature_matrix.py` assembles a 17-column vector per fixture:

| Feature | Source |
|---------|--------|
| `home_elo` / `away_elo` / `elo_diff` | `features/elo.py` → `elo_history` table |
| `home_momentum` / `away_momentum` | `features/momentum.py` → `trophy_events` table |
| `home_fitness` / `away_fitness` | `features/squad_fitness.py` → `player_stats` table |
| `home_strength` / `away_strength` | `features/squad_strength.py` → `player_stats` table |
| `home_points` / `away_points` / `home_goal_diff` / `away_goal_diff` | `features/group_status.py` → `results` table |
| `home_position` / `away_position` | `features/group_status.py` |
| `stage_encoded` | Encoded: Group=0, R32=1, R16=2, QF=3, SF=4, Final=5 |
| `is_neutral_venue` | Always 1 (all WC 2026 at USA/Canada/Mexico) |

### Model Training
```
python scripts/train_models.py
  → models/trainer.py::train_all()
    → load_historical_matches()       # pulls completed fixtures + results
    → build_feature_vector(ht, at, stage) for each row
    → XGBModel.train(X, y)            # Optuna 50-trial CV, saved as xgb_{version}.pkl
    → LGBMModel.train(X, y)           # same, saved as lgbm_{version}.pkl
    → PoissonModel.fit(raw_matches)   # Dixon-Coles MLE, saved as poisson_{version}.pkl
```
Bump `MODEL_VERSION` in `.env` after retraining.

### Prediction
```
python scripts/generate_predictions.py
  → bracket_predictor.predict_full_bracket(n_runs=10000)
    → simulate_tournament(n_runs)     # Monte Carlo → BracketResult
    → _bracket_result_to_dict()       # group matches, standings, KO bracket
  → snapshot_writer.write_snapshot()  # JSON to data/snapshots/ + SQLite upsert
```

### UI Serving
`streamlit run ui/app.py` — four pages:
- **Fixtures**: full schedule with filters, actual + predicted scores, win probability bars
- **Participants**: 48 team cards with squad, news, and tournament outlook per team
- **Analytics**: championship probabilities, bracket predictions, feature importance, accuracy
- **Bracket**: group standings + full KO bracket visualization

---

## Model Design

### Dixon-Coles Poisson (40%)
Bivariate Poisson model accounting for the non-independence of goals and low-score correction (ρ parameter).

Parameters per team: attack strength α_i, defense strength β_i. Global: home advantage γ, low-score correction ρ.

Expected goals: λ_home = α_home · β_away · γ, λ_away = α_away · β_home.

Output: full 15×15 score probability matrix → P(home_win), P(draw), P(away_win) + predicted scoreline.

### XGBoost (30%)
Multiclass classifier (home_win / draw / away_win). 5-fold stratified CV, Optuna-tuned (50 trials). Input: 17-feature vector. Output: probability triplet.

### LightGBM (30%)
Same interface as XGBoost; handles sparse features better, acts as a second gradient-boosted opinion.

### Ensemble
Final probabilities = Poisson×0.4 + XGBoost×0.3 + LightGBM×0.3. Each model degrades gracefully to uniform [1/3, 1/3, 1/3] if artifact is missing.

### Monte Carlo Bracket Simulation
10,000 independent tournament runs. Each run: simulate remaining group matches → rank groups → build R32 bracket → simulate R32→R16→QF→SF→Final. Aggregate win counts → `champion_probs`. Single most-likely path stored in snapshot.

---

## Free Data Sources Evaluation

| Source | What it provides | Rate limit | Current use | Notes |
|--------|-----------------|------------|-------------|-------|
| **API-Football v3** | Fixtures, live scores, standings, form | 100 req/day (free) | ✅ Active | Primary fixture/result source |
| **FBref** (HTML scraper) | Player stats: goals, assists, SCA, GCA, minutes | ~30 req/day safe | ✅ Active | Used for fitness + strength features |
| **Transfermarkt** (HTML scraper) | Player market values (EUR) | ~20 req/day safe | ⚠️ Scraped, not in feature vector | `player_values` table populated but unused |
| **OpenFootball** (github.com/openfootball) | Historical WC match data (CSV) | Unlimited (static) | ❌ Not used | Free historical training data for model |
| **football-data.org** | Match history, form, standings | 10 req/min (free) | ❌ Not used | More generous than API-Football |
| **World Football ELO** (eloratings.net) | Pre-computed national team Elo | Scraper | ❌ Not used | We compute our own; could cross-validate |
| **SportsDB** (thesportsdb.com) | Fixtures, events, team logos | Free tier available | ❌ Not used | Useful for team metadata/logos |
| **FIFA Rankings** (fifa.com/ranking) | Official 48-team rankings | Public (scraper) | ❌ Not used | More stable than Elo for national teams |

### Highest-value additions
1. **OpenFootball historical data** — direct import of WC 2014/2018/2022 match results as training data; replaces need to backfill Elo from scratch.
2. **football-data.org** — richer API than API-Football (form, H2H history); 10 req/min free is sufficient for daily ingestion.
3. **FIFA official rankings** — already available in `TEAM_PROFILES`; adding as a feature (`home_fifa_rank`, `away_fifa_rank`) is a quick win.
4. **Transfermarkt market values** — `player_values` table is already populated; adding `squad_market_value_eur` as a feature requires one line in `feature_matrix.py`.

---

## Model Improvement Opportunities

### Quick wins (no new data required)
| Improvement | Effort | Expected gain |
|------------|--------|---------------|
| Add FIFA rank as feature | Low — 2 features in `feature_matrix.py` | Moderate — more stable than Elo |
| Add squad market value as feature | Low — `player_values` already scraped | Moderate — correlates with talent |
| Calibration with isotonic regression | Low — post-processing step | Improves Brier score ~5–10% |
| Bayesian Elo update after each match | Medium | Better real-time ratings |

### Requires additional data
| Improvement | Data needed | Expected gain |
|------------|-------------|---------------|
| Head-to-head historical win rate | Historical H2H (OpenFootball / football-data.org) | High for evenly-matched pairs |
| Recent international form (last 10 games) | API-Football `/teams/statistics` | High — captures current momentum |
| Set-piece quality (corners, headers) | FBref advanced stats | Moderate |
| Goal distribution shape | Historical match data | Slight Poisson parameter improvement |

### Architecture-level upgrades
- **Bayesian updating** — replace static Poisson priors with posterior updates as tournament progresses; recalibrate after each matchday.
- **Neural team embeddings** — learn latent team representations from the historical matchup graph; replace handcrafted Elo/strength features with learned embeddings.
- **Conformal prediction** — wrap ensemble output in conformal intervals for calibrated uncertainty quantification.

---

## SQLite Schema (key tables)

| Table | Purpose |
|-------|---------|
| `teams` | 48 WC 2026 teams with group, confederation, external IDs |
| `fixtures` | All 104 matches with dates, venue, stage, group_code |
| `results` | Completed match scores (home_score, away_score, status) |
| `predictions` | Model outputs per fixture (score + W/D/L probs) |
| `elo_history` | Time-series of Elo ratings per team |
| `player_stats` | FBref per-player stats (goals, assists, SCA, GCA, injuries) |
| `player_values` | Transfermarkt market values per player |
| `trophy_events` | Tournament wins for momentum calculation |
| `evaluation_log` | Brier score / RPS / accuracy per evaluated fixture |
| `claude_news_cache` | Structured news/injury analysis from Claude API (6-hour TTL) |

WAL journal mode enabled — safe for concurrent Streamlit reads during live matches.

---

## WC 2026 Format Notes

- **48 teams**, 12 groups of 4 (A–L)
- **New R32 round**: top 2 per group (24 teams) + 8 best 3rd-place teams = 32 advance
- **Knockout path**: R32 → R16 → QF → SF → Final (+ Third Place)
- **All neutral venues**: `is_neutral_venue = 1` always; no home-advantage feature needed
- **Dates**: Group stage June 11 – July 2, 2026; Final July 19, 2026
- **R32 pairing**: adjacent group winners vs. runners-up (A1 v B2, B1 v A2, etc.)

---

## Known Limitations

- **API-Football free tier**: 100 req/day cap. Ingestion pipeline caches daily responses to avoid overrun; live score polling (60s TTL) counts against this.
- **No historical odds data**: Models are trained on match outcomes only; market-implied probabilities would meaningfully improve calibration.
- **FBref / Transfermarkt scraping fragility**: HTML structure changes break scrapers; needs periodic maintenance.
- **Sparse training data**: Only ~128 WC group-stage matches per tournament; ensemble relies on generalization from broader international match data.
- **`api_football_id` placeholders**: Sequential IDs in `config/teams.json` are placeholders. Run `python scripts/lookup_team_ids.py` before first data ingestion.
- **R32 3rd-place selection**: Current implementation uses predicted-standings sorted by pts/GD/GF to select best 8 third-place teams; the official WC 2026 rules use a cross-group comparison table that differs slightly.
- **No extra-time / penalty model**: Knockout draws are resolved 50/50; a dedicated AET/penalty model would improve late-round accuracy.

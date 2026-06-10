#!/usr/bin/env bash
# Bootstraps the local environment and launches all services on localhost.
# Runs the full data pipeline so Bracket View and Analytics are prefilled on
# first launch.
set -euo pipefail

VENV_DIR=".venv"
PORT="${STREAMLIT_PORT:-8501}"
ARTIFACTS_DIR="models/artifacts"

echo "======================================="
echo "  FIFA World Cup 2026 Predictor"
echo "======================================="

# ── 1. Virtual environment ──────────────────
if [ ! -d "$VENV_DIR" ]; then
    echo "[1/8] Creating virtual environment..."
    python -m venv "$VENV_DIR"
else
    echo "[1/8] Virtual environment exists — skipping."
fi

# ── 2. Activate (cross-platform) ────────────
echo "[2/8] Activating virtual environment..."
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || "$OSTYPE" == "win32" ]]; then
    source "$VENV_DIR/Scripts/activate"
else
    source "$VENV_DIR/bin/activate"
fi

# ── 3. Install dependencies ─────────────────
echo "[3/8] Installing dependencies..."
python -m pip install --upgrade pip --quiet || true
python -m pip install -r requirements.txt --quiet

# ── 4. Environment file ─────────────────────
if [ ! -f ".env" ]; then
    echo ""
    echo "  WARNING: .env not found."
    echo "  Copying .env.example → .env"
    echo "  Edit .env and add your API keys before live data will work."
    echo ""
    cp .env.example .env
fi

# ── 5. Database & data ingestion ────────────
echo "[4/8] Initialising database schema..."
python scripts/init_db.py

echo "[5/8] Running data ingestion (skips if already fresh today)..."
python -m pipeline.ingestion_runner --skip-if-fresh || true

# ── 6. Elo backfill (seeds ratings) ─────────
echo "[6/8] Backfilling Elo ratings from match history..."
python scripts/backfill_elo.py || true

# ── 7. Model training ────────────────────────
# Use 5 Optuna trials on first run (fast); skip entirely if artifacts exist.
if ls "$ARTIFACTS_DIR"/*.pkl 2>/dev/null | grep -q .; then
    echo "[7/8] Model artifacts found — skipping training."
else
    echo "[7/8] Training models (5 Optuna trials for quick startup)..."
    python scripts/train_models.py --optuna-trials 5 || true
fi

# ── 8. Predictions & evaluation ─────────────
echo "[8/8] Generating predictions and bracket simulation..."
python scripts/generate_predictions.py --skip-if-fresh --no-news --n-sims 500 || true

echo "  Running evaluation against completed matches..."
python scripts/run_evaluation.py || true

# ── Launch Streamlit ─────────────────────────
echo ""
echo "  Launching Streamlit UI → http://localhost:${PORT}"
echo "  Press Ctrl+C to stop."
echo ""
streamlit run ui/app.py \
    --server.port "$PORT" \
    --server.headless true \
    --browser.gatherUsageStats false

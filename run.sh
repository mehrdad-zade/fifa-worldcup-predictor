#!/usr/bin/env bash
# Bootstraps the local environment and launches all services on localhost.
set -euo pipefail

VENV_DIR=".venv"
PORT="${STREAMLIT_PORT:-8501}"

echo "======================================="
echo "  FIFA World Cup 2026 Predictor"
echo "======================================="

# ── 1. Virtual environment ──────────────────
if [ ! -d "$VENV_DIR" ]; then
    echo "[1/5] Creating virtual environment..."
    python -m venv "$VENV_DIR"
else
    echo "[1/5] Virtual environment exists — skipping."
fi

# ── 2. Activate (cross-platform) ────────────
echo "[2/5] Activating virtual environment..."
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || "$OSTYPE" == "win32" ]]; then
    # Git Bash / MSYS on Windows
    source "$VENV_DIR/Scripts/activate"
else
    # Linux / macOS
    source "$VENV_DIR/bin/activate"
fi

# ── 3. Install dependencies ─────────────────
echo "[3/5] Installing dependencies..."
python -m pip install --upgrade pip --quiet || true
python -m pip install -r requirements.txt --quiet

# ── 4. Environment file ─────────────────────
if [ ! -f ".env" ]; then
    echo ""
    echo "  WARNING: .env not found."
    echo "  Copying .env.example → .env"
    echo "  Edit .env and add your API keys before predictions will work."
    echo ""
    cp .env.example .env
fi

# ── 5. Database & data pipeline ─────────────
echo "[4/5] Initialising database schema..."
python scripts/init_db.py

echo "[5/5] Running data ingestion (skips if already fresh today)..."
python -m pipeline.ingestion_runner --skip-if-fresh || true

# ── 6. Launch Streamlit ─────────────────────
echo ""
echo "  Launching Streamlit UI → http://localhost:${PORT}"
echo "  Press Ctrl+C to stop."
echo ""
streamlit run ui/app.py \
    --server.port "$PORT" \
    --server.headless true \
    --browser.gatherUsageStats false

# run.ps1 — PowerShell equivalent of run.sh for native Windows (no Git Bash required).
# Runs the full data pipeline so Bracket View and Analytics are prefilled on
# first launch.
param(
    [int]$Port = 8501
)

$ErrorActionPreference = "Continue"   # don't abort on non-critical failures
$VenvDir      = ".venv"
$ArtifactsDir = "models\artifacts"

Write-Host "=======================================" -ForegroundColor Cyan
Write-Host "  FIFA World Cup 2026 Predictor" -ForegroundColor Cyan
Write-Host "=======================================" -ForegroundColor Cyan

# ── 1. Virtual environment ──────────────────
if (-not (Test-Path $VenvDir)) {
    Write-Host "[1/8] Creating virtual environment..."
    python -m venv $VenvDir
} else {
    Write-Host "[1/8] Virtual environment exists — skipping."
}

# ── 2. Activate ─────────────────────────────
Write-Host "[2/8] Activating virtual environment..."
& "$VenvDir\Scripts\Activate.ps1"

# ── 3. Install dependencies ─────────────────
Write-Host "[3/8] Installing dependencies..."
python -m pip install --upgrade pip --quiet
python -m pip install -r requirements.txt --quiet

# ── 4. Environment file ─────────────────────
if (-not (Test-Path ".env")) {
    Write-Host ""
    Write-Host "  WARNING: .env not found." -ForegroundColor Yellow
    Write-Host "  Copying .env.example -> .env" -ForegroundColor Yellow
    Write-Host "  Edit .env and add your API keys before live data will work." -ForegroundColor Yellow
    Write-Host ""
    Copy-Item ".env.example" ".env"
}

# ── 5. Database & data ingestion ────────────
Write-Host "[4/8] Initialising database schema..."
python scripts/init_db.py

Write-Host "[5/8] Running data ingestion (skips if already fresh today)..."
try { python -m pipeline.ingestion_runner --skip-if-fresh } catch { Write-Host "  Ingestion skipped or failed — continuing." -ForegroundColor Yellow }

# ── 6. Elo backfill (seeds ratings) ─────────
Write-Host "[6/8] Backfilling Elo ratings from match history..."
try { python scripts/backfill_elo.py } catch { Write-Host "  Elo backfill skipped or failed — continuing." -ForegroundColor Yellow }

# ── 7. Model training ────────────────────────
# Use 5 Optuna trials on first run (fast); skip entirely if artifacts exist.
$HasArtifacts = (Test-Path $ArtifactsDir) -and ((Get-ChildItem "$ArtifactsDir\*.pkl" -ErrorAction SilentlyContinue).Count -gt 0)
if ($HasArtifacts) {
    Write-Host "[7/8] Model artifacts found — skipping training."
} else {
    Write-Host "[7/8] Training models (5 Optuna trials for quick startup)..."
    try { python scripts/train_models.py --optuna-trials 5 } catch { Write-Host "  Training failed — predictions will use fallback uniform probabilities." -ForegroundColor Yellow }
}

# ── 8. Predictions & evaluation ─────────────
Write-Host "[8/8] Generating predictions and bracket simulation..."
try { python scripts/generate_predictions.py --skip-if-fresh --no-news --n-sims 500 } catch { Write-Host "  Predictions skipped or failed — continuing." -ForegroundColor Yellow }

Write-Host "  Running evaluation against completed matches..."
try { python scripts/run_evaluation.py } catch { Write-Host "  Evaluation skipped or failed — continuing." -ForegroundColor Yellow }

# ── Launch Streamlit ─────────────────────────
Write-Host ""
Write-Host "  Launching Streamlit UI -> http://localhost:$Port" -ForegroundColor Green
Write-Host "  Press Ctrl+C to stop." -ForegroundColor Green
Write-Host ""
streamlit run ui/app.py `
    --server.port $Port `
    --server.headless true `
    --browser.gatherUsageStats false

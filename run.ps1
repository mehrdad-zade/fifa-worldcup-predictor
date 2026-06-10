# run.ps1 — PowerShell equivalent of run.sh for native Windows (no Git Bash required).
param(
    [int]$Port = 8501
)

$ErrorActionPreference = "Stop"
$VenvDir = ".venv"

Write-Host "=======================================" -ForegroundColor Cyan
Write-Host "  FIFA World Cup 2026 Predictor" -ForegroundColor Cyan
Write-Host "=======================================" -ForegroundColor Cyan

# ── 1. Virtual environment ──────────────────
if (-not (Test-Path $VenvDir)) {
    Write-Host "[1/5] Creating virtual environment..."
    python -m venv $VenvDir
} else {
    Write-Host "[1/5] Virtual environment exists — skipping."
}

# ── 2. Activate ─────────────────────────────
Write-Host "[2/5] Activating virtual environment..."
& "$VenvDir\Scripts\Activate.ps1"

# ── 3. Install dependencies ─────────────────
Write-Host "[3/5] Installing dependencies..."
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet

# ── 4. Environment file ─────────────────────
if (-not (Test-Path ".env")) {
    Write-Host ""
    Write-Host "  WARNING: .env not found." -ForegroundColor Yellow
    Write-Host "  Copying .env.example -> .env" -ForegroundColor Yellow
    Write-Host "  Edit .env and add your API keys before predictions will work." -ForegroundColor Yellow
    Write-Host ""
    Copy-Item ".env.example" ".env"
}

# ── 5. Database & data pipeline ─────────────
Write-Host "[4/5] Initialising database schema..."
python scripts/init_db.py

Write-Host "[5/5] Running data ingestion (skips if already fresh today)..."
try { python -m pipeline.ingestion_runner --skip-if-fresh } catch { Write-Host "Ingestion skipped or failed — continuing." -ForegroundColor Yellow }

# ── 6. Launch Streamlit ─────────────────────
Write-Host ""
Write-Host "  Launching Streamlit UI -> http://localhost:$Port" -ForegroundColor Green
Write-Host "  Press Ctrl+C to stop." -ForegroundColor Green
Write-Host ""
streamlit run ui/app.py `
    --server.port $Port `
    --server.headless true `
    --browser.gatherUsageStats false

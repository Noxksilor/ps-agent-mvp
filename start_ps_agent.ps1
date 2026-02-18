#Requires -Version 5.1
<#
.SYNOPSIS
    One-click launcher for the ps-agent-mvp stack.

.DESCRIPTION
    1. Checks if Docker Desktop is running; starts it if not.
    2. Waits until the Docker daemon is ready.
    3. Runs  docker compose up -d  to start n8n.
    4. Waits until n8n is reachable at http://localhost:5678.
    5. (Optional) Activates a specific n8n workflow via the REST API.
    6. Opens http://localhost:5678 in the default browser.

.NOTES
    Run from the project root:
        .\start_ps_agent.ps1

    No admin rights required (Docker Desktop runs as the current user).
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── Configuration ────────────────────────────────────────────────────────────

# Possible Docker Desktop executable paths (tried in order)
$DockerDesktopPaths = @(
    "C:\Program Files\Docker\Docker\Docker Desktop.exe",
    "$env:LOCALAPPDATA\Docker\Docker Desktop.exe",
    "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
)

$DockerStartTimeoutSeconds  = 120   # max wait for Docker daemon to become ready
$N8nStartTimeoutSeconds     = 90    # max wait for n8n HTTP endpoint
$N8nUrl                     = "http://localhost:5678"
$N8nHealthUrl               = "http://localhost:5678/healthz"

# Optional: set this to your workflow ID to auto-activate it on startup.
# Leave empty ("") to skip workflow activation.
# How to find the ID: open n8n → open the workflow → copy the ID from the URL
#   e.g. http://localhost:5678/workflow/abc123  →  WorkflowId = "abc123"
$WorkflowId = ""

# ── Helpers ──────────────────────────────────────────────────────────────────

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host ">>> $Message" -ForegroundColor Cyan
}

function Write-OK {
    param([string]$Message)
    Write-Host "    [OK] $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host "    [WARN] $Message" -ForegroundColor Yellow
}

function Write-Fail {
    param([string]$Message)
    Write-Host ""
    Write-Host "    [FAIL] $Message" -ForegroundColor Red
}

function Test-DockerReady {
    try {
        $result = & docker info 2>&1
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

function Wait-DockerReady {
    param([int]$TimeoutSeconds)
    Write-Host "    Waiting for Docker daemon (up to ${TimeoutSeconds}s)..." -NoNewline
    $t0 = [System.Diagnostics.Stopwatch]::StartNew()
    while ($t0.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
        if (Test-DockerReady) {
            Write-Host " ready! ($([int]$t0.Elapsed.TotalSeconds)s)" -ForegroundColor Green
            return $true
        }
        Write-Host "." -NoNewline
        Start-Sleep -Seconds 3
    }
    Write-Host " TIMEOUT" -ForegroundColor Red
    return $false
}

function Wait-N8nReady {
    param([int]$TimeoutSeconds)
    Write-Host "    Waiting for n8n at $N8nUrl (up to ${TimeoutSeconds}s)..." -NoNewline
    $t0 = [System.Diagnostics.Stopwatch]::StartNew()
    while ($t0.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
        try {
            $resp = Invoke-WebRequest -Uri $N8nHealthUrl -UseBasicParsing `
                                      -TimeoutSec 3 -ErrorAction SilentlyContinue
            if ($resp.StatusCode -lt 400) {
                Write-Host " ready! ($([int]$t0.Elapsed.TotalSeconds)s)" -ForegroundColor Green
                return $true
            }
        } catch {
            # Not ready yet — keep polling
        }
        # Also try the root URL as fallback (some n8n versions don't have /healthz)
        try {
            $resp2 = Invoke-WebRequest -Uri $N8nUrl -UseBasicParsing `
                                       -TimeoutSec 3 -ErrorAction SilentlyContinue
            if ($resp2.StatusCode -lt 400) {
                Write-Host " ready! ($([int]$t0.Elapsed.TotalSeconds)s)" -ForegroundColor Green
                return $true
            }
        } catch {
            # Not ready yet
        }
        Write-Host "." -NoNewline
        Start-Sleep -Seconds 3
    }
    Write-Host " TIMEOUT" -ForegroundColor Red
    return $false
}

function Enable-N8nWorkflow {
    param([string]$Id)
    Write-Host "    Activating workflow ID: $Id ..."
    try {
        $body = '{"active":true}'
        $resp = Invoke-RestMethod `
            -Uri "$N8nUrl/api/v1/workflows/$Id" `
            -Method PATCH `
            -ContentType "application/json" `
            -Body $body `
            -ErrorAction Stop
        Write-OK "Workflow $Id activated."
    } catch {
        Write-Warn "Could not activate workflow $Id : $_"
        Write-Warn "You can activate it manually in the n8n UI."
    }
}

# ── Main ─────────────────────────────────────────────────────────────────────

Write-Host ""
Write-Host "============================================================" -ForegroundColor White
Write-Host "  ps-agent-mvp  —  One-click stack launcher" -ForegroundColor White
Write-Host "============================================================" -ForegroundColor White

# Change to the script's own directory so docker compose finds docker-compose.yml
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir
Write-Host "    Working directory: $ScriptDir"

# ── Step 1: Check / start Docker Desktop ─────────────────────────────────────
Write-Step "Step 1: Docker Desktop"

if (Test-DockerReady) {
    Write-OK "Docker daemon is already running."
} else {
    Write-Host "    Docker daemon not running. Attempting to start Docker Desktop..."

    $dockerExe = $null
    foreach ($path in $DockerDesktopPaths) {
        if (Test-Path $path) {
            $dockerExe = $path
            break
        }
    }

    if ($null -eq $dockerExe) {
        Write-Fail "Docker Desktop executable not found in any of these paths:"
        foreach ($p in $DockerDesktopPaths) { Write-Host "      $p" }
        Write-Host ""
        Write-Host "  Please start Docker Desktop manually, then re-run this script." -ForegroundColor Yellow
        exit 1
    }

    Write-Host "    Starting: $dockerExe"
    try {
        Start-Process -FilePath $dockerExe -WindowStyle Minimized
    } catch {
        Write-Fail "Failed to start Docker Desktop: $_"
        Write-Host "  Please start Docker Desktop manually, then re-run this script." -ForegroundColor Yellow
        exit 1
    }

    # Wait for Docker daemon to become ready
    if (-not (Wait-DockerReady -TimeoutSeconds $DockerStartTimeoutSeconds)) {
        Write-Fail "Docker daemon did not become ready within ${DockerStartTimeoutSeconds}s."
        Write-Host ""
        Write-Host "  Suggestions:" -ForegroundColor Yellow
        Write-Host "    1. Open Docker Desktop manually and wait for it to finish starting." -ForegroundColor Yellow
        Write-Host "    2. Check Docker Desktop for error messages (whale icon in system tray)." -ForegroundColor Yellow
        Write-Host "    3. Re-run this script once Docker is running." -ForegroundColor Yellow
        exit 1
    }
}

# ── Step 2: docker compose up -d ─────────────────────────────────────────────
Write-Step "Step 2: Starting n8n via docker compose"

if (-not (Test-Path "docker-compose.yml")) {
    Write-Fail "docker-compose.yml not found in $ScriptDir"
    exit 1
}

try {
    Write-Host "    Running: docker compose up -d"
    $composeOutput = & docker compose up -d 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "docker compose up -d failed (exit code $LASTEXITCODE):"
        Write-Host $composeOutput -ForegroundColor Red
        Write-Host ""
        Write-Host "  Suggestions:" -ForegroundColor Yellow
        Write-Host "    1. Run 'docker compose up' (without -d) to see full error output." -ForegroundColor Yellow
        Write-Host "    2. Check that port 5678 is not already in use." -ForegroundColor Yellow
        exit 1
    }
    Write-OK "docker compose up -d succeeded."
    Write-Host $composeOutput
} catch {
    Write-Fail "docker compose command failed: $_"
    exit 1
}

# ── Step 3: Wait for n8n ─────────────────────────────────────────────────────
Write-Step "Step 3: Waiting for n8n to be ready"

if (-not (Wait-N8nReady -TimeoutSeconds $N8nStartTimeoutSeconds)) {
    Write-Fail "n8n did not become reachable at $N8nUrl within ${N8nStartTimeoutSeconds}s."
    Write-Host ""
    Write-Host "  Suggestions:" -ForegroundColor Yellow
    Write-Host "    1. Check container logs:  docker compose logs n8n" -ForegroundColor Yellow
    Write-Host "    2. Verify port 5678 is not blocked by a firewall." -ForegroundColor Yellow
    Write-Host "    3. Try opening $N8nUrl in your browser manually." -ForegroundColor Yellow
    exit 1
}

# ── Step 4 (optional): Activate workflow ─────────────────────────────────────
if ($WorkflowId -ne "") {
    Write-Step "Step 4: Activating n8n workflow"
    Enable-N8nWorkflow -Id $WorkflowId
} else {
    Write-Host ""
    Write-Host "    (Workflow activation skipped — WorkflowId not set in script)" -ForegroundColor DarkGray
    Write-Host "    To auto-activate a workflow, edit start_ps_agent.ps1 and set:" -ForegroundColor DarkGray
    Write-Host '      $WorkflowId = "your-workflow-id"' -ForegroundColor DarkGray
}

# ── Step 5: Open browser ──────────────────────────────────────────────────────
Write-Step "Step 5: Opening browser"
try {
    Start-Process $N8nUrl
    Write-OK "Browser opened: $N8nUrl"
} catch {
    Write-Warn "Could not open browser automatically. Open manually: $N8nUrl"
}

# ── Done ──────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  ps-agent-mvp stack is UP." -ForegroundColor Green
Write-Host "  Open: $N8nUrl" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""

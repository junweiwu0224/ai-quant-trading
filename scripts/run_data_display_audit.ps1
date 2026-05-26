param(
  [int]$Port = 8001,
  [switch]$SkipBrowser,
  [int]$BrowserTimeoutSeconds = 180
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$ReportDir = Join-Path $Root "test-results\data-display-audit"
New-Item -ItemType Directory -Force -Path $ReportDir | Out-Null

function Read-JsonReport {
  param([string]$Path)
  if (Test-Path -LiteralPath $Path) {
    return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
  }
  return $null
}

function Wait-Dashboard {
  param([int]$Port)
  for ($i = 0; $i -lt 80; $i++) {
    try {
      $response = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/" -UseBasicParsing -TimeoutSec 2
      if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
        return $true
      }
    } catch {
      Start-Sleep -Milliseconds 500
    }
  }
  return $false
}

function Get-DescendantProcessIds {
  param([int]$RootProcessId)

  $all = @(Get-CimInstance Win32_Process)
  $frontier = @($RootProcessId)
  $descendants = @()

  while ($frontier.Count -gt 0) {
    $children = @($all | Where-Object { $frontier -contains $_.ParentProcessId })
    if ($children.Count -eq 0) {
      break
    }
    $childIds = @($children | ForEach-Object { [int]$_.ProcessId })
    $descendants += $childIds
    $frontier = $childIds
  }

  return $descendants
}

function Stop-ProcessTree {
  param([int]$RootProcessId)

  $ids = @(Get-DescendantProcessIds -RootProcessId $RootProcessId)
  [array]::Reverse($ids)
  foreach ($id in $ids) {
    Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
  }
  Stop-Process -Id $RootProcessId -Force -ErrorAction SilentlyContinue
}

function Invoke-BrowserAudit {
  param(
    [int]$Port,
    [int]$TimeoutSeconds
  )

  $browserLog = Join-Path $ReportDir "browser-audit.log"
  $browserErr = Join-Path $ReportDir "browser-audit.err.log"
  $node = (Get-Command node -ErrorAction Stop).Source
  $playwrightCli = Join-Path $Root "node_modules\@playwright\test\cli.js"
  if (-not (Test-Path -LiteralPath $playwrightCli)) {
    throw "Missing Playwright CLI at $playwrightCli. Run npm install first."
  }
  $env:PLAYWRIGHT_BASE_URL = "http://127.0.0.1:$Port"

  $process = Start-Process -FilePath $node `
    -ArgumentList @(
      $playwrightCli,
      "test",
      "--config=playwright.config.cjs",
      "--output=test-results/playwright-data-health",
      "tests/e2e/data-display-health.spec.cjs"
    ) `
    -WorkingDirectory $Root `
    -RedirectStandardOutput $browserLog `
    -RedirectStandardError $browserErr `
    -WindowStyle Hidden `
    -PassThru

  if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
    Stop-ProcessTree -RootProcessId $process.Id
    return @{
      ok = $false
      timedOut = $true
      exitCode = $null
      message = "Browser audit timed out after $TimeoutSeconds seconds"
      log = $browserLog
      errorLog = $browserErr
    }
  }

  $process.Refresh()
  $exitCode = $process.ExitCode
  if ($null -eq $exitCode) {
    $reportPath = Join-Path $ReportDir "browser-report.json"
    $report = Read-JsonReport -Path $reportPath
    if ($report -and -not $report.runError -and @($report.hardFindings).Count -eq 0) {
      $exitCode = 0
    } else {
      $exitCode = 1
    }
  }

  return @{
    ok = ($exitCode -eq 0)
    timedOut = $false
    exitCode = $exitCode
    message = "Browser audit exited with code $exitCode"
    log = $browserLog
    errorLog = $browserErr
  }
}

function Write-Summary {
  param(
    [object]$Api,
    [object]$Static,
    [object]$Browser,
    [object]$BrowserStatus
  )

  $lines = @()
  $lines += "# Data Display Audit Summary"
  $lines += ""
  $lines += "- Generated at: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
  if ($Api) {
    $lines += "- API endpoints scanned: $($Api.total_endpoints)"
    $lines += "- API failed endpoints: $($Api.failed_endpoint_count)"
    $lines += "- API hard findings: $($Api.hard_finding_count)"
  } else {
    $lines += "- API scan: report missing"
  }
  if ($Static) {
    $lines += "- Frontend static risks: $($Static.risk_count)"
  } else {
    $lines += "- Frontend static scan: report missing"
  }

  if ($Browser) {
    $consoleCount = @($Browser.consoleErrors).Count
    $requestCount = @($Browser.failedRequests).Count
    $panelHardCount = @($Browser.panels | ForEach-Object { $_.hardMatches } | Where-Object { $_ }).Count
    $stockHardCount = @($Browser.stockDetail.hardMatches).Count
    $lines += "- Browser console errors/warnings: $consoleCount"
    $lines += "- Browser failed requests: $requestCount"
    $lines += "- Browser hard text findings: $($panelHardCount + $stockHardCount)"
  } elseif ($SkipBrowser) {
    $lines += "- Browser audit: skipped"
  } else {
    $message = if ($BrowserStatus) { $BrowserStatus.message } else { "report missing" }
    $lines += "- Browser audit: $message"
  }

  if ($BrowserStatus -and -not $SkipBrowser) {
    $lines += "- Browser audit logs: browser-audit.log / browser-audit.err.log"
  }

  $lines += ""
  $lines += "## Report Files"
  if ($Api) { $lines += "- api-report.json" }
  if ($Static) { $lines += "- frontend-static-report.json" }
  if ($Browser) { $lines += "- browser-report.json" }

  $summaryPath = Join-Path $ReportDir "summary.md"
  $lines | Set-Content -LiteralPath $summaryPath -Encoding UTF8
  Write-Host "Data display audit summary written to $summaryPath"
}

Push-Location $Root
try {
  $apiPath = Join-Path $ReportDir "api-report.json"
  $staticPath = Join-Path $ReportDir "frontend-static-report.json"
  $browserPath = Join-Path $ReportDir "browser-report.json"

  python scripts/dashboard_data_health.py --output $apiPath
  python scripts/frontend_data_render_audit.py --output $staticPath

  $server = $null
  $browserStatus = $null
  try {
    if (-not $SkipBrowser) {
      if (Test-Path -LiteralPath $browserPath) {
        Remove-Item -LiteralPath $browserPath -Force
      }

      $serverLog = Join-Path $ReportDir "dashboard-server.log"
      $serverErr = Join-Path $ReportDir "dashboard-server.err.log"
      $server = Start-Process -FilePath "python" `
        -ArgumentList @("scripts/run_dashboard.py", "--host", "127.0.0.1", "--port", "$Port", "--no-qlib") `
        -WorkingDirectory $Root `
        -RedirectStandardOutput $serverLog `
        -RedirectStandardError $serverErr `
        -WindowStyle Hidden `
        -PassThru

      if (-not (Wait-Dashboard -Port $Port)) {
        throw "Dashboard did not become ready on http://127.0.0.1:$Port/"
      }

      $browserStatus = Invoke-BrowserAudit -Port $Port -TimeoutSeconds $BrowserTimeoutSeconds
    }
  } catch {
    $browserStatus = @{
      ok = $false
      timedOut = $false
      exitCode = $null
      message = $_.Exception.Message
      log = Join-Path $ReportDir "browser-audit.log"
      errorLog = Join-Path $ReportDir "browser-audit.err.log"
    }
  } finally {
    if ($server -and -not $server.HasExited) {
      Stop-Process -Id $server.Id -Force
    }
  }

  $api = Read-JsonReport -Path $apiPath
  $static = Read-JsonReport -Path $staticPath
  $browser = if ($SkipBrowser) { $null } else { Read-JsonReport -Path $browserPath }
  Write-Summary -Api $api -Static $static -Browser $browser -BrowserStatus $browserStatus

  if ($browserStatus -and -not $browserStatus.ok) {
    throw $browserStatus.message
  }
} finally {
  Pop-Location
}

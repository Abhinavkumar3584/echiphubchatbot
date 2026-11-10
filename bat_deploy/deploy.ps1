# Sends the chatbot from this laptop to the AWS server and restarts it.
#   First time (code + knowledge database + AI models):   .\bat_deploy\deploy.bat -Full
#   After code changes (fast, code only):                 .\bat_deploy\deploy.bat
#   After you re-ran 1-extract / 2-load (new knowledge):  .\bat_deploy\deploy.bat -Full
param(
    [switch]$Full,
    [string]$SiteUrl = "http://13.235.238.82",
    [string]$Server  = "ubuntu@13.235.238.82",
    [string]$KeyPath = ""
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Fail($msg) { Write-Host "`nERROR: $msg" -ForegroundColor Red; exit 1 }
function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }

if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) { Fail "ssh is not installed. Windows Settings > Apps > Optional features > add 'OpenSSH Client'." }
if (-not (Get-Command tar -ErrorAction SilentlyContinue)) { Fail "tar is not available (needs Windows 10 1803 or newer)." }
if (-not (Test-Path ".env")) { Fail ".env file not found in $Root" }

# ------------------------------------------------------------ the key file
Step "Preparing the key file"
$SafeKey = Join-Path $HOME ".ssh\wordpress-test.pem"
if (-not (Test-Path $SafeKey)) {
    $candidates = @($KeyPath, (Join-Path $Root "wordpress-test.pem"), (Join-Path $HOME "Downloads\wordpress-test.pem"), (Join-Path $HOME "Desktop\wordpress-test.pem")) | Where-Object { $_ -and (Test-Path $_) }
    if (-not $candidates) { Fail "wordpress-test.pem not found. Copy it into $Root and run again." }
    New-Item -ItemType Directory -Force (Join-Path $HOME ".ssh") | Out-Null
    Copy-Item $candidates[0] $SafeKey
    # Windows version of 'chmod 400': only you can read the key
    icacls $SafeKey /inheritance:r | Out-Null
    icacls $SafeKey /grant:r "$(whoami):R" | Out-Null
}
Write-Host "Key: $SafeKey"
$SshOpts = @("-i", $SafeKey, "-o", "StrictHostKeyChecking=accept-new", "-o", "ServerAliveInterval=30")

# ------------------------------------------------------------ pack
Step ("Packing the project" + $(if ($Full) { " (code + database + models, ~80 MB)" } else { " (code only)" }))
$Pack = Join-Path $env:TEMP "chatbot-upload.tar.gz"
if (Test-Path $Pack) { Remove-Item $Pack -Force }
$items = @(Get-ChildItem -File -Filter *.py | ForEach-Object Name) + @("requirements.txt", ".env", "static", "bat_deploy")
if ($Full) { $items += @("data/qdrant", "data/models", "data/index_meta.json") | Where-Object { Test-Path $_ } }
tar -czf $Pack --exclude "__pycache__" --exclude "*.pyc" --exclude ".lock" --exclude ".locks" --exclude "*.pem" @items
if ($LASTEXITCODE -ne 0) { Fail "Packing failed. If the bot is running on this laptop (3-start.bat), close it and try again." }
Write-Host ("Size: {0:N1} MB" -f ((Get-Item $Pack).Length / 1MB))

# ------------------------------------------------------------ upload
Step "Uploading to $Server"
scp @SshOpts $Pack "${Server}:/tmp/chatbot-upload.tar.gz"
if ($LASTEXITCODE -ne 0) { Fail "Upload failed. Check internet / VPN and that the server is on." }

# ------------------------------------------------------------ install + restart on the server
Step "Installing and restarting on the server"
$remote = "rm -rf /tmp/chatbot-new && mkdir -p /tmp/chatbot-new && tar -xzf /tmp/chatbot-upload.tar.gz -C /tmp/chatbot-new 2>/dev/null; sed -i 's/\r`$//' /tmp/chatbot-new/deploy/server-setup.sh && sudo bash /tmp/chatbot-new/deploy/server-setup.sh '$SiteUrl'"
ssh @SshOpts $Server $remote
if ($LASTEXITCODE -ne 0) { Fail "Something failed on the server - copy the text above and send it to Claude." }

Step "Finished. Test in the browser:  $SiteUrl/chatbot/"
Write-Host "WordPress footer code:" -ForegroundColor Green
Write-Host "<script src=`"$SiteUrl/chatbot/static/widget.js`" data-api=`"$SiteUrl/chatbot`" defer></script>"

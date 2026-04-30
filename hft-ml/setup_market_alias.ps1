# Setup PowerShell alias for market command
# Run this script once in PowerShell

$profileLine = "`nfunction market { V:\quant_project\hft-ml\market.bat @args }"

# Create profile if it doesn't exist
if (-not (Test-Path $PROFILE)) {
    New-Item -ItemType File -Path $PROFILE -Force
    Write-Host "✓ Created PowerShell profile"
}

# Add market function if not already there
$profileContent = Get-Content $PROFILE -Raw
if ($profileContent -notmatch "function market") {
    Add-Content -Path $PROFILE -Value $profileLine
    Write-Host "✓ Added 'market' command to PowerShell profile"
} else {
    Write-Host "✓ 'market' command already exists in profile"
}

# Also add to current session
function market { V:\quant_project\hft-ml\market.bat @args }
Write-Host "✓ 'market' command active in current session"
Write-Host ""
Write-Host "🚀 You can now type 'market' anywhere in PowerShell!"
Write-Host ""

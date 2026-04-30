# PowerShell Setup Script - Full Authentication System
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Setting up HFT Terminal Auth System" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Create directories
$launcherDir = "$env:USERPROFILE\bin"
$dataDir = "$env:USERPROFILE\.hft-terminal"

if (-not (Test-Path $launcherDir)) {
    New-Item -ItemType Directory -Path $launcherDir -Force | Out-Null
}
if (-not (Test-Path $dataDir)) {
    New-Item -ItemType Directory -Path $dataDir -Force | Out-Null
}

# Add to user PATH if not already there
$userPath = [Environment]::GetEnvironmentVariable("PATH", "User")
if ($userPath -notlike "*$launcherDir*") {
    [Environment]::SetEnvironmentVariable("PATH", "$userPath;$launcherDir", "User")
    Write-Host "[+] Added $launcherDir to your PATH" -ForegroundColor Green
}

# Create user database
$dbPath = Join-Path $dataDir "users.json"
$initialUsers = @(
    @{
        username = "vishwas"
        password = "20065"
        role = "admin"
        created = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
        lastLogin = ""
    }
)
$initialUsers | ConvertTo-Json | Set-Content -Path $dbPath -Encoding UTF8
Write-Host "[+] Created user database at: $dbPath" -ForegroundColor Green

# Create the main launcher script
$launcherPath = Join-Path $launcherDir "market.ps1"
$launcherContent = @'
param(
    [string]$arg1
)

$ErrorActionPreference = "SilentlyContinue"

# Paths
$DataDir = "$env:USERPROFILE\.hft-terminal"
$DbPath = Join-Path $DataDir "users.json"
$LogPath = Join-Path $DataDir "access.log"

# ============================================================
# AUTHENTICATION FUNCTIONS
# ============================================================

function Get-Users {
    if (Test-Path $DbPath) {
        return Get-Content -Path $DbPath -Raw | ConvertFrom-Json
    }
    return @()
}

function Save-Users {
    param($users)
    $users | ConvertTo-Json -Depth 3 | Set-Content -Path $DbPath -Encoding UTF8
}

function Log-Access {
    param($username, $action, $success)
    $logEntry = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') | $username | $action | $(if($success){'SUCCESS'}else{'FAILED'})"
    Add-Content -Path $LogPath -Value $logEntry -Encoding UTF8
}

function Show-LoginScreen {
    Clear-Host
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "           HFT TERMINAL TRADING DASHBOARD" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "   Please login to continue." -ForegroundColor White
    Write-Host ""
    Write-Host "   [1] Login" -ForegroundColor Green
    Write-Host "   [2] Register New Account" -ForegroundColor Yellow
    Write-Host "   [3] Exit" -ForegroundColor Red
    Write-Host ""
    
    $choice = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    return $choice.Character
}

function Do-Login {
    Clear-Host
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "           USER LOGIN" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    
    Write-Host "Username: " -ForegroundColor Green -NoNewline
    $username = Read-Host
    
    # Use Read-Host with masking for password
    Write-Host "Password: " -ForegroundColor Green -NoNewline
    $password = Read-Host -AsSecureString
    $BSTR = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($password)
    $plainPassword = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($BSTR)
    
    $users = Get-Users
    $user = $users | Where-Object { $_.username -eq $username -and $_.password -eq $plainPassword }
    
    if ($user) {
        Write-Host ""
        Write-Host "========================================" -ForegroundColor Green
        Write-Host "  LOGIN SUCCESSFUL: $username" -ForegroundColor Green
        if ($user.role -eq "admin") {
            Write-Host "  Role: Administrator" -ForegroundColor Yellow
        }
        Write-Host "========================================" -ForegroundColor Green
        Write-Host ""
        
        # Update last login
        $user.lastLogin = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
        Save-Users $users
        Log-Access $username "LOGIN" $true
        
        Write-Host "[*] Launching HFT Terminal Dashboard..." -ForegroundColor Cyan
        Start-Sleep -Seconds 1
        Set-Location V:\quant_project\hft-ml
        python terminal_dashboard.py
    } else {
        Write-Host ""
        Write-Host "ACCESS DENIED: Invalid username or password." -ForegroundColor Red
        Log-Access $username "LOGIN" $false
        Start-Sleep -Seconds 2
    }
}

function Do-Register {
    Clear-Host
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "        REGISTER NEW ACCOUNT" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    
    Write-Host "Choose a username: " -ForegroundColor Green -NoNewline
    $newUsername = Read-Host
    
    if ([string]::IsNullOrWhiteSpace($newUsername)) {
        Write-Host "[!] Username cannot be empty." -ForegroundColor Red
        Start-Sleep -Seconds 2
        return
    }
    
    $users = Get-Users
    $existing = $users | Where-Object { $_.username -eq $newUsername }
    
    if ($existing) {
        Write-Host "[!] Username '$newUsername' is already taken." -ForegroundColor Red
        Start-Sleep -Seconds 2
        return
    }
    
    Write-Host "Choose a password: " -ForegroundColor Green -NoNewline
    $newPassword = Read-Host -AsSecureString
    $BSTR = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($newPassword)
    $plainPassword = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($BSTR)
    
    if ($plainPassword.Length -lt 4) {
        Write-Host "[!] Password must be at least 4 characters." -ForegroundColor Red
        Start-Sleep -Seconds 2
        return
    }
    
    # Create new user
    $newUser = @{
        username = $newUsername
        password = $plainPassword
        role = "user"
        created = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
        lastLogin = ""
    }
    
    $users += $newUser
    Save-Users $users
    
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "  ACCOUNT CREATED SUCCESSFULLY!" -ForegroundColor Green
    Write-Host "  Username: $newUsername" -ForegroundColor White
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "[*] You can now login with your credentials." -ForegroundColor Cyan
    Log-Access $newUsername "REGISTER" $true
    Start-Sleep -Seconds 2
}

function Show-AdminPanel {
    # Check if current user is admin (passed from initial login)
    param($currentUser)
    
    if ($currentUser.role -ne "admin") {
        Write-Host "[!] Access Denied: Admin privileges required." -ForegroundColor Red
        Start-Sleep -Seconds 2
        return
    }
    
    while ($true) {
        Clear-Host
        Write-Host ""
        Write-Host "========================================" -ForegroundColor Cyan
        Write-Host "        ADMIN PANEL" -ForegroundColor Cyan
        Write-Host "========================================" -ForegroundColor Cyan
        Write-Host ""
        
        $users = Get-Users
        Write-Host "Registered Users:" -ForegroundColor Green
        Write-Host "----------------------------------------" -ForegroundColor DarkGray
        foreach ($u in $users) {
            $roleColor = if ($u.role -eq "admin") { "Yellow" } else { "White" }
            $lastLogin = if ($u.lastLogin) { $u.lastLogin } else { "Never" }
            Write-Host "  $($u.username) [$($u.role)] - Last: $lastLogin" -ForegroundColor $roleColor
        }
        Write-Host "----------------------------------------" -ForegroundColor DarkGray
        Write-Host ""
        Write-Host "  [1] Add New User" -ForegroundColor Green
        Write-Host "  [2] Delete User" -ForegroundColor Red
        Write-Host "  [3] Change User Role" -ForegroundColor Yellow
        Write-Host "  [4] View Access Logs" -ForegroundColor Cyan
        Write-Host "  [5] Back to Main Menu" -ForegroundColor White
        Write-Host ""
        Write-Host "  Select option: " -ForegroundColor Cyan -NoNewline
        $choice = Read-Host
        
        switch ($choice) {
            "1" {
                Write-Host ""
                Write-Host "Username: " -ForegroundColor Green -NoNewline
                $newUser = Read-Host
                Write-Host "Password: " -ForegroundColor Green -NoNewline
                $newPass = Read-Host
                Write-Host "Role (user/admin): " -ForegroundColor Green -NoNewline
                $newRole = Read-Host
                
                $users = Get-Users
                if ($users | Where-Object { $_.username -eq $newUser }) {
                    Write-Host "[!] User already exists." -ForegroundColor Red
                } else {
                    $users += @{
                        username = $newUser
                        password = $newPass
                        role = if ($newRole -eq "admin") { "admin" } else { "user" }
                        created = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
                        lastLogin = ""
                    }
                    Save-Users $users
                    Write-Host "[+] User '$newUser' created." -ForegroundColor Green
                    Log-Access $currentUser.username "ADD_USER:$newUser" $true
                }
                Start-Sleep -Seconds 2
            }
            "2" {
                Write-Host ""
                Write-Host "Username to delete: " -ForegroundColor Red -NoNewline
                $delUser = Read-Host
                
                $users = Get-Users
                if ($delUser -eq $currentUser.username) {
                    Write-Host "[!] Cannot delete yourself." -ForegroundColor Red
                } else {
                    $users = $users | Where-Object { $_.username -ne $delUser }
                    Save-Users $users
                    Write-Host "[+] User '$delUser' deleted." -ForegroundColor Green
                    Log-Access $currentUser.username "DEL_USER:$delUser" $true
                }
                Start-Sleep -Seconds 2
            }
            "3" {
                Write-Host ""
                Write-Host "Username: " -ForegroundColor Yellow -NoNewline
                $roleUser = Read-Host
                Write-Host "New Role (user/admin): " -ForegroundColor Yellow -NoNewline
                $newRole = Read-Host
                
                $users = Get-Users
                $user = $users | Where-Object { $_.username -eq $roleUser }
                if ($user) {
                    $user.role = if ($newRole -eq "admin") { "admin" } else { "user" }
                    Save-Users $users
                    Write-Host "[+] Role updated for '$roleUser'." -ForegroundColor Green
                    Log-Access $currentUser.username "ROLE_CHANGE:$roleUser" $true
                } else {
                    Write-Host "[!] User not found." -ForegroundColor Red
                }
                Start-Sleep -Seconds 2
            }
            "4" {
                if (Test-Path $LogPath) {
                    Get-Content $LogPath -Tail 20
                } else {
                    Write-Host "No logs available." -ForegroundColor Yellow
                }
                Write-Host ""
                Write-Host "Press any key to continue..." -ForegroundColor DarkGray
                $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
            }
            "5" { return }
        }
    }
}

# ============================================================
# MAIN LOGIC
# ============================================================

if ($arg1 -eq "help") {
    Clear-Host
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "           HFT TERMINAL - HELP" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  Type 'market' to open the login screen." -ForegroundColor White
    Write-Host ""
    Write-Host "  Dashboard Controls:" -ForegroundColor Green
    Write-Host "    1-4        Switch tabs" -ForegroundColor White
    Write-Host "    B/S        Buy/Sell mode" -ForegroundColor White
    Write-Host "    R/T/I/H/M  Select stock" -ForegroundColor White
    Write-Host "    0-9        Enter quantity" -ForegroundColor White
    Write-Host "    ENTER      Execute order" -ForegroundColor White
    Write-Host "    Q          Quit" -ForegroundColor White
    Write-Host ""
    Write-Host "Press any key..." -ForegroundColor DarkGray
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit
}

if ($arg1 -eq "news") {
    Clear-Host
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "           MARKET NEWS" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "[*] Fetching news..." -ForegroundColor Yellow
    Write-Host ""
    
    $sources = @(
        @{Name="Economic Times"; URL="https://economictimes.indiatimes.com/rssfeedsdefault.cms"},
        @{Name="MoneyControl"; URL="https://www.moneycontrol.com/rss/business.xml"}
    )
    
    foreach ($src in $sources) {
        Write-Host "=== $($src.Name) ===" -ForegroundColor Green
        try {
            $resp = Invoke-WebRequest -Uri $src.URL -UseBasicParsing -TimeoutSec 10
            $xml = [xml]$resp.Content
            $xml.rss.channel.item | Select-Object -First 3 | ForEach-Object {
                Write-Host "  • $($_.title)" -ForegroundColor White
            }
        } catch {
            Write-Host "  [!] Unable to fetch" -ForegroundColor Red
        }
        Write-Host ""
    }
    Write-Host "Press any key..." -ForegroundColor DarkGray
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit
}

# Main Login Loop
while ($true) {
    $choice = Show-LoginScreen
    
    switch ($choice) {
        "1" {
            Do-Login
            # After login, restart the loop to show login again if they quit
            continue
        }
        "2" {
            Do-Register
        }
        "3" {
            Clear-Host
            Write-Host ""
            Write-Host "Goodbye!" -ForegroundColor Red
            Write-Host ""
            exit
        }
        default {
            Write-Host "[!] Invalid option. Press 1, 2, or 3." -ForegroundColor Red
            Start-Sleep -Seconds 1
        }
    }
}
'@

Set-Content -Path $launcherPath -Value $launcherContent -Encoding UTF8

Write-Host "[+] Created authentication launcher at: $launcherPath" -ForegroundColor Green
Write-Host ""
Write-Host "SUCCESS! Your HFT Terminal is now secured." -ForegroundColor Green
Write-Host ""
Write-Host "Now you can just type:" -ForegroundColor Cyan
Write-Host "  market" -ForegroundColor White
Write-Host ""
Write-Host "from ANYWHERE to open the login screen." -ForegroundColor Cyan
Write-Host ""
Write-Host "Default Login:" -ForegroundColor Yellow
Write-Host "  Username: vishwas" -ForegroundColor White
Write-Host "  Password: 20065" -ForegroundColor White
Write-Host ""
Write-Host "Restart PowerShell to activate." -ForegroundColor Yellow
Write-Host ""

# 🚀 HFT Terminal - Global Access & Login Setup

## ✅ What You Now Have

1. ✅ **Global "market" command** - Type `market` anywhere to open terminal
2. ✅ **Login system** - Username/password authentication
3. ✅ **Password masking** - Passwords hidden with `*` characters
4. ✅ **User registration** - Create new accounts
5. ✅ **Main menu** - How to use, profile, exit options

---

## 🎯 HOW TO USE

### **Open Terminal (Anywhere!)**

Just type:
```
market
```

**Works from:**
- Any folder in Command Prompt
- PowerShell
- Run dialog (Win+R)
- Desktop shortcuts
- Start menu search

### **Login Screen**

When you type `market`, you'll see:

```
  ╔══════════════════════════════════════════════════════╗
  ║                                                      ║
  ║         🚀  HFT TRADING TERMINAL  🚀               ║
  ║                                                      ║
  ║     High-Frequency Trading with AI Predictions      ║
  ║                                                      ║
  ╚══════════════════════════════════════════════════════╝

  Welcome to HFT Trading Terminal

  1. Login to existing account
  2. Create new account

  Select option (1-2) [1]:
```

### **Login**

```
┌─ LOGIN ──────────────────────────────────────┐
│ Username: admin
│ Password (hidden): ********
└────────────────────────────────────────────────┘

✓ Login successful! Welcome, admin!
```

### **Main Menu**

After login:

```
  Welcome, admin!  2026-04-10 14:45:30

  ╔══════════════════════════════════════════════════════╗
  ║                                                      ║
  ║           🚀  HFT TRADING TERMINAL  🚀             ║
  ║                                                      ║
  ║        Autonomous AI-Powered Trading System         ║
  ║                                                      ║
  ╚══════════════════════════════════════════════════════╝

  1   🚀  Start Trading Terminal        Live market data
  2   📖  How to Use Terminal           User guide
  3   👤  User Profile                  Role: admin
  4   🔄  New Login                     Switch user
  5   🚪  Exit                          Close terminal

  ┌────────────────────────────────────────────────┐
  │ Select option (1-5) [1]:
  └────────────────────────────────────────────────┘
```

---

## 📋 MENU OPTIONS

### **1. Start Trading Terminal**
Opens the full HFT trading terminal with:
- Live market data
- Order book display
- Portfolio tracking
- Autonomous AI trading
- All tabs (1-6)

**Press Q to return to menu**

### **2. How to Use Terminal**
Complete user guide showing:
- ⌨️ Keyboard shortcuts
- 🚀 Features list
- 🤖 Autonomous trading setup
- 💡 Tips and tricks

### **3. User Profile**
Shows your account info:
- Username
- Role (admin/user)
- Account created date
- Last login time

### **4. New Login**
Logout and switch to different user:
- Login with existing account
- Create new account
- Returns to main menu after login

### **5. Exit**
Close terminal and return to command prompt

---

## 👤 USER ACCOUNTS

### **Default Account**

**Admin Account:**
- Username: `admin`
- Password: `admin123`
- Role: `admin`

**⚠️ Change this password after first login!**

### **Create New Account**

1. Start terminal: `market`
2. Select: `2. Create new account`
3. Enter username (min 3 characters)
4. Enter password (min 6 characters, hidden with *)
5. Confirm password (hidden with *)
6. Account created and auto-logged in!

### **Password Security**

- Passwords are hashed with SHA-256
- Stored in `users.json`
- Never shown in plain text
- Masked with `*` during entry

---

## ⌨️ KEYBOARD SHORTCUTS (In Terminal)

| Key | Action |
|-----|--------|
| `1-6` | Switch tabs |
| `B` | Buy order |
| `S` | Sell order |
| `R/T/I/H/M` | Select stock |
| `0-9` | Enter quantity |
| `Enter` | Execute trade |
| `A` | Toggle autonomous trading |
| `Q` | Quit to menu |

---

## 📁 FILES CREATED

| File | Purpose |
|------|---------|
| `market.bat` | Global launcher (added to PATH) |
| `terminal_login.py` | Login & menu system |
| `users.json` | User accounts database |

---

## 🔧 TROUBLESHOOTING

### **Problem**: "market" command not found

**Solution:**
```bash
# Open new terminal (PATH updated)
# Or run directly:
V:\quant_project\hft-ml\market.bat

# Or manually add to PATH:
setx PATH "%PATH%;V:\quant_project\hft-ml"
```

### **Problem**: Can't login

**Solution:**
- Default: username=`admin`, password=`admin123`
- Create new account: Select option 2

### **Problem**: Password visible

**Solution:**
- Password is automatically masked with `*`
- Uses `rich.prompt.Password` for secure input
- If still visible, check terminal supports password hiding

---

## 💡 TIPS

1. **Type `market` from anywhere** - No need to navigate to folder
2. **Use Win+R** - Press Win+R, type `market`, Enter
3. **Create desktop shortcut** - Right-click `market.bat` → Send to → Desktop
4. **Pin to taskbar** - Run `market`, right-click taskbar icon → Pin
5. **Multiple users** - Each user has separate login
6. **Press 2 in menu** - See full terminal guide anytime

---

## 🎯 QUICK START

```bash
# 1. Open terminal (anywhere)
market

# 2. Login
Username: admin
Password: ********

# 3. Press 1 to start trading
# 4. Press Q to return to menu
# 5. Press 5 to exit
```

---

**🎉 You're all set! Type `market` anywhere to start trading!** 🚀

---

**Created**: April 10, 2026  
**Status**: ✅ Production Ready  
**Features**: Login + Menu + Global Access

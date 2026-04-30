"""
Terminal Login & Menu System
Authentication and main menu for HFT Terminal
"""

import sys
sys.path.insert(0, r'V:\pylibs')
sys.path.insert(0, '.')

import os
import json
import hashlib
import getpass
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt
from rich.text import Text

console = Console()

# ============================================================
# USER MANAGEMENT
# ============================================================

class UserManager:
    """Manage user accounts and authentication"""
    
    def __init__(self, users_file: str = 'users.json'):
        self.users_file = users_file
        self.users = self._load_users()
        self.current_user: Optional[Dict] = None
    
    def _load_users(self) -> Dict:
        """Load users from file"""
        if Path(self.users_file).exists():
            try:
                with open(self.users_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        
        # Create default admin user
        default_users = {
            'admin': {
                'password_hash': hashlib.sha256('admin123'.encode()).hexdigest(),
                'created': datetime.now().isoformat(),
                'last_login': None,
                'role': 'admin'
            }
        }
        
        self._save_users(default_users)
        return default_users
    
    def _save_users(self, users: Dict):
        """Save users to file"""
        with open(self.users_file, 'w') as f:
            json.dump(users, f, indent=2)
    
    def register_user(self, username: str, password: str) -> bool:
        """Register new user"""
        if username in self.users:
            return False
        
        self.users[username] = {
            'password_hash': hashlib.sha256(password.encode()).hexdigest(),
            'created': datetime.now().isoformat(),
            'last_login': None,
            'role': 'user'
        }
        
        self._save_users(self.users)
        return True
    
    def authenticate(self, username: str, password: str) -> bool:
        """Authenticate user"""
        if username not in self.users:
            return False
        
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        if self.users[username]['password_hash'] == password_hash:
            self.users[username]['last_login'] = datetime.now().isoformat()
            self._save_users(self.users)
            self.current_user = {
                'username': username,
                **self.users[username]
            }
            return True
        
        return False
    
    def logout(self):
        """Logout current user"""
        self.current_user = None
    
    def get_user_count(self) -> int:
        """Get total number of users"""
        return len(self.users)


# ============================================================
# LOGIN SCREEN
# ============================================================

class LoginScreen:
    """Terminal login screen"""
    
    def __init__(self):
        self.user_manager = UserManager()
    
    def show_login(self) -> Optional[Dict]:
        """Show login screen and authenticate"""
        console.clear()
        
        # Login banner
        banner = Text()
        banner.append("\n", style="default")
        banner.append("  ╔══════════════════════════════════════════════════════╗\n", style="bold blue")
        banner.append("  ║                                                      ║\n", style="bold blue")
        banner.append("  ║         🚀  HFT TRADING TERMINAL  🚀               ║\n", style="bold cyan")
        banner.append("  ║                                                      ║\n", style="bold blue")
        banner.append("  ║     High-Frequency Trading with AI Predictions      ║\n", style="dim")
        banner.append("  ║                                                      ║\n", style="bold blue")
        banner.append("  ╚══════════════════════════════════════════════════════╝\n", style="bold blue")
        banner.append("\n", style="default")
        
        console.print(banner)
        
        while True:
            console.print("\n[bold cyan]┌─ LOGIN ──────────────────────────────────────┐[/bold cyan]")
            
            # Get username
            username = Prompt.ask(
                "│ [bold]Username[/bold]",
                console=console
            )
            
            # Get password (masked with *)
            password = Prompt.ask(
                "│ [bold]Password[/bold] (hidden)",
                console=console,
                password=True
            )
            
            console.print("└────────────────────────────────────────────────┘\n")
            
            # Authenticate
            if self.user_manager.authenticate(username, password):
                console.print(f"[bold green]✓ Login successful! Welcome, {username}![/bold green]\n")
                return self.user_manager.current_user
            else:
                console.print("[bold red]✗ Invalid username or password. Please try again.[/bold red]\n")
    
    def show_register(self) -> Optional[Dict]:
        """Show registration screen"""
        console.clear()
        
        banner = Text()
        banner.append("\n", style="default")
        banner.append("  ╔══════════════════════════════════════════════════════╗\n", style="bold blue")
        banner.append("  ║                                                      ║\n", style="bold blue")
        banner.append("  ║         📝  CREATE NEW ACCOUNT  📝                 ║\n", style="bold cyan")
        banner.append("  ║                                                      ║\n", style="bold blue")
        banner.append("  ╚══════════════════════════════════════════════════════╝\n", style="bold blue")
        banner.append("\n", style="default")
        
        console.print(banner)
        
        console.print("[bold cyan]┌─ NEW USER REGISTRATION ────────────────────────┐[/bold cyan]")
        
        while True:
            username = Prompt.ask(
                "│ [bold]Username[/bold] (min 3 characters)",
                console=console
            )
            
            if len(username) < 3:
                console.print("│ [red]✗ Username must be at least 3 characters[/red]")
                continue
            
            if username in self.user_manager.users:
                console.print("│ [red]✗ Username already exists[/red]")
                continue
            
            break
        
        while True:
            password = Prompt.ask(
                "│ [bold]Password[/bold] (min 6 characters, hidden)",
                console=console,
                password=True
            )
            
            if len(password) < 6:
                console.print("│ [red]✗ Password must be at least 6 characters[/red]")
                continue
            
            password_confirm = Prompt.ask(
                "│ [bold]Confirm Password[/bold] (hidden)",
                console=console,
                password=True
            )
            
            if password != password_confirm:
                console.print("│ [red]✗ Passwords do not match[/red]")
                continue
            
            break
        
        console.print("└────────────────────────────────────────────────┘\n")
        
        # Create user
        if self.user_manager.register_user(username, password):
            console.print(f"[bold green]✓ Account created successfully for '{username}'![/bold green]\n")
            console.print("[dim]You can now login with your credentials.[/dim]\n")
            
            # Auto-login
            success = self.user_manager.authenticate(username, password)
            if success:
                return self.user_manager.current_user
            else:
                console.print("[bold red]✗ Auto-login failed. Please login manually.[/bold red]\n")
                return None
        else:
            console.print("[bold red]✗ Failed to create account.[/bold red]\n")
            return None


# ============================================================
# MAIN MENU
# ============================================================

class MainMenu:
    """Main menu system after login"""
    
    def __init__(self, user: Dict):
        self.user = user
    
    def show_menu(self) -> str:
        """Show main menu and get choice"""
        console.clear()
        
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Header
        header = Text()
        header.append(f"\n  Welcome, [bold cyan]{self.user['username']}[/bold cyan]!  ", style="bold green")
        header.append(f"  {now}\n", style="dim")
        header.append("\n", style="default")
        header.append("  ╔══════════════════════════════════════════════════════╗\n", style="bold blue")
        header.append("  ║                                                      ║\n", style="bold blue")
        header.append("  ║           🚀  HFT TRADING TERMINAL  🚀             ║\n", style="bold cyan")
        header.append("  ║                                                      ║\n", style="bold blue")
        header.append("  ║        Autonomous AI-Powered Trading System         ║\n", style="dim")
        header.append("  ║                                                      ║\n", style="bold blue")
        header.append("  ╚══════════════════════════════════════════════════════╝\n", style="bold blue")
        header.append("\n", style="default")
        
        console.print(header)
        
        # Menu table
        menu_table = Table(box=None, show_header=False, expand=True, padding=(0, 2))
        menu_table.add_column("Option", style="bold cyan", width=5)
        menu_table.add_column("Description", style="white")
        menu_table.add_column("Status", style="dim", width=20)
        
        menu_table.add_row("1", "🚀  Start Trading Terminal", "Live market data")
        menu_table.add_row("2", "📖  How to Use Terminal", "User guide")
        menu_table.add_row("3", "👤  User Profile", f"Role: {self.user.get('role', 'user')}")
        menu_table.add_row("4", "🔄  New Login", "Switch user")
        menu_table.add_row("5", "🚪  Exit", "Close terminal")
        
        console.print(menu_table)
        
        console.print("\n  ┌────────────────────────────────────────────────┐")
        choice = Prompt.ask(
            "  │ [bold]Select option (1-5)[/bold]",
            console=console,
            choices=['1', '2', '3', '4', '5'],
            default='1'
        )
        console.print("  └────────────────────────────────────────────────┘\n")
        
        return choice
    
    def show_how_to_use(self):
        """Show how to use the terminal guide"""
        console.clear()
        
        guide = Text()
        guide.append("\n", style="default")
        guide.append("  ╔══════════════════════════════════════════════════════╗\n", style="bold blue")
        guide.append("  ║                                                      ║\n", style="bold blue")
        guide.append("  ║         📖  HOW TO USE THE TERMINAL  📖            ║\n", style="bold cyan")
        guide.append("  ║                                                      ║\n", style="bold blue")
        guide.append("  ╚══════════════════════════════════════════════════════╝\n", style="bold blue")
        guide.append("\n", style="default")
        
        console.print(guide)
        
        # Keyboard shortcuts
        console.print("  [bold cyan]⌨️  KEYBOARD SHORTCUTS[/bold cyan]\n")
        
        shortcuts = Table(box=None, show_header=False, expand=True, padding=(0, 2))
        shortcuts.add_column("Key", style="bold yellow", width=15)
        shortcuts.add_column("Action", style="white")
        
        shortcuts.add_row("1-6", "Switch tabs (Overview, Order Book, Trades, Portfolio, Charts, Auto)")
        shortcuts.add_row("B", "Buy order")
        shortcuts.add_row("S", "Sell order")
        shortcuts.add_row("R/T/I/H/M", "Select stock (RELIANCE/TCS/INFY/HDFCBANK/TATAMOTORS)")
        shortcuts.add_row("0-9", "Enter quantity")
        shortcuts.add_row("Enter", "Execute trade")
        shortcuts.add_row("A", "Toggle autonomous trading")
        shortcuts.add_row("Q", "Quit terminal")
        
        console.print(shortcuts)
        
        # Features
        console.print("\n  [bold cyan]🚀 FEATURES[/bold cyan]\n")
        
        features = Table(box=None, show_header=False, expand=True, padding=(0, 2))
        features.add_column("Feature", style="bold green", width=25)
        features.add_column("Description", style="white")
        
        features.add_row("Live Market Data", "Real-time prices from Yahoo Finance")
        features.add_row("Level 2 Order Book", "Bid/ask spread with depth")
        features.add_row("Portfolio Tracking", "P&L, positions, equity")
        features.add_row("Trade History", "Complete trade log")
        features.add_row("AI Predictions", "Multi-model ensemble voting")
        features.add_row("Autonomous Trading", "AI trades automatically")
        features.add_row("Risk Management", "Stop losses, position sizing")
        
        console.print(features)
        
        # Autonomous trading
        console.print("\n  [bold cyan]🤖 AUTONOMOUS TRADING[/bold cyan]\n")
        console.print("  1. Press [bold]6[/bold] to open Autonomous Trading tab")
        console.print("  2. Press [bold]A[/bold] to enable autonomous trading")
        console.print("  3. AI models analyze stocks every 10 seconds")
        console.print("  4. Signals show BUY/SELL/HOLD with confidence %")
        console.print("  5. Trades execute automatically when confidence > 65%")
        
        console.print("\n  [bold cyan]💡 TIPS[/bold cyan]\n")
        console.print("  • Terminal works during market hours (9:15 AM - 3:30 PM IST)")
        console.print("  • Paper trading mode - no real money at risk")
        console.print("  • Press [bold]2[/bold] anytime to see this guide again")
        console.print("  • Press [bold]Q[/bold] to exit and return to menu")
        
        console.print("\n  Press [bold]Enter[/bold] to return to main menu...")
        console.input()


# ============================================================
# MAIN ENTRY POINT
# ============================================================

def main():
    """Main entry point with login and menu"""
    login_screen = LoginScreen()
    
    console.clear()
    console.print("[bold cyan]Starting HFT Trading Terminal...[/bold cyan]\n")
    
    # Show login/register choice
    while True:
        console.print("\n  [bold]Welcome to HFT Trading Terminal[/bold]\n")
        console.print("  1. Login to existing account")
        console.print("  2. Create new account\n")
        
        choice = Prompt.ask(
            "Select option (1-2)",
            choices=['1', '2'],
            default='1'
        )
        
        if choice == '1':
            user = login_screen.show_login()
            if user:
                break
        elif choice == '2':
            user = login_screen.show_register()
            if user:
                break
    
    # Main menu loop
    main_menu = MainMenu(user)
    
    while True:
        choice = main_menu.show_menu()
        
        if choice == '1':
            # Start trading terminal
            console.print("\n[bold green]🚀 Starting Trading Terminal...[/bold green]\n")
            console.print("[dim]Press Q to return to menu[/dim]\n")
            
            # Import and run terminal dashboard
            try:
                from terminal_dashboard import TerminalDashboard
                dashboard = TerminalDashboard()
                dashboard.portfolio.initial_capital = 10_000_000
                dashboard.run(update_interval=0.5)
            except Exception as e:
                console.print(f"[bold red]Error starting terminal: {e}[/bold red]")
                console.input("Press Enter to continue...")
        
        elif choice == '2':
            # Show how to use
            main_menu.show_how_to_use()
        
        elif choice == '3':
            # User profile
            console.clear()
            console.print("\n  [bold cyan]👤 User Profile[/bold cyan]\n")
            console.print(f"  Username: [bold]{user['username']}[/bold]")
            console.print(f"  Role: [bold]{user.get('role', 'user')}[/bold]")
            console.print(f"  Created: {user.get('created', 'N/A')}")
            console.print(f"  Last Login: {user.get('last_login', 'N/A')}\n")
            console.input("  Press Enter to continue...")
        
        elif choice == '4':
            # New login
            login_screen.user_manager.logout()
            
            while True:
                console.print("\n  [bold]Select action:[/bold]\n")
                console.print("  1. Login")
                console.print("  2. Create new account\n")
                
                choice = Prompt.ask(
                    "Select option (1-2)",
                    choices=['1', '2'],
                    default='1'
                )
                
                if choice == '1':
                    user = login_screen.show_login()
                    if user:
                        main_menu = MainMenu(user)
                        break
                elif choice == '2':
                    user = login_screen.show_register()
                    if user:
                        main_menu = MainMenu(user)
                        break
        
        elif choice == '5':
            # Exit
            console.clear()
            console.print("\n  [bold red]🚪 Exiting HFT Trading Terminal...[/bold red]\n")
            console.print("  [dim]Thank you for using HFT Terminal![/dim]\n")
            console.print("  [bold]Goodbye![/bold]\n")
            break


if __name__ == '__main__':
    main()

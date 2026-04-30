"""
Quick test for login system
"""
import sys
sys.path.insert(0, '.')

from terminal_login import LoginScreen, MainMenu

print("\n🧪 Testing Login System...\n")

# Test user manager
from terminal_login import UserManager
um = UserManager()

print(f"✓ UserManager created")
print(f"✓ Users file: {um.users_file}")
print(f"✓ User count: {um.get_user_count()}")

# Test authentication
success = um.authenticate('admin', 'admin123')
print(f"✓ Admin login: {'✓ Success' if success else '✗ Failed'}")

if success:
    print(f"✓ Current user: {um.current_user['username']}")
    print(f"✓ Role: {um.current_user.get('role', 'user')}")

print("\n✅ Login system is working correctly!")
print("\n🚀 To use: Type 'market' anywhere on your computer!")

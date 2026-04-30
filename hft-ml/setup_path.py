"""
Path setup for HFT ML package
Adds V:\pylibs to Python path for PyTorch and dependencies
"""
import sys
import os

# Add custom PyTorch install path
CUSTOM_PYLIBS = r'V:\pylibs'
if os.path.exists(CUSTOM_PYLIBS) and CUSTOM_PYLIBS not in sys.path:
    sys.path.insert(0, CUSTOM_PYLIBS)

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

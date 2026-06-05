"""Entry point for the SkinVault .exe. Opens the UI by default."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from skinvault.gui import launch

sys.exit(launch())

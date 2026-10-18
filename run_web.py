"""Entry point do PyInstaller para a UI web (SkinVault-web.spec)."""
from skinvault.webapp.app_entry import launch_web

if __name__ == "__main__":
    raise SystemExit(launch_web())

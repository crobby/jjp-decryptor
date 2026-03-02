"""Entry point: python -m jjp_decryptor"""

import sys


def _ensure_admin():
    """On Windows, re-launch as Administrator if not already elevated."""
    if sys.platform != "win32":
        return
    import ctypes
    try:
        if ctypes.windll.shell32.IsUserAnAdmin():
            return  # already admin
    except Exception:
        return  # can't check — proceed anyway

    # Re-launch this script elevated via UAC prompt
    import os
    params = " ".join(f'"{a}"' for a in sys.argv)
    # ShellExecuteW returns >32 on success
    ret = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, params, os.getcwd(), 1)
    if ret > 32:
        sys.exit(0)  # elevated process launched — exit this one
    # If UAC was cancelled or failed, continue without admin
    # (user will see the admin warning banners on SSD tabs)


if __name__ == "__main__":
    _ensure_admin()
    from .app import App
    App().run()

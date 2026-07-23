from __future__ import annotations

from pathlib import Path
import os


STARTUP_DIR = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
STARTUP_FILE = STARTUP_DIR / "MailPilot.vbs"


def is_enabled() -> bool:
    return STARTUP_FILE.exists()


def set_enabled(enabled: bool, app_dir: Path) -> None:
    STARTUP_DIR.mkdir(parents=True, exist_ok=True)
    if enabled:
        exe = app_dir / "MailPilot.exe"
        script = exe if exe.exists() else app_dir / "run_hidden.vbs"
        STARTUP_FILE.write_text(
            f'Set shell = CreateObject("WScript.Shell")\n'
            f'shell.Run """{script}"" --tray", 0, False\n',
            encoding="utf-8",
        )
        return
    if STARTUP_FILE.exists():
        STARTUP_FILE.unlink()

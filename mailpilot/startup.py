from __future__ import annotations

from pathlib import Path
import os

try:
    import winreg
except ImportError:  # pragma: no cover - Windows-only startup integration
    winreg = None


STARTUP_DIR = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
STARTUP_FILE = STARTUP_DIR / "MailPilot.vbs"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "MailPilot"


def _startup_command(exe: Path) -> str:
    return f'"{exe}" --tray'


def _registry_is_enabled() -> bool:
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, RUN_VALUE)
        return True
    except OSError:
        return False


def _set_registry_enabled(enabled: bool, exe: Path | None = None) -> bool:
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled and exe is not None:
                winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, _startup_command(exe))
            else:
                try:
                    winreg.DeleteValue(key, RUN_VALUE)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False


def is_enabled() -> bool:
    return STARTUP_FILE.exists() or _registry_is_enabled()


def set_enabled(enabled: bool, app_dir: Path) -> None:
    STARTUP_DIR.mkdir(parents=True, exist_ok=True)
    if enabled:
        exe = app_dir / "MailPilot.exe"
        if not exe.exists():
            raise FileNotFoundError(f"MailPilot.exe bulunamadi: {exe}")
        if _set_registry_enabled(True, exe):
            if STARTUP_FILE.exists():
                STARTUP_FILE.unlink()
            return
        STARTUP_FILE.write_text(
            f'Set shell = CreateObject("WScript.Shell")\n'
            f'shell.CurrentDirectory = "{app_dir}"\n'
            f'shell.Run """{exe}"" --tray", 0, False\n',
            encoding="utf-8",
        )
        return
    if STARTUP_FILE.exists():
        STARTUP_FILE.unlink()
    _set_registry_enabled(False)

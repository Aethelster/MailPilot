from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import date, datetime
import json
from pathlib import Path
import shutil
import sys


if getattr(sys, "frozen", False):
    APP_DIR = Path(getattr(sys, "_MEIPASS"))
    RUNTIME_DIR = Path(sys.executable).resolve().parent
else:
    APP_DIR = Path(__file__).resolve().parents[1]
    RUNTIME_DIR = APP_DIR

CREDENTIALS_DIR = RUNTIME_DIR / "credentials"
SETTINGS_PATH = CREDENTIALS_DIR / "settings.json"
SUMMARIES_DIR = RUNTIME_DIR / "ozet-loglari"


def ensure_runtime_layout() -> None:
    CREDENTIALS_DIR.mkdir(exist_ok=True)
    SUMMARIES_DIR.mkdir(exist_ok=True)
    legacy_files = ("settings.json", "credentials.json", "outlook_credentials.json", "token.json")
    for name in legacy_files:
        old_path = RUNTIME_DIR / name
        new_path = CREDENTIALS_DIR / name
        if old_path.exists() and not new_path.exists():
            shutil.copy2(old_path, new_path)
    old_accounts = RUNTIME_DIR / "accounts"
    new_accounts = CREDENTIALS_DIR / "accounts"
    if old_accounts.exists() and not new_accounts.exists():
        shutil.copytree(old_accounts, new_accounts)
    old_summaries = RUNTIME_DIR / "summaries"
    if old_summaries.exists():
        for item in old_summaries.glob("*"):
            target = SUMMARIES_DIR / item.name
            if item.is_file() and not target.exists():
                shutil.copy2(item, target)


@dataclass
class Settings:
    enabled: bool = True
    start_with_windows: bool = False
    start_minimized_to_tray: bool = True
    summary_times: list[str] = field(default_factory=lambda: ["09:00", "18:00"])
    scan_mode: str = "since_last_scan"
    lookback_hours: int = 24
    max_messages: int = 20
    last_scan_at: str | None = None
    priority_senders: list[str] = field(default_factory=list)
    completed_message_ids: list[str] = field(default_factory=list)
    email_accounts: list[dict[str, str]] = field(default_factory=list)
    active_account_id: str | None = None
    daily_report_time: str = "09:00"
    last_daily_report_date: str | None = None
    report_scan_mode: str = "since_last_scan"
    date_filter_mode: str = "auto"
    single_scan_date: str = field(default_factory=lambda: date.today().isoformat())
    range_start_date: str = field(default_factory=lambda: date.today().isoformat())
    range_end_date: str = field(default_factory=lambda: date.today().isoformat())
    theme: str = "light"

    @classmethod
    def load(cls) -> "Settings":
        ensure_runtime_layout()
        if not SETTINGS_PATH.exists():
            return cls()
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        default = asdict(cls())
        known_keys = {item.name for item in fields(cls)}
        default.update({key: value for key, value in data.items() if key in known_keys})
        return cls(**default)

    def save(self) -> None:
        ensure_runtime_layout()
        SETTINGS_PATH.write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def mark_scanned_now(self) -> None:
        self.last_scan_at = datetime.now().isoformat(timespec="seconds")
        self.save()

    def mark_daily_report_now(self) -> None:
        self.last_daily_report_date = datetime.now().date().isoformat()
        self.save()


def parse_times(value: str) -> list[str]:
    times: list[str] = []
    for raw in value.split(","):
        item = raw.strip()
        if not item:
            continue
        datetime.strptime(item, "%H:%M")
        times.append(item)
    if not times:
        raise ValueError("En az bir özet saati girilmeli.")
    return sorted(set(times))


def parse_priority_senders(value: str) -> list[str]:
    return sorted({item.strip().lower() for item in value.split(",") if item.strip()})


def parse_single_time(value: str) -> str:
    item = value.strip()
    datetime.strptime(item, "%H:%M")
    return item


def parse_date_value(value: str) -> str:
    item = value.strip()
    datetime.strptime(item, "%Y-%m-%d")
    return item


def scan_mode_label(value: str) -> str:
    labels = {
        "since_last_scan": "Son taramadan sonraki mailler",
        "lookback_window": "Seçilen saat aralığındaki mailler",
    }
    return labels.get(value, value)

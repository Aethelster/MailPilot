from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta
import html
import os
import sys
import threading
import webbrowser

from PySide6.QtCore import QDate, QEasingCurve, QEvent, QLocale, QLockFile, QObject, QPropertyAnimation, QRectF, QSize, QTimer, Qt, Signal, Property
from PySide6.QtGui import QAction, QColor, QFont, QFontDatabase, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QMenu,
    QPushButton,
    QDialog,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QStyle,
    QSystemTrayIcon,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .config import CREDENTIALS_DIR, APP_DIR, RUNTIME_DIR, Settings, parse_date_value, parse_priority_senders, parse_single_time, parse_times
from .gmail_client import (
    GmailNotReady,
    OutlookDeviceLogin,
    add_gmail_account,
    add_outlook_account,
    ensure_default_gmail_account,
    fetch_messages,
    finish_outlook_device_login,
    ensure_account_avatar,
    summaries_path,
)
from .startup import is_enabled as startup_is_enabled
from .startup import set_enabled as set_startup_enabled
from .summarizer import analyze_messages, filter_records, render_general_summary_html, render_summary


FILTERS = ["Hepsi", "Tamamlanmamış", "Acil", "Cevap", "Fatura/Ödeme", "Toplantı", "Güvenlik", "Onay"]

ADD_ACCOUNT_ITEM = "__mailpilot_add_account__"
APP_ICON_PATH = APP_DIR / "assets" / "brand" / "logo" / "mailpilot.ico"
TRAY_ICON_DIR = APP_DIR / "assets" / "brand" / "tray"
TRAY_ICON_PATH = APP_DIR / "assets" / "brand" / "tray" / "mailpilot-tray.ico"
INSTANCE_LOCK_PATH = CREDENTIALS_DIR / "MailPilot.lock"
INSTANCE_RESTORE_PATH = CREDENTIALS_DIR / "MailPilot.restore"
INSTANCE_LOCK: QLockFile | None = None


def _icon(name: str) -> QIcon:
    return QIcon((APP_DIR / "assets" / "icons" / name).as_posix())


def _tray_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 20, 24, 32, 48, 64, 128, 256):
        path = TRAY_ICON_DIR / f"mailpilot-tray-{size}.png"
        if path.exists():
            icon.addFile(str(path), QSize(size, size))
    if not icon.isNull():
        return icon
    return QIcon(str(TRAY_ICON_PATH))


def _safe_font(family: str, point_size: int, weight: QFont.Weight | int | None = None) -> QFont:
    font = QFont(family)
    font.setPointSize(max(1, int(point_size)))
    if weight is not None:
        font.setWeight(weight)
    return font


def _request_existing_instance_restore() -> None:
    try:
        CREDENTIALS_DIR.mkdir(exist_ok=True)
        INSTANCE_RESTORE_PATH.write_text(datetime.now().isoformat(timespec="seconds"), encoding="utf-8")
    except Exception:
        pass


BASE_STYLE = """
* {
  font-family: "Segoe UI Variable Text", "Segoe UI", "Inter", "Arial";
  font-size: 13px;
  letter-spacing: 0px;
}
QMainWindow, QWidget#Root {
  background: %APP_BG%;
}
QFrame#Sidebar {
  background: %SIDEBAR%;
  border: 1px solid %SIDEBAR_BORDER%;
  border-radius: 30px;
}
QFrame#Panel, QFrame#Hero, QFrame#Metric, QFrame#DetailPanel, QFrame#ScopeCard {
  background: %PANEL%;
  border: 1px solid %BORDER%;
  border-radius: 26px;
}
QFrame#Hero {
  background: %HERO%;
}
QFrame#ScopeCard {
  background: %SCOPE%;
}
QLabel {
  color: %TEXT%;
}
QLabel#Brand {
  color: %SIDEBAR_TEXT%;
  font-family: "Orange Avenue DEMO";
  font-size: 42px;
  font-weight: 400;
}
QLabel#SidebarMuted {
  color: %SIDEBAR_MUTED%;
  font-size: 13px;
}
QFrame#Sidebar QCheckBox {
  color: %SIDEBAR_TEXT%;
  font-weight: 700;
}
QCheckBox::indicator {
  width: 18px;
  height: 18px;
  border-radius: 6px;
  border: 1px solid %CHECK_BORDER%;
  background: %CHECK_BG%;
}
QCheckBox::indicator:checked {
  background: %ACCENT%;
  border: 1px solid %ACCENT%;
  image: url("%CHECK_ICON%");
}
QFrame#Sidebar QComboBox {
  color: %SIDEBAR_INPUT_TEXT%;
  background: %SIDEBAR_INPUT%;
  border: 1px solid %SIDEBAR_BUTTON_BORDER%;
  border-radius: 22px;
}
QFrame#Sidebar QComboBox QAbstractItemView {
  color: %TEXT%;
  background: %PANEL%;
  border: 1px solid %BORDER%;
}
QDialog#ReportPopup {
  background: %APP_BG%;
}
QFrame#ReportPopupPanel {
  background: %PANEL%;
  border: 1px solid %BORDER%;
  border-radius: 24px;
}
QTextEdit#ReportSummary {
  color: %TEXT%;
  background: %DETAIL_BG%;
  border: 1px solid %BORDER%;
  border-radius: 18px;
  padding: 18px;
}
QLabel#Eyebrow {
  color: %MUTED%;
  font-size: 11px;
  font-weight: 800;
  text-transform: uppercase;
}
QLabel#Title {
  color: %TEXT%;
  font-size: 30px;
  font-weight: 850;
}
QLabel#SectionTitle {
  color: %TEXT%;
  font-size: 16px;
  font-weight: 800;
}
QLabel#HelpText {
  color: %MUTED%;
  font-size: 12px;
}
QLabel#MetricValue {
  color: %TEXT%;
  font-family: "Orange Avenue DEMO";
  font-size: 34px;
  font-weight: 400;
}
QLabel#MetricLabel {
  color: %MUTED%;
  font-size: 12px;
}
QLabel#StatusPill {
  color: %PILL_TEXT%;
  background: %PILL_BG%;
  border: 1px solid %PILL_BORDER%;
  border-radius: 14px;
  padding: 9px 12px;
  font-weight: 800;
}
QLineEdit, QSpinBox, QComboBox, QDateEdit {
  color: %TEXT%;
  background: %INPUT%;
  border: 1px solid %BORDER%;
  border-radius: 22px;
  padding: 8px 15px;
  min-height: 30px;
  selection-background-color: %SELECT%;
}
QComboBox {
  padding-right: 48px;
}
QDateEdit {
  padding-right: 48px;
}
QComboBox::drop-down, QDateEdit::drop-down {
  width: 42px;
  border: 0;
  border-left: 1px solid %BORDER%;
  border-top-right-radius: 21px;
  border-bottom-right-radius: 21px;
  background: %CONTROL_BUTTON%;
}
QComboBox::down-arrow {
  image: url("%CHEVRON_ICON%");
  width: 18px;
  height: 18px;
}
QDateEdit::down-arrow {
  image: url("%CALENDAR_ICON%");
  width: 18px;
  height: 18px;
}
QSpinBox {
  padding-right: 14px;
}
QSpinBox::up-button, QSpinBox::down-button {
  width: 0px;
  border: 0;
}
QSpinBox::up-arrow, QSpinBox::down-arrow {
  width: 0px;
  height: 0px;
}
QLineEdit::placeholder {
  color: %PLACEHOLDER%;
}
QComboBox QAbstractItemView {
  color: %TEXT%;
  background: %PANEL%;
  border: 1px solid %BORDER%;
  border-radius: 18px;
  padding: 5px;
  outline: 0;
  selection-color: %SELECT_TEXT%;
  selection-background-color: %SELECT%;
}
QComboBox QAbstractItemView::item {
  min-height: 28px;
  padding: 5px 9px;
  border-radius: 14px;
}
QCalendarWidget QWidget {
  color: %TEXT%;
  background: %PANEL%;
}
QCalendarWidget {
  background: %PANEL%;
  border: 1px solid %BORDER%;
  border-radius: 16px;
}
QCalendarWidget QToolButton {
  color: %TEXT%;
  background: %INPUT%;
  border: 1px solid %BORDER%;
  border-radius: 13px;
  min-width: 84px;
  min-height: 26px;
  padding: 2px 7px;
  margin: 2px;
}
QCalendarWidget QToolButton::menu-indicator {
  image: none;
  width: 0px;
}
QCalendarWidget QToolButton#qt_calendar_prevmonth,
QCalendarWidget QToolButton#qt_calendar_nextmonth {
  min-width: 30px;
  max-width: 30px;
}
QCalendarWidget QMenu {
  color: %TEXT%;
  background: %PANEL%;
  border: 1px solid %BORDER%;
  border-radius: 14px;
  padding: 4px;
}
QCalendarWidget QSpinBox {
  color: %TEXT%;
  background: %INPUT%;
  border: 1px solid %BORDER%;
  border-radius: 12px;
  min-width: 76px;
  padding: 3px 7px;
}
QCalendarWidget QAbstractItemView {
  color: %TEXT%;
  background: %PANEL%;
  selection-color: %SELECT_TEXT%;
  selection-background-color: %SELECT%;
  outline: 0;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QDateEdit:focus {
  border: 1px solid %ACCENT%;
}
QCheckBox {
  color: %TEXT%;
  spacing: 8px;
}
QPushButton {
  color: %BUTTON_TEXT%;
  background-color: %BUTTON%;
  border: 1px solid %BUTTON_BORDER%;
  border-radius: 20px;
  padding: 11px 16px;
  min-height: 20px;
  font-weight: 800;
}
QPushButton:hover {
  background-color: %BUTTON_HOVER%;
  border: 1px solid %ACCENT%;
  border-radius: 20px;
}
QPushButton#PrimaryButton {
  color: white;
  background-color: %ACCENT%;
  border: 1px solid %ACCENT%;
  border-radius: 20px;
}
QPushButton#PrimaryButton:hover {
  background-color: %ACCENT_HOVER%;
  border: 1px solid %ACCENT_HOVER%;
  border-radius: 20px;
}
QPushButton#ScanButton {
  color: white;
  background-color: %SCAN%;
  border: 1px solid %SCAN%;
  border-radius: 24px;
  padding: 14px 18px;
  font-size: 14px;
  font-weight: 850;
}
QPushButton#ScanButton:hover {
  background-color: %SCAN_HOVER%;
  border: 1px solid %SCAN_HOVER%;
  border-radius: 24px;
}
QPushButton#DangerButton {
  color: %DANGER_TEXT%;
  background-color: %DANGER_BG%;
  border: 1px solid %DANGER_BORDER%;
  border-radius: 20px;
  padding: 9px 12px;
  min-height: 20px;
}
QPushButton#DangerButton:hover {
  background-color: %DANGER_HOVER%;
  border: 1px solid %DANGER_BORDER%;
  border-radius: 20px;
}
QPushButton#GhostButton {
  color: %SIDEBAR_TEXT%;
  background-color: %SIDEBAR_BUTTON%;
  border: 1px solid %SIDEBAR_BUTTON_BORDER%;
  border-radius: 20px;
}
QPushButton#GhostButton:hover {
  background-color: %SIDEBAR_BUTTON_HOVER%;
  border: 1px solid %ACCENT%;
  border-radius: 20px;
}
QPushButton#SmallGhostButton {
  color: %SIDEBAR_TEXT%;
  background-color: %SIDEBAR_BUTTON%;
  border: 1px solid %SIDEBAR_BUTTON_BORDER%;
  border-radius: 20px;
  padding: 9px 12px;
  font-weight: 800;
}
QPushButton#SmallGhostButton:hover {
  background-color: %SIDEBAR_BUTTON_HOVER%;
  border: 1px solid %ACCENT%;
  border-radius: 20px;
}
QPushButton#SettingsButton {
  color: %SIDEBAR_TEXT%;
  background-color: %SIDEBAR_BUTTON%;
  border: 1px solid %SIDEBAR_BUTTON_BORDER%;
  border-radius: 20px;
  padding: 11px 16px;
  font-weight: 850;
}
QPushButton#SettingsButton:hover {
  background-color: %SIDEBAR_BUTTON_HOVER%;
  border: 1px solid %ACCENT%;
  border-radius: 20px;
}
QFrame#Toast {
  background: %PANEL%;
  border: 1px solid %ACCENT%;
  border-radius: 20px;
}
QLabel#ToastTitle {
  color: %TEXT%;
  font-size: 13px;
  font-weight: 850;
}
QLabel#ToastText {
  color: %MUTED%;
  font-size: 12px;
}
QPushButton#ToastClose {
  color: %TEXT%;
  background: transparent;
  border: 0px;
  border-radius: 12px;
  padding: 3px 6px;
  font-weight: 900;
}
QPushButton#ToastClose:hover {
  color: %SELECT_TEXT%;
  background: %SELECT%;
}
QFrame#SettingsPopover {
  background: %PANEL%;
  border: 1px solid %BORDER%;
  border-radius: 22px;
}
QFrame#SettingsPopover QLabel {
  color: %TEXT%;
}
QFrame#SettingsPopover QCheckBox {
  color: %TEXT%;
  background: transparent;
  padding: 2px 0px;
}
QFrame#SettingsPopover QCheckBox:hover {
  background: transparent;
}
QPushButton#ModeButton {
  color: %MUTED%;
  background-color: %TAB%;
  border: 1px solid %BORDER%;
  border-radius: 20px;
  padding: 11px 20px;
  min-width: 92px;
}
QPushButton#ModeButton:checked {
  color: %TEXT%;
  background-color: %PANEL%;
  border-radius: 20px;
  font-weight: 850;
}
QPushButton#ModeButton:hover {
  border: 1px solid %ACCENT%;
  border-radius: 20px;
}
QTabWidget::pane {
  border: 0;
  background: transparent;
}
QTabBar::tab {
  color: %MUTED%;
  background-color: %TAB%;
  border: 1px solid %BORDER%;
  border-radius: 20px;
  padding: 11px 20px;
  margin-right: 8px;
}
QTabBar::tab:selected {
  color: %TEXT%;
  background-color: %PANEL%;
  border-radius: 20px;
  font-weight: 850;
}
QTabBar::tab:hover {
  border: 1px solid %ACCENT%;
  border-radius: 20px;
}
QListWidget {
  color: %TEXT%;
  background: %LIST_BG%;
  border: 1px solid %BORDER%;
  border-radius: 22px;
  padding: 8px;
}
QListWidget::item {
  padding: 0px;
  border-radius: 15px;
  margin: 5px;
}
QListWidget::item:selected {
  color: %SELECT_TEXT%;
  background: %SELECT%;
}
QWidget#MailListItem {
  background: transparent;
}
QLabel#MailItemSubject {
  color: %TEXT%;
  font-weight: 800;
  font-size: 13px;
}
QLabel#MailItemMeta {
  color: %MUTED%;
  font-size: 12px;
}
QLabel#MailItemLine {
  color: %TEXT%;
  font-size: 12px;
}
QLabel#ListTagUrgent, QLabel#ListTagReply, QLabel#ListTagMoney, QLabel#ListTagMeeting,
QLabel#ListTagSecurity, QLabel#ListTagApproval, QLabel#ListTagInfo {
  border-radius: 10px;
  padding: 3px 8px;
  font-size: 10px;
  font-weight: 850;
}
QLabel#ListTagUrgent {
  color: #9f1239;
  background: #ffe4e6;
  border: 1px solid #fecdd3;
}
QLabel#ListTagReply {
  color: #1d4ed8;
  background: #dbeafe;
  border: 1px solid #bfdbfe;
}
QLabel#ListTagMoney {
  color: #166534;
  background: #dcfce7;
  border: 1px solid #bbf7d0;
}
QLabel#ListTagMeeting {
  color: #7c2d12;
  background: #ffedd5;
  border: 1px solid #fed7aa;
}
QLabel#ListTagSecurity {
  color: #5b21b6;
  background: #ede9fe;
  border: 1px solid #ddd6fe;
}
QLabel#ListTagApproval {
  color: #854d0e;
  background: #fef3c7;
  border: 1px solid #fde68a;
}
QLabel#ListTagInfo {
  color: #334155;
  background: #e2e8f0;
  border: 1px solid #cbd5e1;
}
QFrame#DetailFrame {
  color: %TEXT%;
  background: %DETAIL_BG%;
  border: 1px solid %BORDER%;
  border-radius: 22px;
}
QScrollArea#DetailScroll {
  color: %TEXT%;
  background: transparent;
  border: 0px;
}
QScrollArea#DetailScroll > QWidget > QWidget {
  background: transparent;
}
QWidget#DetailContainer {
  background: transparent;
}
QScrollArea#DetailScroll QScrollBar:vertical {
  background: transparent;
  width: 10px;
  margin: 14px 4px 14px 0px;
}
QScrollArea#DetailScroll QScrollBar::handle:vertical {
  background: %BORDER%;
  border-radius: 5px;
  min-height: 36px;
}
QScrollArea#DetailScroll QScrollBar::add-line:vertical,
QScrollArea#DetailScroll QScrollBar::sub-line:vertical {
  height: 0px;
  border: 0px;
}
QFrame#DetailMailCard {
  background: %PANEL%;
  border: 1px solid %BORDER%;
  border-radius: 18px;
}
QFrame#DetailInfoBlock {
  background: %SCOPE%;
  border: 1px solid %BORDER%;
  border-radius: 18px;
}
QLabel#DetailSubject {
  color: %TEXT%;
  font-size: 18px;
  font-weight: 850;
}
QLabel#DetailSender {
  color: %MUTED%;
  font-size: 13px;
}
QLabel#DetailBlockTitle {
  color: %TEXT%;
  font-size: 13px;
  font-weight: 850;
}
QLabel#DetailBlockText {
  color: %TEXT%;
  font-size: 14px;
  line-height: 145%;
}
QLabel#DetailLine {
  color: %TEXT%;
  font-size: 13px;
}
QLabel#DetailEmpty {
  color: %MUTED%;
  font-size: 13px;
}
QLabel#TagUrgent, QLabel#TagReply, QLabel#TagMoney, QLabel#TagMeeting,
QLabel#TagSecurity, QLabel#TagApproval, QLabel#TagInfo, QLabel#DateChip {
  border-radius: 11px;
  padding: 4px 10px;
  font-size: 11px;
  font-weight: 850;
}
QLabel#TagUrgent {
  color: #9f1239;
  background: #ffe4e6;
  border: 1px solid #fecdd3;
}
QLabel#TagReply {
  color: #1d4ed8;
  background: #dbeafe;
  border: 1px solid #bfdbfe;
}
QLabel#TagMoney {
  color: #166534;
  background: #dcfce7;
  border: 1px solid #bbf7d0;
}
QLabel#TagMeeting {
  color: #7c2d12;
  background: #ffedd5;
  border: 1px solid #fed7aa;
}
QLabel#TagSecurity {
  color: #5b21b6;
  background: #ede9fe;
  border: 1px solid #ddd6fe;
}
QLabel#TagApproval {
  color: #854d0e;
  background: #fef3c7;
  border: 1px solid #fde68a;
}
QLabel#TagInfo {
  color: #334155;
  background: #e2e8f0;
  border: 1px solid #cbd5e1;
}
QLabel#DateChip {
  color: %MUTED%;
  background: %TAB%;
  border: 1px solid %BORDER%;
}
QTextEdit {
  color: %TEXT%;
  background: %DETAIL_BG%;
  border: 1px solid %BORDER%;
  border-radius: 22px;
  padding: 18px;
  line-height: 145%;
}
QTextEdit#GeneralSummary {
  font-size: 14px;
}
QSplitter::handle {
  background: transparent;
}
"""


def _style(**colors: str) -> str:
    style = BASE_STYLE
    for key, value in colors.items():
        style = style.replace(f"%{key}%", value)
    return style


LIGHT_STYLE = _style(
    APP_BG="#f6f8fb",
    SIDEBAR="#ffffff",
    SIDEBAR_BORDER="#dbe4ef",
    SIDEBAR_TEXT="#0f172a",
    SIDEBAR_MUTED="#536174",
    SIDEBAR_INPUT="#f8fbff",
    SIDEBAR_INPUT_TEXT="#0f172a",
    SIDEBAR_BUTTON="#f8fbff",
    SIDEBAR_BUTTON_BORDER="#d9e2ee",
    SIDEBAR_BUTTON_HOVER="#eef4fb",
    PANEL="#ffffff",
    HERO="#ffffff",
    SCOPE="#f7fbff",
    INPUT="#ffffff",
    LIST_BG="#fbfdff",
    DETAIL_BG="#fbfdff",
    TEXT="#111827",
    MUTED="#4b5b70",
    PLACEHOLDER="#64748b",
    BORDER="#d6e0ec",
    ACCENT="#7c3aed",
    ACCENT_HOVER="#6d28d9",
    SCAN="#111827",
    SCAN_HOVER="#293241",
    BUTTON="#ffffff",
    BUTTON_HOVER="#f2f6fb",
    BUTTON_BORDER="#d6e0ec",
    BUTTON_TEXT="#111827",
    TAB="#edf3fa",
    SELECT="#ede9fe",
    SELECT_TEXT="#1e1b4b",
    PILL_BG="#eefdf5",
    PILL_TEXT="#066145",
    PILL_BORDER="#b7f0d0",
    DANGER_BG="#fff7ed",
    DANGER_HOVER="#ffedd5",
    DANGER_BORDER="#fed7aa",
    DANGER_TEXT="#9a3412",
    CHECK_BG="#ffffff",
    CHECK_BORDER="#aab7c7",
    SWITCH_LIGHT="#fff7ed",
    SWITCH_DARK="#1e293b",
    CONTROL_BUTTON="#f3f7fb",
    CHECK_ICON=(APP_DIR / "assets" / "icons" / "check-light.svg").as_posix(),
    SUN_ICON=(APP_DIR / "assets" / "icons" / "sun.svg").as_posix(),
    MOON_ICON=(APP_DIR / "assets" / "icons" / "moon.svg").as_posix(),
    CHEVRON_ICON=(APP_DIR / "assets" / "icons" / "chevron-down-dark.svg").as_posix(),
    CALENDAR_ICON=(APP_DIR / "assets" / "icons" / "calendar-dark.svg").as_posix(),
)

DARK_STYLE = _style(
    APP_BG="#0b0f14",
    SIDEBAR="#0f172a",
    SIDEBAR_BORDER="#1e293b",
    SIDEBAR_TEXT="#f8fafc",
    SIDEBAR_MUTED="#94a3b8",
    SIDEBAR_INPUT="#111827",
    SIDEBAR_INPUT_TEXT="#f8fafc",
    SIDEBAR_BUTTON="#172033",
    SIDEBAR_BUTTON_BORDER="#263449",
    SIDEBAR_BUTTON_HOVER="#1e2a42",
    PANEL="#111821",
    HERO="#121b26",
    SCOPE="#101923",
    INPUT="#0d141c",
    LIST_BG="#0d141c",
    DETAIL_BG="#0d141c",
    TEXT="#e5eef7",
    MUTED="#9fb0c3",
    PLACEHOLDER="#7f8fa3",
    BORDER="#243244",
    ACCENT="#60a5fa",
    ACCENT_HOVER="#3b82f6",
    SCAN="#60a5fa",
    SCAN_HOVER="#3b82f6",
    BUTTON="#151f2b",
    BUTTON_HOVER="#1b2938",
    BUTTON_BORDER="#2a3a4f",
    BUTTON_TEXT="#e5eef7",
    TAB="#101720",
    SELECT="#1d4ed8",
    SELECT_TEXT="#ffffff",
    PILL_BG="#0b2a1d",
    PILL_TEXT="#86efac",
    PILL_BORDER="#14532d",
    DANGER_BG="#2a170d",
    DANGER_HOVER="#431f0d",
    DANGER_BORDER="#7c2d12",
    DANGER_TEXT="#fdba74",
    CHECK_BG="#0d141c",
    CHECK_BORDER="#44546a",
    SWITCH_LIGHT="#fff7ed",
    SWITCH_DARK="#0b1220",
    CONTROL_BUTTON="#111b26",
    CHECK_ICON=(APP_DIR / "assets" / "icons" / "check-light.svg").as_posix(),
    SUN_ICON=(APP_DIR / "assets" / "icons" / "sun.svg").as_posix(),
    MOON_ICON=(APP_DIR / "assets" / "icons" / "moon.svg").as_posix(),
    CHEVRON_ICON=(APP_DIR / "assets" / "icons" / "chevron-down-light.svg").as_posix(),
    CALENDAR_ICON=(APP_DIR / "assets" / "icons" / "calendar-light.svg").as_posix(),
)


class ScanSignals(QObject):
    log = Signal(str)
    summary_ready = Signal(list, str)
    report_ready = Signal(list, str)
    status = Signal(str)
    warning = Signal(str)
    error = Signal(str)
    report_error = Signal(str)
    notify = Signal(str, str)
    finished = Signal()
    avatars_updated = Signal()


class ReportPopup(QDialog):
    def __init__(self, parent: "MailPilotWindow") -> None:
        super().__init__(parent)
        self.parent_window = parent
        self.setObjectName("ReportPopup")
        if APP_ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(APP_ICON_PATH)))
        self.setWindowTitle("MailPilot Genel Özet")
        self.resize(760, 560)

        shell = QVBoxLayout(self)
        shell.setContentsMargins(18, 18, 18, 18)
        panel = QFrame()
        panel.setObjectName("ReportPopupPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel("Genel Özet")
        title.setObjectName("Title")
        open_button = QPushButton("Uygulamayı Aç")
        open_button.setObjectName("PrimaryButton")
        open_button.setIcon(_icon("open-app.svg"))
        open_button.setIconSize(QSize(18, 18))
        open_button.clicked.connect(self.open_main_app)
        header.addWidget(title)
        header.addStretch()
        self.account_widget = self._build_account_widget()
        header.addWidget(self.account_widget)
        header.addWidget(open_button)

        self.summary = QTextEdit()
        self.summary.setObjectName("ReportSummary")
        self.summary.setReadOnly(True)
        self.summary.setPlainText("Mailler taranıyor...")
        layout.addLayout(header)
        layout.addWidget(self.summary, 1)
        shell.addWidget(panel)

    def _build_account_widget(self) -> QWidget:
        accounts = self.parent_window.settings.email_accounts
        if len(accounts) <= 1:
            row = QWidget()
            layout = QHBoxLayout(row)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(8)
            if accounts:
                email = accounts[0].get("email", "Mail hesabı")
                icon = QLabel()
                icon.setPixmap(self.parent_window._account_icon(accounts[0]).pixmap(28, 28))
                text = QLabel(email)
                text.setObjectName("HelpText")
                layout.addWidget(icon)
                layout.addWidget(text)
            else:
                text = QLabel("Mail hesabı yok")
                text.setObjectName("HelpText")
                layout.addWidget(text)
            return row
        combo = QComboBox()
        for account in accounts:
            email = account.get("email", "mail")
            combo.addItem(self.parent_window._account_icon(account), email, account.get("id"))
        combo.setCurrentIndex(max(0, combo.findData(self.parent_window.settings.active_account_id)))
        combo.currentIndexChanged.connect(lambda: self.parent_window.on_report_account_changed(combo.currentData()))
        return combo

    def set_summary(self, html_body: str) -> None:
        self.summary.setHtml(html_body)

    def set_message(self, text: str) -> None:
        self.summary.setPlainText(text)

    def open_main_app(self) -> None:
        self.parent_window.showNormal()
        self.parent_window.raise_()
        self.parent_window.activateWindow()
        self.close()


class ElideLabel(QLabel):
    def __init__(self, text: str = "") -> None:
        super().__init__()
        self._full_text = text
        super().setText(text)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

    def set_full_text(self, text: str) -> None:
        self._full_text = text
        self._refresh_text()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._refresh_text()

    def _refresh_text(self) -> None:
        width = max(24, self.width())
        text = self.fontMetrics().elidedText(self._full_text, Qt.TextElideMode.ElideRight, width)
        super().setText(text)


def list_tag_object_name(tag: str) -> str:
    return {
        "Acil": "ListTagUrgent",
        "Cevap": "ListTagReply",
        "Fatura/Ödeme": "ListTagMoney",
        "Toplantı": "ListTagMeeting",
        "Güvenlik": "ListTagSecurity",
        "Onay": "ListTagApproval",
        "Bilgi": "ListTagInfo",
    }.get(tag, "ListTagInfo")


class ThemeSwitch(QWidget):
    toggled = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self._checked = False
        self._position = 0.0
        self.setFixedSize(74, 32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.animation = QPropertyAnimation(self, b"position", self)
        self.animation.setDuration(220)
        self.animation.setEasingCurve(QEasingCurve.Type.OutQuart)

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool) -> None:
        checked = bool(checked)
        if self._checked == checked:
            self._position = 1.0 if checked else 0.0
            self.update()
            return
        self._checked = checked
        self.animation.stop()
        self.animation.setStartValue(self._position)
        self.animation.setEndValue(1.0 if checked else 0.0)
        self.animation.start()
        self.toggled.emit(checked)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self.setChecked(not self._checked)
            event.accept()
            return
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(1, 1, self.width() - 2, self.height() - 2)
        dark_track = QColor("#0b1220")
        light_track = QColor("#fff7ed")
        border = QColor("#60a5fa" if self._checked else "#d6e0ec")
        painter.setPen(QPen(border, 1.2))
        painter.setBrush(dark_track if self._checked else light_track)
        painter.drawRoundedRect(rect, 16, 16)

        sun_center_x = 18
        sun_center_y = 16
        painter.setPen(QPen(QColor("#f59e0b"), 1.35))
        painter.setBrush(QColor("#fbbf24"))
        painter.drawEllipse(QRectF(sun_center_x - 3.8, sun_center_y - 3.8, 7.6, 7.6))
        for x1, y1, x2, y2 in (
            (18, 6, 18, 8),
            (18, 24, 18, 26),
            (8, 16, 10, 16),
            (26, 16, 28, 16),
            (11, 9, 12, 10),
            (24, 22, 25, 23),
            (11, 23, 12, 22),
            (24, 10, 25, 9),
        ):
            painter.drawLine(x1, y1, x2, y2)

        moon_color = QColor("#1d4ed8" if not self._checked else "#93c5fd")
        overlay_color = dark_track if self._checked else light_track
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(moon_color)
        painter.drawEllipse(QRectF(self.width() - 27, 8, 15, 15))
        painter.setBrush(overlay_color)
        painter.drawEllipse(QRectF(self.width() - 22, 5, 15, 15))

        knob_width = 31
        knob_height = 24
        knob_x = 4 + (self.width() - knob_width - 8) * self._position
        knob = QRectF(knob_x, 4, knob_width, knob_height)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#ffffff" if not self._checked else "#172033"))
        painter.drawRoundedRect(knob, 12, 12)

    def get_position(self) -> float:
        return self._position

    def set_position(self, value: float) -> None:
        self._position = max(0.0, min(1.0, float(value)))
        self.update()

    position = Property(float, get_position, set_position)


class MailListItemWidget(QWidget):
    def __init__(self, record: dict) -> None:
        super().__init__()
        self.setObjectName("MailListItem")
        self.setMinimumHeight(146)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(7)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(7)
        for tag in record.get("tags", [])[:3]:
            chip = QLabel(tag)
            chip.setObjectName(list_tag_object_name(tag))
            chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chip.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            header.addWidget(chip)

        self.subject = ElideLabel(("✓ " if record["completed"] else "") + record["subject"])
        self.subject.setObjectName("MailItemSubject")
        self.subject.setWordWrap(False)
        self.subject.setMinimumWidth(1)
        self.subject.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.subject.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        header.addWidget(self.subject, 1)

        if record.get("date"):
            date_chip = QLabel(record["date"])
            date_chip.setObjectName("DateChip")
            date_chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
            date_chip.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            header.addWidget(date_chip)

        self.meta = ElideLabel(f"Kimden: {record['sender']}")
        self.meta.setObjectName("MailItemMeta")
        self.meta.setWordWrap(False)
        self.meta.setMinimumWidth(1)
        self.meta.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.action = ElideLabel(f"Yapılacak: {record.get('action', '-')}")
        self.action.setObjectName("MailItemLine")
        self.action.setMinimumWidth(1)
        self.action.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.note = ElideLabel(f"Kısa not: {record.get('note', '-')}")
        self.note.setObjectName("MailItemLine")
        self.note.setMinimumWidth(1)
        self.note.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout.addLayout(header)
        layout.addWidget(self.meta)
        layout.addWidget(self.action)
        layout.addWidget(self.note)


class MailPilotWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("MailPilot")
        if APP_ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(APP_ICON_PATH)))
        self.resize(1180, 760)
        self.settings = Settings.load()
        self.records: list[dict] = []
        self.running_scan = False
        self.scan_thread: threading.Thread | None = None
        self.report_thread: threading.Thread | None = None
        self.report_popup: ReportPopup | None = None
        self.pending_daily_report_date: str | None = None
        self.daily_report_retry_after: datetime | None = None
        self.force_quit = False
        self.account_flow_active = False
        self.scan_started_at: datetime | None = None
        self.ran_slots: set[str] = set()
        self.loading = True
        self.signals = ScanSignals()
        self.signals.log.connect(self.write_log)
        self.signals.summary_ready.connect(self.show_records)
        self.signals.report_ready.connect(self.show_report_popup)
        self.signals.status.connect(self.set_status)
        self.signals.warning.connect(self.show_warning)
        self.signals.error.connect(self.show_error)
        self.signals.report_error.connect(self.show_report_error)
        self.signals.notify.connect(self.show_notification)
        self.signals.finished.connect(self.scan_finished)
        self.signals.avatars_updated.connect(self.refresh_account_picker)

        self._build_ui()
        self._build_tray()
        self._load_to_ui()
        self.loading = False
        self.apply_theme(self.settings.theme)
        self.scheduler = QTimer(self)
        self.scheduler.timeout.connect(self.check_schedule)
        self.scheduler.start(30_000)
        self.instance_command_timer = QTimer(self)
        self.instance_command_timer.timeout.connect(self.check_instance_restore_request)
        self.instance_command_timer.start(700)
        QTimer.singleShot(1_000, self.check_schedule)
        QTimer.singleShot(1_500, self.refresh_missing_avatars)

    def _build_ui(self) -> None:
        root = QWidget()
        self.root = root
        root.setObjectName("Root")
        shell = QHBoxLayout(root)
        shell.setContentsMargins(18, 18, 18, 18)
        shell.setSpacing(18)

        shell.addWidget(self._build_sidebar())
        shell.addWidget(self._build_workspace(), 1)
        self.setCentralWidget(root)
        self._build_toast(root)

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        self.sidebar = sidebar
        sidebar.setObjectName("Sidebar")
        self._elevate(sidebar, blur=28, y=10, alpha=45)
        sidebar.setFixedWidth(340)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(16)

        brand = QLabel("MailPilot")
        brand.setObjectName("Brand")
        brand.setFont(_safe_font("Orange Avenue DEMO", 36))
        muted = QLabel("Akıllı mail önceliklendirme ve aksiyon paneli.")
        muted.setObjectName("SidebarMuted")
        muted.setWordWrap(True)
        self.status_label = QLabel("Hazır")
        self.status_label.setObjectName("StatusPill")

        self.enabled_check = QCheckBox("Otomatik tarama açık")
        self.startup_check = QCheckBox("Windows ile başlat")
        self.start_minimized_check = QCheckBox("Başlangıçta simgede başlat")
        self.theme_switch = ThemeSwitch()
        self.theme_switch.toggled.connect(self.on_theme_switch_changed)

        self.save_button = self._button("Kaydet", "SmallGhostButton")
        self.scan_button = self._button("Mailleri Tara", "ScanButton")
        self.reset_button = self._button("Sıfırla", "DangerButton")
        self.summaries_button = self._button("Özetler", "SmallGhostButton")
        self.tray_button = self._button("Simgeye Al", "SmallGhostButton")
        self.settings_button = self._button("Ayarlar", "SettingsButton")
        self.save_button.setIcon(_icon("save.svg"))
        self.scan_button.setIcon(_icon("mail-search.svg"))
        self.reset_button.setIcon(_icon("reset.svg"))
        self.summaries_button.setIcon(_icon("folder.svg"))
        self.tray_button.setIcon(_icon("tray.svg"))
        self.settings_button.setIcon(_icon("settings.svg"))
        self.save_button.clicked.connect(self.save_settings)
        self.scan_button.clicked.connect(self.scan_now)
        self.reset_button.clicked.connect(self.reset_scan)
        self.summaries_button.clicked.connect(self.open_summaries)
        self.tray_button.clicked.connect(self.minimize_to_tray)
        self.settings_button.clicked.connect(self.toggle_settings_popover)

        layout.addWidget(brand)
        layout.addWidget(muted)
        layout.addWidget(self.status_label)
        layout.addSpacing(10)
        layout.addWidget(self.scan_button)
        actions_grid = QGridLayout()
        actions_grid.setHorizontalSpacing(8)
        actions_grid.setVerticalSpacing(8)
        actions_grid.addWidget(self.save_button, 0, 0)
        actions_grid.addWidget(self.reset_button, 0, 1)
        actions_grid.addWidget(self.summaries_button, 1, 0)
        actions_grid.addWidget(self.tray_button, 1, 1)
        layout.addLayout(actions_grid)
        layout.addStretch()

        self.report_scope_input = QComboBox()
        self.report_scope_input.addItem("Rapor: son taramadan beri", "since_last_scan")
        self.report_scope_input.addItem("Rapor: son 1 saat", "last_1h")
        self.report_scope_input.addItem("Rapor: son 6 saat", "last_6h")
        self.report_scope_input.addItem("Rapor: son 24 saat", "last_24h")
        self.report_test_button = self._button("Rapor Pop-up Test", "GhostButton")
        self.report_test_button.setIcon(_icon("popup.svg"))
        self.report_test_button.clicked.connect(self.test_report_popup)
        self.account_input = QComboBox()
        self.account_input.setMinimumWidth(270)
        self.account_input.view().setMinimumWidth(285)
        self.account_input.currentIndexChanged.connect(self.on_account_changed)
        self.last_scan_label = QLabel()
        self.last_scan_label.setObjectName("SidebarMuted")
        self.last_scan_label.setTextFormat(Qt.TextFormat.RichText)
        account_row = QHBoxLayout()
        account_row.setSpacing(8)
        account_row.addWidget(self.account_input, 1)
        layout.addLayout(account_row)
        layout.addWidget(self.settings_button)
        layout.addWidget(self.last_scan_label)
        self.settings_popover = self._build_settings_popover(sidebar)
        self.settings_popover.hide()
        self.account_popover = self._build_account_popover(sidebar)
        self.account_popover.hide()
        return sidebar

    def _build_settings_popover(self, parent: QWidget) -> QFrame:
        popover = QFrame(parent)
        popover.setObjectName("SettingsPopover")
        popover.setFixedSize(242, 330)
        layout = QVBoxLayout(popover)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        title = QLabel("Ayarlar")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)
        theme_row = QHBoxLayout()
        theme_row.setContentsMargins(0, 0, 0, 0)
        theme_row.setSpacing(10)
        theme_row.addWidget(self.theme_switch)
        theme_label = QLabel("Tema")
        theme_label.setObjectName("HelpText")
        theme_row.addWidget(theme_label)
        theme_row.addStretch()
        layout.addLayout(theme_row)
        layout.addWidget(self.enabled_check)
        layout.addWidget(self.startup_check)
        layout.addWidget(self.start_minimized_check)
        layout.addSpacing(4)
        layout.addWidget(self._sidebar_label("Mini rapor"))
        layout.addWidget(self.report_scope_input)
        layout.addWidget(self.report_test_button)
        layout.addStretch()
        return popover

    def _build_account_popover(self, parent: QWidget) -> QFrame:
        popover = QFrame(parent)
        popover.setObjectName("SettingsPopover")
        popover.setFixedSize(242, 150)
        layout = QVBoxLayout(popover)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        title = QLabel("Mail hesabı ekle")
        title.setObjectName("SectionTitle")
        self.add_gmail_button = self._button("Gmail ekle", "GhostButton")
        self.add_gmail_button.setIcon(QIcon((APP_DIR / "assets" / "icons" / "gmail.svg").as_posix()))
        self.add_gmail_button.clicked.connect(self.add_gmail_account_from_ui)
        self.add_outlook_button = self._button("Outlook ekle", "GhostButton")
        self.add_outlook_button.setIcon(QIcon((APP_DIR / "assets" / "icons" / "outlook.svg").as_posix()))
        self.add_outlook_button.clicked.connect(self.add_outlook_account_from_ui)
        layout.addWidget(title)
        layout.addWidget(self.add_gmail_button)
        layout.addWidget(self.add_outlook_button)
        return popover

    def toggle_settings_popover(self) -> None:
        self.account_popover.hide()
        if self.settings_popover.isVisible():
            self.close_settings_popover(animated=True)
            return
        self.open_settings_popover()

    def toggle_account_popover(self) -> None:
        self.settings_popover.hide()
        self._position_account_popover()
        self.account_popover.setVisible(not self.account_popover.isVisible())
        self.account_popover.raise_()

    def open_settings_popover(self) -> None:
        self._position_settings_popover()
        self.settings_popover.show()
        self.settings_popover.raise_()

    def close_settings_popover(self, animated: bool = True) -> None:
        del animated
        if not hasattr(self, "settings_popover") or not self.settings_popover.isVisible():
            return
        self.settings_popover.hide()

    def _position_settings_popover(self) -> None:
        if not hasattr(self, "settings_popover"):
            return
        margin = 22
        x = margin
        y = max(margin, self.sidebar.height() - self.settings_popover.height() - 86)
        self.settings_popover.move(x, y)

    def _position_account_popover(self) -> None:
        if not hasattr(self, "account_popover"):
            return
        margin = 22
        x = margin
        y = max(margin, self.sidebar.height() - self.account_popover.height() - 148)
        self.account_popover.move(x, y)

    def refresh_account_picker(self) -> None:
        self.account_input.blockSignals(True)
        self.account_input.clear()
        self._ensure_default_account()
        accounts = self.settings.email_accounts
        self.account_input.setEnabled(True)
        for account in accounts:
            email = account.get("email", "mail")
            self.account_input.addItem(self._account_icon(account), email, account.get("id"))
        self.account_input.insertSeparator(self.account_input.count())
        self.account_input.addItem(_icon("plus.svg"), "E-posta ekle", ADD_ACCOUNT_ITEM)
        active = self.settings.active_account_id
        index = self.account_input.findData(active)
        if index < 0 and accounts:
            index = 0
            self.settings.active_account_id = accounts[0].get("id")
            self.settings.save()
        self.account_input.setCurrentIndex(index if index >= 0 else self.account_input.count() - 1)
        self.account_input.setMaxVisibleItems(max(4, self.account_input.count()))
        self.account_input.blockSignals(False)

    def _ensure_default_account(self) -> None:
        if self.settings.email_accounts or not (CREDENTIALS_DIR / "token.json").exists():
            return
        try:
            account = ensure_default_gmail_account(self.settings)
        except Exception:
            return
        if account:
            self.write_log(f"Gmail hesabı bağlandı: {account.get('email')}")

    def _account_icon(self, account: dict[str, str] | str) -> QIcon:
        if isinstance(account, dict):
            email = account.get("email", "mail")
            avatar_path = account.get("avatar_path")
        else:
            email = account
            avatar_path = None
        if avatar_path and os.path.exists(avatar_path):
            avatar = QPixmap(avatar_path)
            if not avatar.isNull():
                size = 28
                source = avatar.scaled(
                    size,
                    size,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
                pixmap = QPixmap(size, size)
                pixmap.fill(Qt.GlobalColor.transparent)
                painter = QPainter(pixmap)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                path = QPainterPath()
                path.addEllipse(0, 0, size, size)
                painter.setClipPath(path)
                x = (size - source.width()) // 2
                y = (size - source.height()) // 2
                painter.drawPixmap(x, y, source)
                painter.end()
                return QIcon(pixmap)

        letter = (email.strip()[:1] or "M").upper()
        colors = ["#60a5fa", "#a78bfa", "#34d399", "#f59e0b", "#f472b6"]
        color = colors[sum(ord(ch) for ch in email) % len(colors)]
        pixmap = QPixmap(28, 28)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        painter.drawEllipse(1, 1, 26, 26)
        painter.setPen(QColor("#ffffff"))
        painter.setFont(_safe_font("Segoe UI", 11, QFont.Weight.Bold))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, letter)
        painter.end()
        return QIcon(pixmap)

    def refresh_missing_avatars(self) -> None:
        if not self.settings.email_accounts:
            return
        threading.Thread(target=self._refresh_missing_avatars_worker, daemon=True).start()

    def _refresh_missing_avatars_worker(self) -> None:
        updated = False
        for account in list(self.settings.email_accounts):
            if account.get("avatar_path") and os.path.exists(account["avatar_path"]):
                continue
            try:
                updated = ensure_account_avatar(self.settings, account) or updated
            except Exception:
                continue
        if updated:
            self.signals.avatars_updated.emit()

    def add_gmail_account_from_ui(self) -> None:
        self.account_popover.hide()
        self.account_flow_active = True
        try:
            account = add_gmail_account(self.settings)
        except Exception as exc:
            self.show_error(str(exc))
            return
        finally:
            self.account_flow_active = False
        self.refresh_account_picker()
        self.write_log(f"Gmail hesabı eklendi: {account.get('email')}")
        self.scan_now()

    def add_outlook_account_from_ui(self) -> None:
        self.account_popover.hide()
        self.account_flow_active = True
        try:
            account = add_outlook_account(self.settings)
        except OutlookDeviceLogin as login:
            QMessageBox.information(
                self,
                "MailPilot Outlook",
                f"Tarayıcıda Outlook girişini tamamla.\n\nKod: {login.device.get('user_code', '-')}\n\nGiriş bitince Tamam'a bas.",
            )
            try:
                account = finish_outlook_device_login(self.settings, login.device, login.client_id, login.tenant)
            except Exception as exc:
                self.show_error(str(exc))
                return
        except Exception as exc:
            self.show_error(str(exc))
            return
        finally:
            self.account_flow_active = False
        self.refresh_account_picker()
        self.write_log(f"Outlook hesabı eklendi: {account.get('email')}")
        self.scan_now()

    def on_account_changed(self) -> None:
        if self.loading or not self.account_input.isEnabled():
            return
        account_id = self.account_input.currentData()
        if account_id == ADD_ACCOUNT_ITEM:
            active_index = self.account_input.findData(self.settings.active_account_id)
            self.account_input.blockSignals(True)
            self.account_input.setCurrentIndex(active_index if active_index >= 0 else 0)
            self.account_input.blockSignals(False)
            self.toggle_account_popover()
            return
        if not account_id or account_id == self.settings.active_account_id:
            return
        self.settings.active_account_id = account_id
        self.settings.save()
        self.write_log("Aktif mail hesabı değişti, tarama başlatılıyor.")
        self.scan_now()

    def on_report_account_changed(self, account_id: str | None) -> None:
        if not account_id or account_id == self.settings.active_account_id:
            return
        self.settings.active_account_id = account_id
        self.settings.save()
        self.refresh_account_picker()
        self.start_report_popup_scan(force=True)

    def _build_workspace(self) -> QWidget:
        workspace = QWidget()
        layout = QVBoxLayout(workspace)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        hero = QFrame()
        hero.setObjectName("Hero")
        self._elevate(hero, blur=24, y=8, alpha=22)
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(20, 14, 20, 14)
        hero_layout.setSpacing(14)

        title_box = QVBoxLayout()
        eyebrow = QLabel("Gelen Kutusu Kontrol Merkezi")
        eyebrow.setObjectName("Eyebrow")
        title = QLabel("Bugün gerçekten neye bakman gerekiyor?")
        title.setObjectName("Title")
        title.setWordWrap(True)
        help_text = QLabel("Kapsamı seç, takvimden aralığı belirle, önemli mailleri tek ekranda yönet.")
        help_text.setObjectName("HelpText")
        title_box.addWidget(eyebrow)
        title_box.addWidget(title)
        title_box.addWidget(help_text)

        self.action_metric = self._metric("0", "Aksiyon")
        self.important_metric = self._metric("0", "Önemli")
        self.total_metric = self._metric("0", "Mail")
        hero_layout.addLayout(title_box, 1)
        hero_layout.addWidget(self.action_metric)
        hero_layout.addWidget(self.important_metric)
        hero_layout.addWidget(self.total_metric)
        layout.addWidget(hero)

        controls = QHBoxLayout()
        controls.setSpacing(14)
        controls.addWidget(self._build_scope_card(), 3)
        controls.addWidget(self._build_automation_card(), 2)
        layout.addLayout(controls)
        layout.addWidget(self._build_content(), 1)
        return workspace

    def _build_scope_card(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("ScopeCard")
        self._elevate(panel, blur=18, y=6, alpha=16)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        section = QLabel("Tarama kapsamı")
        section.setObjectName("SectionTitle")
        hint = QLabel("Tarama modu ve tarih seçimi artık tek sistemde çalışır")
        hint.setObjectName("HelpText")
        header.addWidget(section)
        header.addWidget(hint)
        header.addStretch()
        layout.addLayout(header)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(12)

        self.scope_input = QComboBox()
        self.scope_input.addItem("Son taramadan beri", "since_last_scan")
        self.scope_input.addItem("Son X saat", "lookback_window")
        self.scope_input.addItem("Tek gün", "single_day")
        self.scope_input.addItem("Tarih aralığı", "date_range")
        self.scope_input.setFixedWidth(270)
        self.scope_input.view().setMinimumWidth(270)
        self.scope_input.currentIndexChanged.connect(self.update_scope_fields)
        self.lookback_input = QSpinBox()
        self.lookback_input.setRange(1, 720)
        self.lookback_input.setFixedWidth(120)
        self.max_input = QSpinBox()
        self.max_input.setRange(1, 100)
        self.max_input.setFixedWidth(110)
        self.single_date_input = self._date_input()
        self.range_start_input = self._date_input()
        self.range_end_input = self._date_input()

        self._add_field(grid, 0, 0, "Kapsam", self.scope_input)
        self.lookback_box = self._field_box("Saat aralığı", self.lookback_input)
        grid.addLayout(self.lookback_box, 0, 1)
        self.single_date_box = self._field_box("Takvim", self.single_date_input)
        grid.addLayout(self.single_date_box, 0, 1)
        range_box = QHBoxLayout()
        self.range_start_box = self._field_box("Başlangıç", self.range_start_input)
        self.range_end_box = self._field_box("Bitiş", self.range_end_input)
        range_box.addLayout(self.range_start_box)
        range_box.addLayout(self.range_end_box)
        grid.addLayout(range_box, 0, 1)
        self._add_field(grid, 0, 2, "Mail limiti", self.max_input)
        layout.addLayout(grid)
        return panel

    def _build_automation_card(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("Panel")
        self._elevate(panel, blur=18, y=6, alpha=14)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        section = QLabel("Rutinler")
        section.setObjectName("SectionTitle")
        hint = QLabel("Otomatik özet saatleri, günlük rapor ve önemli gönderenler")
        hint.setObjectName("HelpText")
        header.addWidget(section)
        header.addWidget(hint)
        header.addStretch()
        layout.addLayout(header)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(12)
        self.times_input = QLineEdit()
        self.times_input.setFixedWidth(150)
        self.daily_report_input = QLineEdit()
        self.daily_report_input.setFixedWidth(120)
        self.priority_senders_input = QLineEdit()
        self.priority_senders_input.setFixedWidth(220)
        self.priority_senders_input.setPlaceholderText("ör. banka.com, patron@")
        self._add_field(grid, 0, 0, "Özet saatleri", self.times_input)
        self._add_field(grid, 0, 1, "Günlük rapor", self.daily_report_input)
        self._add_field(grid, 0, 2, "Önemli gönderenler", self.priority_senders_input)
        layout.addLayout(grid)
        return panel

    def _build_content(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("Panel")
        self._elevate(panel, blur=20, y=8, alpha=16)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        self.tabs = QTabWidget()
        self.summary_tab = QWidget()
        summary_layout = QVBoxLayout(self.summary_tab)
        summary_layout.setContentsMargins(0, 10, 0, 0)
        summary_layout.setSpacing(16)

        toolbar = QHBoxLayout()
        title = QLabel("Özet")
        title.setObjectName("SectionTitle")
        self.filter_input = QComboBox()
        self.filter_input.addItems(FILTERS)
        self.filter_input.currentTextChanged.connect(self.refresh_summary_view)
        self.open_button = self._button("Gmail'de Aç")
        self.done_button = self._button("Tamamlandı")
        self.open_button.clicked.connect(self.open_selected_mail)
        self.done_button.clicked.connect(self.mark_selected_completed)
        toolbar.addWidget(title)
        toolbar.addStretch()
        self.filter_label = QLabel("Filtre")
        toolbar.addWidget(self.filter_label)
        toolbar.addWidget(self.filter_input)
        toolbar.addWidget(self.open_button)
        toolbar.addWidget(self.done_button)
        summary_layout.addLayout(toolbar)

        mode_row = QHBoxLayout()
        mode_row.setContentsMargins(0, 0, 0, 4)
        mode_row.setSpacing(8)
        self.general_mode_button = self._button("Genel Özet", "ModeButton")
        self.detail_mode_button = self._button("Detaylı Özet", "ModeButton")
        self.general_mode_button.setCheckable(True)
        self.detail_mode_button.setCheckable(True)
        self.general_mode_button.clicked.connect(lambda: self.set_summary_mode(0))
        self.detail_mode_button.clicked.connect(lambda: self.set_summary_mode(1))
        mode_row.addWidget(self.general_mode_button)
        mode_row.addWidget(self.detail_mode_button)
        mode_row.addStretch()
        summary_layout.addLayout(mode_row)

        self.summary_modes = QStackedWidget()
        self.general_summary = QTextEdit()
        self.general_summary.setObjectName("GeneralSummary")
        self.general_summary.setReadOnly(True)
        self.detail_frame = QFrame()
        self.detail_frame.setObjectName("DetailFrame")
        detail_frame_layout = QVBoxLayout(self.detail_frame)
        detail_frame_layout.setContentsMargins(1, 1, 1, 1)
        detail_frame_layout.setSpacing(0)
        self.detail_scroll = QScrollArea()
        self.detail_scroll.setObjectName("DetailScroll")
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.detail_scroll.viewport().setAutoFillBackground(False)
        self.detail_scroll.viewport().setStyleSheet("background: transparent;")
        self.detail_container = QWidget()
        self.detail_container.setObjectName("DetailContainer")
        self.detail_layout = QVBoxLayout(self.detail_container)
        self.detail_layout.setContentsMargins(18, 18, 18, 18)
        self.detail_layout.setSpacing(14)
        self.detail_scroll.setWidget(self.detail_container)
        detail_frame_layout.addWidget(self.detail_scroll)

        self.detail_tab = QWidget()
        detail_tab_layout = QVBoxLayout(self.detail_tab)
        detail_tab_layout.setContentsMargins(0, 0, 0, 0)
        detail_tab_layout.setSpacing(0)
        self.summary_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.mail_list = QListWidget()
        self.mail_list.setObjectName("MailList")
        self.mail_list.currentItemChanged.connect(self.update_selected_detail)
        self.summary_splitter.addWidget(self.mail_list)
        self.summary_splitter.addWidget(self.detail_frame)
        self.summary_splitter.setStretchFactor(0, 3)
        self.summary_splitter.setStretchFactor(1, 5)
        detail_tab_layout.addWidget(self.summary_splitter, 1)

        self.summary_modes.addWidget(self.general_summary)
        self.summary_modes.addWidget(self.detail_tab)
        summary_layout.addWidget(self.summary_modes, 1)
        self.summary_modes.currentChanged.connect(self.on_summary_mode_changed)
        self.set_summary_mode(0)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setObjectName("DetailPanel")
        self.tabs.addTab(self.summary_tab, "Özet")
        self.tabs.addTab(self.log, "Log")
        layout.addWidget(self.tabs, 1)
        return panel

    def _date_input(self) -> QDateEdit:
        widget = QDateEdit()
        widget.setCalendarPopup(True)
        widget.setDisplayFormat("dd.MM.yyyy")
        widget.setDate(QDate.currentDate())
        widget.setLocale(QLocale(QLocale.Language.Turkish, QLocale.Country.Turkey))
        widget.setFixedWidth(220)
        widget.calendarWidget().setLocale(QLocale(QLocale.Language.Turkish, QLocale.Country.Turkey))
        widget.calendarWidget().setGridVisible(False)
        widget.calendarWidget().setMinimumSize(300, 280)
        return widget

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(self)
        icon = _tray_icon()
        if icon.isNull():
            icon = self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation)
        self.tray.setIcon(icon)
        self.tray.setToolTip("MailPilot")
        menu = QMenu(self)
        show_action = QAction("MailPilot'u Aç", self)
        show_action.setIcon(_icon("open-app.svg"))
        show_action.triggered.connect(self.restore_from_tray)
        report_action = QAction("Rapor Pop-up Test", self)
        report_action.setIcon(_icon("popup.svg"))
        report_action.triggered.connect(self.test_report_popup)
        quit_action = QAction("Çıkış", self)
        quit_action.triggered.connect(self.quit_app)
        menu.addAction(show_action)
        menu.addAction(report_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.on_tray_activated)
        self.tray.show()

    def _metric(self, value: str, label: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName("Metric")
        frame.setFixedSize(112, 102)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        value_label = QLabel(value)
        value_label.setObjectName("MetricValue")
        value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text_label = QLabel(label)
        text_label.setObjectName("MetricLabel")
        text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        value_font = _safe_font("Orange Avenue DEMO", 28)
        value_label.setFont(value_font)
        layout.addWidget(value_label)
        layout.addWidget(text_label)
        frame.value_label = value_label
        return frame

    def _button(self, text: str, object_name: str | None = None) -> QPushButton:
        button = QPushButton(text)
        if object_name:
            button.setObjectName(object_name)
        button.setIconSize(QSize(18, 18))
        button.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        return button

    def _build_toast(self, parent: QWidget) -> None:
        self.toast = QFrame(parent)
        self.toast.setObjectName("Toast")
        self.toast.setFixedSize(310, 92)
        layout = QHBoxLayout(self.toast)
        layout.setContentsMargins(16, 12, 10, 12)
        layout.setSpacing(10)
        text_box = QVBoxLayout()
        text_box.setSpacing(3)
        self.toast_title = QLabel()
        self.toast_title.setObjectName("ToastTitle")
        self.toast_text = QLabel()
        self.toast_text.setObjectName("ToastText")
        self.toast_text.setWordWrap(True)
        text_box.addWidget(self.toast_title)
        text_box.addWidget(self.toast_text)
        close_button = QPushButton("×")
        close_button.setObjectName("ToastClose")
        close_button.setFixedSize(28, 28)
        close_button.clicked.connect(self.hide_toast)
        layout.addLayout(text_box, 1)
        layout.addWidget(close_button, 0, Qt.AlignmentFlag.AlignTop)
        self.toast_timer = QTimer(self)
        self.toast_timer.setSingleShot(True)
        self.toast_timer.timeout.connect(self.hide_toast)
        self.toast.hide()

    def _position_toast(self) -> None:
        if not hasattr(self, "toast"):
            return
        margin = 18
        self.toast.move(
            max(margin, self.root.width() - self.toast.width() - margin),
            max(margin, self.root.height() - self.toast.height() - margin),
        )

    def show_toast(self, title: str, text: str) -> None:
        self.toast_title.setText(title)
        self.toast_text.setText(text)
        self._position_toast()
        self.toast.raise_()
        self.toast.show()
        self.toast_timer.start(20_000)

    def hide_toast(self) -> None:
        if hasattr(self, "toast"):
            self.toast.hide()

    def _elevate(self, widget: QWidget, blur: int, y: int, alpha: int) -> None:
        shadow = QGraphicsDropShadowEffect(widget)
        shadow.setBlurRadius(blur)
        shadow.setOffset(0, y)
        shadow.setColor(QColor(15, 23, 42, alpha))
        widget.setGraphicsEffect(shadow)

    def _sidebar_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("SidebarMuted")
        return label

    def _add_field(self, grid: QGridLayout, row: int, column: int, label: str, widget: QWidget, span: int = 1) -> None:
        grid.addLayout(self._field_box(label, widget), row, column, 1, span)

    def _field_box(self, label: str, widget: QWidget) -> QVBoxLayout:
        box = QVBoxLayout()
        label_widget = QLabel(label)
        label_widget.setObjectName("HelpText")
        box.addWidget(label_widget)
        box.addWidget(widget)
        return box

    def _load_to_ui(self) -> None:
        self.enabled_check.setChecked(self.settings.enabled)
        self.startup_check.setChecked(startup_is_enabled())
        self.start_minimized_check.setChecked(self.settings.start_minimized_to_tray)
        self.times_input.setText(", ".join(self.settings.summary_times))
        scope = self._scope_from_settings()
        self.scope_input.setCurrentIndex(max(0, self.scope_input.findData(scope)))
        self.lookback_input.setValue(self.settings.lookback_hours)
        self.max_input.setValue(self.settings.max_messages)
        self.daily_report_input.setText(self.settings.daily_report_time)
        self.report_scope_input.setCurrentIndex(max(0, self.report_scope_input.findData(self.settings.report_scan_mode)))
        self.priority_senders_input.setText(", ".join(self.settings.priority_senders))
        self.single_date_input.setDate(self._qdate(self.settings.single_scan_date))
        self.range_start_input.setDate(self._qdate(self.settings.range_start_date))
        self.range_end_input.setDate(self._qdate(self.settings.range_end_date))
        self.theme_switch.setChecked(self.settings.theme == "dark")
        self.refresh_account_picker()
        self.update_scope_fields()
        self.refresh_status_labels()
        self.set_general_summary(render_general_summary_html([], "Hepsi"))
        self.render_detail_cards([])
        self.on_summary_mode_changed()
        self.write_log("Hazır. İlk kullanımda credentials.json gerekli.")

    def save_settings(self, show_feedback: bool = True) -> bool:
        try:
            self.settings.enabled = self.enabled_check.isChecked()
            self.settings.start_with_windows = self.startup_check.isChecked()
            self.settings.start_minimized_to_tray = self.start_minimized_check.isChecked()
            self.settings.summary_times = parse_times(self.times_input.text())
            self._apply_scope_to_settings()
            self.settings.lookback_hours = self.lookback_input.value()
            self.settings.max_messages = self.max_input.value()
            self.settings.daily_report_time = parse_single_time(self.daily_report_input.text())
            self.settings.report_scan_mode = self.report_scope_input.currentData()
            if self.account_input.count() and self.account_input.currentData() != ADD_ACCOUNT_ITEM:
                self.settings.active_account_id = self.account_input.currentData()
            self.settings.priority_senders = parse_priority_senders(self.priority_senders_input.text())
            self.settings.single_scan_date = parse_date_value(self.single_date_input.date().toString("yyyy-MM-dd"))
            self.settings.range_start_date = parse_date_value(self.range_start_input.date().toString("yyyy-MM-dd"))
            self.settings.range_end_date = parse_date_value(self.range_end_input.date().toString("yyyy-MM-dd"))
            self.settings.theme = "dark" if self.theme_switch.isChecked() else "light"
            self.settings.save()
            set_startup_enabled(self.settings.start_with_windows, RUNTIME_DIR)
        except Exception as exc:
            QMessageBox.critical(self, "MailPilot", str(exc))
            return False
        self.set_status("Ayarlar kaydedildi")
        self.refresh_status_labels()
        self.write_log("Ayarlar kaydedildi.")
        if show_feedback:
            self.show_toast("Ayarlar kaydedildi", "Değişiklikler uygulandı.")
        return True

    def scan_now(self) -> None:
        if not self.save_settings(show_feedback=False):
            return
        self._sync_scan_state()
        if self.running_scan:
            self.write_log(f"Tarama devam ediyor ({self._scan_elapsed_text()}). Takıldıysa Taramayı Sıfırla'ya bas.")
            self.set_status("Tarama devam ediyor")
            return
        self.running_scan = True
        self.scan_started_at = datetime.now()
        self.set_status("Taranıyor")
        self.scan_thread = threading.Thread(target=self._scan_worker, daemon=True)
        self.scan_thread.start()

    def reset_scan(self) -> None:
        self.running_scan = False
        self.scan_started_at = None
        self.scan_thread = None
        self.show_toast("Tarama sıfırlandı", "Takıldıysa artık tekrar tarama başlatabilirsin.")
        self.set_status("Tarama sıfırlandı")
        self.write_log("Tarama durumu sıfırlandı. Şimdi tekrar tarayabilirsin.")

    def _scan_worker(self) -> None:
        self.signals.log.emit("Gmail taraması başladı.")
        try:
            messages = fetch_messages(self.settings)
            records = analyze_messages(
                messages,
                priority_senders=self.settings.priority_senders,
                completed_ids=self.settings.completed_message_ids,
            )
            summary = render_summary(records)
            filename = datetime.now().strftime("%Y-%m-%d_%H-%M-%S.txt")
            output = summaries_path() / filename
            output.write_text(summary, encoding="utf-8")
            self.settings.mark_scanned_now()
            open_actions = len([item for item in records if item["section"] == "Yapılacak" and not item["completed"]])
            important = len([item for item in records if item["score"] >= 30 and not item["completed"]])
            self.signals.status.emit("Özet hazır")
            self.signals.summary_ready.emit(records, summary)
            self.signals.notify.emit("MailPilot özeti", f"{important} önemli mail, {open_actions} aksiyon var.")
            self.signals.log.emit(f"Özet hazır: {output}")
        except GmailNotReady as exc:
            message = str(exc)
            self.signals.status.emit("Gmail hazır değil")
            self.signals.log.emit(message)
            self.signals.warning.emit(message)
        except Exception as exc:
            message = str(exc)
            self.signals.status.emit("Hata")
            self.signals.log.emit(f"Hata: {message}")
            self.signals.error.emit(message)
        finally:
            self.signals.finished.emit()

    def show_records(self, records: list[dict], summary: str) -> None:
        self.records = records
        self.update_metrics()
        self.refresh_summary_view()
        if not records:
            self.set_general_summary(render_general_summary_html(records, self.filter_input.currentText()))
            self.render_detail_cards([])
        else:
            self.set_general_summary(render_general_summary_html(records, self.filter_input.currentText()))
        self.tabs.setCurrentWidget(self.summary_tab)

    def refresh_summary_view(self) -> None:
        selected_id = self.current_record_id()
        self.mail_list.clear()
        filtered = filter_records(self.records, self.filter_input.currentText())
        for record in filtered:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, record["id"])
            item.setSizeHint(QSize(0, 158))
            widget = MailListItemWidget(record)
            self.mail_list.addItem(item)
            self.mail_list.setItemWidget(item, widget)
            if record["id"] == selected_id:
                self.mail_list.setCurrentItem(item)
        if self.mail_list.count() and self.mail_list.currentRow() < 0:
            self.mail_list.setCurrentRow(0)
        selected = self.current_record()
        if not self.mail_list.count():
            self.set_general_summary(render_general_summary_html(self.records, self.filter_input.currentText()))
            self.render_detail_cards([])
        else:
            self.set_general_summary(render_general_summary_html(self.records, self.filter_input.currentText()))
            self.render_detail_cards([selected] if selected else filtered)

    def set_general_summary(self, body: str) -> None:
        dark = self.theme_switch.isChecked() if hasattr(self, "theme_switch") else False
        text = "#e5eef7" if dark else "#111827"
        muted = "#9fb0c3" if dark else "#64748b"
        html_body = body.replace("color:inherit", f"color:{text}").replace("#64748b", muted)
        self.general_summary.setHtml(html_body)

    def on_summary_mode_changed(self) -> None:
        if not hasattr(self, "mail_list"):
            return
        general_mode = self.summary_modes.currentIndex() == 0
        if hasattr(self, "general_mode_button"):
            self.general_mode_button.setChecked(general_mode)
            self.detail_mode_button.setChecked(not general_mode)
        self.open_button.setVisible(not general_mode)
        self.done_button.setVisible(not general_mode)
        self.filter_label.setVisible(not general_mode)
        self.filter_input.setVisible(not general_mode)
        if not general_mode:
            self.refresh_summary_view()

    def set_summary_mode(self, index: int) -> None:
        if hasattr(self, "summary_modes"):
            self.summary_modes.setCurrentIndex(index)
        self.on_summary_mode_changed()

    def render_detail_cards(self, records: list[dict]) -> None:
        while self.detail_layout.count():
            item = self.detail_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        visible = [item for item in records if not item.get("completed")]
        if not visible:
            empty = QLabel("Şimdi Tara dediğinde detaylı özet burada görünecek.")
            empty.setObjectName("DetailEmpty")
            empty.setWordWrap(True)
            self.detail_layout.addWidget(empty)
            self.detail_layout.addStretch()
            return

        self.detail_layout.addWidget(self._detail_summary_card(visible[0]))
        self.detail_layout.addStretch()

    def _detail_summary_card(self, record: dict) -> QFrame:
        frame = QFrame()
        frame.setObjectName("DetailMailCard")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)

        header = QHBoxLayout()
        header.setSpacing(7)
        header.setContentsMargins(0, 0, 0, 0)
        for tag in record.get("tags", []):
            header.addWidget(self._chip(tag, self._tag_object_name(tag)))

        subject = ElideLabel(record.get("subject", "Başlıksız mail"))
        subject.setObjectName("DetailSubject")
        subject.setMinimumWidth(1)
        subject.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        header.addWidget(subject, 1)

        if record.get("date"):
            header.addWidget(self._chip(record["date"], "DateChip"))
        layout.addLayout(header)

        sender = ElideLabel(f"Kimden: {record.get('sender', '-')}")
        sender.setObjectName("DetailSender")
        sender.setMinimumWidth(1)
        sender.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(sender)
        layout.addWidget(self._info_block("Bu mail ne anlatıyor?", record.get("overview", record.get("note", "-"))))
        layout.addWidget(self._info_block("Senden beklenen", record.get("action", "-")))
        layout.addWidget(self._info_block("Detaylı özet", record.get("detail_summary", record.get("note", "-"))))
        layout.addWidget(self._info_block("Kısa karar", self._decision_text(record)))
        return frame

    def _info_block(self, title: str, text: str) -> QFrame:
        block = QFrame()
        block.setObjectName("DetailInfoBlock")
        layout = QVBoxLayout(block)
        layout.setContentsMargins(16, 13, 16, 13)
        layout.setSpacing(6)
        title_label = QLabel(title)
        title_label.setObjectName("DetailBlockTitle")
        text_label = QLabel(text or "-")
        text_label.setObjectName("DetailBlockText")
        text_label.setTextFormat(Qt.TextFormat.PlainText)
        text_label.setWordWrap(True)
        text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(title_label)
        layout.addWidget(text_label)
        return block

    def _decision_text(self, record: dict) -> str:
        if record.get("completed"):
            return "Bu mail tamamlandı olarak işaretlenmiş."
        if record.get("section") == "Yapılacak":
            return "Bunu açık iş olarak tut; önce bu aksiyonu kontrol etmeni öneririm."
        if record.get("score", 0) >= 30:
            return "Önemli görünüyor; bugün içinde göz atmak iyi olur."
        return "Acil aksiyon görünmüyor; bilgi olarak okuyabilirsin."

    def _chip(self, text: str, object_name: str) -> QLabel:
        chip = QLabel(text or "-")
        chip.setObjectName(object_name)
        chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        chip.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        return chip

    def _tag_object_name(self, tag: str) -> str:
        return {
            "Acil": "TagUrgent",
            "Cevap": "TagReply",
            "Fatura/Ödeme": "TagMoney",
            "Toplantı": "TagMeeting",
            "Güvenlik": "TagSecurity",
            "Onay": "TagApproval",
            "Bilgi": "TagInfo",
        }.get(tag, "TagInfo")

    def update_selected_detail(self) -> None:
        record = self.current_record()
        if not record:
            return
        self.done_button.setText("Geri Al" if record["completed"] else "Tamamlandı")
        self.render_detail_cards([record])

    def mark_selected_completed(self) -> None:
        record = self.current_record()
        if not record:
            return
        message_id = record["id"]
        completed = set(self.settings.completed_message_ids)
        if message_id in completed:
            completed.remove(message_id)
            record["completed"] = False
            self.done_button.setText("Tamamlandı")
            self.write_log("Mail tekrar açık duruma alındı.")
        else:
            completed.add(message_id)
            record["completed"] = True
            self.done_button.setText("Geri Al")
            self.write_log("Mail tamamlandı olarak işaretlendi.")
        self.settings.completed_message_ids = sorted(completed)
        self.settings.save()
        self.update_metrics()
        self.refresh_summary_view()

    def open_selected_mail(self) -> None:
        record = self.current_record()
        if not record:
            return
        webbrowser.open(record["gmail_url"])
        self.write_log("Mail Gmail'de açıldı.")

    def current_record_id(self) -> str | None:
        item = self.mail_list.currentItem()
        return str(item.data(Qt.ItemDataRole.UserRole)) if item else None

    def current_record(self) -> dict | None:
        record_id = self.current_record_id()
        if not record_id:
            return None
        return next((item for item in self.records if item["id"] == record_id), None)

    def update_metrics(self) -> None:
        action_count = len([item for item in self.records if item["section"] == "Yapılacak" and not item["completed"]])
        important_count = len([item for item in self.records if item["score"] >= 30 and not item["completed"]])
        self.action_metric.value_label.setText(str(action_count))
        self.important_metric.value_label.setText(str(important_count))
        self.total_metric.value_label.setText(str(len(self.records)))

    def scan_finished(self) -> None:
        self.running_scan = False
        self.scan_started_at = None
        self.refresh_status_labels()

    def check_instance_restore_request(self) -> None:
        if not INSTANCE_RESTORE_PATH.exists():
            return
        try:
            INSTANCE_RESTORE_PATH.unlink()
        except OSError:
            pass
        self.restore_from_tray()

    def check_schedule(self) -> None:
        now = datetime.now()
        current_day = now.date().isoformat()
        now_slot = now.strftime("%H:%M")
        if self.settings.enabled and now_slot in self.settings.summary_times:
            key = f"{current_day}-{now_slot}"
            if key not in self.ran_slots:
                self.ran_slots.add(key)
                self.scan_now()
        if self.settings.enabled and self._daily_report_due(now):
            self.start_report_popup_scan(force=True, daily_report_date=current_day)
        old_days = {slot for slot in self.ran_slots if not slot.startswith(current_day)}
        self.ran_slots.difference_update(old_days)

    def _daily_report_due(self, now: datetime) -> bool:
        if self.settings.last_daily_report_date == now.date().isoformat():
            return False
        if self.pending_daily_report_date == now.date().isoformat():
            return False
        if self.daily_report_retry_after and now < self.daily_report_retry_after:
            return False
        try:
            report_time = datetime.strptime(self.settings.daily_report_time, "%H:%M").time()
        except ValueError:
            return False
        return now.time() >= report_time

    def open_summaries(self) -> None:
        os.startfile(summaries_path())

    def minimize_to_tray(self) -> None:
        self.hide()
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.showMessage(
                "MailPilot simgeye küçültüldü",
                "Rapor saati gelirse mini Genel Özet burada açılacak.",
                QSystemTrayIcon.MessageIcon.Information,
                3500,
            )
        self.write_log("Uygulama simge alanına küçültüldü.")

    def restore_from_tray(self) -> None:
        self.setWindowState(Qt.WindowState.WindowNoState)
        self.showNormal()
        self._raise_after_tray_restore()
        self.write_log("Uygulama simgeden açıldı.")
        QTimer.singleShot(120, self._raise_after_tray_restore)
        QTimer.singleShot(350, self._raise_after_tray_restore)

    def _raise_after_tray_restore(self) -> None:
        if not self.isVisible():
            self.showNormal()
        if sys.platform.startswith("win"):
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
            self.show()
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, False)
            self.show()
        self.raise_()
        self.activateWindow()

    def on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in {
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
            QSystemTrayIcon.ActivationReason.MiddleClick,
        }:
            self.restore_from_tray()

    def notify_started_in_tray(self) -> None:
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.showMessage(
                "MailPilot çalışıyor",
                "Arka planda simge alanında başladı. Açmak için MailPilot simgesine tıkla.",
                QSystemTrayIcon.MessageIcon.Information,
                6000,
            )
        self.write_log("MailPilot Windows ile simge alanında başlatıldı.")

    def quit_app(self) -> None:
        self.force_quit = True
        QApplication.quit()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self.force_quit or not QSystemTrayIcon.isSystemTrayAvailable():
            event.accept()
            return
        event.ignore()
        self.minimize_to_tray()

    def changeEvent(self, event) -> None:  # type: ignore[override]
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and self.isMinimized():
            QTimer.singleShot(0, self.minimize_to_tray)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._position_settings_popover()
        self._position_account_popover()
        self._position_toast()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if getattr(self, "account_flow_active", False):
            event.accept()
            return
        super().mousePressEvent(event)
        target = self.childAt(event.position().toPoint())
        if hasattr(self, "settings_popover") and self.settings_popover.isVisible():
            if target and (self.settings_popover.isAncestorOf(target) or target is self.settings_popover or target is self.settings_button):
                return
            self.close_settings_popover(animated=True)
        if hasattr(self, "account_popover") and self.account_popover.isVisible():
            if target and (self.account_popover.isAncestorOf(target) or target is self.account_popover or target is self.account_input):
                return
            self.account_popover.hide()

    def write_log(self, text: str) -> None:
        self.log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {text}")

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def show_warning(self, text: str) -> None:
        QMessageBox.warning(self, "MailPilot", text)

    def show_error(self, text: str) -> None:
        QMessageBox.critical(self, "MailPilot", text)

    def show_notification(self, title: str, text: str) -> None:
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.showMessage(title, text, QSystemTrayIcon.MessageIcon.Information, 8000)
        self.write_log(f"Bildirim: {title} - {text}")

    def is_app_foreground(self) -> bool:
        active = QApplication.activeWindow()
        return self.isVisible() and not self.isMinimized() and active is not None

    def test_report_popup(self) -> None:
        self.save_settings()
        self.start_report_popup_scan(force=True)

    def start_report_popup_scan(self, force: bool = False, daily_report_date: str | None = None) -> None:
        if self.report_thread and self.report_thread.is_alive():
            if daily_report_date:
                self.pending_daily_report_date = daily_report_date
            self.write_log("Mini rapor taraması zaten çalışıyor.")
            return
        if not force and self.is_app_foreground():
            return
        self.pending_daily_report_date = daily_report_date
        if daily_report_date:
            self.daily_report_retry_after = None
        self.report_popup = ReportPopup(self)
        self.report_popup.setStyleSheet(DARK_STYLE if self.settings.theme == "dark" else LIGHT_STYLE)
        self.report_popup.show()
        self.report_popup.raise_()
        self.write_log("Mini rapor taraması başladı.")
        self.report_thread = threading.Thread(target=self._report_worker, daemon=True)
        self.report_thread.start()

    def _report_worker(self) -> None:
        try:
            report_settings = self._report_settings()
            messages = fetch_messages(report_settings)
            records = analyze_messages(
                messages,
                priority_senders=self.settings.priority_senders,
                completed_ids=self.settings.completed_message_ids,
            )
            body = render_general_summary_html(records)
            self.settings.mark_scanned_now()
            self.signals.report_ready.emit(records, body)
        except Exception as exc:
            self.signals.report_error.emit(str(exc))

    def _report_settings(self) -> Settings:
        mode = self.settings.report_scan_mode
        report_settings = replace(self.settings)
        report_settings.date_filter_mode = "auto"
        report_settings.scan_mode = "since_last_scan"
        if mode.startswith("last_"):
            hours = {"last_1h": 1, "last_6h": 6, "last_24h": 24}.get(mode, 24)
            report_settings.scan_mode = "lookback_window"
            report_settings.lookback_hours = hours
        return report_settings

    def show_report_popup(self, records: list[dict], body: str) -> None:
        self.records = records
        self.update_metrics()
        self.refresh_summary_view()
        if not self.report_popup:
            self.report_popup = ReportPopup(self)
        self.report_popup.setStyleSheet(DARK_STYLE if self.settings.theme == "dark" else LIGHT_STYLE)
        dark = self.settings.theme == "dark"
        text = "#e5eef7" if dark else "#111827"
        muted = "#9fb0c3" if dark else "#64748b"
        html_body = body.replace("color:inherit", f"color:{text}").replace("#64748b", muted)
        self.report_popup.set_summary(html_body)
        self.report_popup.show()
        self.report_popup.raise_()
        if self.pending_daily_report_date == date.today().isoformat():
            self.settings.mark_daily_report_now()
            self.pending_daily_report_date = None
            self.daily_report_retry_after = None
        self.write_log("Mini rapor hazır.")
        self.refresh_status_labels()

    def show_report_error(self, text: str) -> None:
        if self.pending_daily_report_date == date.today().isoformat():
            self.daily_report_retry_after = datetime.now() + timedelta(minutes=15)
        self.pending_daily_report_date = None
        if not self.report_popup:
            self.report_popup = ReportPopup(self)
        self.report_popup.set_message(f"Mini rapor hazırlanamadı:\n\n{text}")
        self.report_popup.show()
        self.report_popup.raise_()
        self.write_log(f"Mini rapor hatası: {text}")

    def on_theme_switch_changed(self) -> None:
        theme = "dark" if self.theme_switch.isChecked() else "light"
        self.apply_theme(theme)
        if not self.loading:
            self.settings.theme = theme
            self.settings.save()

    def update_scope_fields(self) -> None:
        scope = self.scope_input.currentData()
        self._set_layout_visible(self.lookback_box, scope == "lookback_window")
        self._set_layout_visible(self.single_date_box, scope == "single_day")
        self._set_layout_visible(self.range_start_box, scope == "date_range")
        self._set_layout_visible(self.range_end_box, scope == "date_range")

    def _set_layout_visible(self, layout: QVBoxLayout, visible: bool) -> None:
        for index in range(layout.count()):
            item = layout.itemAt(index)
            widget = item.widget()
            if widget:
                widget.setVisible(visible)

    def apply_theme(self, theme: str) -> None:
        self.setStyleSheet(DARK_STYLE if theme == "dark" else LIGHT_STYLE)
        if hasattr(self, "general_summary") and self.records:
            self.set_general_summary(render_general_summary_html(self.records, self.filter_input.currentText()))

    def _scope_from_settings(self) -> str:
        if self.settings.date_filter_mode in {"single_day", "date_range"}:
            return self.settings.date_filter_mode
        return self.settings.scan_mode

    def _apply_scope_to_settings(self) -> None:
        scope = self.scope_input.currentData()
        if scope in {"single_day", "date_range"}:
            self.settings.date_filter_mode = scope
            self.settings.scan_mode = "lookback_window"
            return
        self.settings.date_filter_mode = "auto"
        self.settings.scan_mode = scope

    def refresh_status_labels(self) -> None:
        self.last_scan_label.setText(f"Son tarama:<br>{self._formatted_last_scan()}")

    def _formatted_last_scan(self) -> str:
        if not self.settings.last_scan_at:
            return "-"
        try:
            parsed = datetime.fromisoformat(self.settings.last_scan_at)
        except ValueError:
            return html.escape(self.settings.last_scan_at)
        months = [
            "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
            "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
        ]
        main = f"{parsed.day} {months[parsed.month - 1]} {parsed.year}, {parsed.hour:02d}:{parsed.minute:02d}"
        return f"<b>{main}</b>:{parsed.second:02d}"

    def _sync_scan_state(self) -> None:
        if self.running_scan and self.scan_thread and not self.scan_thread.is_alive():
            self.running_scan = False
            self.scan_started_at = None

    def _scan_elapsed_text(self) -> str:
        if not self.scan_started_at:
            return "süre bilinmiyor"
        seconds = int((datetime.now() - self.scan_started_at).total_seconds())
        minutes, seconds = divmod(max(0, seconds), 60)
        if minutes:
            return f"{minutes} dk {seconds} sn"
        return f"{seconds} sn"

    def _load_latest_summary(self) -> str:
        path = summaries_path()
        files = sorted(path.glob("*.txt"), key=lambda item: item.stat().st_mtime, reverse=True)
        if not files:
            return "Henüz özet yok.\n\nTarih aralığını seçip Şimdi Tara dediğinde öncelikli mailler burada görünecek."
        return files[0].read_text(encoding="utf-8")

    def _notification_from_summary(self, summary: str) -> str:
        for line in summary.splitlines():
            if "mail tarandı" in line:
                return line
        return "Günlük özet hazır."

    def _qdate(self, value: str) -> QDate:
        parsed = QDate.fromString(value, "yyyy-MM-dd")
        return parsed if parsed.isValid() else QDate.currentDate()


def main() -> None:
    global INSTANCE_LOCK
    QLocale.setDefault(QLocale(QLocale.Language.Turkish, QLocale.Country.Turkey))
    app = QApplication(sys.argv)
    app.setApplicationName("MailPilot")
    app.setQuitOnLastWindowClosed(False)
    CREDENTIALS_DIR.mkdir(exist_ok=True)
    instance_lock = QLockFile(str(INSTANCE_LOCK_PATH))
    if not instance_lock.tryLock(100):
        _request_existing_instance_restore()
        return
    INSTANCE_LOCK = instance_lock
    if APP_ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(APP_ICON_PATH)))
    font_family = "Segoe UI Variable Text"
    for font_path in (
        APP_DIR / "assets" / "fonts" / "OrangeAvenueDEMO-Regular.otf",
    ):
        if font_path.exists():
            QFontDatabase.addApplicationFont(str(font_path))
    app_font = _safe_font(font_family, 10)
    app.setFont(app_font)
    window = MailPilotWindow()
    if window.settings.start_minimized_to_tray and "--tray" in sys.argv:
        window.hide()
        QTimer.singleShot(1_200, window.notify_started_in_tray)
    else:
        window.show()
    sys.exit(app.exec())

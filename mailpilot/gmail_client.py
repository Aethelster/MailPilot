from __future__ import annotations

from base64 import urlsafe_b64decode
from datetime import date, datetime, time, timedelta, timezone
import json
import hashlib
import re
import shutil
import time as time_module
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request as UrlRequest, urlopen
import webbrowser

from .config import CREDENTIALS_DIR, Settings, SUMMARIES_DIR, ensure_runtime_layout


SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
CREDENTIALS_PATH = CREDENTIALS_DIR / "credentials.json"
OUTLOOK_CREDENTIALS_PATH = CREDENTIALS_DIR / "outlook_credentials.json"
TOKEN_PATH = CREDENTIALS_DIR / "token.json"
ACCOUNTS_DIR = CREDENTIALS_DIR / "accounts"
OUTLOOK_SCOPES = ["offline_access", "User.Read", "Mail.Read"]


class GmailNotReady(RuntimeError):
    pass


class OutlookDeviceLogin(RuntimeError):
    def __init__(self, device: dict[str, Any], client_id: str, tenant: str) -> None:
        self.device = device
        self.client_id = client_id
        self.tenant = tenant
        super().__init__(device.get("message", "Outlook girişini tarayıcıda tamamla."))


class OutlookAuthPending(RuntimeError):
    pass


def _load_google_modules():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise GmailNotReady(
            "Gmail paketleri kurulu değil. Önce 'pip install -r requirements.txt' çalıştırılmalı."
        ) from exc
    return Request, Credentials, InstalledAppFlow, build


def build_service(settings: Settings | None = None, account_id: str | None = None):
    ensure_runtime_layout()
    Request, Credentials, InstalledAppFlow, build = _load_google_modules()
    if not CREDENTIALS_PATH.exists():
        raise GmailNotReady("credentials.json bulunamadı. Google OAuth dosyasını uygulama klasörüne koy.")

    token_path = _token_path(settings, account_id)
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.parent.mkdir(exist_ok=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")
    return build("gmail", "v1", credentials=creds)


def fetch_messages(settings: Settings) -> list[dict[str, Any]]:
    account = _active_account(settings)
    if account and account.get("provider") == "outlook":
        return _fetch_outlook_messages(settings, account)
    service = build_service(settings)
    after, before = _scan_window(settings)
    query = f"after:{after.strftime('%Y/%m/%d')}"
    if before:
        query += f" before:{before.strftime('%Y/%m/%d')}"
    response = service.users().messages().list(
        userId="me",
        q=query,
        maxResults=settings.max_messages,
    ).execute()
    items = response.get("messages", [])
    messages: list[dict[str, Any]] = []
    after_ms = int(after.timestamp() * 1000)
    before_ms = int(before.timestamp() * 1000) if before else None

    for item in items:
        detail = service.users().messages().get(
            userId="me",
            id=item["id"],
            format="full",
        ).execute()
        internal_date = int(detail.get("internalDate", "0"))
        if internal_date and internal_date < after_ms:
            continue
        if before_ms and internal_date and internal_date >= before_ms:
            continue
        messages.append(_message_to_dict(detail))

    messages.sort(key=lambda item: item.get("internal_date", 0), reverse=True)
    return messages


def add_gmail_account(settings: Settings) -> dict[str, str]:
    service = build_service(settings, account_id="new")
    profile = service.users().getProfile(userId="me").execute()
    email = profile.get("emailAddress", "gmail")
    account_id = _account_id(email)
    new_token = _account_token_path("new")
    final_token = _account_token_path(account_id)
    if new_token.exists() and new_token != final_token:
        final_token.parent.mkdir(exist_ok=True)
        new_token.replace(final_token)
    account = {"id": account_id, "email": email, "provider": "gmail"}
    settings.email_accounts = [item for item in settings.email_accounts if item.get("id") != account_id]
    settings.email_accounts.append(account)
    settings.active_account_id = account_id
    settings.save()
    return account


def add_outlook_account(settings: Settings) -> dict[str, str]:
    config = _load_outlook_config()
    tenant = config.get("tenant", "common")
    client_id = config["client_id"]
    device = _outlook_post(
        f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/devicecode",
        {
            "client_id": client_id,
            "scope": " ".join(OUTLOOK_SCOPES),
        },
    )
    verification_uri = device.get("verification_uri") or device.get("verification_url")
    if verification_uri:
        webbrowser.open(verification_uri)
    raise OutlookDeviceLogin(device, client_id, tenant)


def finish_outlook_device_login(settings: Settings, device: dict[str, Any], client_id: str, tenant: str) -> dict[str, str]:
    token_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    interval = int(device.get("interval", 5))
    expires_at = time_module.time() + int(device.get("expires_in", 900))
    token: dict[str, Any] | None = None
    while time_module.time() < expires_at:
        try:
            token = _outlook_post(
                token_url,
                {
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "client_id": client_id,
                    "device_code": device["device_code"],
                },
            )
            break
        except OutlookAuthPending:
            time_module.sleep(interval)
    if not token:
        raise GmailNotReady("Outlook girişi tamamlanmadı. Süre dolduysa tekrar Outlook ekle.")
    profile = _outlook_get("https://graph.microsoft.com/v1.0/me", token["access_token"])
    email = profile.get("mail") or profile.get("userPrincipalName") or "outlook"
    account_id = _account_id(email)
    account = {"id": account_id, "email": email, "provider": "outlook"}
    token["client_id"] = client_id
    token["tenant"] = tenant
    token["expires_at"] = str(int(time_module.time()) + int(token.get("expires_in", 3600)))
    token_path = _account_token_path(account_id)
    token_path.parent.mkdir(exist_ok=True)
    token_path.write_text(json.dumps(token, indent=2), encoding="utf-8")
    settings.email_accounts = [item for item in settings.email_accounts if item.get("id") != account_id]
    settings.email_accounts.append(account)
    settings.active_account_id = account_id
    settings.save()
    return account


def ensure_default_gmail_account(settings: Settings) -> dict[str, str] | None:
    ensure_runtime_layout()
    if settings.email_accounts or not TOKEN_PATH.exists():
        return None
    Request, Credentials, _, build = _load_google_modules()
    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
        else:
            return None
    service = build("gmail", "v1", credentials=creds)
    profile = service.users().getProfile(userId="me").execute()
    email = profile.get("emailAddress")
    if not email:
        return None
    account_id = _account_id(email)
    final_token = _account_token_path(account_id)
    final_token.parent.mkdir(exist_ok=True)
    if not final_token.exists():
        shutil.copy2(TOKEN_PATH, final_token)
    account = {"id": account_id, "email": email, "provider": "gmail"}
    settings.email_accounts = [account]
    settings.active_account_id = account_id
    settings.save()
    return account


def _token_path(settings: Settings | None, account_id: str | None = None):
    selected = account_id or (settings.active_account_id if settings else None)
    if selected:
        return _account_token_path(selected)
    return TOKEN_PATH


def _account_token_path(account_id: str):
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", account_id)
    return ACCOUNTS_DIR / f"{safe}.json"


def _account_id(email: str) -> str:
    normalized = email.strip().lower()
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:8]
    safe = re.sub(r"[^a-z0-9_.-]+", "_", normalized)
    return f"{safe}-{digest}"


def _active_account(settings: Settings) -> dict[str, str] | None:
    if not settings.email_accounts:
        return None
    selected = settings.active_account_id or settings.email_accounts[0].get("id")
    for account in settings.email_accounts:
        if account.get("id") == selected:
            return account
    return settings.email_accounts[0]


def _load_outlook_config() -> dict[str, str]:
    ensure_runtime_layout()
    if not OUTLOOK_CREDENTIALS_PATH.exists():
        raise GmailNotReady(
            "outlook_credentials.json bulunamadı. Outlook için uygulama klasörüne {\"client_id\":\"...\"} dosyası koymalısın."
        )
    data = json.loads(OUTLOOK_CREDENTIALS_PATH.read_text(encoding="utf-8"))
    client_id = str(data.get("client_id", "")).strip()
    if not client_id:
        raise GmailNotReady("outlook_credentials.json içinde client_id eksik.")
    return {"client_id": client_id, "tenant": str(data.get("tenant", "common")).strip() or "common"}


def _outlook_post(url: str, data: dict[str, str]) -> dict[str, Any]:
    body = urlencode(data).encode("utf-8")
    request = UrlRequest(url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        payload = json.loads(exc.read().decode("utf-8", errors="replace") or "{}")
        if payload.get("error") == "authorization_pending":
            raise OutlookAuthPending(payload.get("error_description", "authorization_pending")) from exc
        message = payload.get("error_description") or payload.get("error") or str(exc)
        raise GmailNotReady(f"Outlook hatası: {message}") from exc


def _outlook_get(url: str, access_token: str) -> dict[str, Any]:
    request = UrlRequest(url, headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"})
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        payload = json.loads(exc.read().decode("utf-8", errors="replace") or "{}")
        message = payload.get("error", {}).get("message") or payload.get("error_description") or str(exc)
        raise GmailNotReady(f"Outlook hatası: {message}") from exc


def _outlook_access_token(account: dict[str, str]) -> str:
    token_path = _account_token_path(account["id"])
    if not token_path.exists():
        raise GmailNotReady("Outlook oturumu bulunamadı. Hesabı tekrar ekle.")
    token = json.loads(token_path.read_text(encoding="utf-8"))
    if int(token.get("expires_at", "0")) > int(time_module.time()) + 60:
        return token["access_token"]
    refresh_token = token.get("refresh_token")
    if not refresh_token:
        raise GmailNotReady("Outlook oturumu yenilenemedi. Hesabı tekrar ekle.")
    refreshed = _outlook_post(
        f"https://login.microsoftonline.com/{token.get('tenant', 'common')}/oauth2/v2.0/token",
        {
            "grant_type": "refresh_token",
            "client_id": token["client_id"],
            "refresh_token": refresh_token,
            "scope": " ".join(OUTLOOK_SCOPES),
        },
    )
    refreshed["client_id"] = token["client_id"]
    refreshed["tenant"] = token.get("tenant", "common")
    refreshed["expires_at"] = str(int(time_module.time()) + int(refreshed.get("expires_in", 3600)))
    token_path.write_text(json.dumps(refreshed, indent=2), encoding="utf-8")
    return refreshed["access_token"]


def _fetch_outlook_messages(settings: Settings, account: dict[str, str]) -> list[dict[str, Any]]:
    access_token = _outlook_access_token(account)
    after, before = _scan_window(settings)
    filters = [f"receivedDateTime ge {_graph_time(after)}"]
    if before:
        filters.append(f"receivedDateTime lt {_graph_time(before)}")
    query = urlencode(
        {
            "$top": str(settings.max_messages),
            "$orderby": "receivedDateTime desc",
            "$filter": " and ".join(filters),
            "$select": "id,conversationId,subject,receivedDateTime,from,bodyPreview,body,webLink",
        }
    )
    response = _outlook_get(f"https://graph.microsoft.com/v1.0/me/messages?{query}", access_token)
    messages = [_outlook_message_to_dict(item) for item in response.get("value", [])]
    messages.sort(key=lambda item: item.get("internal_date", 0), reverse=True)
    return messages


def _graph_time(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.astimezone()
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _outlook_message_to_dict(item: dict[str, Any]) -> dict[str, Any]:
    received = item.get("receivedDateTime", "")
    timestamp = 0
    if received:
        try:
            timestamp = int(datetime.fromisoformat(received.replace("Z", "+00:00")).timestamp() * 1000)
        except ValueError:
            timestamp = 0
    sender = ((item.get("from") or {}).get("emailAddress") or {})
    body = item.get("body") or {}
    return {
        "id": item.get("id"),
        "thread_id": item.get("conversationId") or item.get("id"),
        "gmail_url": item.get("webLink") or "https://outlook.live.com/mail/",
        "internal_date": timestamp,
        "from": f"{sender.get('name', '')} <{sender.get('address', '')}>".strip(),
        "subject": item.get("subject") or "(Konu yok)",
        "date": received,
        "snippet": item.get("bodyPreview", ""),
        "body": _strip_html(body.get("content", "")),
    }


def _strip_html(value: str) -> str:
    text = re.sub(r"<(br|p|div|li)\b[^>]*>", "\n", value, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _scan_window(settings: Settings) -> tuple[datetime, datetime | None]:
    if settings.date_filter_mode == "single_day":
        selected = date.fromisoformat(settings.single_scan_date)
        after = datetime.combine(selected, time.min)
        before = after + timedelta(days=1)
        return after, before
    if settings.date_filter_mode == "date_range":
        start = date.fromisoformat(settings.range_start_date)
        end = date.fromisoformat(settings.range_end_date)
        if end < start:
            start, end = end, start
        after = datetime.combine(start, time.min)
        before = datetime.combine(end + timedelta(days=1), time.min)
        return after, before
    return _scan_after(settings), None


def _scan_after(settings: Settings) -> datetime:
    if settings.scan_mode == "since_last_scan" and settings.last_scan_at:
        try:
            return datetime.fromisoformat(settings.last_scan_at)
        except ValueError:
            pass
    hours = max(1, int(settings.lookback_hours))
    return datetime.now() - timedelta(hours=hours)


def _message_to_dict(detail: dict[str, Any]) -> dict[str, Any]:
    headers = {h["name"].lower(): h["value"] for h in detail.get("payload", {}).get("headers", [])}
    thread_id = detail.get("threadId") or detail.get("id")
    return {
        "id": detail.get("id"),
        "thread_id": thread_id,
        "gmail_url": f"https://mail.google.com/mail/u/0/#all/{thread_id}",
        "internal_date": int(detail.get("internalDate", "0")),
        "from": headers.get("from", ""),
        "subject": headers.get("subject", "(Konu yok)"),
        "date": headers.get("date", ""),
        "snippet": detail.get("snippet", ""),
        "body": _extract_body(detail.get("payload", {})),
    }


def _extract_body(payload: dict[str, Any]) -> str:
    mime_type = payload.get("mimeType", "")
    body = payload.get("body", {})
    data = body.get("data")
    if data and mime_type in {"text/plain", "text/html"}:
        return _decode_body(data)
    for part in payload.get("parts", []) or []:
        text = _extract_body(part)
        if text:
            return text
    return ""


def _decode_body(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    try:
        return urlsafe_b64decode(padded).decode("utf-8", errors="replace")
    except Exception:
        return ""


def summaries_path():
    ensure_runtime_layout()
    return SUMMARIES_DIR

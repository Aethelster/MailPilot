from __future__ import annotations

from datetime import datetime
from email.utils import parsedate_to_datetime
import html
import re
from typing import Any


CATEGORY_KEYWORDS = {
    "Acil": {"acil", "urgent", "asap", "hemen", "son tarih", "deadline", "due", "last call"},
    "Cevap": {"cevap", "yanıt", "reply", "respond", "geri dönüş", "feedback"},
    "Fatura/Ödeme": {"öde", "ödeme", "payment", "fatura", "invoice", "receipt", "borç", "tahsilat"},
    "Toplantı": {"toplantı", "meeting", "randevu", "appointment", "calendar", "zoom", "teams"},
    "Güvenlik": {"güvenlik", "security", "şifre", "password", "alert", "uyarı", "login", "oturum"},
    "Onay": {"onay", "approve", "approval", "imza", "signature", "confirm", "doğrula"},
}

IMPORTANT_WORDS = {
    "acil": 40,
    "urgent": 40,
    "asap": 34,
    "hemen": 30,
    "son tarih": 34,
    "deadline": 34,
    "due": 24,
    "security": 34,
    "güvenlik": 34,
    "şifre": 28,
    "password": 28,
    "ödeme": 28,
    "payment": 28,
    "fatura": 24,
    "invoice": 24,
    "onay": 26,
    "approve": 26,
    "approval": 26,
    "cevap": 24,
    "reply": 24,
    "yanıt": 24,
    "toplantı": 20,
    "meeting": 20,
    "randevu": 18,
    "appointment": 18,
    "failed": 18,
    "başarısız": 18,
    "sözleşme": 18,
    "contract": 18,
    "imza": 18,
    "signature": 18,
}

LOW_VALUE_WORDS = {
    "newsletter",
    "kampanya",
    "campaign",
    "indirim",
    "discount",
    "unsubscribe",
    "no-reply",
    "noreply",
    "promotions",
    "social",
}


def analyze_messages(
    messages: list[dict[str, Any]],
    priority_senders: list[str] | None = None,
    completed_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    priority_senders = [item.lower() for item in priority_senders or []]
    completed = set(completed_ids or [])
    records = [_enrich(message, priority_senders, completed) for message in messages]
    return sorted(records, key=lambda item: (item["completed"], -item["score"], -item["internal_date"]))


def summarize_messages(
    messages: list[dict[str, Any]],
    priority_senders: list[str] | None = None,
    completed_ids: list[str] | None = None,
) -> str:
    return render_summary(analyze_messages(messages, priority_senders, completed_ids))


def render_summary(records: list[dict[str, Any]], filter_name: str = "Hepsi") -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    visible = filter_records(records, filter_name)
    open_records = [item for item in records if not item["completed"]]
    action_records = [item for item in visible if item["section"] == "Yapılacak" and not item["completed"]]
    info_records = [item for item in visible if item["section"] == "Bilgi" and not item["completed"]]

    if not records:
        return f"MailPilot özeti - {now}\n\nYeni mail yok. Şimdilik aksiyon görünmüyor.\n"

    lines = [
        f"MailPilot özeti - {now}",
        f"{len(records)} mail tarandı. Açık konu: {len(open_records)}. Filtre: {filter_name}.",
        "",
        "Yapman gerekenler:",
    ]

    if action_records:
        for index, item in enumerate(action_records[:8], 1):
            lines.append(format_record(item, index, include_action=True))
    else:
        lines.append("- Bu filtrede net aksiyon isteyen mail yok.")

    lines.extend(["", "Bilmen gerekenler:"])
    if info_records:
        for index, item in enumerate(info_records[:8], 1):
            lines.append(format_record(item, index, include_action=False))
    else:
        lines.append("- Bu filtrede önemli bilgilendirme yok.")

    completed_count = len([item for item in records if item["completed"]])
    hidden_count = max(0, len(visible) - len(action_records[:8]) - len(info_records[:8]) - completed_count)
    if completed_count or hidden_count:
        lines.append("")
    if completed_count:
        lines.append(f"Tamamlanan: {completed_count} mail.")
    if hidden_count:
        lines.append(f"Düşük öncelik/limit dışı: {hidden_count} mail.")

    return "\n".join(lines) + "\n"


def render_general_summary(records: list[dict[str, Any]], filter_name: str = "Hepsi") -> str:
    visible = [item for item in filter_records(records, filter_name) if not item["completed"]]
    if not records:
        return "Yeni mail yok. Şu an yapılacak bir şey görünmüyor."
    if not visible:
        return "Bu filtrede açık konu yok."

    lines: list[str] = []
    for index, item in enumerate(visible[:10], 1):
        lines.append(
            f"{index}. {item['sender']} sana {item['subject']} hakkında mail attı. "
            f"Tavsiyem: {item['action']}"
        )
    return "\n".join(lines)


def render_general_summary_html(records: list[dict[str, Any]], filter_name: str = "Hepsi") -> str:
    visible = [item for item in filter_records(records, filter_name) if not item["completed"]]
    if not records:
        return _general_html("<p><b>Yeni mail yok.</b> Şu an senden aksiyon isteyen bir şey görünmüyor.</p>")
    if not visible:
        return _general_html("<p><b>Bu filtrede açık konu yok.</b> Şimdilik ekstra aksiyon gerekmiyor.</p>")

    important = [
        item
        for item in visible
        if item["section"] == "Yapılacak" or item["score"] >= 30 or any(tag != "Bilgi" for tag in item["tags"])
    ]
    info = [item for item in visible if item not in important]
    filter_note = "" if filter_name == "Hepsi" else f" <span style='color:#64748b'>Filtre: {html.escape(filter_name)}.</span>"
    intro = (
        f"<p><b>Bugün {len(records)} mail tarandı.</b> "
        f"Bunlardan <b>{len(important)}</b> tanesi gerçekten bakmaya değer görünüyor.{filter_note}</p>"
    )

    if important:
        items = []
        for item in important[:5]:
            items.append(
                "<li>"
                f"<b>{html.escape(item['subject'])}</b> - {html.escape(item['sender'])}<br>"
                f"<u>Yapılacak:</u> {html.escape(item['action'])}"
                "</li>"
            )
        focus = "<p><b>Öne çıkanlar:</b></p><ul>" + "".join(items) + "</ul>"
    else:
        focus = "<p><b>Öne çıkan acil bir konu yok.</b> Mail trafiği daha çok bilgilendirme gibi duruyor.</p>"

    if info:
        sample = ", ".join(html.escape(item["subject"]) for item in info[:3])
        tail = f" Kalan bilgilendirmeler genel olarak şunlar: {sample}."
    else:
        tail = " Kalan tarafta ayrıca önemli bir bilgilendirme görünmüyor."
    close = f"<p><b>Kısa sonuç:</b>{tail} Önce yukarıdaki aksiyon isteyen maillere bakmanı öneririm.</p>"
    return _general_html(intro + focus + close)


def render_detail_html(records: list[dict[str, Any]], filter_name: str = "Hepsi") -> str:
    visible = [item for item in filter_records(records, filter_name) if not item["completed"]]
    if not records:
        return _html_page("<p class='empty'>Yeni mail yok. Şu an yapılacak bir şey görünmüyor.</p>")
    if not visible:
        return _html_page("<p class='empty'>Bu filtrede açık konu yok.</p>")

    blocks = []
    for item in visible[:12]:
        chips = "".join(_chip_cell(tag) for tag in item["tags"])
        chips += _chip_cell(item["date"] or "-", "date")
        blocks.append(
            "<section class='mail-card'>"
            "<table class='topline' cellspacing='0' cellpadding='0'><tr>"
            f"{chips}"
            f"<td class='subject-cell'><strong>{html.escape(item['subject'])}</strong></td>"
            "</tr></table>"
            f"<div class='sender'>Kimden: {html.escape(item['sender'])}</div>"
            "<div class='spacer'></div>"
            f"<p><b>Yapılacak:</b> {html.escape(item['action'])}</p>"
            f"<p><b>Kısa not:</b> {html.escape(item['note'])}</p>"
            "</section>"
        )
    return _html_page("".join(blocks))


def filter_records(records: list[dict[str, Any]], filter_name: str) -> list[dict[str, Any]]:
    if filter_name == "Tamamlanmamış":
        return [item for item in records if not item["completed"]]
    if filter_name in {"Acil", "Cevap", "Fatura/Ödeme", "Toplantı", "Güvenlik", "Onay"}:
        return [item for item in records if filter_name in item["tags"]]
    return records


def format_record(item: dict[str, Any], index: int, include_action: bool = True) -> str:
    tags = ", ".join(item["tags"]) if item["tags"] else "Bilgi"
    lines = [
        f"{index}. [{tags}] {item['subject']}",
        f"   Kimden: {item['sender']}",
    ]
    if item["date"]:
        lines.append(f"   Tarih: {item['date']}")
    lines.append(f"   Neden: {item['reason']}")
    if include_action:
        lines.append(f"   Yapılacak: {item['action']}")
    lines.append(f"   Kısa not: {item['note']}")
    return "\n".join(lines)


def detail_plain_text(item: dict[str, Any]) -> str:
    tags = ", ".join(item["tags"]) if item["tags"] else "Bilgi"
    return (
        f"[{tags}] {item['subject']}\n"
        f"Tarih: {item['date'] or '-'}\n"
        f"Kimden: {item['sender']}\n\n"
        f"Yapılacak: {item['action']}\n"
        f"Kısa not: {item['note']}"
    )


def _enrich(message: dict[str, Any], priority_senders: list[str], completed: set[str]) -> dict[str, Any]:
    subject = clean_text(message.get("subject", "(Konu yok)"), 150)
    sender = clean_sender(message.get("from", "Bilinmeyen"))
    raw_body = message.get("body") or message.get("snippet", "")
    body = clean_text(raw_body, 4000, ellipsis=False)
    haystack = f"{subject} {sender} {body}".lower()
    tags = _tags(haystack)
    score = _score(haystack, sender, priority_senders, tags)
    message_id = str(message.get("id") or "")
    action = _action_hint(tags, haystack)
    section = "Yapılacak" if tags.intersection({"Acil", "Cevap", "Fatura/Ödeme", "Toplantı", "Güvenlik", "Onay"}) or score >= 30 else "Bilgi"
    return {
        "id": message_id,
        "thread_id": message.get("thread_id") or message_id,
        "gmail_url": message.get("gmail_url") or f"https://mail.google.com/mail/u/0/#all/{message.get('thread_id') or message_id}",
        "internal_date": int(message.get("internal_date") or 0),
        "subject": subject,
        "sender": sender,
        "date": format_date(message.get("date", "")),
        "note": _short_note(body, subject, sender, tags),
        "overview": _overview(subject, body, tags),
        "detail_summary": _detail_summary(body, subject, sender, tags, action),
        "score": score,
        "tags": sorted(tags) or ["Bilgi"],
        "reason": _reason(tags, sender, priority_senders),
        "action": action,
        "section": section,
        "completed": message_id in completed,
    }


def _tags(text: str) -> set[str]:
    found: set[str] = set()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            found.add(category)
    return found


def _score(text: str, sender: str, priority_senders: list[str], tags: set[str]) -> int:
    score = 0
    for word, value in IMPORTANT_WORDS.items():
        if word in text:
            score += value
    for word in LOW_VALUE_WORDS:
        if word in text:
            score -= 18
    if any(priority in sender.lower() for priority in priority_senders):
        score += 35
    if "Acil" in tags:
        score += 20
    if "Güvenlik" in tags:
        score += 14
    return max(0, score)


def _reason(tags: set[str], sender: str, priority_senders: list[str]) -> str:
    reasons: list[str] = []
    if any(priority in sender.lower() for priority in priority_senders):
        reasons.append("önemli gönderen")
    if "Acil" in tags:
        reasons.append("zaman hassas")
    if "Cevap" in tags:
        reasons.append("cevap bekliyor olabilir")
    if "Fatura/Ödeme" in tags:
        reasons.append("ödeme/fatura")
    if "Toplantı" in tags:
        reasons.append("takvim/toplantı")
    if "Güvenlik" in tags:
        reasons.append("güvenlik")
    if "Onay" in tags:
        reasons.append("onay/imza")
    return ", ".join(reasons) if reasons else "bilgilendirme"


def _action_hint(tags: set[str], text: str) -> str:
    if "Güvenlik" in tags:
        return "Hesap/giriş bilgisini kontrol et."
    if "Fatura/Ödeme" in tags:
        return "Ödeme veya fatura detayını kontrol et."
    if "Onay" in tags:
        return "Onay/imza gerekip gerekmediğine bak."
    if "Cevap" in tags:
        return "Kısa cevap ver veya takip listene al."
    if "Toplantı" in tags:
        return "Takvimini kontrol et."
    if "Acil" in tags:
        return "Bugün içinde bak."
    if "review" in text or "incele" in text:
        return "İncele."
    return "Bilgi olarak oku."


def _short_note(body: str, subject: str, sender: str, tags: set[str]) -> str:
    summary = _detail_summary(body, subject, sender, tags, _action_hint(tags, f"{subject} {body}".lower()), limit=260)
    return summary or "İçerik kısa/boş geldi."


def _overview(subject: str, body: str, tags: set[str]) -> str:
    if "Güvenlik" in tags:
        return "Hesap güvenliği veya giriş doğrulamasıyla ilgili bir uyarı."
    if "Fatura/Ödeme" in tags:
        return "Ödeme, fatura veya tahsilat kontrolü gerektiren bir mail."
    if "Onay" in tags:
        return "Onay, doğrulama ya da imza bekleyen bir konu."
    if "Toplantı" in tags:
        return "Takvim veya toplantı planlamasıyla ilgili bir bildirim."
    if "Cevap" in tags:
        return "Senden dönüş bekleyebilecek bir mesaj."
    if "Acil" in tags:
        return "Bugün içinde bakılması iyi olacak zaman hassas bir konu."
    return clean_text(subject or body, 180) or "Bilgilendirme amaçlı kısa bir mail."


def _detail_summary(body: str, subject: str, sender: str, tags: set[str], action: str, limit: int = 700) -> str:
    text = clean_text(body or subject, 4000, ellipsis=False)
    if not text:
        return "Mail içeriği çok kısa geldi; konu başlığı üzerinden değerlendirdim."
    actor = _sender_name(sender)
    subject_hint = _subject_hint(subject)
    service = _service_hint(text, subject, sender)
    sentences: list[str] = []
    if "Güvenlik" in tags:
        target = "hesabınla ilgili" if service and service.lower() in actor.lower() else (f"{service} hesabında" if service else "hesabında")
        sentences = [
            f"{actor}, {target} güvenlik veya erişim izniyle ilgili bir uyarı gönderiyor.",
            "Bu işlem sana ait değilse hesabına başka biri erişmeye çalışıyor olabilir.",
            f"Yapman gereken: {action}",
        ]
    elif "Onay" in tags:
        sentences = [
            f"{actor}, {subject_hint} için onay ya da doğrulama bekliyor.",
            "İşlem sana aitse onay adımını tamamla; değilse hesabını ve izinleri kontrol et.",
            f"Yapman gereken: {action}",
        ]
    elif "Cevap" in tags:
        sentences = [
            f"{actor}, {subject_hint} hakkında senden dönüş bekleyebilir.",
            "Konuyu bekletmemek için kısa cevap ver ya da takip listene al.",
            f"Yapman gereken: {action}",
        ]
    elif "Fatura/Ödeme" in tags:
        sentences = [
            f"{actor}, {subject_hint} ile ilgili ödeme veya fatura bilgisi gönderiyor.",
            "Tutar, tarih ve ödeme durumunu kontrol etmen iyi olur.",
            f"Yapman gereken: {action}",
        ]
    elif "Toplantı" in tags:
        sentences = [
            f"{actor}, {subject_hint} için takvim veya toplantı bilgisi paylaşıyor.",
            "Saat, bağlantı ve katılım durumunu kontrol et.",
            f"Yapman gereken: {action}",
        ]
    elif "Acil" in tags:
        sentences = [
            f"{actor}, {subject_hint} konusunda zaman hassas bir mail göndermiş.",
            "Bugün içinde bakman ve gerekiyorsa aksiyon alman iyi olur.",
            f"Yapman gereken: {action}",
        ]
    else:
        topic = _topic_from_text(text, subject)
        sentences = [
            f"{actor}, {topic} hakkında bilgilendirme gönderiyor.",
            "Acil bir aksiyon görünmüyor; bilgi olarak okuyabilirsin.",
        ]
    return _compose_limited_summary(sentences, limit)


def _compose_limited_summary(sentences: list[str], limit: int) -> str:
    chosen: list[str] = []
    length = 0
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if sentence[-1] not in ".!?":
            sentence += "."
        next_length = length + len(sentence) + (1 if chosen else 0)
        if next_length > limit:
            continue
        chosen.append(sentence)
        length = next_length
    if chosen:
        return " ".join(chosen)
    fallback = "Bu mail önemli bir bilgilendirme içeriyor."
    return fallback if len(fallback) <= limit else "Bilgilendirme var."


def _sender_name(sender: str) -> str:
    if not sender:
        return "Gönderen"
    return sender.split("(", 1)[0].strip() or "Gönderen"


def _subject_hint(subject: str) -> str:
    subject = clean_text(subject, 90, ellipsis=False)
    return subject.rstrip(".") or "bu konu"


def _service_hint(text: str, subject: str, sender: str) -> str:
    combined = f"{subject} {sender} {text}".lower()
    known = {
        "google": "Google",
        "openai": "OpenAI",
        "chatgpt": "ChatGPT",
        "linkedin": "LinkedIn",
        "github": "GitHub",
        "microsoft": "Microsoft",
        "apple": "Apple",
    }
    for needle, label in known.items():
        if needle in combined:
            return label
    return ""


def _topic_from_text(text: str, subject: str) -> str:
    subject = _subject_hint(subject)
    if subject and subject != "bu konu":
        return subject
    words = [word for word in re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşü0-9]{4,}", text) if word.lower() not in {"mail", "email", "hesap", "google"}]
    return " ".join(words[:5]) if words else "bu konu"


def _fit_summary(prefix: str, text: str, limit: int) -> str:
    available = max(120, limit - len(prefix))
    sentences = _summary_sentences(text, available)
    core = " ".join(sentences).strip()
    if not core:
        core = _trim_without_ellipsis(text, available)
    return (prefix + core).strip()


def _summary_sentences(text: str, limit: int) -> list[str]:
    pieces = [item.strip() for item in re.split(r"(?<=[.!?])\s+", text) if item.strip()]
    cleaned: list[str] = []
    seen: set[str] = set()
    length = 0
    for piece in pieces:
        piece = _trim_sentence_noise(piece)
        if len(piece) < 12:
            continue
        key = piece.lower()
        if key in seen:
            continue
        next_length = length + len(piece) + (1 if cleaned else 0)
        if next_length > limit:
            continue
        seen.add(key)
        cleaned.append(piece)
        length = next_length
        if len(cleaned) >= 4:
            break
    return cleaned


def _trim_sentence_noise(value: str) -> str:
    value = value.strip().strip(".")
    value = re.sub(r"\s+", " ", value)
    return value + "." if value else value


def _trim_without_ellipsis(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    trimmed = text[:limit].rsplit(" ", 1)[0].strip()
    return trimmed.rstrip(".,;:-")


def clean_text(value: str, limit: int = 900, ellipsis: bool = True) -> str:
    value = re.sub(r"<(script|style).*?</\1>", " ", value or "", flags=re.IGNORECASE | re.DOTALL)
    value = re.sub(r"\[\s*image\s*:\s*[^\]]+\]", " ", value, flags=re.IGNORECASE)
    value = re.sub(r"\bimage\s*:\s*\S+", " ", value, flags=re.IGNORECASE)
    value = re.sub(r"<[^>]+>", " ", value)
    value = (
        value.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
    )
    value = re.sub(r"https?://\S+", "", value)
    value = re.sub(r"([a-zığüşöç])([A-ZİĞÜŞÖÇ])", r"\1 \2", value)
    value = value.replace("Open AI", "OpenAI").replace("Chat GPT", "ChatGPT")
    value = re.sub(r"\b(OpenAI|ChatGPT|Google)([a-zığüşöç])", r"\1 \2", value)
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) <= limit:
        return value
    if not ellipsis:
        return _trim_without_ellipsis(value, limit)
    return value[: max(1, limit - 3)].rstrip() + "..."


def clean_sender(value: str) -> str:
    raw = value or ""
    match = re.search(r"([^<]+)<([^>]+)>", raw)
    if match:
        name = match.group(1).strip().strip('"')
        email = match.group(2).strip()
        return f"{name} ({email})" if name else email
    return clean_text(raw, 180)


def format_date(value: str) -> str:
    try:
        parsed = parsedate_to_datetime(value)
    except Exception:
        return value
    months = ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"]
    return f"{parsed.day:02d} {months[parsed.month - 1]} {parsed.year}, {parsed.hour:02d}:{parsed.minute:02d}"


def _chip_cell(text: str, kind: str | None = None) -> str:
    class_name = "date-chip" if kind == "date" else TAG_CLASSES.get(text, "tag-info")
    return f"<td class='chip-gap'><span class='chip {class_name}'>{html.escape(text)}</span></td>"


TAG_CLASSES = {
    "Acil": "tag-urgent",
    "Cevap": "tag-reply",
    "Fatura/Ödeme": "tag-money",
    "Toplantı": "tag-meeting",
    "Güvenlik": "tag-security",
    "Onay": "tag-approval",
    "Bilgi": "tag-info",
}


def _general_html(body: str) -> str:
    return f"""
    <div style="font-family:'Plus Jakarta Sans','Segoe UI',Arial; font-size:14px; line-height:1.55; color:inherit;">
      {body}
    </div>
    """


def _html_page(body: str) -> str:
    return f"""
<html>
<head>
<style>
body {{
  margin: 0;
  font-family: "Plus Jakarta Sans", "Segoe UI", sans-serif;
  color: #111827;
  background: transparent;
}}
.empty {{
  color: #64748b;
  font-size: 14px;
  padding: 10px;
}}
.mail-card {{
  border-bottom: 1px solid #e5edf6;
  padding: 0 0 18px 0;
  margin: 0 0 18px 0;
}}
.topline {{
  margin-bottom: 8px;
}}
.subject-cell {{
  white-space: nowrap;
}}
.subject-cell strong {{
  font-size: 15px;
}}
.sender {{
  color: #475569;
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}}
.spacer {{
  height: 10px;
}}
p {{
  margin: 4px 0;
  line-height: 1.45;
}}
b {{
  font-weight: 800;
}}
.chip-gap {{
  padding-right: 7px;
  padding-bottom: 4px;
  white-space: nowrap;
}}
.chip {{
  display: inline-block;
  border-radius: 10px;
  padding: 4px 10px;
  font-size: 11px;
  font-weight: 800;
  border: 1px solid transparent;
}}
.date-chip {{
  background: #f1f5f9;
  color: #334155;
  border: 1px solid #dbe4ef;
}}
.tag-urgent {{ background: #fee2e2; color: #991b1b; border-color: #fecaca; }}
.tag-reply {{ background: #dbeafe; color: #1e40af; border-color: #bfdbfe; }}
.tag-money {{ background: #dcfce7; color: #166534; border-color: #bbf7d0; }}
.tag-meeting {{ background: #fef3c7; color: #92400e; border-color: #fde68a; }}
.tag-security {{ background: #ede9fe; color: #5b21b6; border-color: #ddd6fe; }}
.tag-approval {{ background: #fae8ff; color: #86198f; border-color: #f5d0fe; }}
.tag-info {{ background: #e2e8f0; color: #334155; border-color: #cbd5e1; }}
</style>
</head>
<body>{body}</body>
</html>
"""

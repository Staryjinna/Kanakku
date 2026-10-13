"""Reminder drafting: explicit steps, not an open-ended loop.

gather facts -> choose tone -> 1 model call -> check the draft against the facts -> at most 1
repair call -> otherwise fall back to a fixed template. The owner always reviews and approves."""

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from app.followups.templates import amount_decimal, fmt_date, fmt_inr, render_template
from app.llm.gateway import Gateway
from app.llm.providers.base import LLMError

GENTLE_UNDER = 15  # days overdue: < 15 gentle, 15-45 firm, > 45 final
FINAL_OVER = 45

FORBIDDEN_EN = (
    "interest", "penalty", "penalties", "legal", "lawyer", "court", "police", "late fee",
    "fine of", "charges",
)  # fmt: skip
FORBIDDEN_TA = ("வட்டி", "அபராதம்", "சட்ட", "நீதிமன்ற", "காவல்")
GENTLE_BANNED = ("final", "immediately", "urgent")
FIRM_BANNED = ("final",)


@dataclass
class Facts:
    customer_name: str
    invoice_no: str
    amount_paise: int  # balance still due
    due_date: str  # ISO
    days_overdue: int
    business_name: str
    language: str = "en"
    channel: str = "whatsapp"
    earlier_reminders: int = 0

    @property
    def tone(self) -> str:
        return choose_tone(self.days_overdue)


@dataclass
class DraftResult:
    text: str
    tone: str
    used_template: bool
    llm_calls: int
    problems: list[str] = field(default_factory=list)  # what the model's last attempt got wrong


def choose_tone(days_overdue: int) -> str:
    if days_overdue < GENTLE_UNDER:
        return "gentle"
    return "firm" if days_overdue <= FINAL_OVER else "final"


def days_overdue(due_date: str, today: date) -> int:
    return max(0, (today - date.fromisoformat(due_date)).days)


# ---------- checking a draft against the facts ----------


def _ascii_digits(text: str) -> str:
    out = []
    for ch in text:
        out.append(str(unicodedata.decimal(ch)) if ch.isdigit() else ch)
    return "".join(out)


def _numbers_in(text: str) -> list[str]:
    return [m.replace(",", "") for m in re.findall(r"\d[\d,]*(?:\.\d+)?", _ascii_digits(text))]


def _digit_groups(text: str) -> set[str]:
    return {str(int(g)) for g in re.findall(r"\d+", _ascii_digits(text))}


def check_draft(text: str, facts: Facts) -> list[str]:
    """Return a list of problems (empty = the draft is safe to show)."""
    problems: list[str] = []
    lower = text.lower()
    if not text.strip():
        return ["The message is empty."]
    if facts.customer_name.lower() not in lower:
        problems.append(f"It must address the customer exactly as '{facts.customer_name}'.")
    if facts.invoice_no.lower() not in lower:
        problems.append(f"It must mention invoice number {facts.invoice_no}.")
    amount = amount_decimal(facts.amount_paise)
    due = date.fromisoformat(facts.due_date)
    allowed = {
        *_digit_groups(facts.invoice_no),
        *_digit_groups(facts.business_name),
        *_digit_groups(facts.customer_name),
        str(due.day),
        str(due.month),
        str(due.year),
        str(facts.days_overdue),
    }
    found_amount = False
    stray: list[str] = []
    for token in _numbers_in(text):
        try:
            value = Decimal(token)
        except InvalidOperation:
            continue
        if value == amount:
            found_amount = True
        elif "." in token or str(int(value)) not in allowed:
            stray.append(token)
    if not found_amount:
        problems.append(f"It must state the amount due as ₹{fmt_inr(facts.amount_paise)}.")
    if stray:
        problems.append(
            "It contains numbers that are not in the facts: " + ", ".join(sorted(set(stray))) + "."
        )
    banned = FORBIDDEN_EN + FORBIDDEN_TA
    hit = [w for w in banned if w in lower]
    if hit:
        problems.append("It must not mention " + ", ".join(hit) + ".")
    if facts.language == "en":
        tone_banned = {"gentle": GENTLE_BANNED, "firm": FIRM_BANNED}.get(facts.tone, ())
        words = [w for w in tone_banned if w in lower]
        if words:
            problems.append(f"The tone must be {facts.tone}; avoid: {', '.join(words)}.")
        if facts.tone == "final" and "final" not in lower:
            problems.append("This is the final reminder; say so plainly.")
    return problems


def clean(raw: str) -> str:
    text = raw.strip()
    text = re.sub(r"^```[a-z]*\n?|```$", "", text, flags=re.M).strip()
    text = re.sub(r"^(message|reminder|draft)\s*:\s*", "", text, flags=re.I).strip()
    if len(text) > 1 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1].strip()
    return text


# ---------- prompts ----------

TONE_RULES = {
    "gentle": "Friendly and polite. Treat it as a simple reminder. Do not sound upset.",
    "firm": "Polite but firm. Say the payment is overdue and ask for payment soon.",
    "final": "Serious and direct. Say this is the final reminder and ask for immediate payment. "
    "Do not threaten anything.",
}


def build_messages(facts: Facts) -> list[dict[str, str]]:
    language = "Tamil (தமிழ்)" if facts.language == "ta" else "English"
    length = "at most 70 words" if facts.channel == "whatsapp" else "at most 120 words"
    system = (
        "You write short payment reminder messages for a small Indian business owner to send to "
        f"a customer by {facts.channel}.\n"
        f"Write in {language}. Tone: {TONE_RULES[facts.tone]}\n"
        "Rules:\n"
        "- Use ONLY the facts provided. Do not invent anything.\n"
        "- Write the customer's name and the invoice number exactly as given (do not translate).\n"
        "- State the amount due as ₹ followed by the number given, and the due date.\n"
        "- Do not mention any other amount, date, fee, interest, penalty, legal action, bank "
        "details or phone number.\n"
        f"- Sign off with the business name. Plain text only, {length}.\n"
        "Reply with the message text only."
    )
    lines = [
        f"Customer name: {facts.customer_name}",
        f"Invoice number: {facts.invoice_no}",
        f"Amount due: ₹{fmt_inr(facts.amount_paise)}",
        f"Due date: {fmt_date(facts.due_date)}",
        f"Days overdue: {facts.days_overdue}",
        f"Business name: {facts.business_name}",
    ]
    if facts.earlier_reminders:
        lines.append(
            "Earlier reminders were already sent (you may say this is a follow-up, "
            "but do not state a number)."
        )
    return [{"role": "system", "content": system}, {"role": "user", "content": "\n".join(lines)}]


def template_for(facts: Facts) -> str:
    return render_template(
        facts.language,
        facts.tone,
        name=facts.customer_name,
        business=facts.business_name,
        invoice_no=facts.invoice_no,
        amount_paise=facts.amount_paise,
        due_date=facts.due_date,
        days_overdue=facts.days_overdue,
    )


async def draft_reminder(
    gateway: Gateway, facts: Facts, business_id: int, *, variation: bool = False
) -> DraftResult:
    """At most 1 model call plus 1 repair call; falls back to a template, never fails open."""
    messages = build_messages(facts)
    temperature = 0.4 if variation else 0.0
    calls = 0
    problems: list[str] = []
    text = ""
    try:
        resp = await gateway.chat(
            messages, purpose="followup_draft", business_id=business_id, temperature=temperature
        )
        calls += 1
        text = clean(resp.text)
        problems = check_draft(text, facts)
        if problems:
            repair = [
                *messages,
                {"role": "assistant", "content": text},
                {
                    "role": "user",
                    "content": "That message has problems:\n- "
                    + "\n- ".join(problems)
                    + "\nRewrite it fixing every problem. Reply with the message text only.",
                },
            ]
            resp = await gateway.chat(
                repair, purpose="followup_repair", business_id=business_id, temperature=temperature
            )
            calls += 1
            text = clean(resp.text)
            problems = check_draft(text, facts)
    except LLMError:
        problems = problems or ["The AI model was unavailable."]
        text = ""
    if text and not problems:
        return DraftResult(text, facts.tone, False, calls)
    return DraftResult(template_for(facts), facts.tone, True, calls, problems)

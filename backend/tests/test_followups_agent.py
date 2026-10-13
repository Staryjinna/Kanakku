import json
from datetime import date
from pathlib import Path

import pytest

from app.followups import agent
from app.followups.agent import Facts, check_draft, choose_tone
from app.followups.templates import (
    fmt_date,
    fmt_inr,
    mailto_url,
    normalize_phone,
    render_template,
    whatsapp_url,
)
from app.llm.gateway import Gateway
from app.llm.providers.fake import FakeProvider

ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = [
    json.loads(line)
    for line in (ROOT / "evals" / "followup_scenarios.jsonl").read_text().splitlines()
    if line.strip()
]


def facts_from(d: dict) -> Facts:  # type: ignore[type-arg]
    return Facts(
        customer_name=d["customer_name"],
        invoice_no=d["invoice_no"],
        amount_paise=d["total_paise"] - d["paid_paise"],
        due_date=d["due_date"],
        days_overdue=agent.days_overdue(d["due_date"], date.fromisoformat(d["today"])),
        business_name=d["business_name"],
        language=d["language"],
        channel=d["channel"],
        earlier_reminders=d["earlier_reminders"],
    )


@pytest.mark.parametrize(
    ("days", "tone"),
    [
        (0, "gentle"),
        (14, "gentle"),
        (15, "firm"),
        (30, "firm"),
        (45, "firm"),
        (46, "final"),
        (400, "final"),
    ],
)
def test_choose_tone_boundaries(days: int, tone: str) -> None:
    assert choose_tone(days) == tone


def test_days_overdue() -> None:
    assert agent.days_overdue("2026-06-05", date(2026, 6, 15)) == 10
    assert agent.days_overdue("2026-06-15", date(2026, 6, 15)) == 0
    assert agent.days_overdue("2026-07-01", date(2026, 6, 15)) == 0


def test_formatting() -> None:
    assert fmt_inr(500000) == "5,000"
    assert fmt_inr(12500000) == "1,25,000"
    assert fmt_inr(123456789) == "12,34,567.89"
    assert fmt_inr(99) == "0.99" and fmt_inr(100) == "1"
    assert fmt_date("2026-05-16") == "16 May 2026"


def test_phone_and_links() -> None:
    assert normalize_phone("98765 43210") == "919876543210"
    assert normalize_phone("+91 98765-43210") == "919876543210"
    assert normalize_phone("09876543210") == "919876543210"
    assert normalize_phone("12345") is None and normalize_phone(None) is None
    url = whatsapp_url("9876543210", "Hi & bye? ₹5,000\nline2")
    assert url and url.startswith("https://wa.me/919876543210?text=")
    assert " " not in url and "&" not in url.split("?text=")[1] and "%0A" in url
    assert whatsapp_url("bad", "x") is None
    m = mailto_url("a@b.com", "Payment reminder: invoice INV-1", "Hello & thanks")
    assert m and m.startswith("mailto:a@b.com?subject=Payment%20reminder") and "%26" in m
    assert mailto_url(None, "s", "b") is None


@pytest.mark.parametrize("language", ["en", "ta"])
@pytest.mark.parametrize("days", [3, 20, 90])
def test_fallback_templates_always_pass_their_own_checks(language: str, days: int) -> None:
    f = Facts("Ravi Kumar", "INV-101", 123456, "2026-04-05", days, "Asha Traders 2", language)
    text = render_template(
        language, f.tone, name=f.customer_name, business=f.business_name,
        invoice_no=f.invoice_no, amount_paise=f.amount_paise, due_date=f.due_date,
        days_overdue=days,
    )  # fmt: skip
    assert check_draft(text, f) == [], text


def test_check_draft_catches_each_problem() -> None:
    f = Facts("Ravi Kumar", "INV-101", 500000, "2026-06-05", 10, "Asha Traders")
    good = "Hello Ravi Kumar, invoice INV-101 for ₹5,000 due on 5 Jun 2026 is pending. Asha Traders"
    assert check_draft(good, f) == []
    assert check_draft("", f) == ["The message is empty."]
    assert any("Ravi Kumar" in p for p in check_draft(good.replace("Ravi Kumar", "Ravi"), f))
    assert any("INV-101" in p for p in check_draft(good.replace("INV-101", "INV-102"), f))
    assert any("₹5,000" in p for p in check_draft(good.replace("5,000", "6,000"), f))
    assert any("not in the facts" in p for p in check_draft(good + " Pay ₹250 more.", f))
    assert any("interest" in p for p in check_draft(good + " Interest applies.", f))
    assert any("tone" in p for p in check_draft(good + " This is urgent.", f))
    assert check_draft(good.replace("5,000", "5000.00"), f) == []  # same amount, other format


def test_check_draft_final_tone_must_say_final() -> None:
    f = Facts("Ravi Kumar", "INV-101", 500000, "2026-04-01", 75, "Asha Traders")
    base = "Dear Ravi Kumar, invoice INV-101 for ₹5,000 due on 1 Apr 2026 is 75 days overdue."
    assert any("final" in p for p in check_draft(base, f))
    assert check_draft(base + " This is the final reminder.", f) == []


def test_prompt_contains_facts_and_no_contact_details() -> None:
    f = Facts("Ravi Kumar", "INV-101", 500000, "2026-06-05", 10, "Asha Traders", "ta", "email", 1)
    system, user = agent.build_messages(f)
    assert "Tamil" in system["content"] and "email" in system["content"]
    for needle in (
        "Ravi Kumar",
        "INV-101",
        "₹5,000",
        "5 Jun 2026",
        "Asha Traders",
        "do not state a number",
    ):
        assert needle in user["content"]


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s["name"] for s in SCENARIOS])
async def test_scenario(
    scenario: dict, gateway: Gateway, provider: FakeProvider, business_id: int
) -> None:  # type: ignore[type-arg]
    facts = facts_from(scenario["facts"])
    expect = scenario["expect"]
    template = agent.template_for(facts)
    for reply in scenario["fake_replies"]:
        provider.push(template if reply == "__TEMPLATE__" else reply)
    result = await agent.draft_reminder(gateway, facts, business_id)
    assert result.tone == expect["tone"]
    assert result.used_template is expect["used_template"]
    assert result.llm_calls == expect["calls"]  # never more than 1 call + 1 repair
    assert result.llm_calls <= 2
    for needle in expect["includes"]:
        assert needle in result.text
    for needle in expect["excludes"]:
        assert needle not in result.text
    # whatever happens, the final text is safe to show
    assert check_draft(result.text, facts) == []


async def test_model_down_falls_back_to_template(
    gateway: Gateway, provider: FakeProvider, business_id: int
) -> None:
    from app.llm.providers.base import LLMError

    async def boom(**kwargs):  # type: ignore[no-untyped-def]
        raise LLMError("down")

    provider.chat = boom  # type: ignore[method-assign,assignment]
    f = Facts("Ravi Kumar", "INV-101", 500000, "2026-06-05", 10, "Asha Traders")
    r = await agent.draft_reminder(gateway, f, business_id)
    assert r.used_template and r.llm_calls == 0 and "Ravi Kumar" in r.text


async def test_variation_skips_cache(
    gateway: Gateway, provider: FakeProvider, business_id: int
) -> None:
    f = Facts("Ravi Kumar", "INV-101", 500000, "2026-06-05", 10, "Asha Traders")
    good1 = (
        "Hello Ravi Kumar, invoice INV-101 for ₹5,000 due on 5 Jun 2026 is pending. Asha Traders"
    )
    good2 = "Hi Ravi Kumar, a reminder: INV-101, ₹5,000, due 5 Jun 2026. Thanks, Asha Traders"
    provider.push(good1, good2)
    a = await agent.draft_reminder(gateway, f, business_id)
    b = await agent.draft_reminder(gateway, f, business_id)  # deterministic call: cached
    assert a.text == b.text == good1
    c = await agent.draft_reminder(gateway, f, business_id, variation=True)
    assert c.text == good2

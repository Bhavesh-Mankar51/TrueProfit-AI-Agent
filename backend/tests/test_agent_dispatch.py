import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent import graph as agent_graph
from app.agent.graph import RouterDecision, missing_required_fields, route_after_router

COMPLETE_FIELDS = {
    "log_expense": dict(
        amount=40,
        category="inventory",
        description="10 kg rice",
        vendor_name="Sharma Traders",
        payment_method="cash",
    ),
    "log_income": dict(
        amount=4000, description="chair", customer_name="Ramesh", payment_method="cash"
    ),
    "log_credit_repayment": dict(amount=300, customer_name="Ramesh"),
    "vendor_credit": dict(amount=2000, vendor_name="Sharma Traders", due_date="2026-08-01"),
    "vendor_payment": dict(amount=2000, vendor_name="Sharma Traders", payment_method="cash"),
    "customer_credit": dict(amount=300, customer_name="Ramesh", due_date="2026-08-01"),
    "query_report": {},
    "list_dues": dict(dues_type="vendor"),
    "other": {},
}


def decision(**overrides) -> RouterDecision:
    defaults = dict(intent="other")
    defaults.update(overrides)
    return RouterDecision(**defaults)


@pytest.mark.parametrize(
    "intent,expected_node",
    [
        ("log_expense", "call_expense_tool"),
        ("log_income", "call_income_tool"),
        ("log_credit_repayment", "call_credit_repayment_tool"),
        ("vendor_credit", "call_vendor_credit_tool"),
        ("vendor_payment", "call_vendor_payment_tool"),
        ("customer_credit", "call_customer_credit_tool"),
        ("query_report", "call_report_tool"),
        ("list_dues", "call_list_dues_tool"),
        ("other", "unclear"),
    ],
)
def test_route_after_router_maps_intent_to_node(intent, expected_node):
    state = {"decision": decision(intent=intent, **COMPLETE_FIELDS[intent])}
    assert route_after_router(state) == expected_node


def test_route_after_router_clarification_overrides_intent():
    state = {"decision": decision(intent="log_expense", clarification_needed=True)}
    assert route_after_router(state) == "clarify"


@pytest.mark.parametrize(
    "intent,dropped",
    [
        ("log_income", "customer_name"),
        ("log_income", "description"),
        ("log_income", "amount"),
        ("log_income", "payment_method"),
        ("log_expense", "category"),
        ("log_expense", "description"),
        ("log_expense", "vendor_name"),
        ("log_expense", "payment_method"),
        ("log_credit_repayment", "customer_name"),
        ("vendor_credit", "due_date"),
        ("vendor_payment", "vendor_name"),
        ("vendor_payment", "payment_method"),
        ("customer_credit", "customer_name"),
        ("list_dues", "dues_type"),
    ],
)
def test_route_after_router_clarifies_when_required_field_missing(intent, dropped):
    fields = {k: v for k, v in COMPLETE_FIELDS[intent].items() if k != dropped}
    state = {"decision": decision(intent=intent, **fields)}
    assert route_after_router(state) == "clarify"


def test_income_without_customer_name_never_reaches_the_tool():
    state = {
        "decision": decision(
            intent="log_income", amount=4000, description="sale of chair", payment_method="cash"
        )
    }
    assert missing_required_fields(state["decision"]) == ["customer_name"]
    assert route_after_router(state) == "clarify"


def test_blank_customer_name_counts_as_missing():
    state = {
        "decision": decision(
            intent="log_income",
            amount=4000,
            description="chair",
            customer_name="   ",
            payment_method="cash",
        )
    }
    assert route_after_router(state) == "clarify"


def test_income_without_item_description_never_reaches_the_tool():
    state = {
        "decision": decision(
            intent="log_income", amount=20000, customer_name="Rajesh", payment_method="cash"
        )
    }
    assert missing_required_fields(state["decision"]) == ["description"]
    assert route_after_router(state) == "clarify"


def test_income_without_payment_method_never_reaches_the_tool():
    state = {
        "decision": decision(
            intent="log_income", amount=100000, description="furniture", customer_name="Karan"
        )
    }
    assert missing_required_fields(state["decision"]) == ["payment_method"]
    assert route_after_router(state) == "clarify"


def test_credit_repayment_is_distinct_from_income():
    state = {"decision": decision(intent="log_credit_repayment", customer_name="Ramesh", amount=300)}
    assert route_after_router(state) == "call_credit_repayment_tool"


@pytest.fixture
def captured_calls(monkeypatch):
    calls = []

    async def fake_invoke_tool(name, args):
        calls.append((name, args))
        return {"ok": True, "tool": name, "args": args}

    monkeypatch.setattr(agent_graph, "_invoke_tool", fake_invoke_tool)
    return calls


async def test_call_expense_tool_passes_every_field_through(captured_calls):
    state = {"decision": decision(intent="log_expense", **COMPLETE_FIELDS["log_expense"])}
    result = await agent_graph.call_expense_tool(state)

    assert captured_calls == [
        (
            "log_expense",
            {
                "amount": 40,
                "category": "inventory",
                "description": "10 kg rice",
                "vendor_name": "Sharma Traders",
                "payment_method": "cash",
                "date": None,
            },
        )
    ]
    assert result["tool_error"] is None


async def test_call_expense_tool_keeps_non_cash_payment_method(captured_calls):
    fields = {**COMPLETE_FIELDS["log_expense"], "payment_method": "UPI"}
    state = {"decision": decision(intent="log_expense", **fields)}
    await agent_graph.call_expense_tool(state)

    assert captured_calls[0][1]["payment_method"] == "upi"


def test_expense_without_payment_method_never_reaches_the_tool():
    fields = {k: v for k, v in COMPLETE_FIELDS["log_expense"].items() if k != "payment_method"}
    state = {"decision": decision(intent="log_expense", **fields)}
    assert missing_required_fields(state["decision"]) == ["payment_method"]
    assert route_after_router(state) == "clarify"


@pytest.mark.parametrize(
    "payment_method,expected_category",
    [("cash", "cash_sale"), ("upi", "online_payment"), ("card", "online_payment")],
)
async def test_call_income_tool_derives_category_from_payment_method(
    captured_calls, payment_method, expected_category
):
    fields = {**COMPLETE_FIELDS["log_income"], "payment_method": payment_method}
    state = {"decision": decision(intent="log_income", **fields)}
    await agent_graph.call_income_tool(state)

    name, args = captured_calls[0]
    assert name == "log_income"
    assert args["category"] == expected_category
    assert args["payment_method"] == payment_method
    assert args["customer_name"] == "Ramesh"


async def test_call_income_tool_ignores_router_supplied_category(captured_calls):
    fields = {**COMPLETE_FIELDS["log_income"], "payment_method": "upi", "category": "cash_sale"}
    state = {"decision": decision(intent="log_income", **fields)}
    await agent_graph.call_income_tool(state)

    assert captured_calls[0][1]["category"] == "online_payment"


async def test_call_credit_repayment_tool_passes_customer_and_amount(captured_calls):
    state = {"decision": decision(intent="log_credit_repayment", customer_name="Ramesh", amount=300)}
    await agent_graph.call_credit_repayment_tool(state)

    assert captured_calls == [
        ("log_credit_repayment", {"customer_name": "Ramesh", "amount": 300, "date": None})
    ]


async def test_call_vendor_credit_tool(captured_calls):
    state = {
        "decision": decision(
            intent="vendor_credit", vendor_name="Sharma Traders", amount=2000, due_date="2026-08-01"
        )
    }
    await agent_graph.call_vendor_credit_tool(state)

    name, args = captured_calls[0]
    assert name == "add_vendor_credit"
    assert args["vendor_name"] == "Sharma Traders"
    assert args["due_date"] == "2026-08-01"


async def test_call_vendor_payment_tool(captured_calls):
    fields = {**COMPLETE_FIELDS["vendor_payment"], "payment_method": "UPI"}
    state = {"decision": decision(intent="vendor_payment", **fields)}
    await agent_graph.call_vendor_payment_tool(state)

    name, args = captured_calls[0]
    assert name == "log_vendor_payment"
    assert args["vendor_name"] == "Sharma Traders"
    assert args["amount"] == 2000
    assert args["payment_method"] == "upi"


def test_vendor_payment_is_distinct_from_vendor_credit():
    state = {"decision": decision(intent="vendor_payment", **COMPLETE_FIELDS["vendor_payment"])}
    assert route_after_router(state) == "call_vendor_payment_tool"


async def test_call_customer_credit_tool_passes_due_date(captured_calls):
    state = {
        "decision": decision(
            intent="customer_credit", customer_name="Ramesh", amount=300, due_date="2026-08-01"
        )
    }
    await agent_graph.call_customer_credit_tool(state)

    name, args = captured_calls[0]
    assert name == "add_customer_credit"
    assert args["customer_name"] == "Ramesh"
    assert args["due_date"] == "2026-08-01"


async def test_call_list_dues_tool_passes_type(captured_calls):
    state = {"decision": decision(intent="list_dues", dues_type="vendor")}
    await agent_graph.call_list_dues_tool(state)

    assert captured_calls == [("list_pending_dues", {"type": "vendor"})]


async def test_call_report_tool_defaults_to_profit_current_month(captured_calls):
    state = {"decision": decision(intent="query_report")}
    await agent_graph.call_report_tool(state)

    name, args = captured_calls[0]
    assert name == "get_profit_summary"
    assert "start_date" in args and "end_date" in args


async def test_call_report_tool_comparison_fetches_two_periods(captured_calls):
    state = {
        "decision": decision(
            intent="query_report",
            comparison=True,
            category="electricity",
            start_date="2026-07-01",
            end_date="2026-07-25",
        )
    }
    result = await agent_graph.call_report_tool(state)

    assert [c[0] for c in captured_calls] == ["get_expense_summary", "get_expense_summary"]
    assert result["tool_result"]["comparison"] is True


async def test_clarify_node_uses_router_question():
    state = {
        "decision": decision(
            intent="log_expense",
            clarification_needed=True,
            clarification_question="How much did you spend?",
            **COMPLETE_FIELDS["log_expense"],
        )
    }
    result = await agent_graph.clarify_node(state)
    assert result["reply"] == "How much did you spend?"


async def test_clarify_node_asks_expense_specific_wording():
    state = {"decision": decision(intent="log_expense", amount=8000, category="electricity")}
    reply = (await agent_graph.clarify_node(state))["reply"].lower()
    assert "expense for" in reply and "who did you pay" in reply
    assert "how did you pay — cash, upi, or card?" in reply
    assert "sold" not in reply


async def test_clarify_node_asks_for_missing_customer_name_on_income():
    state = {
        "decision": decision(
            intent="log_income", amount=4000, description="chair", payment_method="cash"
        )
    }
    result = await agent_graph.clarify_node(state)
    assert "customer" in result["reply"].lower()


async def test_clarify_node_asks_for_every_missing_income_field_in_one_turn():
    state = {"decision": decision(intent="log_income", amount=20000)}
    reply = (await agent_graph.clarify_node(state))["reply"].lower()
    assert "sold" in reply and "customer" in reply and "upi" in reply


async def test_clarify_node_asks_payment_mode_when_only_that_is_missing():
    fields = {k: v for k, v in COMPLETE_FIELDS["log_income"].items() if k != "payment_method"}
    state = {"decision": decision(intent="log_income", **fields)}
    reply = (await agent_graph.clarify_node(state))["reply"].lower()
    assert "cash, upi, or card" in reply


async def test_unclear_node_returns_canned_reply():
    result = await agent_graph.unclear_node({"decision": decision(intent="other")})
    assert "rephrase" in result["reply"].lower()

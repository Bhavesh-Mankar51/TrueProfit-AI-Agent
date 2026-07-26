import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mcp_server.tools.credit import add_customer_credit, add_vendor_credit, list_pending_dues
from mcp_server.tools.expenses import log_expense
from mcp_server.tools.income import log_credit_repayment, log_income
from mcp_server.tools.reports import get_expense_summary, get_income_summary, get_profit_summary
from mcp_server.validation import ValidationError


async def test_log_expense_valid(db_pool):
    row = await log_expense(amount=40, category="inventory", description="biscuits")
    assert row["amount"] == 40.0
    assert row["category"] == "inventory"
    assert row["payment_method"] == "cash"
    assert row["expense_date"] is not None


async def test_log_expense_resolves_vendor(db_pool):
    row = await log_expense(amount=500, category="inventory", vendor_name="Sharma Traders")
    assert row["vendor_id"] is not None


@pytest.mark.parametrize("bad_amount", [0, -10])
async def test_log_expense_rejects_bad_amount(db_pool, bad_amount):
    with pytest.raises(ValidationError):
        await log_expense(amount=bad_amount, category="misc")


async def test_log_income_defaults_cash(db_pool):
    row = await log_income(amount=40, category="cash_sale", item_description="2 packets biscuits")
    assert row["payment_method"] == "cash"


async def test_log_income_rejects_credit_repayment_category(db_pool):
    with pytest.raises(ValueError):
        await log_income(amount=40, category="credit_repayment")


async def test_credit_repayment_settles_pending_row(db_pool):
    await add_customer_credit(customer_name="Ramesh", amount=300)
    result = await log_credit_repayment(customer_name="Ramesh", amount=300)
    assert result["amount"] == 300.0
    assert len(result["settled_customer_credit_ids"]) == 1
    assert result["unmatched_amount"] == 0.0

    dues = await list_pending_dues(type="customer")
    assert all(d["customer_name"] != "Ramesh" for d in dues)


async def test_credit_repayment_with_no_pending_credit_leaves_unmatched(db_pool):
    result = await log_credit_repayment(customer_name="NoOneOwesThis", amount=100)
    assert result["settled_customer_credit_ids"] == []
    assert result["unmatched_amount"] == 100.0


async def test_add_vendor_credit_and_list_pending_dues(db_pool):
    await add_vendor_credit(vendor_name="Sharma Traders", amount=2000, note="stock restock")
    dues = await list_pending_dues(type="vendor")
    assert len(dues) == 1
    assert dues[0]["vendor_name"] == "Sharma Traders"
    assert dues[0]["amount"] == 2000.0


async def test_add_customer_credit_and_list_pending_dues(db_pool):
    await add_customer_credit(customer_name="Ramesh", amount=300, due_date="2026-08-01")
    dues = await list_pending_dues(type="customer")
    assert len(dues) == 1
    assert dues[0]["customer_name"] == "Ramesh"
    assert dues[0]["due_date"] == "2026-08-01"


async def test_add_customer_credit_without_due_date_is_still_allowed(db_pool):
    row = await add_customer_credit(customer_name="Ramesh", amount=300)
    assert row["due_date"] is None


async def test_expense_summary_grouping(db_pool):
    await log_expense(amount=100, category="rent")
    await log_expense(amount=50, category="rent")
    await log_expense(amount=20, category="transport")

    summary = await get_expense_summary(start_date="2020-01-01", end_date="2030-01-01", group_by="category")
    assert summary["total"] == 170.0
    categories = {b["category"]: b["total"] for b in summary["breakdown"]}
    assert categories["rent"] == 150.0
    assert categories["transport"] == 20.0


async def test_income_summary_grouping(db_pool):
    await log_income(amount=40, category="cash_sale")
    await log_income(amount=60, category="online_payment")

    summary = await get_income_summary(start_date="2020-01-01", end_date="2030-01-01")
    assert summary["total"] == 100.0


async def test_concurrent_log_expense_calls_dont_corrupt_data(db_pool):
    results = await asyncio.gather(
        log_expense(amount=40, category="inventory", description="first"),
        log_expense(amount=55, category="transport", description="second"),
    )
    amounts = sorted(r["amount"] for r in results)
    assert amounts == [40.0, 55.0]
    assert len({r["id"] for r in results}) == 2

    summary = await get_expense_summary(start_date="2020-01-01", end_date="2030-01-01")
    assert summary["total"] == 95.0


async def test_profit_summary(db_pool):
    await log_income(amount=200, category="cash_sale")
    await log_expense(amount=80, category="inventory")

    summary = await get_profit_summary(start_date="2020-01-01", end_date="2030-01-01")
    assert summary["total_income"] == 200.0
    assert summary["total_expenses"] == 80.0
    assert summary["profit"] == 120.0

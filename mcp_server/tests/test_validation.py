import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mcp_server.validation import (
    ValidationError,
    clean_amount,
    clean_date,
    clean_dues_type,
    clean_group_by,
    clean_income_category,
    clean_name,
    clean_payment_method,
)


def test_clean_amount_valid():
    assert clean_amount(40) == Decimal("40.00")
    assert clean_amount("40.5") == Decimal("40.50")


@pytest.mark.parametrize("bad", [0, -5, "not-a-number", None])
def test_clean_amount_rejects_invalid(bad):
    with pytest.raises(ValidationError):
        clean_amount(bad)


def test_clean_amount_rejects_absurdly_large():
    with pytest.raises(ValidationError):
        clean_amount(10**12)


def test_clean_date_defaults_to_today():
    from datetime import date

    assert clean_date(None) == date.today()
    assert clean_date("") == date.today()


def test_clean_date_parses_iso():
    from datetime import date

    assert clean_date("2026-01-15") == date(2026, 1, 15)


@pytest.mark.parametrize("bad", ["15-01-2026", "not-a-date", "2026/01/15"])
def test_clean_date_rejects_bad_format(bad):
    with pytest.raises(ValidationError):
        clean_date(bad)


def test_clean_name_requires_nonempty():
    with pytest.raises(ValidationError):
        clean_name("   ")
    with pytest.raises(ValidationError):
        clean_name(None)
    assert clean_name(" Ramesh ") == "Ramesh"


def test_clean_payment_method_valid_and_default():
    assert clean_payment_method(None) == "cash"
    assert clean_payment_method("UPI") == "upi"


def test_clean_payment_method_rejects_unknown():
    with pytest.raises(ValidationError):
        clean_payment_method("bitcoin")


def test_clean_income_category_valid():
    assert clean_income_category("cash_sale") == "cash_sale"


def test_clean_income_category_rejects_unknown():
    with pytest.raises(ValidationError):
        clean_income_category("rent")


def test_clean_group_by_default_and_valid():
    assert clean_group_by(None) == "category"
    assert clean_group_by("week") == "week"


def test_clean_group_by_rejects_unknown():
    with pytest.raises(ValidationError):
        clean_group_by("year")


def test_clean_dues_type():
    assert clean_dues_type("vendor") == "vendor"
    assert clean_dues_type("CUSTOMER") == "customer"
    with pytest.raises(ValidationError):
        clean_dues_type("supplier")


def test_clean_amount_rejects_sql_injection_string():
    with pytest.raises(ValidationError):
        clean_amount("40; DROP TABLE expenses;--")

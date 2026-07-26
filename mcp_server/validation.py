from datetime import date as date_cls
from datetime import datetime
from decimal import Decimal, InvalidOperation

VALID_INCOME_CATEGORIES = {"cash_sale", "online_payment", "credit_repayment"}
VALID_PAYMENT_METHODS = {"cash", "upi", "card"}


class ValidationError(ValueError):
    pass


def clean_amount(amount) -> Decimal:
    try:
        value = Decimal(str(amount))
    except (InvalidOperation, TypeError):
        raise ValidationError(f"amount must be a number, got {amount!r}")
    if value <= 0:
        raise ValidationError("amount must be greater than 0")
    if value > Decimal("100000000"):
        raise ValidationError("amount is unreasonably large")
    return value.quantize(Decimal("0.01"))


def clean_date(value: str | None) -> date_cls:
    if value is None or value == "":
        return date_cls.today()
    if isinstance(value, date_cls):
        return value
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise ValidationError(f"date must be in YYYY-MM-DD format, got {value!r}")


def clean_text(value: str | None, *, max_len: int = 500) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    if len(value) > max_len:
        value = value[:max_len]
    return value or None


def clean_name(value: str, field: str = "name") -> str:
    value = str(value).strip() if value is not None else ""
    if not value:
        raise ValidationError(f"{field} is required")
    if len(value) > 200:
        raise ValidationError(f"{field} is too long")
    return value


def clean_payment_method(value: str | None) -> str:
    value = (value or "cash").strip().lower()
    if value not in VALID_PAYMENT_METHODS:
        raise ValidationError(
            f"payment_method must be one of {sorted(VALID_PAYMENT_METHODS)}, got {value!r}"
        )
    return value


def clean_income_category(value: str) -> str:
    value = (value or "").strip().lower()
    if value not in VALID_INCOME_CATEGORIES:
        raise ValidationError(
            f"category must be one of {sorted(VALID_INCOME_CATEGORIES)}, got {value!r}"
        )
    return value


def clean_group_by(value: str | None, allowed=("category", "day", "week")) -> str:
    value = (value or "category").strip().lower()
    if value not in allowed:
        raise ValidationError(f"group_by must be one of {allowed}, got {value!r}")
    return value


def clean_dues_type(value: str) -> str:
    value = (value or "").strip().lower()
    if value not in {"vendor", "customer"}:
        raise ValidationError(f"type must be 'vendor' or 'customer', got {value!r}")
    return value

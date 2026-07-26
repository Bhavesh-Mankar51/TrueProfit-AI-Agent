from datetime import date, datetime
from decimal import Decimal


def jsonable(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def row_to_dict(row) -> dict:
    return {k: jsonable(v) for k, v in dict(row).items()}


def rows_to_list(rows) -> list[dict]:
    return [row_to_dict(r) for r in rows]

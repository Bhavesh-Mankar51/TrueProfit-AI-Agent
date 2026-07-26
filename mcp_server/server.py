import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.fastmcp import FastMCP

from mcp_server.tools.credit import add_customer_credit, add_vendor_credit, list_pending_dues
from mcp_server.tools.expenses import log_expense
from mcp_server.tools.income import log_credit_repayment, log_income
from mcp_server.tools.reports import get_expense_summary, get_income_summary, get_profit_summary

mcp = FastMCP("shopkeeper-tools")

mcp.tool()(log_expense)
mcp.tool()(log_income)
mcp.tool()(log_credit_repayment)
mcp.tool()(add_vendor_credit)
mcp.tool()(add_customer_credit)
mcp.tool()(list_pending_dues)
mcp.tool()(get_expense_summary)
mcp.tool()(get_income_summary)
mcp.tool()(get_profit_summary)


if __name__ == "__main__":
    mcp.run(transport="stdio")

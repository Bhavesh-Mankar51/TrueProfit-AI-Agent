import os
from datetime import date, datetime, timedelta
from typing import Annotated, Literal, TypedDict, cast

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

from app.agent.mcp_tools import call_tool

load_dotenv()

MODEL_NAME = os.getenv("AGENT_MODEL", "gpt-4o")

Intent = Literal[
    "log_expense",
    "log_income",
    "log_credit_repayment",
    "vendor_credit",
    "customer_credit",
    "query_report",
    "list_dues",
    "other",
]


class RouterDecision(BaseModel):
    intent: Intent = Field(description="The classified intent of the user's latest message.")
    clarification_needed: bool = Field(
        default=False,
        description="True only if a genuinely required field is missing and cannot be defaulted.",
    )
    clarification_question: str | None = Field(
        default=None, description="Short follow-up question to ask, if clarification_needed."
    )

    amount: float | None = None
    category: str | None = Field(
        default=None,
        description="Expense category (inventory/rent/electricity/salary/transport/misc/etc) "
        "or income category (cash_sale/online_payment).",
    )
    description: str | None = None
    vendor_name: str | None = None
    customer_name: str | None = None
    payment_method: str | None = Field(default=None, description="cash | upi | card")
    date: str | None = Field(default=None, description="YYYY-MM-DD, defaults to today")
    due_date: str | None = Field(
        default=None,
        description="YYYY-MM-DD — when this vendor/customer credit is due to be paid back. "
        "Required for vendor_credit and customer_credit; ask if not stated.",
    )
    note: str | None = None

    dues_type: Literal["vendor", "customer"] | None = None

    report_scope: Literal["expense", "income", "profit"] | None = None
    start_date: str | None = Field(default=None, description="YYYY-MM-DD")
    end_date: str | None = Field(default=None, description="YYYY-MM-DD")
    group_by: Literal["category", "day", "week"] | None = None
    comparison: bool = Field(
        default=False, description="True if the user is comparing this period to a prior one."
    )


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    decision: RouterDecision | None
    tool_result: dict | list | None
    tool_error: str | None
    reply: str | None


def _decision(state: AgentState) -> RouterDecision:
    decision = state["decision"]
    assert decision is not None, "decision must be set by router_node before this node runs"
    return decision


def _llm():
    return ChatOpenAI(model=MODEL_NAME, temperature=0)


ROUTER_SYSTEM_PROMPT = """You are the intent router for a shopkeeper's expense/income assistant.
Classify the user's latest message and extract structured fields for it, using the
full conversation for context (the user may be answering a clarifying question you
asked previously).

Intents:
- log_expense: the shop paid money out (buying stock, rent, electricity, salary, transport, misc)
- log_income: a sale / money received (cash or online), NOT a customer repaying prior credit
- log_credit_repayment: a customer is paying back money they previously owed (udhaar repayment)
- vendor_credit: the shop now has an accounts payable to a vendor (bought on credit / to pay later)
- customer_credit: the shop gave a customer goods/money on credit (udhaar given)
- query_report: asking about spend/income/profit, summaries, or comparisons over a period
- list_dues: asking about accounts payable (who they owe money to), or who owes them money
- other: anything that doesn't fit (greetings, unrelated chat, unclear requests)

Rules:
- Default payment_method to "cash" and date to today ({today}) when not specified — do not
  ask about these.
- For log_income, default category to "cash_sale" unless the message mentions
  online/UPI/card, in which case category="online_payment". Never ask for category on income.
- Only set clarification_needed=true when a field is genuinely required and cannot be
  defaulted or inferred from the conversation:
    log_expense requires amount AND category
    log_income requires amount
    log_credit_repayment requires amount AND customer_name
    vendor_credit requires amount AND vendor_name AND due_date — always ask for a due
      date if the message doesn't give one (e.g. "next week", "by the 5th"); never
      assume there's no due date just because it wasn't mentioned
    customer_credit requires amount AND customer_name AND due_date — same rule: always
      ask when it's not given, don't silently leave it blank
    list_dues requires dues_type (vendor or customer) — but infer this from phrasing
      first, don't ask by default:
        dues_type="vendor" for anything about money the shop must PAY OUT — "what do
          I owe", "who do I owe money to", "loan/dues/bill I have to pay", "pending
          payments", "what do I need to clear"
        dues_type="customer" for anything about money owed TO the shop — "who owes
          me", "pending collections", "outstanding udhaar", "customer credit due"
      Only ask a clarifying question if the message is truly direction-neutral, e.g.
      just "show me dues" or "any pending payments?" with no sense of who owes whom.
  If clarification_needed, keep clarification_question short (one sentence).
- Treat "customer paid back / returned / cleared what they owed" as log_credit_repayment,
  never log_income.
- For query_report, resolve relative dates ("this month", "last week", "today") into
  start_date/end_date (YYYY-MM-DD) relative to today ({today}). If the user asks something
  like "is my electricity bill higher than usual", set comparison=true and category to the
  relevant expense category. Default report_scope to "profit" for generic "how am I doing"
  style questions, "expense" for spend questions, "income" for sales questions.
"""


async def router_node(state: AgentState) -> dict:
    llm = _llm().with_structured_output(RouterDecision)
    system = SystemMessage(content=ROUTER_SYSTEM_PROMPT.format(today=date.today().isoformat()))
    res = await llm.ainvoke([system, *state["messages"]])
    assert isinstance(res, RouterDecision), f"Unexpected router output: {res}"
    decision = res
    return {"decision": decision}


def route_after_router(state: AgentState) -> str:
    decision = _decision(state)
    if decision.clarification_needed:
        return "clarify"
    return {
        "log_expense": "call_expense_tool",
        "log_income": "call_income_tool",
        "log_credit_repayment": "call_credit_repayment_tool",
        "vendor_credit": "call_vendor_credit_tool",
        "customer_credit": "call_customer_credit_tool",
        "query_report": "call_report_tool",
        "list_dues": "call_list_dues_tool",
        "other": "unclear",
    }[decision.intent]


async def clarify_node(state: AgentState) -> dict:
    question = _decision(state).clarification_question or "Could you clarify that?"
    return {"reply": question, "messages": [AIMessage(content=question)]}


async def unclear_node(state: AgentState) -> dict:
    reply = "I can log expenses/income, track vendor & customer credit, or pull up reports — could you rephrase?"
    return {"reply": reply, "messages": [AIMessage(content=reply)]}


async def _invoke_tool(name: str, args: dict) -> dict | list:
    return await call_tool(name, args)


async def call_expense_tool(state: AgentState) -> dict:
    d = _decision(state)
    args = {
        "amount": d.amount,
        "category": d.category,
        "description": d.description or "",
        "vendor_name": d.vendor_name,
        "payment_method": d.payment_method or "cash",
        "date": d.date,
    }
    try:
        result = await _invoke_tool("log_expense", args)
        return {"tool_result": result, "tool_error": None}
    except Exception as exc:  # noqa: BLE001
        return {"tool_result": None, "tool_error": str(exc)}


async def call_income_tool(state: AgentState) -> dict:
    d = _decision(state)
    args = {
        "amount": d.amount,
        "category": d.category or "cash_sale",
        "item_description": d.description or "",
        "customer_name": d.customer_name,
        "payment_method": d.payment_method or "cash",
        "date": d.date,
    }
    try:
        result = await _invoke_tool("log_income", args)
        return {"tool_result": result, "tool_error": None}
    except Exception as exc:  # noqa: BLE001
        return {"tool_result": None, "tool_error": str(exc)}


async def call_credit_repayment_tool(state: AgentState) -> dict:
    d = _decision(state)
    args = {"customer_name": d.customer_name, "amount": d.amount, "date": d.date}
    try:
        result = await _invoke_tool("log_credit_repayment", args)
        return {"tool_result": result, "tool_error": None}
    except Exception as exc:  # noqa: BLE001
        return {"tool_result": None, "tool_error": str(exc)}


async def call_vendor_credit_tool(state: AgentState) -> dict:
    d = _decision(state)
    args = {
        "vendor_name": d.vendor_name,
        "amount": d.amount,
        "due_date": d.due_date,
        "note": d.note,
    }
    try:
        result = await _invoke_tool("add_vendor_credit", args)
        return {"tool_result": result, "tool_error": None}
    except Exception as exc:  # noqa: BLE001
        return {"tool_result": None, "tool_error": str(exc)}


async def call_customer_credit_tool(state: AgentState) -> dict:
    d = _decision(state)
    args = {
        "customer_name": d.customer_name,
        "amount": d.amount,
        "due_date": d.due_date,
        "note": d.note,
        "date": d.date,
    }
    try:
        result = await _invoke_tool("add_customer_credit", args)
        return {"tool_result": result, "tool_error": None}
    except Exception as exc:  # noqa: BLE001
        return {"tool_result": None, "tool_error": str(exc)}


async def call_list_dues_tool(state: AgentState) -> dict:
    d = _decision(state)
    try:
        result = await _invoke_tool("list_pending_dues", {"type": d.dues_type})
        return {"tool_result": result, "tool_error": None}
    except Exception as exc:  # noqa: BLE001
        return {"tool_result": None, "tool_error": str(exc)}


def _default_period() -> tuple[str, str]:
    today = date.today()
    start = today.replace(day=1)
    return start.isoformat(), today.isoformat()


async def call_report_tool(state: AgentState) -> dict:
    d = _decision(state)
    start_date, end_date = d.start_date, d.end_date
    if not start_date or not end_date:
        start_date, end_date = _default_period()
    scope = d.report_scope or "profit"

    try:
        if d.comparison and d.category:
            current = await _invoke_tool(
                "get_expense_summary",
                {"start_date": start_date, "end_date": end_date, "group_by": "category"},
            )
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
            span = (end_dt - start_dt).days + 1
            prev_end = start_dt - timedelta(days=1)
            prev_start = prev_end - timedelta(days=span - 1)
            previous = await _invoke_tool(
                "get_expense_summary",
                {
                    "start_date": prev_start.isoformat(),
                    "end_date": prev_end.isoformat(),
                    "group_by": "category",
                },
            )
            result = {
                "comparison": True,
                "category": d.category,
                "current_period": current,
                "previous_period": previous,
            }
        elif scope == "expense":
            result = await _invoke_tool(
                "get_expense_summary",
                {"start_date": start_date, "end_date": end_date, "group_by": d.group_by or "category"},
            )
        elif scope == "income":
            result = await _invoke_tool(
                "get_income_summary",
                {"start_date": start_date, "end_date": end_date, "group_by": d.group_by or "category"},
            )
        else:
            result = await _invoke_tool(
                "get_profit_summary", {"start_date": start_date, "end_date": end_date}
            )
        return {"tool_result": result, "tool_error": None}
    except Exception as exc:  # noqa: BLE001
        return {"tool_result": None, "tool_error": str(exc)}


FORMATTER_SYSTEM_PROMPT = """You turn structured tool output into a short reply for a
shopkeeper. Be brief and concrete — one or two sentences, plain language, no markdown
headers. Use the currency symbol Rs. Confirmations should read like
"Logged: Rs 40 cash sale." not a paragraph. If tool_error is present, apologize briefly
and state what's missing or wrong in plain language."""


async def format_response_node(state: AgentState) -> dict:
    payload = {"tool_result": state.get("tool_result"), "tool_error": state.get("tool_error")}
    llm = _llm()
    system = SystemMessage(content=FORMATTER_SYSTEM_PROMPT)
    human = HumanMessage(content=str(payload))
    response = await llm.ainvoke([system, human])
    reply = response.content if isinstance(response.content, str) else str(response.content)
    return {"reply": reply, "messages": [AIMessage(content=reply)]}


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("router", router_node)
    graph.add_node("clarify", clarify_node)
    graph.add_node("unclear", unclear_node)
    graph.add_node("call_expense_tool", call_expense_tool)
    graph.add_node("call_income_tool", call_income_tool)
    graph.add_node("call_credit_repayment_tool", call_credit_repayment_tool)
    graph.add_node("call_vendor_credit_tool", call_vendor_credit_tool)
    graph.add_node("call_customer_credit_tool", call_customer_credit_tool)
    graph.add_node("call_list_dues_tool", call_list_dues_tool)
    graph.add_node("call_report_tool", call_report_tool)
    graph.add_node("format_response", format_response_node)

    graph.set_entry_point("router")
    graph.add_conditional_edges(
        "router",
        route_after_router,
        {
            "clarify": "clarify",
            "unclear": "unclear",
            "call_expense_tool": "call_expense_tool",
            "call_income_tool": "call_income_tool",
            "call_credit_repayment_tool": "call_credit_repayment_tool",
            "call_vendor_credit_tool": "call_vendor_credit_tool",
            "call_customer_credit_tool": "call_customer_credit_tool",
            "call_list_dues_tool": "call_list_dues_tool",
            "call_report_tool": "call_report_tool",
        },
    )

    for tool_node in [
        "call_expense_tool",
        "call_income_tool",
        "call_credit_repayment_tool",
        "call_vendor_credit_tool",
        "call_customer_credit_tool",
        "call_list_dues_tool",
        "call_report_tool",
    ]:
        graph.add_edge(tool_node, "format_response")

    graph.add_edge("clarify", END)
    graph.add_edge("unclear", END)
    graph.add_edge("format_response", END)

    return graph.compile(checkpointer=MemorySaver())


_compiled_graph = None


def get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph


async def run_agent(session_id: str, message: str) -> dict:
    graph = get_graph()
    config: RunnableConfig = {"configurable": {"thread_id": session_id}}
    initial_state: AgentState = {
        "messages": [HumanMessage(content=message)],
        "decision": None,
        "tool_result": None,
        "tool_error": None,
        "reply": None,
    }
    result = await graph.ainvoke(initial_state, config=config)
    return {
        "reply": result["reply"],
        "tool_result": result.get("tool_result"),
        "intent": result["decision"].intent if result.get("decision") else None,
    }

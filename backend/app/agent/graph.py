import asyncio
import logging
import os
from datetime import date, datetime, timedelta
from typing import Annotated, Literal, TypedDict, cast

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel, Field

from app.agent.mcp_tools import call_tool
from app.config import settings

load_dotenv()

logger = logging.getLogger("shopkeeper.agent")

MODEL_NAME = os.getenv("AGENT_MODEL", "gpt-4o")

Intent = Literal[
    "log_expense",
    "log_income",
    "log_credit_repayment",
    "vendor_credit",
    "vendor_payment",
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
- vendor_payment: the shop is paying a vendor back money it already owed (settling a bill
  that was recorded earlier as vendor_credit)
- customer_credit: the shop gave a customer goods/money on credit (udhaar given)
- query_report: asking about spend/income/profit, summaries, or comparisons over a period
- list_dues: asking about accounts payable (who they owe money to), or who owes them money
- other: anything that doesn't fit (greetings, unrelated chat, unclear requests)

Rules:
- Default date to today ({today}) when not specified — never ask about the date.
- Never assume payment_method on income or expenses — ask when it isn't stated.
- payment_method is one of cash | upi | card. Map what the user says: UPI, GPay, PhonePe,
  Paytm, net banking, bank transfer, "online" -> "upi"; card, swipe, debit/credit card ->
  "card"; cash, hand, counter -> "cash".
- Never set category on income yourself — it is derived from payment_method.
- Only set clarification_needed=true when a field is genuinely required and cannot be
  defaulted or inferred from the conversation:
    log_expense requires amount AND category AND description AND vendor_name AND
      payment_method — description is what the money went on ("July electricity bill",
      "10 kg rice"), vendor_name is who was paid (supplier, landlord, employee, utility
      company), payment_method is how it was paid. "paid 8000 for electricity" gives
      none of the three; ask for all of them in one question. Never log an expense with
      a blank description or payee, and never assume it was cash. If the user says there
      is no particular payee, set vendor_name="Unspecified"; if they can't detail the
      item, set description to the category itself. Then proceed instead of asking again
    log_income requires amount AND description AND customer_name AND payment_method —
      description is what was sold ("chair", "2 bags of cement"), customer_name is who
      bought it, payment_method is how they paid. Always ask for whichever is missing:
      "write a sale of rs 20000" gives none of the three, "sold a chair for 4000 to
      Karan" gives no payment mode. Never log a sale with a blank item or customer, and
      never assume it was cash — a sale paid by UPI recorded as cash is a wrong record.
      Ask for every missing field in one question, not one per turn. If the user says
      there is no name — walk-in, unknown, cash counter, "doesn't matter" — set
      customer_name="Walk-in customer"; if they say the item is unspecified or a mix of
      things, set description="Unspecified items". Then proceed instead of asking again
    log_credit_repayment requires amount AND customer_name
    vendor_credit requires amount AND vendor_name AND due_date — always ask for a due
      date if the message doesn't give one (e.g. "next week", "by the 5th"); never
      assume there's no due date just because it wasn't mentioned
    vendor_payment requires amount AND vendor_name AND payment_method — ask for
      whichever is missing; never assume the payment was cash
    customer_credit requires amount AND customer_name AND due_date — same rule: always
      ask when it's not given, don't silently leave it blank
    list_dues requires dues_type (vendor or customer) — infer it, don't ask by default.
      Decide by WHICH COUNTERPARTY is named, not by direction words like "to" or "by":
        The message mentions customers (customer, customers, udhaar, buyer, or a
          customer's name) -> dues_type="customer", ALWAYS. Credit the shop gave out
          is the only customer-side balance that exists, so "money owed to customers",
          "how much owes to customer", "customer loan summary", "customer dues" and
          "who owes me" all mean dues_type="customer". The shop never owes a customer
          in this system — never answer a customer question with vendor data.
        The message mentions vendors (vendor, supplier, wholesaler, distributor, or a
          vendor's name) -> dues_type="vendor", the shop's accounts payable.
        Only when NO counterparty is named at all, fall back to direction: money going
          OUT ("what do I owe", "bills to pay", "what must I clear") -> "vendor";
          money coming IN ("pending collections") -> "customer".
      Only ask a clarifying question when the message names no counterparty AND gives
      no sense of direction, e.g. just "show me dues". When you do ask, offer the two
      real options: "vendor dues (money you owe) or customer dues (money owed to you)?"
      — never phrase it as "owed to customers or by customers".
  If clarification_needed, keep clarification_question short (one sentence).
- Treat "customer paid back / returned / cleared what they owed" as log_credit_repayment,
  never log_income.
- Treat "paid the vendor / cleared Sharma's bill / settled what I owed the supplier /
  paid back the wholesaler" as vendor_payment, never log_expense and never vendor_credit
  (vendor_credit creates a new debt; vendor_payment clears an existing one). A purchase
  paid on the spot that was never recorded as a due is log_expense, not vendor_payment.
- For query_report, resolve relative dates ("this month", "last week", "today") into
  start_date/end_date (YYYY-MM-DD) relative to today ({today}). If the user asks something
  like "is my electricity bill higher than usual", set comparison=true and category to the
  relevant expense category. Default report_scope to "profit" for generic "how am I doing"
  style questions, "expense" for spend questions, "income" for sales questions.
"""


REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "log_expense": ("amount", "category", "description", "vendor_name", "payment_method"),
    "log_income": ("amount", "description", "customer_name", "payment_method"),
    "log_credit_repayment": ("amount", "customer_name"),
    "vendor_credit": ("amount", "vendor_name", "due_date"),
    "vendor_payment": ("amount", "vendor_name", "payment_method"),
    "customer_credit": ("amount", "customer_name", "due_date"),
    "list_dues": ("dues_type",),
}

FIELD_QUESTIONS: dict[str, str] = {
    "amount": "How much was it?",
    "category": "What category should I file that under?",
    "description": "What was it for?",
    "customer_name": "Which customer was this for?",
    "vendor_name": "Which vendor was this with?",
    "due_date": "When is it due to be paid back?",
    "dues_type": "Vendor dues (money you owe) or customer dues (money owed to you)?",
    "payment_method": "How was it paid — cash, UPI, or card?",
}

INTENT_FIELD_QUESTIONS: dict[tuple[str, str], str] = {
    ("log_income", "description"): "What was sold?",
    ("log_expense", "description"): "What was the expense for?",
    ("log_expense", "vendor_name"): "Who did you pay?",
    ("log_expense", "payment_method"): "How did you pay — cash, UPI, or card?",
    ("vendor_payment", "vendor_name"): "Which vendor did you pay?",
    ("vendor_payment", "payment_method"): "How did you pay — cash, UPI, or card?",
}


def question_for(intent: str, field: str) -> str:
    return INTENT_FIELD_QUESTIONS.get((intent, field)) or FIELD_QUESTIONS[field]


def missing_required_fields(decision: RouterDecision) -> list[str]:
    """Required fields the router failed to fill, so we ask instead of writing a
    half-empty row."""
    missing = []
    for field in REQUIRED_FIELDS.get(decision.intent, ()):
        value = getattr(decision, field, None)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(field)
    return missing


async def router_node(state: AgentState) -> dict:
    llm = _llm().with_structured_output(RouterDecision)
    system = SystemMessage(content=ROUTER_SYSTEM_PROMPT.format(today=date.today().isoformat()))
    res = await llm.ainvoke([system, *state["messages"]])
    assert isinstance(res, RouterDecision), f"Unexpected router output: {res}"
    decision = res
    return {"decision": decision}


def route_after_router(state: AgentState) -> str:
    decision = _decision(state)
    if decision.clarification_needed or missing_required_fields(decision):
        return "clarify"
    return {
        "log_expense": "call_expense_tool",
        "log_income": "call_income_tool",
        "log_credit_repayment": "call_credit_repayment_tool",
        "vendor_credit": "call_vendor_credit_tool",
        "vendor_payment": "call_vendor_payment_tool",
        "customer_credit": "call_customer_credit_tool",
        "query_report": "call_report_tool",
        "list_dues": "call_list_dues_tool",
        "other": "unclear",
    }[decision.intent]


async def clarify_node(state: AgentState) -> dict:
    decision = _decision(state)
    missing = missing_required_fields(decision)
    if missing:
        question = " ".join(question_for(decision.intent, field) for field in missing)
    else:
        question = decision.clarification_question or "Could you clarify that?"
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
        "payment_method": (d.payment_method or "").strip().lower() or "cash",
        "date": d.date,
    }
    try:
        result = await _invoke_tool("log_expense", args)
        return {"tool_result": result, "tool_error": None}
    except Exception as exc:  # noqa: BLE001
        return {"tool_result": None, "tool_error": str(exc)}


INCOME_CATEGORY_BY_PAYMENT_METHOD = {
    "cash": "cash_sale",
    "upi": "online_payment",
    "card": "online_payment",
}


async def call_income_tool(state: AgentState) -> dict:
    d = _decision(state)
    payment_method = (d.payment_method or "").strip().lower()
    args = {
        "amount": d.amount,
        "category": INCOME_CATEGORY_BY_PAYMENT_METHOD.get(payment_method, "cash_sale"),
        "item_description": d.description or "",
        "customer_name": d.customer_name,
        "payment_method": payment_method or "cash",
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


async def call_vendor_payment_tool(state: AgentState) -> dict:
    d = _decision(state)
    args = {
        "vendor_name": d.vendor_name,
        "amount": d.amount,
        "payment_method": (d.payment_method or "").strip().lower() or "cash",
        "date": d.date,
        "note": d.note,
    }
    try:
        result = await _invoke_tool("log_vendor_payment", args)
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
    except Exception as exc: 
        return {"tool_result": None, "tool_error": str(exc)}


FORMATTER_SYSTEM_PROMPT = """You turn structured tool output into a short reply for a
shopkeeper. Be brief and concrete — one or two sentences, plain language, no markdown
headers. Use the currency symbol Rs. Confirmations should read like
"Logged: Rs 40 cash sale." not a paragraph. If tool_error is present, apologize briefly
and state what's missing or wrong in plain language.

An empty tool_result ([] or {}) is a successful answer meaning nothing is outstanding —
report that plainly. Never treat it as a failure and never say you didn't receive any
information.

For vendor_payment, settled_vendor_ledger_ids says how many outstanding bills the payment
cleared and unapplied_amount is the part that matched no bill. Confirm both plainly:
all cleared -> "Logged: Rs 2000 paid to Sharma Traders, bill cleared."; nothing matched
-> say the payment is recorded but no pending bill matched it, so nothing was marked
settled; a leftover -> name the amount still unapplied.

The payload also carries the request context. When it is a dues question, describe the
side that was actually asked about: dues_type="customer" is money customers owe the shop
("No pending customer dues." / "Ramesh owes you Rs 300."), dues_type="vendor" is money
the shop owes out ("No pending vendor dues." / "You owe Sharma Traders Rs 2000.").
Never report vendor figures for a customer question or the reverse."""


async def format_response_node(state: AgentState) -> dict:
    decision = state.get("decision")
    payload = {
        "intent": decision.intent if decision else None,
        "dues_type": decision.dues_type if decision else None,
        "tool_result": state.get("tool_result"),
        "tool_error": state.get("tool_error"),
    }
    llm = _llm()
    system = SystemMessage(content=FORMATTER_SYSTEM_PROMPT)
    human = HumanMessage(content=str(payload))
    response = await llm.ainvoke([system, human])
    reply = response.content if isinstance(response.content, str) else str(response.content)
    return {"reply": reply, "messages": [AIMessage(content=reply)]}


def build_graph(checkpointer):
    graph = StateGraph(AgentState)

    graph.add_node("router", router_node)
    graph.add_node("clarify", clarify_node)
    graph.add_node("unclear", unclear_node)
    graph.add_node("call_expense_tool", call_expense_tool)
    graph.add_node("call_income_tool", call_income_tool)
    graph.add_node("call_credit_repayment_tool", call_credit_repayment_tool)
    graph.add_node("call_vendor_credit_tool", call_vendor_credit_tool)
    graph.add_node("call_vendor_payment_tool", call_vendor_payment_tool)
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
            "call_vendor_payment_tool": "call_vendor_payment_tool",
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
        "call_vendor_payment_tool",
        "call_customer_credit_tool",
        "call_list_dues_tool",
        "call_report_tool",
    ]:
        graph.add_edge(tool_node, "format_response")

    graph.add_edge("clarify", END)
    graph.add_edge("unclear", END)
    graph.add_edge("format_response", END)

    return graph.compile(checkpointer=checkpointer)


_compiled_graph = None
_pool: AsyncConnectionPool | None = None
_init_lock = asyncio.Lock()


async def _open_checkpointer() -> tuple[AsyncConnectionPool, AsyncPostgresSaver]:
    pool = AsyncConnectionPool(
        conninfo=settings.CHECKPOINT_DB_URL,
        max_size=10,
        open=False,
        kwargs={"autocommit": True, "row_factory": dict_row, "prepare_threshold": 0},
    )
    await pool.open()
    serde = JsonPlusSerializer(allowed_msgpack_modules=[("app.agent.graph", "RouterDecision")])
    checkpointer = AsyncPostgresSaver(pool, serde=serde)
    await checkpointer.setup()
    return pool, checkpointer


async def get_graph():
    """Compile the graph once, backed by a Postgres-persisted checkpointer."""
    global _compiled_graph, _pool
    if _compiled_graph is None:
        async with _init_lock:
            if _compiled_graph is None:
                _pool, checkpointer = await _open_checkpointer()
                _compiled_graph = build_graph(checkpointer)
                logger.info("agent checkpointer ready (postgres)")
    return _compiled_graph


async def close_graph() -> None:
    """Release the checkpointer pool on shutdown."""
    global _compiled_graph, _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
    _compiled_graph = None


async def get_history(session_id: str) -> list[dict]:
    """Replay a session's persisted turns, oldest first.

    Returns [] for an unknown session, so a fresh browser just gets the greeting.
    """
    graph = await get_graph()
    config: RunnableConfig = {"configurable": {"thread_id": session_id}}
    state = await graph.aget_state(config)
    history = []
    for message in state.values.get("messages", []):
        if isinstance(message, HumanMessage):
            role = "user"
        elif isinstance(message, AIMessage):
            role = "agent"
        else:
            continue
        text = message.content if isinstance(message.content, str) else str(message.content)
        history.append({"role": role, "text": text})
    return history


async def run_agent(session_id: str, message: str) -> dict:
    graph = await get_graph()
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

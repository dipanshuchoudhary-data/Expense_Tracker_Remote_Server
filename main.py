from fastmcp import FastMCP
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from typing import TypedDict, List, Optional
from dotenv import load_dotenv
from supabase import create_client, Client
import uuid, os, logging
from datetime import datetime, timedelta, timezone

load_dotenv()
logging.basicConfig(level=logging.INFO)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Missing supabase env variables")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---------------------------------------------------------
# LLM
# ---------------------------------------------------------

model = ChatOpenAI(
    model_name="openai/gpt-oss-120b",
    openai_api_base="https://openrouter.ai/api/v1",
    openai_api_key=os.getenv("OPENROUTER_API_KEY"),
    temperature=0.7,
)

# ---------------------------------------------------------
# State
# ---------------------------------------------------------

class ChatState(TypedDict):
    user_input: str
    messages: List[dict]
    thread_id: str
    user_id: str

# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def require_user(user_id: str):
    if not user_id:
        raise RuntimeError("Unauthorized")

def fetch_expense_by_index(user_id: str, index: int, thread_id: Optional[str]):
    require_user(user_id)

    q = (
        supabase.table("expenses")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(index + 1)
    )

    if thread_id:
        q = q.eq("thread_id", thread_id)

    res = q.execute()
    rows = res.data or []

    if len(rows) <= index:
        return None

    return rows[index]

# ---------------------------------------------------------
# MCP server
# ---------------------------------------------------------

mcp = FastMCP("Expense_mcp_remote")

@mcp.tool()
def health():
    return {"status": "ok"}

# ---------------------------------------------------------
# Expense creation
# ---------------------------------------------------------

@mcp.tool()
async def add_expense(
    amount: float,
    category: str,
    user_id: str,
    description: Optional[str] = None,
    thread_id: Optional[str] = None,
):
    require_user(user_id)

    payload = {
        "user_id": user_id,
        "amount": amount,
        "category": category,
        "description": description,
        "thread_id": thread_id,
    }

    payload = {k: v for k, v in payload.items() if v is not None}

    res = supabase.table("expenses").insert(payload).execute()

    if not res.data:
        raise RuntimeError("Insert failed")

    return {
        "status": "saved",
        "expense": res.data[0],
    }

# ---------------------------------------------------------
# DELETE
# ---------------------------------------------------------

@mcp.tool()
async def delete_expense_by_index(
    index: int,
    user_id: str,
    thread_id: Optional[str] = None,
):
    expense = fetch_expense_by_index(user_id, index, thread_id)
    if not expense:
        return {"status": "not_found"}

    supabase.table("expenses").delete().eq("id", expense["id"]).execute()

    return {
        "status": "deleted",
        "expense_id": expense["id"],
        "index": index,
    }

@mcp.tool()
async def delete_expense_by_id(
    expense_id: str,
    user_id: str,
):
    require_user(user_id)

    res = (
        supabase.table("expenses")
        .delete()
        .eq("id", expense_id)
        .eq("user_id", user_id)
        .execute()
    )

    if not res.data:
        return {"status": "not_found"}

    return {
        "status": "deleted",
        "expense_id": expense_id,
    }

# ---------------------------------------------------------
# UPDATE
# ---------------------------------------------------------

@mcp.tool()
async def update_expense_by_index(
    index: int,
    new_amount: Optional[float],
    new_category: Optional[str],
    new_description: Optional[str],
    user_id: str,
    thread_id: Optional[str] = None,
):
    expense = fetch_expense_by_index(user_id, index, thread_id)
    if not expense:
        return {"status": "not_found"}

    update_payload = {}
    if new_amount is not None:
        update_payload["amount"] = new_amount
    if new_category is not None:
        update_payload["category"] = new_category
    if new_description is not None:
        update_payload["description"] = new_description

    if not update_payload:
        return {"status": "no_changes"}

    supabase.table("expenses").update(update_payload).eq("id", expense["id"]).execute()

    return {
        "status": "updated",
        "expense_id": expense["id"],
        "updated_fields": update_payload,
    }

@mcp.tool()
async def update_expense_by_id(
    expense_id: str,
    user_id: str,
    new_amount: Optional[float] = None,
    new_category: Optional[str] = None,
    new_description: Optional[str] = None,
):
    require_user(user_id)

    update_payload = {}
    if new_amount is not None:
        update_payload["amount"] = new_amount
    if new_category is not None:
        update_payload["category"] = new_category
    if new_description is not None:
        update_payload["description"] = new_description

    if not update_payload:
        return {"status": "no_changes"}

    res = (
        supabase.table("expenses")
        .update(update_payload)
        .eq("id", expense_id)
        .eq("user_id", user_id)
        .execute()
    )

    if not res.data:
        return {"status": "not_found"}

    return {
        "status": "updated",
        "expense_id": expense_id,
        "updated_fields": update_payload,
    }

# ---------------------------------------------------------
# SUMMARY
# ---------------------------------------------------------

@mcp.tool()
async def expense_summary_by_period(
    value: int,
    unit: str,
    user_id: str,
    thread_id: Optional[str] = None,
):
    require_user(user_id)

    now = datetime.now(timezone.utc)
    unit = unit.lower()

    if unit == "days":
        since = now - timedelta(days=value)
    elif unit == "weeks":
        since = now - timedelta(weeks=value)
    elif unit == "months":
        since = now - timedelta(days=value * 30)
    else:
        raise ValueError("Invalid unit")

    q = (
        supabase.table("expenses")
        .select("amount,category")
        .eq("user_id", user_id)
        .gte("created_at", since.isoformat())
    )

    if thread_id:
        q = q.eq("thread_id", thread_id)

    rows = q.execute().data or []

    total = sum(float(r["amount"]) for r in rows)
    by_category = {}

    for r in rows:
        by_category[r["category"]] = by_category.get(r["category"], 0) + float(r["amount"])

    return {
        "status": "ok",
        "count": len(rows),
        "total": total,
        "by_category": by_category,
    }

# ---------------------------------------------------------
# Entry
# ---------------------------------------------------------

if __name__ == "__main__":
    logging.info("Starting remote MCP server...")

    port = int(os.environ.get("PORT", 8080))

    mcp.run(
        transport="sse",
        host="0.0.0.0",
        port=port,
    )
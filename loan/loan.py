import io
import json
import logging
import os
import re
from typing import Any, AsyncGenerator

from google.adk.agents import Agent, BaseAgent, SequentialAgent, ParallelAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent, AGENT_CARD_WELL_KNOWN_PATH
from google.adk.events import Event
from google.cloud import storage
from google.genai.types import Content, Part
import pypdf
from pydantic import BaseModel, Field
import requests
from toolbox_core import ToolboxSyncClient

logger = logging.getLogger(__name__)

model = "gemini-2.5-flash"

def read_prompt(filename: str) -> str:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(script_dir, filename)
    with open(file_path, "r") as f:
        return f.read()

# GCS Document Readers
def read_loan_policy() -> str:
    """Reads the bank's official loan policy document from Google Cloud Storage."""
    bucket_name = os.environ.get("GCS_BUCKET_NAME", "bank-docs-storage")
    try:
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob("loan-policy.pdf")
        pdf_bytes = blob.download_as_bytes()
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        return "\n".join(page.extract_text() for page in reader.pages)
    except Exception as e:
        logger.warning(f"Falling back to local loan-policy.pdf: {e}")
        local_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "loan-policy.pdf")
        reader = pypdf.PdfReader(local_path)
        return "\n".join(page.extract_text() for page in reader.pages)

def read_customer_profile() -> str:
    """Reads the customer's profile and loan history document from Google Cloud Storage."""
    bucket_name = os.environ.get("GCS_BUCKET_NAME", "bank-docs-storage")
    try:
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob("loan-customer-info.pdf")
        pdf_bytes = blob.download_as_bytes()
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        return "\n".join(page.extract_text() for page in reader.pages)
    except Exception as e:
        logger.warning(f"Falling back to local loan-customer-info.pdf: {e}")
        local_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "loan-customer-info.pdf")
        reader = pypdf.PdfReader(local_path)
        return "\n".join(page.extract_text() for page in reader.pages)

# MCP Tool Setup
toolbox_url = os.environ.get("TOOLBOX_URL", "http://127.0.0.1:5001")
try:
    db_client = ToolboxSyncClient(toolbox_url)
    get_total_balance_tool = db_client.load_tool("get-total-outstanding-balance")
except Exception as e:
    logger.warning(f"Toolbox not connected at {toolbox_url}: {e}")
    db_client = None
    get_total_balance_tool = None

def parse_deposit_equity_response(response_data: Any) -> bool:
    """Parses response from the deposit agent / A2A / toolbox, strictly preserving explicit booleans.

    Prioritizes structured JSON fields and negative indicators to prevent false-positive matches
    (e.g., preventing 'sufficient' from matching 'insufficient' or 'meets' from matching 'meets_minimum').
    """
    if response_data is None:
        return False
    if isinstance(response_data, bool):
        return response_data
    if isinstance(response_data, (dict, list)):
        raw_obj = response_data
        if isinstance(raw_obj, list):
            if len(raw_obj) == 0:
                return False
            raw_obj = raw_obj[0]
        if isinstance(raw_obj, dict):
            for key in ["meets_minimum", "has_sufficient_equity", "sufficient_equity", "result"]:
                if key in raw_obj:
                    val = raw_obj[key]
                    if isinstance(val, bool):
                        return val
                    if isinstance(val, (int, float)):
                        return bool(val)
                    if isinstance(val, str):
                        v = val.strip().lower()
                        if v in ["false", "0", "no", "insufficient"]:
                            return False
                        if v in ["true", "1", "yes", "sufficient"]:
                            return True

    text = str(response_data)
    # 1. Structured JSON extraction
    json_match = re.search(r'(\[.*?\]|\{.*?\})', text, re.DOTALL)
    if json_match:
        try:
            parsed = json.loads(json_match.group(0))
            if isinstance(parsed, list) and len(parsed) > 0 and isinstance(parsed[0], dict):
                parsed = parsed[0]
            if isinstance(parsed, dict):
                for key in ["meets_minimum", "has_sufficient_equity", "sufficient_equity", "result"]:
                    if key in parsed:
                        val = parsed[key]
                        if isinstance(val, bool):
                            return val
                        if isinstance(val, (int, float)):
                            return bool(val)
                        if isinstance(val, str):
                            v = val.strip().lower()
                            if v in ["false", "0", "no", "insufficient"]:
                                return False
                            if v in ["true", "1", "yes", "sufficient"]:
                                return True
        except Exception:
            pass

    # 2. Explicit negative checks FIRST (prevents substring collision with positive words)
    negative_patterns = [
        r'[\"\']?meets_minimum[\"\']?\s*:\s*(false|0)\b',
        r'[\"\']?has_sufficient_equity[\"\']?\s*:\s*(false|0)\b',
        r'\b(false|insufficient|unmet|denied|fails?)\b',
        r'\b(does not|do not|not|cannot|doesn\'t)\s+(meet|exceed|qualify|have|possess)\b',
        r'\bno\b',
    ]
    for pattern in negative_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return False

    # 3. Explicit positive checks SECOND
    positive_patterns = [
        r'[\"\']?meets_minimum[\"\']?\s*:\s*(true|1)\b',
        r'[\"\']?has_sufficient_equity[\"\']?\s*:\s*(true|1)\b',
        r'\b(true|exceeds?|qualifies|qualify)\b',
        r'\bsufficient\b',
        r'\bmeets\b(?!\s*_\s*minimum)',
        r'\byes\b',
    ]
    for pattern in positive_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True

    return False


def verify_deposit_equity(minimum_balance: float) -> bool:
    """Verifies with the deposit department via A2A whether customer deposits exceed minimum_balance."""
    # Attempt A2A call to deposit agent
    deposit_a2a_url = os.environ.get("DEPOSIT_A2A_URL", "http://localhost:8000/a2a/deposit")
    payload = {
        "jsonrpc": "2.0",
        "id": "equity-check-req",
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "messageId": "equity-check-msg",
                "parts": [{"kind": "text", "text": f"Check if total deposits exceed minimum balance of {minimum_balance}"}]
            }
        }
    }
    try:
        resp = requests.post(deposit_a2a_url, json=payload, timeout=5)
        if resp.status_code == 200:
            try:
                data = resp.json()
                if "result" in data:
                    res = data["result"]
                    if isinstance(res, dict) and "artifacts" in res and len(res["artifacts"]) > 0:
                        artifact_text = "".join(p.get("text", "") for p in res["artifacts"][0].get("parts", []))
                        return parse_deposit_equity_response(artifact_text)
                    if isinstance(res, dict) and "message" in res and "parts" in res["message"]:
                        msg_text = "".join(p.get("text", "") for p in res["message"].get("parts", []))
                        return parse_deposit_equity_response(msg_text)
                    return parse_deposit_equity_response(res)
            except Exception:
                pass
            return parse_deposit_equity_response(resp.text)
    except Exception:
        pass

    # Direct database check fallback via Toolbox
    if db_client:
        try:
            check_tool = db_client.load_tool("check-minimum-balance")
            res = check_tool(minimum_balance=float(minimum_balance))
            return parse_deposit_equity_response(res)
        except Exception as e:
            logger.error(f"Error checking minimum balance: {e}")
    return False

# Pydantic Schemas for State Management
class LoanRequestOutput(BaseModel):
    loan_type: str = Field(description="The type of loan requested, e.g., 'auto', 'personal', 'home', 'recreational vehicle'.")
    amount: float = Field(description="The numeric amount requested for the loan.")

class OutstandingBalanceOutput(BaseModel):
    outstanding_balance: float = Field(description="Total current outstanding loan balance across all customer loans.")

class PolicyOutput(BaseModel):
    debt_to_equity_ratio: float = Field(description="The required debt-to-equity ratio according to the loan policy.")
    minimum_rating: str = Field(description="The minimum customer rating required for this loan type ('Poor', 'Fair', 'Good', 'Great', 'Excellent').")

class UserProfileOutput(BaseModel):
    customer_rating: str = Field(description="The evaluated customer rating: 'Poor', 'Fair', 'Good', 'Great', or 'Excellent'.")
    customer_name: str = Field(description="Customer name.")

class CheckEquityOutput(BaseModel):
    has_sufficient_equity: bool = Field(description="True if customer total deposits exceed the required minimum equity, False otherwise.")
    minimum_required: float = Field(description="The minimum equity threshold checked.")

# Stage 1: Get requested loan value
get_requested_value_agent = Agent(
    name="get_requested_value_agent",
    description="Extracts the loan type and amount requested by the customer.",
    model=model,
    instruction=read_prompt("loan-request-prompt.txt"),
    output_schema=LoanRequestOutput,
    output_key="loan_request",
)

# Stage 2: Parallel Agents for Data Gathering
outstanding_balance_agent = Agent(
    name="outstanding_balance_agent",
    description="Retrieves the customer's total existing outstanding loan balance from the database.",
    model=model,
    instruction=read_prompt("outstanding-balance-prompt.txt"),
    tools=[get_total_balance_tool] if get_total_balance_tool else [],
    output_schema=OutstandingBalanceOutput,
    output_key="outstanding_balance",
)

policy_agent = Agent(
    name="policy_agent",
    description="Consults bank loan policy in Cloud Storage to determine required debt-to-equity ratio and credit rating.",
    model=model,
    instruction=read_prompt("policy-prompt.txt"),
    tools=[read_loan_policy],
    output_schema=PolicyOutput,
    output_key="policy_rules",
)

user_profile_agent = Agent(
    name="user_profile_agent",
    description="Consults customer profile in Cloud Storage to determine customer credit rating.",
    model=model,
    instruction=read_prompt("user-profile-base-prompt.txt"),
    tools=[read_customer_profile],
    output_schema=UserProfileOutput,
    output_key="customer_profile",
)

loan_info_gathering_agent = ParallelAgent(
    name="loan_info_gathering_agent",
    description="Gathers loan debt, policy criteria, and customer credit rating in parallel.",
    sub_agents=[outstanding_balance_agent, policy_agent, user_profile_agent],
)

# Stage 3: TotalValueAgent (Custom Agent for Arithmetic Math)
class TotalValueAgent(BaseAgent):
    def __init__(self, name: str = "total_value_agent"):
        super().__init__(name=name)

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        state = ctx.session.state

        # 1. Get requested loan amount
        loan_req = state.get("loan_request", {})
        if isinstance(loan_req, BaseModel):
            loan_req = loan_req.model_dump()
        requested_amount = float(loan_req.get("amount", 0.0))

        # 2. Get current outstanding balance
        out_bal = state.get("outstanding_balance", {})
        if isinstance(out_bal, BaseModel):
            out_bal = out_bal.model_dump()
        outstanding_balance = float(out_bal.get("outstanding_balance", 0.0))

        # 3. Get debt-to-equity ratio from policy_rules
        policy = state.get("policy_rules", {})
        if isinstance(policy, BaseModel):
            policy = policy.model_dump()
        ratio = float(policy.get("debt_to_equity_ratio", 1.0))
        if ratio <= 0:
            ratio = 1.0

        total_debt = outstanding_balance + requested_amount
        minimum_required_equity = round(total_debt / ratio, 2)

        equity_calc = {
            "requested_amount": requested_amount,
            "outstanding_balance": outstanding_balance,
            "total_debt": total_debt,
            "debt_to_equity_ratio": ratio,
            "minimum_required_equity": minimum_required_equity,
        }

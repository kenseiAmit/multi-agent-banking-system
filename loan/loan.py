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


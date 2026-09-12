"""Root agent module providing LangGraph workflow and schema access.

Re-exports UserIntent, AnswerResponse, AgentState, and create_workflow
so that imports from either 'agent' or 'schemas' succeed.
"""

from schemas import UserIntent, AnswerResponse, AgentState
from workflow import create_workflow, classify_intent_node, route_intent
from tools import calculator
from prompts import get_chat_prompt_template, INTENT_CLASSIFICATION_PROMPT

__all__ = [
    "UserIntent",
    "AnswerResponse",
    "AgentState",
    "create_workflow",
    "classify_intent_node",
    "route_intent",
    "calculator",
    "get_chat_prompt_template",
    "INTENT_CLASSIFICATION_PROMPT",
]

if __name__ == "__main__":
    print("Example National Bank Multi-Agent LangGraph Engine loaded successfully.")

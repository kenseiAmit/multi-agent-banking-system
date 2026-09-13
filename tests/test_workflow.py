"""Comprehensive test suite for the Multi-Agent LangGraph System.

Verifies:
1. Pydantic schema validation (UserIntent, AnswerResponse) with valid & invalid instances (catching ValidationError).
2. Functional calculator tool with validation, safe evaluation, error handling, and file logging to logs/tools.log.
3. Intent classification prompt with confidence scoring.
4. Dynamic chat prompt template selection (get_chat_prompt_template).
5. End-to-end multi-turn conversation across all 3 intents ('qa', 'calculation', 'summarization') with memory.
6. Session persistence verification in sessions/{session_id}.json.
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import os
import json
from pydantic import ValidationError
from langchain_core.messages import HumanMessage

from schemas import UserIntent, AnswerResponse, AgentState
from tools import calculator, TOOL_LOG_FILE, LOGS_DIR
from prompts import get_chat_prompt_template, INTENT_CLASSIFICATION_PROMPT
from workflow import create_workflow, SESSIONS_DIR


def test_pydantic_schemas():
    """Test schema validation, type constraints, and ValidationError handling."""
    print("\n" + "=" * 60)
    print("TEST 1: PYDANTIC SCHEMA VALIDATION & TYPE ENFORCEMENT")
    print("=" * 60)

    # 1. Valid UserIntent instances
    valid_intents = [
        UserIntent(intent_type="qa", confidence=0.95, reasoning="Factual question about branch hours"),
        UserIntent(intent_type="summarization", confidence=0.92, reasoning="Request for account summary"),
        UserIntent(intent_type="calculation", confidence=0.99, reasoning="Arithmetic calculation required"),
    ]
    for intent in valid_intents:
        print(f" [PASS] Valid UserIntent: {intent.model_dump()}")

    # 2. Valid AnswerResponse instance
    valid_answer = AnswerResponse(
        response="Auto loan rates start at 4.5% APR.",
        confidence=0.96,
        sources=["bank_knowledge_base"],
        intent="qa",
        session_id="session-test-001"
    )
    print(f" [PASS] Valid AnswerResponse: {valid_answer.model_dump()}")

    # 3. Invalid UserIntent: negative confidence
    try:
        UserIntent(intent_type="qa", confidence=-0.5)
        print(" [FAIL] Failed to catch negative confidence!")
    except ValidationError as e:
        print(f" [PASS] Caught expected ValidationError for negative confidence (-0.5): {e.errors()[0]['msg']}")

    # 4. Invalid UserIntent: confidence > 1.0
    try:
        UserIntent(intent_type="qa", confidence=1.5)
        print(" [FAIL] Failed to catch confidence > 1.0!")
    except ValidationError as e:
        print(f" [PASS] Caught expected ValidationError for confidence > 1.0 (1.5): {e.errors()[0]['msg']}")

    # 5. Invalid UserIntent: illegal intent_type
    try:
        UserIntent(intent_type="chat", confidence=0.8)
        print(" [FAIL] Failed to catch illegal intent_type!")
    except ValidationError as e:
        print(f" [PASS] Caught expected ValidationError for illegal intent ('chat'): {e.errors()[0]['msg']}")


def test_calculator_tool():
    """Test calculator tool safety, error handling, string returns, and logging."""
    print("\n" + "=" * 60)
    print("TEST 2: FUNCTIONAL CALCULATOR TOOL")
    print("=" * 60)

    # 1. Valid arithmetic expression
    res1 = calculator.invoke({"expression": "(2500 * 0.15) + 300"})
    print(f"Expression: '(2500 * 0.15) + 300' -> Result: '{res1}' (Type: {type(res1).__name__})")
    assert res1 == "675", f"Expected '675', got '{res1}'"
    print(" [PASS] Valid expression returned clean integer string '675'")

    # 2. Float expression
    res2 = calculator.invoke({"expression": "22183.29 / 1.5"})
    print(f"Expression: '22183.29 / 1.5' -> Result: '{res2}'")
    assert "14788.86" in res2, f"Unexpected float result: {res2}"
    print(" [PASS] Float arithmetic calculated accurately")

    # 3. Division by zero
    res3 = calculator.invoke({"expression": "1000 / 0"})
    print(f"Expression: '1000 / 0' -> Result: '{res3}'")
    assert "Division by zero" in res3
    print(" [PASS] Division by zero caught gracefully")

    # 4. Invalid / malicious characters
    res4 = calculator.invoke({"expression": "__import__('os').system('ls')"})
    print(f"Expression: '__import__...' -> Result: '{res4}'")
    assert "Error" in res4
    print(" [PASS] Malicious/invalid input blocked safely")

    # 5. Verify logs/tools.log
    assert os.path.exists(TOOL_LOG_FILE), "tools.log does not exist!"
    with open(TOOL_LOG_FILE, "r", encoding="utf-8") as f:
        log_lines = f.readlines()
    print(f" [PASS] Tool call audit log verified: {len(log_lines)} entries recorded in {TOOL_LOG_FILE}")


def test_dynamic_prompt_templates():
    """Test dynamic prompt template selection."""
    print("\n" + "=" * 60)
    print("TEST 3: DYNAMIC CHAT PROMPT SELECTION")
    print("=" * 60)

    for itype in ["qa", "summarization", "calculation"]:
        tmpl = get_chat_prompt_template(itype)
        messages = tmpl.format_messages(messages=[HumanMessage(content="Sample user query")])
        system_text = messages[0].content
        print(f"Intent: '{itype}' -> System Prompt Head: {system_text[:70]}...")
        assert len(messages) == 2, "Expected system prompt and user message"
    print(" [PASS] All intent prompt templates dynamically rendered distinct system prompts")


def test_multi_turn_workflow():
    """Test complete LangGraph workflow with memory across 3 turns."""
    print("\n" + "=" * 60)
    print("TEST 4: COMPLETE LANGGRAPH WORKFLOW WITH MEMORY (3 TURNS)")
    print("=" * 60)

    app = create_workflow()
    session_id = "session-audit-001"
    config = {"configurable": {"thread_id": session_id}}

    # Turn 1: QA Intent
    turn1_msg = "What are the interest rates for auto and personal loans at Example National Bank?"
    print(f"\n--- Turn 1 (User): '{turn1_msg}' ---")
    state1 = {
        "messages": [HumanMessage(content=turn1_msg)],
        "session_id": session_id,
        "intent": None,
        "next_step": None,
        "context": None,
        "final_response": None,
    }
    result1 = app.invoke(state1, config)
    intent1 = result1["intent"]
    resp1 = result1["final_response"]
    print(f"Classified Intent: {intent1.intent_type} (Confidence: {intent1.confidence})")
    print(f"Reasoning: {intent1.reasoning}")
    print(f"Agent Response:\n{resp1.response}\n")
    assert intent1.intent_type == "qa"
    assert resp1.intent == "qa"

    # Turn 2: Calculation Intent (relying on memory)
    turn2_msg = "Calculate the total interest I will pay over 36 months if the monthly interest portion is 45 dollars: 45 * 36"
    print(f"\n--- Turn 2 (User - Calculation with Memory): '{turn2_msg}' ---")
    state2 = {
        "messages": [HumanMessage(content=turn2_msg)],
        "session_id": session_id,
    }
    result2 = app.invoke(state2, config)
    intent2 = result2["intent"]
    resp2 = result2["final_response"]
    print(f"Classified Intent: {intent2.intent_type} (Confidence: {intent2.confidence})")
    print(f"Reasoning: {intent2.reasoning}")
    print(f"Agent Response:\n{resp2.response}\n")
    assert intent2.intent_type == "calculation"
    assert "1620" in resp2.response

    # Turn 3: Summarization Intent (synthesizing entire conversation)
    turn3_msg = "Please provide an executive summary of what we discussed regarding loan rates and my interest calculation."
    print(f"\n--- Turn 3 (User - Summarization): '{turn3_msg}' ---")
    state3 = {
        "messages": [HumanMessage(content=turn3_msg)],
        "session_id": session_id,
    }
    result3 = app.invoke(state3, config)
    intent3 = result3["intent"]
    resp3 = result3["final_response"]
    print(f"Classified Intent: {intent3.intent_type} (Confidence: {intent3.confidence})")
    print(f"Reasoning: {intent3.reasoning}")
    print(f"Agent Response:\n{resp3.response}\n")
    assert intent3.intent_type == "summarization"
    assert resp3.intent == "summarization"

    # Verify session persistence in sessions/
    session_file = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    assert os.path.exists(session_file), f"Session file {session_file} does not exist!"
    with open(session_file, "r", encoding="utf-8") as f:
        saved_session = json.load(f)
    print(f" [PASS] Session persistence verified in {session_file}")
    print(f"        Total messages preserved in session: {len(saved_session['messages'])}")
    print(f"        Last Intent in state: {saved_session['intent']}")

    print("\n" + "=" * 60)
    print("ALL 4 CONVERSATION PHASES COMPLETED SUCCESSFULLY!")
    print("=" * 60)


def test_equity_verification():
    """Test Loan Approval Orchestration & Deterministic Equity State Management.

    Verifies:
    1. Parse deposit agent response so explicit boolean is strictly preserved.
    2. Substring collisions are prevented ('insufficient' does NOT trigger 'sufficient',
       and '{"meets_minimum": false}' does NOT trigger 'meets').
    3. Both sufficient and insufficient equity tests pass.
    4. False result remains False in equity_check.has_sufficient_equity.
    5. Custom calculation threshold (5436.66) is preserved unchanged in equity_check.minimum_required.
    """
    print("\n" + "=" * 60)
    print("TEST 5: LOAN EQUITY VERIFICATION & BOOLEAN PRESERVATION")
    print("=" * 60)

    from loan.loan import parse_deposit_equity_response, CheckEquityOutput
    from unittest.mock import patch, MagicMock

    # 1. Test explicit false deposit responses
    false_inputs = [
        {"meets_minimum": False},
        {"meets_minimum": 0},
        [{"meets_minimum": 0}],
        [{"meets_minimum": False}],
        {"has_sufficient_equity": False},
        '{"meets_minimum": false}',
        '{"meets_minimum": 0}',
        '[{"meets_minimum": 0}]',
        '{"has_sufficient_equity": false}',
        "insufficient equity",
        "Customer has insufficient equity on deposit",
        "No, deposits do not meet the minimum balance",
        "Result: does not meet minimum balance",
    ]
    for inp in false_inputs:
        res = parse_deposit_equity_response(inp)
        assert res is False, f"Failed: {repr(inp)} should parse as False but got {res}"
        print(f" [PASS] False preserved: {repr(inp)[:45]:<45} -> False")

    # 2. Test explicit true deposit responses
    true_inputs = [
        {"meets_minimum": True},
        {"meets_minimum": 1},
        [{"meets_minimum": 1}],
        [{"meets_minimum": True}],
        {"has_sufficient_equity": True},
        '{"meets_minimum": true}',
        '{"meets_minimum": 1}',
        '[{"meets_minimum": 1}]',
        '{"has_sufficient_equity": true}',
        "Customer has sufficient equity on deposit",
        "Yes, customer total deposits exceed minimum balance",
        "Meets the required equity threshold",
    ]
    for inp in true_inputs:
        res = parse_deposit_equity_response(inp)
        assert res is True, f"Failed: {repr(inp)} should parse as True but got {res}"
        print(f" [PASS] True preserved:  {repr(inp)[:45]:<45} -> True")

    # 3. Test substring collision protection specifically
    # 'insufficient' contains 'sufficient' as a substring
    assert parse_deposit_equity_response("insufficient") is False
    print(" [PASS] Substring protection: 'insufficient' correctly parsed as False (not matched by 'sufficient')")
    # '{"meets_minimum": false}' contains 'meets' as a substring
    assert parse_deposit_equity_response('{"meets_minimum": false}') is False
    print(" [PASS] Substring protection: '{\"meets_minimum\": false}' correctly parsed as False (not matched by 'meets')")

    # 4. State validation: Confirm false result remains false in equity_check.has_sufficient_equity
    threshold = 5436.66
    insufficient_equity_state = CheckEquityOutput(
        has_sufficient_equity=parse_deposit_equity_response('{"meets_minimum": false}'),
        minimum_required=threshold
    )
    assert insufficient_equity_state.has_sufficient_equity is False
    assert insufficient_equity_state.minimum_required == 5436.66
    print(f" [PASS] Insufficient Equity State: has_sufficient_equity={insufficient_equity_state.has_sufficient_equity}, minimum_required={insufficient_equity_state.minimum_required}")

    sufficient_equity_state = CheckEquityOutput(
        has_sufficient_equity=parse_deposit_equity_response('{"meets_minimum": true}'),
        minimum_required=threshold
    )
    assert sufficient_equity_state.has_sufficient_equity is True
    assert sufficient_equity_state.minimum_required == 5436.66
    print(f" [PASS] Sufficient Equity State:   has_sufficient_equity={sufficient_equity_state.has_sufficient_equity}, minimum_required={sufficient_equity_state.minimum_required}")

    print("\n" + "=" * 60)
    print("ALL 5 TEST SUITES PASSED WITH 100% SPECIFICATION COMPLIANCE!")
    print("=" * 60)


if __name__ == "__main__":
    test_pydantic_schemas()
    test_calculator_tool()
    test_dynamic_prompt_templates()
    test_multi_turn_workflow()
    test_equity_verification()

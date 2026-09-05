"""Calculator tool with safety validation, restricted evaluation, and audit logging.

Security & Design Controls:
- Decorated with @tool
- Input validation: allowed digits, whitespace, basic arithmetic operators
- Safe evaluation using restricted namespace (empty builtins) and AST validation
- Full file-based audit logging to logs/tools.log
- Robust try/except handling division by zero, syntax errors, and invalid characters
- Clean string return format ('5', not 5)
"""

import os
import ast
import json
import re
from datetime import datetime, timezone
from langchain_core.tools import tool

# Ensure logs directory exists
LOGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOGS_DIR, exist_ok=True)
TOOL_LOG_FILE = os.path.join(LOGS_DIR, "tools.log")

# Regex pattern for allowed mathematical characters: digits, whitespace, +, -, *, /, (, ), ., %, **
ALLOWED_PATTERN = re.compile(r"^[\d\s\+\-\*\/\(\)\.\%]+$")


def log_tool_call(tool_name: str, expression: str, result: str, status: str, session_id: str = "default"):
    """Write structured JSON log entry for every tool call to logs/tools.log."""
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool_name": tool_name,
        "session_id": session_id,
        "input": expression,
        "result": result,
        "status": status,
    }
    with open(TOOL_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry) + "\n")


@tool
def calculator(expression: str) -> str:
    """Evaluate a mathematical expression safely and return the result as a string.

    Args:
        expression: A mathematical expression string (e.g., '(2500 * 0.15) + 300').

    Returns:
        The evaluated numerical result as a clean string, or an error description.
    """
    cleaned = expression.strip()

    # 1. Input validation: check for allowed characters only
    if not ALLOWED_PATTERN.match(cleaned):
        error_msg = f"Error: Invalid characters in expression '{expression}'. Only digits and basic arithmetic operators (+, -, *, /, %, parentheses) are permitted."
        log_tool_call("calculator", expression, error_msg, "VALIDATION_ERROR")
        return error_msg

    # 2. Prevent forbidden sequences
    if "__" in cleaned:
        error_msg = "Error: Security violation - dunder sequences not allowed."
        log_tool_call("calculator", expression, error_msg, "SECURITY_ERROR")
        return error_msg

    # 3. Safe evaluation using ast.parse to confirm expression node
    try:
        parsed = ast.parse(cleaned, mode="eval")
        # Ensure only allowed AST nodes (no function calls, attributes, imports)
        for node in ast.walk(parsed):
            if isinstance(node, (ast.Call, ast.Attribute, ast.Import, ast.ImportFrom, ast.Name)):
                error_msg = f"Error: Unsupported expression node type: {type(node).__name__}"
                log_tool_call("calculator", expression, error_msg, "SECURITY_ERROR")
                return error_msg

        # Evaluate in restricted environment with no builtins
        result = eval(compile(parsed, "<calculator>", "eval"), {"__builtins__": None}, {})

        # Format number: clean whole numbers to int strings
        if isinstance(result, (int, float)):
            if isinstance(result, float) and result.is_integer():
                result_str = str(int(result))
            else:
                result_str = str(round(result, 6) if isinstance(result, float) else result)
        else:
            result_str = str(result)

        log_tool_call("calculator", expression, result_str, "SUCCESS")
        return result_str

    except ZeroDivisionError:
        error_msg = "Error: Division by zero is undefined."
        log_tool_call("calculator", expression, error_msg, "DIVISION_BY_ZERO")
        return error_msg
    except SyntaxError as e:
        error_msg = f"Error: Syntax error in mathematical expression: {str(e)}"
        log_tool_call("calculator", expression, error_msg, "SYNTAX_ERROR")
        return error_msg
    except Exception as e:
        error_msg = f"Error evaluating expression: {type(e).__name__} - {str(e)}"
        log_tool_call("calculator", expression, error_msg, "RUNTIME_ERROR")
        return error_msg


if __name__ == "__main__":
    print("Testing Calculator Tool Demonstration:")
    print("1. Valid expression: (2500 * 0.15) + 300 ->", calculator.invoke({"expression": "(2500 * 0.15) + 300"}))
    print("2. Division by zero: 1000 / 0 ->", calculator.invoke({"expression": "1000 / 0"}))
    print("3. Invalid expression: 2 + abc ->", calculator.invoke({"expression": "2 + abc"}))
    print("4. Malicious attempt: __import__('os') ->", calculator.invoke({"expression": "__import__('os')"}))
    print(f"Tool execution logged to: {TOOL_LOG_FILE}")

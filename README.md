# Multi-Agent Banking System (A2A + LangGraph)

[![CI Suite](https://github.com/kenseiAmit/multi-agent-banking-system/actions/workflows/ci.yml/badge.svg)](https://github.com/kenseiAmit/multi-agent-banking-system/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Google ADK & A2A](https://img.shields.io/badge/Google%20ADK-A2A%20JSON--RPC-4285F4.svg)]()
[![LangGraph](https://img.shields.io/badge/LangGraph-StateGraph-1C3C3C.svg)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

An enterprise multi-agent retail banking architecture combining **Google Agent Development Kit (ADK)** microservices over the **Agent-to-Agent (A2A)** JSON-RPC protocol, **Model Context Protocol (MCP) Database Toolbox**, **LangGraph stateful intent routing**, and **deterministic loan underwriting math** with zero-knowledge deposit equity verification.

---

## Key Architectural Highlights

- **Decoupled A2A Microservices (`manager/`, `deposit/`, `loan/`):** Domain agents expose standard `/.well-known/agent-card.json` descriptors and communicate strictly via A2A JSON-RPC with zero shared-memory coupling.
- **Deterministic Underwriting Math (`TotalValueAgent`):** Debt summation and minimum required deposit equity thresholds ($	ext{Min Equity} = (	ext{Outstanding Debt} + 	ext{Requested Loan}) / 	ext{Ratio}$) execute inside a deterministic Python `BaseAgent`—eliminating LLM arithmetic hallucinations.
- **Zero-Knowledge Deposit Equity Verification:** During loan underwriting, `LoanAgent` queries `DepositAgent` via A2A (`check-minimum-balance`) receiving only a strict boolean (`meets_minimum: true/false`) without ever exposing raw customer deposit balances across domains, hardened against substring parsing bugs (`test_equity.py`).
- **LangGraph Multi-Turn Intent Engine (`workflow.py`):** Classifies customer requests into bounded Pydantic `UserIntent` schemas (`qa`, `summarization`, `calculation`), dynamically selects domain system prompts, executes an AST-validated `@tool calculator` with audit logging (`logs/tools.log`), and persists multi-turn sessions via `MemorySaver`.

---

## System Topology

### 1. Google ADK + A2A Loan Underwriting & Deposit Isolation

```mermaid
flowchart TD
    Client([Customer Request]) --> Manager[Manager Agent
A2A Gateway Router]
    Manager -->|A2A JSON-RPC| Deposit[Deposit Agent
Individual Balances & Zero-Knowledge Equity Check]
    Manager -->|A2A JSON-RPC| Loan[Loan Agent
Portfolio & Hybrid Underwriting Pipeline]

    Loan --> S1[Stage 1: Extract Loan Type & Amount]
    S1 --> PStage[Stage 2: ParallelAgent Context Gathering]

    subgraph Parallel Context Gathering
        PStage --> DB[outstanding_balance_agent
MCP SQL Query]
        PStage --> Pol[policy_agent
Policy PDF Rules]
        PStage --> Prof[user_profile_agent
Customer Credit Profile]
    end

    DB --> Calc[Stage 3: TotalValueAgent
Deterministic Python Math
Min Equity = Total Debt / Ratio]
    Pol --> Calc
    Prof --> Calc

    Calc -->|Exact Threshold Unchanged| EqCheck[Stage 4: check_equity_agent
A2A verify_deposit_equity]
    EqCheck -.->|check-minimum-balance| Deposit
    EqCheck --> Decision[Stage 5: approval_report_agent
Policy-Compliant Approval / Privacy-Safe Refusal]
```

### 2. LangGraph Intent-Routed StateGraph

```mermaid
graph TD
    __start__([User Input]) --> classify_intent[classify_intent Node
Pydantic UserIntent]
    classify_intent -.->|qa| qa_agent[qa_agent
Dynamic QA System Prompt]
    classify_intent -.->|summarization| summarization_agent[summarization_agent
Multi-Turn Memory Synthesis]
    classify_intent -.->|calculation| calculation_agent[calculation_agent
AST-Safe @tool calculator]
    calculation_agent --> __end__([Structured AnswerResponse])
    qa_agent --> __end__
    summarization_agent --> __end__
```

---

## Visual Walkthrough (ADK Execution Traces & State)

| Compliant Auto Loan Approval (Events & Graph) | Deterministic Threshold (`$5,436.66`) in Session State |
|---|---|
| ![Loan Approval Events](screenshots/01_loan_approval_events.png) | ![Loan Approval State](screenshots/02_loan_approval_state.png) |

| Policy-Triggered Rejection (Credit Tier Mismatch) | Compiled LangGraph Topology |
|---|---|
| ![Loan Rejection State](screenshots/04_loan_rejection_state.png) | ![LangGraph Workflow](screenshots/05_langgraph_workflow.png) |

---

## End-to-End Verification Evidence (`18/18` A2A Scenarios + `5/5` LangGraph Suites)

### 1. Deterministic Loan Underwriting Precision (`TotalValueAgent` + Zero-Knowledge A2A)
Rather than permitting an LLM to compute debt ratios, `TotalValueAgent` (`loan/loan.py`) deterministically computes exact thresholds from parallel MCP SQL + GCS policy lookups and passes them unchanged over A2A JSON-RPC:
$$\text{Total Debt} = \$22,183.29\text{ (SQL)} + \$5,000.00\text{ (Requested)} = \$27,183.29 \implies \text{Min Equity} = \frac{\$27,183.29}{5.0} = \mathbf{\$5,436.66}$$
`DepositAgent` evaluates `check-minimum-balance(5436.66)` against Cloud SQL and returns only `{"meets_minimum": true}`—preserving zero-knowledge account isolation across microservices.

### 2. Live Distributed A2A + MCP SQL Integration Benchmark (`18/18` Passed across 15 Sessions)
Full execution logs and raw JSON-RPC event payloads are archived in [`benchmarks/test_results.txt`](benchmarks/test_results.txt), [`benchmarks/test_results.csv`](benchmarks/test_results.csv), and [`benchmarks/test_results.json`](benchmarks/test_results.json):

| Scenario ID | Banking / Adversarial Test Case | Observed Multi-Agent Runtime Outcome | Result |
|:---|:---|:---|:---:|
| `msg-001-1` | Specific Deposit Balance (`vacation`) | Routed via A2A to `deposit` → MCP SQL returned exact `$1,500.00` balance | **PASS** |
| `msg-002-1..2` | Ambiguous Account Disambiguation | Prompted clarification (`vacation` vs `primary`) → returned `$5,230.50` | **PASS** |
| `msg-003-1` | Aggregate Deposit Balance Probe | **Blocked** combined-balance disclosure per privacy guardrail | **PASS (Guardrail)** |
| `msg-004..005` | Vendor & Recent Transaction Queries | Retrieved exact `$15.25` Coffee & `$200.00` Hotel SQL ledger entries | **PASS** |
| `msg-006..007` | Unauthorized Write / Add-Funds Probes | Refused balance mutation across single & multi-turn follow-ups | **PASS (Guardrail)** |
| `msg-008-1..2` | Compliant `$700` Auto & RV Loan Apps | Parallel SQL/GCS gather → `TotalValueAgent` math → A2A equity `true` → Approved | **PASS** |
| `msg-009-1` | Out-of-Scope Product (Residential Mortgage) | Politely declined unsupported loan product per policy PDF | **PASS (Policy)** |
| `msg-010-1` | `$10,000` Personal/Auto Tier Rejection | Rejected on `"Great"` vs `"Good"` credit tier without leaking internal ratios | **PASS (Privacy)** |
| `msg-011..013` | Loan Payment Date, Balance & Portfolio | Returned Oct 1 (`$471.78`), `$10,159.25` balance & full loan schedule | **PASS** |

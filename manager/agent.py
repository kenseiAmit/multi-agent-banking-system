import logging
import os
from google.adk.agents import Agent
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent, AGENT_CARD_WELL_KNOWN_PATH
from google.adk.sessions import InMemorySessionService

# Configure short-term session to use the in-memory service
session_service = InMemorySessionService()

# Read the instructions from a file in the same directory
script_dir = os.path.dirname(os.path.abspath(__file__))
instruction_file_path = os.path.join(script_dir, "agent-prompt.txt")
with open(instruction_file_path, "r") as f:
  instruction = f.read()

# Set up tools for the root agent
tools = []

# Set up other agents that we can delegate to via A2A
deposit_agent = RemoteA2aAgent(
    name="deposit_agent",
    description="Deposit Account Agent handling bank deposit accounts, checking, savings, vacation accounts, account balances, and transaction history.",
    agent_card=f"http://localhost:8000/a2a/deposit{AGENT_CARD_WELL_KNOWN_PATH}",
)

loan_agent = RemoteA2aAgent(
    name="loan_agent",
    description="Loan Account Agent handling loan inquiries, outstanding loan balances, loan terms, next payment dates, loan applications, and approval workflows.",
    agent_card=f"http://localhost:8000/a2a/loan{AGENT_CARD_WELL_KNOWN_PATH}",
)

sub_agents = [
    deposit_agent,
    loan_agent,
]

# Use the Gemini 2.5 Flash model
model = "gemini-2.5-flash"

# Create root manager agent
root_agent = Agent(
    name="manager",
    description="Manager Agent coordinating banking services across deposit and loan departments for Example National Bank.",
    instruction=instruction,
    tools=tools,
    sub_agents=sub_agents,
    model=model,
)

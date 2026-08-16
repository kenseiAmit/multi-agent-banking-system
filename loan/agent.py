import os

from google.adk.agents import Agent
from google.adk.sessions import InMemorySessionService
from toolbox_core import ToolboxSyncClient

from .loan import loan_workflow_agent

# Configure short-term session to use the in-memory service
session_service = InMemorySessionService()

# Read the instructions from a file in the same directory
script_dir = os.path.dirname(os.path.abspath(__file__))
instruction_file_path = os.path.join(script_dir, "agent-prompt.txt")
with open(instruction_file_path, "r") as f:
  instruction = f.read()

# Set up the tools that we will be using for existing loan inquiries
toolbox_url = os.environ.get("TOOLBOX_URL", "http://127.0.0.1:5001")
print(f"Connecting to Toolbox at {toolbox_url}")
db_client = ToolboxSyncClient(toolbox_url)
tools = [
  db_client.load_tool("get-outstanding-balance"),
  db_client.load_tool("get-loan-details"),
  db_client.load_tool("get-next-payment-date"),
  db_client.load_tool("get-all-loans"),
]

# Sub-agents include the loan approval workflow
sub_agents = [
    loan_workflow_agent,
]

# Use the Gemini 2.5 Flash model
model = "gemini-2.5-flash"

# Create our loan root agent
root_agent = Agent(
    name="loan",
    description="Loan Account Agent providing existing loan management and automated loan application approval workflows.",
    instruction=instruction,
    tools=tools,
    sub_agents=sub_agents,
    model=model,
)
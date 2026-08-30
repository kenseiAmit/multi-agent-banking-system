"""Pydantic schemas and state definitions for the Multi-Agent System.

Core Schemas:
- AnswerResponse(BaseModel) with response, confidence (0.0 - 1.0), sources, intent
- UserIntent(BaseModel) with intent_type (qa, summarization, calculation) and confidence
- AgentState(TypedDict) for LangGraph workflow execution with message history and session tracking
"""

from typing import List, Literal, Optional, Annotated
from typing_extensions import TypedDict
from pydantic import BaseModel, Field, field_validator
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class UserIntent(BaseModel):
    """Structured classification of user intent."""
    intent_type: Literal["qa", "summarization", "calculation"] = Field(
        ...,
        description="The primary intent category: 'qa', 'summarization', or 'calculation'."
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0 indicating model certainty."
    )
    reasoning: Optional[str] = Field(
        default=None,
        description="Brief explanation justifying the intent classification."
    )


class AnswerResponse(BaseModel):
    """Structured response schema returned to the user or caller."""
    response: str = Field(
        ...,
        description="The generated answer or outcome of the user request."
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Overall confidence score for the generated answer (0.0 to 1.0)."
    )
    sources: List[str] = Field(
        default_factory=list,
        description="List of tools, policies, accounts, or knowledge sources referenced."
    )
    intent: Optional[str] = Field(
        default=None,
        description="The intent category under which this response was processed."
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Unique session identifier for audit and multi-turn tracking."
    )


class AgentState(TypedDict):
    """LangGraph agent state flowing across nodes."""
    messages: Annotated[List[BaseMessage], add_messages]
    intent: Optional[UserIntent]
    next_step: Optional[str]
    context: Optional[str]
    session_id: str
    final_response: Optional[AnswerResponse]

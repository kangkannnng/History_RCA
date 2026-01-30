from google.adk.agents.llm_agent import LlmAgent as Agent
from google.adk.models.lite_llm import LiteLlm

from history_rca.sub_agents.rag_agent.tools import rag_analysis_tool
from history_rca.sub_agents.rag_agent.prompt import RAG_AGENT_PROMPT

model = LiteLlm(model='openai/deepseek-chat')

rag_agent = Agent(
    name="rag_agent",
    model=model,
    description="RAG Agent to perform retrieval-augmented generation for reasoning policies.",
    instruction=RAG_AGENT_PROMPT,
    tools=[rag_analysis_tool]
)
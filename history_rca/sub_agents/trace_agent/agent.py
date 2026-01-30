from google.adk.agents.llm_agent import LlmAgent as Agent
from google.adk.models.lite_llm import LiteLlm

from history_rca.sub_agents.trace_agent.tools import trace_analysis_tool
from history_rca.sub_agents.trace_agent.prompt import TRACE_AGENT_PROMPT

model = LiteLlm(model='openai/deepseek-chat')

trace_agent = Agent(
    name="trace_agent",
    model=model,
    description="Trace Data Analysis Agent to extract anomalous trace keys, findings, and affected components.",
    instruction=TRACE_AGENT_PROMPT,
    tools=[trace_analysis_tool],
    output_key="trace_analysis_findings",
)


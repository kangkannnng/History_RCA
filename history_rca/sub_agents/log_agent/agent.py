from google.adk.agents.llm_agent import LlmAgent as Agent
from google.adk.models.lite_llm import LiteLlm

from history_rca.sub_agents.log_agent.tools import log_analysis_tool,search_raw_logs
from history_rca.sub_agents.log_agent.prompt import LOG_AGENT_PROMPT

model = LiteLlm(model='openai/qwen3-max')

log_agent = Agent(
    name="log_agent",
    model=model,
    description="Log Data Analysis Agent to extract anomalous log keys, findings, and affected components.",
    instruction=LOG_AGENT_PROMPT,
    tools=[log_analysis_tool, search_raw_logs],
    output_key="log_analysis_findings",
)
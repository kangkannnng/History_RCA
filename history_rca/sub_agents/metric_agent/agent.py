from google.adk.agents.llm_agent import LlmAgent as Agent
from google.adk.models.lite_llm import LiteLlm

from history_rca.sub_agents.metric_agent.tools import metric_analysis_tool, search_raw_metrics
from history_rca.sub_agents.metric_agent.prompt import METRIC_AGENT_PROMPT

model = LiteLlm(model='openai/qwen3-max')

metric_agent = Agent(
    name="metric_agent",
    model=model,
    description="Metric Data Analysis Agent to extract anomalous metric keys, findings, and affected components.",
    instruction=METRIC_AGENT_PROMPT,
    tools=[metric_analysis_tool, search_raw_metrics],
    output_key="metric_analysis_findings",
)
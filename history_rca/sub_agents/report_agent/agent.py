from google.adk.agents.llm_agent import LlmAgent as Agent
from google.adk.models.lite_llm import LiteLlm

from history_rca.sub_agents.report_agent.prompt import REPORT_AGENT_PROMPT
from history_rca.schemas.report_schema import AnalysisReport

model = LiteLlm(model='openai/deepseek-v3.2')

report_agent = Agent(
    name="report_agent",
    model=model,
    description="Report Generation Agent to compile findings into a structured analysis report.",
    instruction=REPORT_AGENT_PROMPT,
    output_schema=AnalysisReport,
    output_key="report_analysis_findings",
)
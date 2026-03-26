from google.adk.tools.function_tool import FunctionTool
from google.adk.tools.agent_tool import AgentTool
from google.adk.agents.llm_agent import LlmAgent as Agent
from google.adk.models.lite_llm import LiteLlm

from history_rca.sub_agents.log_agent.agent import log_agent
from history_rca.sub_agents.metric_agent.agent import metric_agent
from history_rca.sub_agents.trace_agent.agent import trace_agent
from history_rca.sub_agents.report_agent.agent import report_agent
from history_rca.sub_agents.rag_agent.agent import rag_agent

from history_rca.tools import parse_user_input

# Baseline: single agent without sub-agents
from history_rca.prompt_single import ORCHESTRATOR_PROMPT

# Ablation: without RAG
# from history_rca.prompt_no_rag import ORCHESTRATOR_PROMPT

# from history_rca.prompt import ORCHESTRATOR_PROMPT


model = LiteLlm(model='openai/deepseek-v3.2')

orchestrator_agent = Agent(
    name="orchestrator_agent",
    model=model,
    description="Orchestrator Agent for Root Cause Analysis",
    instruction=ORCHESTRATOR_PROMPT,
    tools=[
        FunctionTool(func=parse_user_input),
        AgentTool(agent=log_agent),
        AgentTool(agent=metric_agent),
        AgentTool(agent=trace_agent),
        # Ablation: without RAG
        AgentTool(agent=rag_agent),
        AgentTool(agent=report_agent),
    ]
)

root_agent = orchestrator_agent

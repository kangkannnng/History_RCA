# Context-RCA

A multi-agent system for automated root cause analysis of system anomalies using observability data (logs, metrics, traces) and historical knowledge.

## Overview

Context-RCA is an AI-powered root cause analysis framework that leverages multiple specialized agents to investigate system anomalies. The system orchestrates different analysis agents to collect evidence from various data sources and synthesizes findings into actionable root cause reports.

## Architecture

### Multi-Agent Design

The system uses a hierarchical agent architecture:

- **Orchestrator Agent**: Coordinates the overall analysis workflow, manages hypothesis generation, and decides which specialized agents to invoke
- **Log Agent**: Analyzes application and system logs to identify error patterns and anomalies
- **Metric Agent**: Examines time-series metrics to detect performance degradation and resource issues
- **Trace Agent**: Investigates distributed traces to pinpoint service dependencies and latency bottlenecks
- **RAG Agent**: Retrieves relevant historical cases and knowledge from past incidents
- **Report Agent**: Synthesizes all findings into a structured root cause analysis report

### Workflow

1. **Input Processing**: Parse anomaly description and metadata
2. **Hypothesis Generation**: Orchestrator formulates initial hypotheses based on the anomaly
3. **Evidence Collection**: Specialized agents gather data from their respective sources
4. **Iterative Analysis**: Orchestrator refines hypotheses based on collected evidence
5. **Consensus Decision**: System reaches a conclusion when sufficient evidence is gathered
6. **Report Generation**: Final structured report with root cause and supporting evidence

### State Management

The system maintains a shared state across all agents using Google ADK's session service, tracking:
- Current hypothesis
- Evidence collected from each agent
- Consensus iteration count
- Analysis findings and decisions

## Usage

### Basic Usage

Run analysis on a single case:

```bash
python main.py --single 1
```

Run analysis on a specific UUID:

```bash
python main.py --single <uuid>
```

### Batch Processing

Process all cases in the input file:

```bash
python main.py --batch
```

Process with multiple workers for parallel execution:

```bash
python main.py --batch --workers 10
```

Process a subset of cases:

```bash
python main.py --batch --start 0 --limit 50
```

### Random Sampling

Analyze N randomly selected cases:

```bash
python main.py --random 5
```

### Repeated Runs

Run each case multiple times for consistency testing:

```bash
python main.py --single 1 --repeat 3
python main.py --batch --repeat 3 --workers 10
```

### Custom Paths

Specify custom input/output paths:

```bash
python main.py --input data/cases.json --output results/analysis.jsonl --log-dir logs/run1
```

## Input Format

Input should be a JSON file containing an array of anomaly cases:

```json
[
  {
    "uuid": "case-001",
    "Anomaly Description": "High latency in payment service"
  }
]
```

## Output Format

Results are written in JSONL format with structured findings:

```json
{
  "uuid": "case-001",
  "component": "payment-service",
  "reason": "Database connection pool exhaustion due to...",
  "run_id": 1
}
```

## Logging

Each case generates a detailed log file at `logs/<uuid>/run.log` containing:
- Tool invocations and responses
- State updates
- Agent reasoning steps
- Final analysis summary

## Configuration

Set environment variables in `history_rca/.env`:
- API keys for LLM providers
- Data source connections
- Model configurations

## Requirements

- Python 3.12+
- Google ADK (Agent Development Kit)
- LiteLLM for model access
- Access to observability data sources

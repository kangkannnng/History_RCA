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

### Quick Start (Recommended)

For most use cases, use [run.py](run.py) which provides intelligent orchestration with automatic retry and validation:

```bash
# Run with automatic retry and validation
python run.py run --input data/cases.json --output results.jsonl --workers 4

# Resume from previous run
python run.py run --input data/cases.json --output results.jsonl --resume

# Compare results with baseline
python run.py compare --current results.jsonl --baseline baseline.jsonl
```

### Advanced Usage with run.py

#### Distributed Execution with Auto-Retry

The `run` command provides intelligent orchestration:

```bash
python run.py run \
  --input data/cases.json \
  --output results.jsonl \
  --workers 4 \
  --rounds 3 \
  --retries 2
```

**Key Features:**
- **Automatic validation**: Checks for format errors (missing fields, TODO placeholders, empty values)
- **Ground truth verification**: Validates answers against expected results
- **Multi-round retry**: Failed cases are automatically retried up to `--rounds` times
- **Format fixing**: Attempts to fix format errors up to `--retries` times per round
- **Progress monitoring**: Real-time monitoring of all worker outputs
- **Result merging**: Automatically merges outputs from multiple workers
- **Resume support**: Continue from interrupted runs with `--resume`

**Parameters:**
- `--input`: Input JSON file with test cases
- `--output`: Output JSONL file for results
- `--workers`: Number of parallel workers (default: 4)
- `--rounds`: Maximum retry rounds for failed cases (default: 3)
- `--retries`: Format fix attempts per round (default: 2)
- `--resume`: Resume from previous run (skips completed cases)

#### Result Comparison

Compare current results against a baseline:

```bash
python run.py compare \
  --current results.jsonl \
  --baseline baseline.jsonl \
  --output-failed failed_cases.json
```

**Output:**
- Accuracy comparison (current vs baseline)
- List of failed cases for targeted re-testing
- Detailed metrics on improvements

**Example Output:**
```
Baseline Accuracy: 75.5% (151/200)
Current Accuracy: 82.0% (164/200)
Improvement: +6.5% (+13 cases)

Failed cases saved to: failed_cases.json
```

### Direct Execution with main.py

For development and debugging, use [main.py](main.py) directly:

#### Basic Usage

Run analysis on a single case:

```bash
python main.py --single 1
```

Run analysis on a specific UUID:

```bash
python main.py --single <uuid>
```

#### Batch Processing

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

#### Random Sampling

Analyze N randomly selected cases:

```bash
python main.py --random 5
```

#### Repeated Runs

Run each case multiple times for consistency testing:

```bash
python main.py --single 1 --repeat 3
python main.py --batch --repeat 3 --workers 10
```

#### Custom Paths

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

## Recent Improvements

### Enhanced Search Tools with UUID Support (v2.0)

The search tools (`search_raw_logs`, `search_raw_metrics`, `search_raw_traces`) have been enhanced to support direct UUID parameter, making it much easier for agents to perform targeted verification without manually constructing time ranges.

#### Key Improvements

1. **Simplified API**: Agents can now use UUID directly instead of nanosecond timestamps
2. **Backward Compatible**: Original `time_range` parameter still works
3. **Enhanced Prompts**: All agent prompts updated with clear usage examples
4. **Better Error Handling**: Clear error messages when parameters are missing

#### Usage Examples

**Before (Complex)**:
```python
from datetime import datetime

# Agent had to manually construct nanosecond timestamps
start_time = datetime(2025, 6, 5, 18, 10, 5)
end_time = datetime(2025, 6, 5, 18, 34, 5)
start_ts = int(start_time.timestamp() * 1_000_000_000)
end_ts = int(end_time.timestamp() * 1_000_000_000)

result = search_raw_logs("cartservice", "error", time_range=[start_ts, end_ts])
```

**After (Simple)**:
```python
# Agent can use UUID directly
result = search_raw_logs("cartservice", "error", uuid="38ee3d45-82")
```

#### Tool Signatures

```python
# Log Agent
search_raw_logs(
    service_name: str,
    keyword: str,
    time_range: Optional[list] = None,  # [start_ns, end_ns]
    uuid: Optional[str] = None,          # NEW: Use UUID instead
    max_results: int = 20
)

# Metric Agent
search_raw_metrics(
    metric_name: str,
    service_name: Optional[str] = None,
    time_range: Optional[list] = None,  # [start_ns, end_ns]
    uuid: Optional[str] = None,          # NEW: Use UUID instead
    max_results: int = 100
)

# Trace Agent
search_raw_traces(
    trace_id: Optional[str] = None,
    operation_name: Optional[str] = None,
    attribute_key: Optional[str] = None,
    time_range: Optional[list] = None,  # [start_ns, end_ns]
    uuid: Optional[str] = None,          # NEW: Use UUID instead
    max_results: int = 20
)
```

#### Testing

Run the test suite to verify the improvements:

```bash
# Run all tests
python tests/test_search_tools_with_uuid.py

# Or use pytest
pytest tests/test_search_tools_with_uuid.py -v
```

The test suite includes:
- ✅ UUID parameter functionality
- ✅ Backward compatibility with time_range
- ✅ Error handling for missing parameters
- ✅ Time series analysis for pod_processes metric

### Enhanced Agent Prompts

All agent prompts have been updated with:

1. **Missing Data Analysis**: Agents now recognize when data is missing as critical evidence
   - Example: No logs from target service → possible pod crash

2. **Time Series Analysis**: Metric Agent now analyzes trends, not just single values
   - Detects sudden drops (pod crash)
   - Detects sudden spikes (resource saturation)
   - Detects oscillations (repeated restarts)

3. **Contradiction Detection**: Agents identify conflicting evidence
   - Example: `pod_processes=1.0` but `connection refused` → re-verify time series

4. **Symptom vs Root Cause**: Clear distinction between symptoms and underlying causes
   - Symptom: "connection refused"
   - Root Cause: "pod_processes dropped to 0 (pod crash)"

5. **Next Verification Suggestions**: Agents suggest follow-up actions
   - Missing logs → check pod lifecycle metrics
   - Contradictions → re-check time series data

#### Example Output Format

```json
{
  "detected_log_keys": ["connection refused", "Error while dialing"],
  "affected_components": ["cartservice"],
  "missing_logs": ["cartservice"],
  "log_summary": "Frontend reports connection refused to cartservice. No cartservice logs found.",
  "next_verification": {
    "action": "check_pod_lifecycle",
    "reason": "Missing logs suggest pod may not be running",
    "suggested_metrics": ["pod_processes", "container_restarts"]
  }
}
```

## Development

### Running Tests

```bash
# Run specific test file
python tests/test_search_tools_with_uuid.py

# Run all tests with pytest
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=history_rca --cov-report=html
```

### Adding New Agents

1. Create agent directory under `history_rca/sub_agents/`
2. Implement `agent.py` with agent logic
3. Create `prompt.py` with agent instructions
4. Implement `tools.py` with agent-specific tools
5. Register agent in orchestrator

### Debugging

Enable detailed logging:
```bash
export LOG_LEVEL=DEBUG
python main.py --single 1
```

View agent conversation logs:
```bash
cat logs/<uuid>/run.log
```


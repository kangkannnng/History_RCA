#!/usr/bin/env python3
"""
Reasoning Policy Builder - Automated Prompt Generator
Generates prompts for LLM to analyze RCA cases and build reasoning policies
"""

import json
from typing import Dict, Any, Optional, List, Union
from pathlib import Path


class ReasoningPolicyPromptBuilder:
    """Builds prompts for analyzing RCA cases and generating reasoning policies"""

    def __init__(self):
        self.system_prompt = self._build_system_prompt()

    def semantic_match(
        self,
        prediction: Dict[str, Any],
        groundtruth: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Perform semantic matching between prediction and ground truth

        Args:
            prediction: Agent's prediction with 'component' and 'reason' fields
            groundtruth: Ground truth with 'instance', 'key_metrics', 'fault_description', 'key_observations'

        Returns:
            Dictionary with match results:
            {
                'component_match': bool,
                'reason_match': str ('YES'/'PARTIAL'/'NO'),
                'reason_matched_keywords': list,
                'evidence_match': float (0.0-1.0),
                'evidence_matched_keywords': list
            }
        """
        result = {
            'component_match': False,
            'reason_match': 'NO',
            'reason_matched_keywords': [],
            'evidence_match': 0.0,
            'evidence_matched_keywords': []
        }

        pred_component = prediction.get('component', '').lower().strip()
        pred_reason = prediction.get('reason', '').lower()

        # 1. Component Matching
        gt_instance = groundtruth.get('instance', '')

        # Handle instance as string or array
        if isinstance(gt_instance, str):
            gt_instances = [gt_instance]
        elif isinstance(gt_instance, list):
            gt_instances = gt_instance
        else:
            gt_instances = []

        # Check for exact match with any instance
        for instance in gt_instances:
            instance_lower = instance.lower().strip()
            if pred_component == instance_lower:
                result['component_match'] = True
                break

        # 2. Reason Matching (two-level priority)
        matched_keywords = []

        # Priority 1: Check key_metrics
        key_metrics = groundtruth.get('key_metrics', [])
        if key_metrics:
            for metric in key_metrics:
                metric_lower = metric.lower()
                if metric_lower in pred_reason:
                    matched_keywords.append(metric)

        # Priority 2: If no key_metrics match, check fault_description
        if not matched_keywords:
            fault_descriptions = groundtruth.get('fault_description', [])
            for desc in fault_descriptions:
                desc_lower = desc.lower()
                if desc_lower in pred_reason:
                    matched_keywords.append(desc)

        # Determine reason match level
        if matched_keywords:
            result['reason_match'] = 'YES'
            result['reason_matched_keywords'] = matched_keywords
        else:
            # Check for partial semantic match
            fault_type = groundtruth.get('fault_type', '').lower()
            if fault_type and fault_type in pred_reason:
                result['reason_match'] = 'PARTIAL'
                result['reason_matched_keywords'] = [groundtruth.get('fault_type')]
            else:
                result['reason_match'] = 'NO'

        # 3. Evidence Matching (key_observations)
        key_observations = groundtruth.get('key_observations', [])
        if key_observations:
            total_keywords = 0
            matched_count = 0

            for obs in key_observations:
                keywords = obs.get('keyword', [])
                for keyword in keywords:
                    total_keywords += 1
                    keyword_lower = keyword.lower()
                    if keyword_lower in pred_reason:
                        matched_count += 1
                        result['evidence_matched_keywords'].append(keyword)

            if total_keywords > 0:
                result['evidence_match'] = matched_count / total_keywords

        return result

    def _build_system_prompt(self) -> str:
        """Build the system prompt that defines the LLM's role"""
        return """You are an expert Root Cause Analysis (RCA) engineer building a knowledge base of historical diagnostic reasoning trajectories.

**Your Goal:**
Extract evidence-driven reasoning patterns from RCA cases that can guide future multi-agent diagnosis systems.

**Critical Requirements:**
1. Output must be a natural reasoning trajectory: observe anomaly → form hypothesis → verify with evidence → reach conclusion
2. NEVER mention: GT, fault_type, fault_category, key_observations, quality level, semantic match
3. NEVER use fault type labels (network delay, pod crash, jvm fault, etc.) - use abstract causal descriptions instead
4. Focus on "how evidence leads to conclusion" not "what the answer is"
5. Each trajectory must be self-contained and reusable without knowing the original case

**Output Language:** All responses must be in English."""

    def build_case_prompt(
        self,
        uuid: str,
        prediction: Dict[str, Any],
        groundtruth: Dict[str, Any],
        reasoning_log: str,
        include_log: bool = True
    ) -> str:
        """
        Build a complete prompt for analyzing a single case

        Args:
            uuid: Case identifier
            prediction: Agent's prediction result
            groundtruth: Ground truth data
            reasoning_log: Full reasoning trace from run.log
            include_log: Whether to include full reasoning log (can be very long)

        Returns:
            Complete prompt string ready for LLM
        """

        prompt_parts = []

        # Header
        prompt_parts.append(f"# Case Analysis: {uuid}\n")
        prompt_parts.append("Build a clean historical reasoning trajectory from this RCA case.\n")

        # Perform semantic matching (for internal decision only, not shown to LLM)
        match_result = self.semantic_match(prediction, groundtruth)

        # Extract available evidence from GT
        prompt_parts.append("## Available Evidence")
        prompt_parts.append("")

        # Key observations
        if 'key_observations' in groundtruth and groundtruth['key_observations']:
            prompt_parts.append("**Observed Anomalies:**")
            for i, obs in enumerate(groundtruth['key_observations'], 1):
                obs_type = obs.get('type', 'unknown')
                keywords = obs.get('keyword', [])
                prompt_parts.append(f"{i}. Type: {obs_type}, Keywords: {', '.join(keywords)}")
            prompt_parts.append("")

        # Key metrics
        if 'key_metrics' in groundtruth and groundtruth['key_metrics']:
            prompt_parts.append("**Metric Anomalies:**")
            for metric in groundtruth['key_metrics']:
                prompt_parts.append(f"- {metric}")
            prompt_parts.append("")

        # Fault description (for understanding, not for copying)
        if 'fault_description' in groundtruth and groundtruth['fault_description']:
            prompt_parts.append("**Fault Characteristics:**")
            for desc in groundtruth['fault_description']:
                prompt_parts.append(f"- {desc}")
            prompt_parts.append("")

        # Service/instance info
        if 'service' in groundtruth:
            prompt_parts.append(f"**Affected Service:** {groundtruth['service']}")
        if 'instance' in groundtruth:
            instances = groundtruth['instance'] if isinstance(groundtruth['instance'], list) else [groundtruth['instance']]
            prompt_parts.append(f"**Affected Instance(s):** {', '.join(instances)}")
        prompt_parts.append("")

        # Agent's reasoning (if available and potentially useful)
        prompt_parts.append("## Agent's Analysis")
        prompt_parts.append("```json")
        prompt_parts.append(json.dumps({
            'component': prediction.get('component', 'UNKNOWN'),
            'reason': prediction.get('reason', 'No prediction available')
        }, indent=2, ensure_ascii=False))
        prompt_parts.append("```")
        prompt_parts.append("")

        # Internal note about quality (helps LLM decide strategy)
        strategy_hint = ""
        if match_result['component_match'] and match_result['reason_match'] == 'YES':
            strategy_hint = "Note: Agent's reasoning appears sound. Consider Strategy A (extract and reformat)."
        else:
            strategy_hint = "Note: Agent's conclusion may be incorrect or incomplete. Consider Strategy B (reconstruct from evidence)."
        prompt_parts.append(f"**Internal Assessment:** {strategy_hint}\n")

        # Reasoning Trace (optional, can be very long)
        if include_log:
            prompt_parts.append("## Agent Reasoning Trace")
            prompt_parts.append("```")
            # Truncate if too long (keep first and last parts)
            if len(reasoning_log) > 50000:
                lines = reasoning_log.split('\n')
                truncated = '\n'.join(lines[:200]) + "\n\n... [TRUNCATED] ...\n\n" + '\n'.join(lines[-200:])
                prompt_parts.append(truncated)
            else:
                prompt_parts.append(reasoning_log)
            prompt_parts.append("```\n")

        # Task Instructions
        prompt_parts.append(self._build_task_instructions())

        return "\n".join(prompt_parts)

    def _build_task_instructions(self) -> str:
        """Build the task instructions section"""
        return """## Your Task

Analyze this case and construct a clean, evidence-driven reasoning trajectory for the knowledge base.

---

### Step 1: Assess Evidence Quality

**Can you construct a natural reasoning path from observable evidence?**

Check if the case has:
- At least 2 concrete anomaly observations (logs/metrics/traces)
- Clear causal relationship between observations
- Sufficient evidence to support elimination logic

**If NO** → Output DISCARD and explain why
**If YES** → Continue to Step 2

---

### Step 2: Determine Reconstruction Strategy

**Strategy A - Use Agent Reasoning (if all conditions met):**
- Component conclusion is reasonable
- Reasoning starts from evidence (not from answer)
- No GT/fault_type references in agent trace
- Causal logic is sound

→ Extract and reformat agent's reasoning into standard template

**Strategy B - Reconstruct from Evidence (if any condition fails):**
- Component is wrong, OR
- Reasoning is answer-driven, OR
- Agent trace contains GT leakage, OR
- Logic is flawed

→ Use available evidence to build a new reasoning path that naturally leads to the correct conclusion

---

### Step 3: Generate Historical Reasoning Trajectory

**IMPORTANT**: Output ONLY the reasoning trajectory content below. Do NOT include:
- Code fence markers (```)
- Instruction text or reminders
- Section descriptions like "Describe initial observable anomalies"
- Constraint reminders like "DO NOT mention..."

Output in this exact format:

[Trigger]
- Log anomaly pattern: [describe what changed]
- Metric anomaly pattern: [describe the change]
- Trace anomaly pattern: [describe the behavior]

[Focus Evidence]
Primary evidence (core causal indicators):
- Evidence 1: [describe what it shows] - why this matters for causality
- Evidence 2: [describe what it shows] - why this matters for causality

Secondary evidence (downstream effects or noise):
- Evidence 3: [describe what it shows] - why this is a consequence not cause
- Evidence 4: [describe what it shows] - why this can be deprioritized

[Reasoning]
Step 1: Initial hypothesis based on primary evidence
"Given [specific observation], we suspect [abstract causal description]"

Step 2: Verification or elimination
"If this were caused by [alternative explanation], we would expect [specific pattern];
However, actual observation shows [different pattern];
This rules out [alternative explanation]"

Step 3: Convergence to conclusion
"The combination of [evidence A] and [evidence B] indicates [abstract root cause description]"

[Conclusion]
"The root cause is [abstract description of what went wrong and why]"

[Next Action]
- "Verify whether [specific evidence type] exists"
- "Check for [specific pattern] in [data source]"

---

### Step 4: Final Quality Check

Before outputting, verify:
- ✅ No mentions of: GT, fault_type, fault_category, key_observations, quality level, semantic match
- ✅ No fault type labels (network delay, pod crash, jvm fault, etc.)
- ✅ Reasoning flows naturally from observation to conclusion
- ✅ Uses abstract causal descriptions
- ✅ No operational commands in Next Action
- ✅ Reads like a natural diagnostic thought process

If any check fails, revise before outputting.

---

### Special Case: DISCARD

If evidence is insufficient or contradictory, output:

[Decision: DISCARD]

Reason: [Explain specifically why this case cannot produce a valid reasoning trajectory]

---

**FINAL REMINDER**: Your output should contain ONLY the trajectory content (starting with [Trigger] and ending with [Next Action] or [Decision: DISCARD]). Do NOT include any instruction text, code fences, or reminders in your output.

---

Now analyze the case above and generate the historical reasoning trajectory."""

    def build_batch_prompt(
        self,
        cases: list[Dict[str, Any]],
        max_cases: int = 5
    ) -> str:
        """
        Build a prompt for batch processing multiple cases

        Args:
            cases: List of case dictionaries with uuid, prediction, gt, log
            max_cases: Maximum number of cases to include

        Returns:
            Batch processing prompt
        """
        prompt_parts = []

        prompt_parts.append("# Batch Case Analysis Task\n")
        prompt_parts.append(f"Analyze the following {min(len(cases), max_cases)} cases and generate reasoning policies.\n")

        for i, case in enumerate(cases[:max_cases], 1):
            prompt_parts.append(f"\n{'='*80}")
            prompt_parts.append(f"## CASE {i}/{min(len(cases), max_cases)}")
            prompt_parts.append('='*80 + "\n")

            # Build individual case prompt without full instructions
            prompt_parts.append(f"### Case UUID: {case['uuid']}\n")

            prompt_parts.append("**Ground Truth:**")
            prompt_parts.append("```json")
            prompt_parts.append(json.dumps(case['groundtruth'], indent=2, ensure_ascii=False))
            prompt_parts.append("```\n")

            prompt_parts.append("**Agent Prediction:**")
            prompt_parts.append("```json")
            prompt_parts.append(json.dumps(case['prediction'], indent=2, ensure_ascii=False))
            prompt_parts.append("```\n")

            # Abbreviated reasoning trace
            if 'reasoning_summary' in case:
                prompt_parts.append("**Reasoning Summary:**")
                prompt_parts.append(case['reasoning_summary'])
                prompt_parts.append("")

        prompt_parts.append("\n" + "="*80)
        prompt_parts.append("## TASK")
        prompt_parts.append("="*80 + "\n")
        prompt_parts.append("For each case above, generate a reasoning policy following the format specified in the system prompt.")
        prompt_parts.append("Output each policy separated by a line of dashes (----).\n")

        return "\n".join(prompt_parts)


def load_case_data(uuid: str, base_path: str = ".") -> Dict[str, Any]:
    """
    Load all data for a specific case

    Args:
        uuid: Case identifier
        base_path: Base directory containing logs and output folders

    Returns:
        Dictionary with prediction, groundtruth, and reasoning_log
    """
    base = Path(base_path)

    # Load prediction result (you'll need to specify where this is stored)
    # For now, assuming it's in a results file
    prediction = None

    # Load groundtruth
    gt_file = base / "output" / "groundtruth.jsonl"
    groundtruth = None
    if gt_file.exists():
        with open(gt_file, 'r', encoding='utf-8') as f:
            for line in f:
                data = json.loads(line)
                if data.get('uuid') == uuid:
                    groundtruth = data
                    break

    # Load reasoning log
    log_file = base / "logs" / uuid / "run.log"
    reasoning_log = ""
    if log_file.exists():
        with open(log_file, 'r', encoding='utf-8') as f:
            reasoning_log = f.read()

    return {
        'uuid': uuid,
        'prediction': prediction,
        'groundtruth': groundtruth,
        'reasoning_log': reasoning_log
    }


def main():
    """Example usage"""
    builder = ReasoningPolicyPromptBuilder()

    # Example: Build prompt for a single case
    case_data = {
        'uuid': '744d4e2b-106',
        'prediction': {
            'uuid': '744d4e2b-106',
            'component': 'adservice',
            'reason': 'Chaos Mesh stress testing injection causing AdService--stress-1749237006 Byteman agent failure and rrt_max spike',
            'reasoning_trace': [
                {'step': 1, 'action': 'LogSearch(adservice)', 'observation': 'Found AdService--stress-1749237006 Byteman agent failure'},
                {'step': 2, 'action': 'LoadMetrics(adservice)', 'observation': 'pod_cpu_usage increased from 0.01 to 0.6 (193% change)'},
                {'step': 3, 'action': 'TraceAnalysis(744d4e2b-106)', 'observation': 'frontend->adservice calls showed rrt_max increase from 5.4s to 32s'}
            ]
        },
        'groundtruth': {
            'fault_category': 'jvm fault',
            'fault_type': 'jvm cpu',
            'service': 'adservice',
            'key_observations': [
                {'type': 'log', 'keyword': ['adservice--stress']},
                {'type': 'metric', 'keyword': ['pod_cpu_usage']}
            ],
            'fault_description': ['JVM CPU spike', 'JVM CPU overload']
        },
        'reasoning_log': '... full log content ...'
    }

    # Generate prompt
    prompt = builder.build_case_prompt(
        uuid=case_data['uuid'],
        prediction=case_data['prediction'],
        groundtruth=case_data['groundtruth'],
        reasoning_log=case_data['reasoning_log'],
        include_log=False  # Set to True to include full log
    )

    # Print system prompt + case prompt
    print("="*80)
    print("SYSTEM PROMPT")
    print("="*80)
    print(builder.system_prompt)
    print("\n" + "="*80)
    print("CASE PROMPT")
    print("="*80)
    print(prompt)


if __name__ == '__main__':
    main()

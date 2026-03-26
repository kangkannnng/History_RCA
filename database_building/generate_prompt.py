#!/usr/bin/env python3
"""
Generate Knowledge Base Construction Prompts (Improved Version)
改进版：要求LLM严格使用GT中的标准术语
"""

import json
import argparse
from pathlib import Path
from typing import Dict, Any, Optional


SYSTEM_PROMPT = """# Role
You are an AIOps Knowledge Base Construction Expert. Your task is to map critical information from **Ground Truth** back to raw Log/Trace/Metric data, constructing **rigorous, reproducible, and retrievable** fault diagnosis rules.

# Input Data
1. **Ground Truth**: {ground_truth_json}
   - This is the **absolute truth**. Your task is not to "analyze" the fault, but to "reverse engineer" how to locate these standard answers from the raw data.
   - **instance**: The standard name of the faulty component (may be a string or a list; if a list, any match is valid).
   - **key_metrics**: The standardized name of the root cause (this is the core of Root Cause, must match exactly).
   - **key_observations**: Key evidence of fault features (contains keywords, this is the core basis for the reasoning process).
2. **Historical Conclusion**: {past_result}
   - For reference only. If it conflicts with Ground Truth, **ignore it completely**.
3. **Full Context**: {full_process_log}
   - The raw source of evidence. Every specific detail in your output must be supported by raw data here.

# Constraints (Crucial! Must be strictly followed)
1. **Component Identity**:
   - The **fault component** in the output must **verbatim copy** the `instance` field from Ground Truth.
   - Do not use abbreviations, aliases, or descriptive language.
   - If `instance` is a list, choose the specific name that appears in Full Context.

2. **Root Cause Terminology**:
   - The **fault cause** in the output must **verbatim include** the values from the `key_metrics` field in Ground Truth.
   - This is the core index for subsequent retrieval, **no synonym substitution allowed**.

3. **Feature Construction (Reasoning)**:
   - Your reasoning process (`expert_knowledge`) must be based on `key_observations` -> `keyword` from Ground Truth.
   - **Do not summarize features yourself**. You must find the specific context (log lines or metric changes) where these `keywords` appear in Full Context and use them as evidence.
   - Your task is to prove: "Why is the `keyword` in GT a key feature leading to the fault?"

# Processing Workflow
1. **Locate**: Search for keywords from Ground Truth's `instance` and `key_observations` in Full Context.
2. **Verify**: Confirm that these keywords indeed appear in error logs or abnormal metrics.
3. **Formulate**: Assemble the verified evidence into a rule: "If [keyword] is observed AND component is [instance], THEN cause is [key_metrics]".

# Output Format (JSON Only)
{{
    "uuid": "Keep original ID",
    "fault_type": "Must directly use key_metrics from Ground Truth (combine if multiple)",
    "symptom_vector": "English summary of surface symptoms (refer to fault_description in GT)",
    "expert_knowledge": {{
        "root_cause_desc": "English description. Format must be: Component [instance] experienced [key_metrics] fault. Must include the **original values** of these two variables.",
        "reasoning_chain": [
            "Step 1: Check Metadata - Confirm faulty component is [instance] (From Ground Truth)",
            "Step 2: Check Observation - Found keyword [keyword] in [Log/Metric] (From GT key_observations)",
            "Step 3: Derive Root Cause - Based on above features, determined cause is [key_metrics] (From Ground Truth)"
        ],
        "critical_checks": [
            {{
                "modality": "Trace" | "Log" | "Metric", 
                "target": "Must be the original keyword from GT key_observations", 
                "expected_pattern": "Describe specific manifestation of this keyword in Full Context (e.g., 'Connection refused' error appeared)",
                "instruction": "Specific and executable instruction (English), e.g., 'Search for keyword [keyword] in Log'"
            }}
        ]
    }}
}}

# Example
Assuming Ground Truth is:
{{
    "instance": ["redis-cart"],
    "key_metrics": ["redis_memory_usage", "evicted_keys"],
    "key_observations": [
        {{"type": "metric", "keyword": ["used_memory_rss"]}}, 
        {{"type": "log", "keyword": ["OOM command not allowed"]}}
    ]
}}

Output must be similar to:
{{
    "uuid": "...",
    "fault_type": "redis_memory_usage", 
    "symptom_vector": "Redis service extracting failure due to memory limit",
    "expert_knowledge": {{
        "root_cause_desc": "Component [redis-cart] experienced [redis_memory_usage] fault, accompanied by [evicted_keys] anomaly.",
        "reasoning_chain": [
            "Step 1: Check Metadata - Locked faulty component as [redis-cart].",
            "Step 2: Check Observation - Observed keyword [used_memory_rss] continuously rising in Metric.",
            "Step 3: Check Observation - Precisely matched keyword [OOM command not allowed] in Log.",
            "Step 4: Derive Conclusion - Based on combine features, determined root cause is [redis_memory_usage] exceeding limit."
        ],
        "critical_checks": [
            {{
                "modality": "Metric",
                "target": "used_memory_rss",
                "expected_pattern": "Value exceeds limit",
                "instruction": "Check if metric [used_memory_rss] is approaching the limit"
            }},
            {{
                "modality": "Log",
                "target": "OOM command not allowed",
                "expected_pattern": "Error log entry exists",
                "instruction": "Search for keyword 'OOM command not allowed' in logs"
            }}
        ]
    }}
}}
"""


def load_groundtruth_data(gt_file: str) -> Dict[str, Dict[str, Any]]:
    """加载groundtruth数据"""
    groundtruths = {}
    gt_path = Path(gt_file)

    if not gt_path.exists():
        raise FileNotFoundError(f"Ground truth file not found: {gt_file}")

    with open(gt_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            if 'uuid' in data:
                # 保留完整的GT数据
                groundtruths[data['uuid']] = data

    return groundtruths


def load_result_data(result_file: str) -> Dict[str, Dict[str, Any]]:
    """加载历史结论数据"""
    results = {}
    result_path = Path(result_file)

    if not result_path.exists():
        print(f"Warning: Result file not found: {result_file}")
        return results

    with open(result_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            if 'uuid' in data:
                results[data['uuid']] = data

    return results


def load_run_log(uuid: str, logs_dir: str) -> str:
    """加载run.log文件"""
    log_path = Path(logs_dir) / uuid / "run.log"

    if not log_path.exists():
        return f"[Log file not found: {log_path}]"

    try:
        with open(log_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"[Error reading log file: {e}]"


def generate_prompt(
    uuid: str,
    groundtruth: Dict[str, Any],
    past_result: Optional[Dict[str, Any]],
    full_log: str
) -> str:
    """生成单个case的prompt"""

    # 格式化ground truth JSON（保留完整信息）
    gt_json = json.dumps(groundtruth, indent=2, ensure_ascii=False)

    # 格式化历史结论
    if past_result:
        past_result_json = json.dumps({
            'component': past_result.get('component', 'UNKNOWN'),
            'reason': past_result.get('reason', 'No conclusion available'),
            'reasoning_trace': past_result.get('reasoning_trace', [])
        }, indent=2, ensure_ascii=False)
    else:
        past_result_json = json.dumps({
            'component': 'UNKNOWN',
            'reason': 'No historical conclusion available',
            'reasoning_trace': []
        }, indent=2, ensure_ascii=False)

    # 填充模板
    prompt = SYSTEM_PROMPT.format(
        ground_truth_json=gt_json,
        past_result=past_result_json,
        full_process_log=full_log
    )

    return prompt


def main():
    parser = argparse.ArgumentParser(
        description='Generate knowledge base construction prompts (Improved)'
    )
    parser.add_argument(
        '--gt-file',
        default='output/groundtruth.jsonl',
        help='Path to groundtruth.jsonl file'
    )
    parser.add_argument(
        '--result-file',
        default='output/result.jsonl',
        help='Path to result.jsonl file (historical conclusions)'
    )
    parser.add_argument(
        '--logs-dir',
        default='logs',
        help='Base directory containing case logs (with uuid subdirectories)'
    )
    parser.add_argument(
        '--output-dir',
        default='knowledge_base_prompts_v2',
        help='Directory to save generated prompts'
    )
    parser.add_argument(
        '--split-file',
        default='output/splits/seen_train.jsonl',
        help='Use specific split file (default: seen_train.jsonl)'
    )
    parser.add_argument(
        '--cases',
        nargs='+',
        help='Specific case UUIDs to process (overrides --split-file)'
    )

    args = parser.parse_args()

    # 创建输出目录
    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)

    # 加载数据
    print("Loading ground truth data...")
    groundtruths = load_groundtruth_data(args.gt_file)
    print(f"Loaded {len(groundtruths)} ground truth entries")

    print("Loading historical results...")
    results = load_result_data(args.result_file)
    print(f"Loaded {len(results)} historical results")

    # 确定要处理的cases
    if args.cases:
        # 优先使用命令行指定的cases
        case_uuids = args.cases
        print(f"Using {len(case_uuids)} cases from command line")
    elif args.split_file:
        # 从split文件加载
        split_path = Path(args.split_file)
        if split_path.exists():
            case_uuids = []
            with open(split_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    # 支持两种格式：纯UUID文本文件 或 JSONL格式
                    if line.startswith('{'):
                        # JSONL格式
                        data = json.loads(line)
                        if 'uuid' in data:
                            case_uuids.append(data['uuid'])
                    else:
                        # 纯文本格式
                        case_uuids.append(line)
            print(f"Loaded {len(case_uuids)} cases from split file: {args.split_file}")
        else:
            print(f"Warning: Split file not found: {args.split_file}")
            print("Falling back to all cases from groundtruth")
            case_uuids = list(groundtruths.keys())
    else:
        # 处理所有cases
        case_uuids = list(groundtruths.keys())
        print(f"Processing all {len(case_uuids)} cases from groundtruth")

    print(f"\nProcessing {len(case_uuids)} cases...")

    # 处理每个case
    success_count = 0
    failed_cases = []

    for idx, uuid in enumerate(case_uuids, 1):
        print(f"\n[{idx}/{len(case_uuids)}] Processing case: {uuid}")

        # 获取ground truth
        gt = groundtruths.get(uuid)
        if not gt:
            print(f"  Warning: No ground truth found for {uuid}, skipping")
            failed_cases.append((uuid, "No ground truth"))
            continue

        # 获取历史结论
        past_result = results.get(uuid)
        if not past_result:
            print(f"  Warning: No historical result found for {uuid}, will use placeholder")

        # 加载run.log
        full_log = load_run_log(uuid, args.logs_dir)
        if full_log.startswith("[Log file not found"):
            print(f"  Warning: {full_log}")

        # 生成prompt
        try:
            prompt = generate_prompt(
                uuid=uuid,
                groundtruth=gt,
                past_result=past_result,
                full_log=full_log
            )

            # 保存prompt
            prompt_file = output_dir / f"{uuid}.txt"
            with open(prompt_file, 'w', encoding='utf-8') as f:
                f.write(prompt)

            print(f"  ✓ Saved prompt to: {prompt_file}")
            success_count += 1

        except Exception as e:
            print(f"  ✗ Error generating prompt: {e}")
            failed_cases.append((uuid, str(e)))

    # 输出统计信息
    print(f"\n{'='*80}")
    print(f"Processing Complete!")
    print(f"{'='*80}")
    print(f"Total cases: {len(case_uuids)}")
    print(f"Successfully processed: {success_count}")
    print(f"Failed: {len(failed_cases)}")

    if failed_cases:
        print(f"\nFailed cases:")
        for uuid, reason in failed_cases:
            print(f"  - {uuid}: {reason}")

    print(f"\nOutput directory: {output_dir.absolute()}")
    print(f"\nNext steps:")
    print(f"  1. Review generated prompts in {output_dir}")
    print(f"  2. Use call_llm.py with --prompts-dir {output_dir}")
    print(f"  3. Validate results with validate.py")


if __name__ == '__main__':
    main()

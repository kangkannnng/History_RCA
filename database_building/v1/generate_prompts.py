#!/usr/bin/env python3
"""
Generate prompts for all cases and save them for LLM processing
"""

import json
import argparse
from pathlib import Path
from typing import Dict, Any, List
from v1.reasoning_policy_builder import ReasoningPolicyPromptBuilder


def load_all_predictions(results_file: str) -> Dict[str, Dict[str, Any]]:
    """
    Load all prediction results from a JSON/JSONL file

    Args:
        results_file: Path to results file

    Returns:
        Dictionary mapping uuid to prediction data
    """
    predictions = {}
    results_path = Path(results_file)

    if not results_path.exists():
        print(f"Warning: Results file not found: {results_file}")
        return predictions

    with open(results_path, 'r', encoding='utf-8') as f:
        # Try JSONL format first
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                if 'uuid' in data:
                    predictions[data['uuid']] = data
            except json.JSONDecodeError:
                # Try as single JSON file
                f.seek(0)
                try:
                    all_data = json.load(f)
                    if isinstance(all_data, list):
                        for item in all_data:
                            if 'uuid' in item:
                                predictions[item['uuid']] = item
                    elif isinstance(all_data, dict) and 'uuid' in all_data:
                        predictions[all_data['uuid']] = all_data
                except:
                    pass
                break

    return predictions


def load_all_groundtruths(gt_file: str) -> Dict[str, Dict[str, Any]]:
    """
    Load all ground truth data from groundtruth.jsonl

    Args:
        gt_file: Path to groundtruth.jsonl

    Returns:
        Dictionary mapping uuid to groundtruth data
    """
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
                groundtruths[data['uuid']] = data

    return groundtruths


def load_reasoning_log(uuid: str, logs_dir: str) -> str:
    """
    Load reasoning log for a specific case

    Args:
        uuid: Case identifier
        logs_dir: Base logs directory

    Returns:
        Log content as string
    """
    log_path = Path(logs_dir) / uuid / "run.log"

    if not log_path.exists():
        return f"[Log file not found: {log_path}]"

    with open(log_path, 'r', encoding='utf-8') as f:
        return f.read()


def extract_reasoning_summary(log_content: str, max_lines: int = 100) -> str:
    """
    Extract a summary of the reasoning process from the log

    Args:
        log_content: Full log content
        max_lines: Maximum lines to include in summary

    Returns:
        Summarized reasoning trace
    """
    lines = log_content.split('\n')

    # Extract key lines (consensus, hypothesis, findings)
    key_lines = []
    for line in lines:
        if any(keyword in line for keyword in [
            'CONSENSUS', 'Hypothesis', 'hypothesis', 'AGREED', 'DISAGREED',
            'root cause', 'Root Cause', 'component', 'reason',
            'Final State', 'Analysis Completed'
        ]):
            key_lines.append(line)

    if len(key_lines) > max_lines:
        return '\n'.join(key_lines[:max_lines//2] + ['...'] + key_lines[-max_lines//2:])

    return '\n'.join(key_lines) if key_lines else log_content[:5000]


def generate_single_case_prompt(
    uuid: str,
    prediction: Dict[str, Any],
    groundtruth: Dict[str, Any],
    reasoning_log: str,
    builder: ReasoningPolicyPromptBuilder,
    include_full_log: bool = False
) -> str:
    """Generate prompt for a single case"""

    return builder.build_case_prompt(
        uuid=uuid,
        prediction=prediction,
        groundtruth=groundtruth,
        reasoning_log=reasoning_log,
        include_log=include_full_log
    )


def main():
    parser = argparse.ArgumentParser(
        description='Generate reasoning policy prompts for RCA cases'
    )
    parser.add_argument(
        '--gt-file',
        default='output/groundtruth.jsonl',
        help='Path to groundtruth.jsonl file'
    )
    parser.add_argument(
        '--results-file',
        default='output/predictions.jsonl',
        help='Path to predictions/results file'
    )
    parser.add_argument(
        '--logs-dir',
        default='logs',
        help='Base directory containing case logs'
    )
    parser.add_argument(
        '--output-dir',
        default='prompts',
        help='Directory to save generated prompts'
    )
    parser.add_argument(
        '--cases',
        nargs='+',
        help='Specific case UUIDs to process (default: all)'
    )
    parser.add_argument(
        '--include-full-log',
        action='store_true',
        help='Include full reasoning log in prompts (can be very long)'
    )
    parser.add_argument(
        '--batch-mode',
        action='store_true',
        help='Generate batch prompts (multiple cases per file)'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=5,
        help='Number of cases per batch prompt'
    )

    args = parser.parse_args()

    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)

    # Load data
    print("Loading ground truth data...")
    groundtruths = load_all_groundtruths(args.gt_file)
    print(f"Loaded {len(groundtruths)} ground truth entries")

    print("Loading prediction results...")
    predictions = load_all_predictions(args.results_file)
    print(f"Loaded {len(predictions)} prediction results")

    # Determine which cases to process
    if args.cases:
        case_uuids = args.cases
    else:
        # Process all cases that have ground truth
        case_uuids = list(groundtruths.keys())

    print(f"\nProcessing {len(case_uuids)} cases...")

    # Initialize builder
    builder = ReasoningPolicyPromptBuilder()

    # Save system prompt once
    system_prompt_file = output_dir / "system_prompt.txt"
    with open(system_prompt_file, 'w', encoding='utf-8') as f:
        f.write(builder.system_prompt)
    print(f"Saved system prompt to: {system_prompt_file}")

    if args.batch_mode:
        # Batch processing mode
        batches = [case_uuids[i:i+args.batch_size]
                   for i in range(0, len(case_uuids), args.batch_size)]

        for batch_idx, batch_uuids in enumerate(batches, 1):
            print(f"\nGenerating batch {batch_idx}/{len(batches)}...")

            batch_cases = []
            for uuid in batch_uuids:
                gt = groundtruths.get(uuid)
                pred = predictions.get(uuid, {
                    'uuid': uuid,
                    'component': 'UNKNOWN',
                    'reason': 'No prediction available',
                    'reasoning_trace': []
                })

                log_content = load_reasoning_log(uuid, args.logs_dir)
                reasoning_summary = extract_reasoning_summary(log_content)

                batch_cases.append({
                    'uuid': uuid,
                    'groundtruth': gt,
                    'prediction': pred,
                    'reasoning_summary': reasoning_summary
                })

            batch_prompt = builder.build_batch_prompt(batch_cases, max_cases=args.batch_size)

            batch_file = output_dir / f"batch_{batch_idx:03d}.txt"
            with open(batch_file, 'w', encoding='utf-8') as f:
                f.write(batch_prompt)
            print(f"Saved batch prompt to: {batch_file}")

    else:
        # Individual case mode
        for idx, uuid in enumerate(case_uuids, 1):
            print(f"\n[{idx}/{len(case_uuids)}] Processing case: {uuid}")

            # Get ground truth
            gt = groundtruths.get(uuid)
            if not gt:
                print(f"  Warning: No ground truth found for {uuid}, skipping")
                continue

            # Get prediction (may not exist for all cases)
            pred = predictions.get(uuid, {
                'uuid': uuid,
                'component': 'UNKNOWN',
                'reason': 'No prediction available',
                'reasoning_trace': []
            })

            # Load reasoning log
            log_content = load_reasoning_log(uuid, args.logs_dir)

            # Generate prompt
            prompt = generate_single_case_prompt(
                uuid=uuid,
                prediction=pred,
                groundtruth=gt,
                reasoning_log=log_content,
                builder=builder,
                include_full_log=args.include_full_log
            )

            # Save prompt
            prompt_file = output_dir / f"{uuid}.txt"
            with open(prompt_file, 'w', encoding='utf-8') as f:
                f.write(prompt)

            print(f"  Saved prompt to: {prompt_file}")

    print(f"\n✓ All prompts generated successfully!")
    print(f"  Output directory: {output_dir.absolute()}")
    print(f"\nNext steps:")
    print(f"  1. Review system prompt: {system_prompt_file}")
    print(f"  2. Send prompts to LLM for analysis")
    print(f"  3. Collect reasoning policies from LLM responses")


if __name__ == '__main__':
    main()

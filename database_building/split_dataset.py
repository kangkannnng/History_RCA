#!/usr/bin/env python3
"""
Split dataset into Seen-Train, Seen-Test, and Unseen-Test
Based on fault_type stratification
"""

import json
import random
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple


def load_groundtruth(gt_file: str) -> List[Dict]:
    """Load all groundtruth data"""
    cases = []
    with open(gt_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            cases.append(json.loads(line))
    return cases


def analyze_fault_types(cases: List[Dict]) -> Dict[str, List[Dict]]:
    """Group cases by fault_type"""
    fault_type_groups = defaultdict(list)

    for case in cases:
        fault_type = case.get('fault_type', 'unknown')
        fault_type_groups[fault_type].append(case)

    return dict(fault_type_groups)


def split_dataset(
    cases: List[Dict],
    unseen_fault_types: List[str],
    seen_train_ratio: float = 0.70,
    random_seed: int = 42
) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    """
    Split dataset into Seen-Train, Seen-Test, and Unseen-Test

    Args:
        cases: All cases
        unseen_fault_types: List of fault_types to use as unseen
        seen_train_ratio: Ratio of seen data to use for training (within seen pool)
        random_seed: Random seed for reproducibility

    Returns:
        (seen_train, seen_test, unseen_test)
    """
    random.seed(random_seed)

    # Step 1: Separate unseen cases
    unseen_test = []
    seen_pool = []

    for case in cases:
        fault_type = case.get('fault_type', 'unknown')
        if fault_type in unseen_fault_types:
            unseen_test.append(case)
        else:
            seen_pool.append(case)

    # Step 2: Group seen cases by fault_type for stratified split
    seen_by_type = defaultdict(list)
    for case in seen_pool:
        fault_type = case.get('fault_type', 'unknown')
        seen_by_type[fault_type].append(case)

    # Step 3: Stratified split of seen data
    seen_train = []
    seen_test = []

    for fault_type, type_cases in seen_by_type.items():
        # Shuffle cases of this type
        random.shuffle(type_cases)

        # Calculate split point
        n_train = int(len(type_cases) * seen_train_ratio)

        # Split
        seen_train.extend(type_cases[:n_train])
        seen_test.extend(type_cases[n_train:])

    # Shuffle final lists
    random.shuffle(seen_train)
    random.shuffle(seen_test)
    random.shuffle(unseen_test)

    return seen_train, seen_test, unseen_test


def save_split(cases: List[Dict], output_file: str):
    """Save cases to JSONL file"""
    with open(output_file, 'w', encoding='utf-8') as f:
        for case in cases:
            f.write(json.dumps(case, ensure_ascii=False) + '\n')


def print_statistics(
    all_cases: List[Dict],
    seen_train: List[Dict],
    seen_test: List[Dict],
    unseen_test: List[Dict]
):
    """Print dataset statistics"""

    def count_by_type(cases):
        counts = defaultdict(int)
        for case in cases:
            fault_type = case.get('fault_type', 'unknown')
            counts[fault_type] += 1
        return dict(counts)

    print("\n" + "="*80)
    print("DATASET SPLIT STATISTICS")
    print("="*80)

    total_seen = len(seen_train) + len(seen_test)

    print(f"\nTotal cases: {len(all_cases)}")
    print(f"  - Seen-Train: {len(seen_train)} ({len(seen_train)/len(all_cases)*100:.1f}% of total, {len(seen_train)/total_seen*100:.1f}% of seen)")
    print(f"  - Seen-Test:  {len(seen_test)} ({len(seen_test)/len(all_cases)*100:.1f}% of total, {len(seen_test)/total_seen*100:.1f}% of seen)")
    print(f"  - Unseen-Test: {len(unseen_test)} ({len(unseen_test)/len(all_cases)*100:.1f}% of total)")
    print(f"\nSeen Train:Test Ratio = {len(seen_train)/total_seen:.2f}:{len(seen_test)/total_seen:.2f} ≈ {len(seen_train)/len(seen_test):.1f}:1")

    print("\n" + "-"*80)
    print("FAULT TYPE DISTRIBUTION")
    print("-"*80)

    all_types = count_by_type(all_cases)
    train_types = count_by_type(seen_train)
    test_types = count_by_type(seen_test)
    unseen_types = count_by_type(unseen_test)

    print(f"\n{'Fault Type':<30} {'Total':<8} {'Train':<8} {'Test':<8} {'Unseen':<8} {'Train%':<10} {'Test%':<10}")
    print("-"*100)

    for fault_type in sorted(all_types.keys()):
        total = all_types[fault_type]
        train = train_types.get(fault_type, 0)
        test = test_types.get(fault_type, 0)
        unseen = unseen_types.get(fault_type, 0)

        # Calculate percentages within seen pool for this fault_type
        seen_total = train + test
        train_pct = f"{train/seen_total*100:.1f}%" if seen_total > 0 else "N/A"
        test_pct = f"{test/seen_total*100:.1f}%" if seen_total > 0 else "N/A"

        marker = " [UNSEEN]" if unseen > 0 else ""
        print(f"{fault_type:<30} {total:<8} {train:<8} {test:<8} {unseen:<8} {train_pct:<10} {test_pct:<10}{marker}")

    print("\n" + "="*80)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Split dataset into Seen-Train, Seen-Test, and Unseen-Test'
    )
    parser.add_argument(
        '--gt-file',
        default='output/groundtruth.jsonl',
        help='Path to groundtruth.jsonl file'
    )
    parser.add_argument(
        '--output-dir',
        default='output/splits',
        help='Directory to save split files'
    )
    parser.add_argument(
        '--unseen-types',
        nargs='+',
        default=['jvm gc', 'network loss'],
        help='Fault types to use as unseen (default: jvm gc, network loss)'
    )
    parser.add_argument(
        '--train-ratio',
        type=float,
        default=0.70,
        help='Ratio of seen data to use for training (default: 0.70 for 7:3 split)'
    )
    parser.add_argument(
        '--seed',
        type=int,
        default=42,
        help='Random seed for reproducibility (default: 42)'
    )

    args = parser.parse_args()

    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load data
    print(f"Loading groundtruth from: {args.gt_file}")
    all_cases = load_groundtruth(args.gt_file)
    print(f"Loaded {len(all_cases)} cases")

    # Analyze fault types
    print("\nAnalyzing fault types...")
    fault_type_groups = analyze_fault_types(all_cases)
    print(f"Found {len(fault_type_groups)} unique fault types:")
    for fault_type, cases in sorted(fault_type_groups.items(), key=lambda x: -len(x[1])):
        print(f"  - {fault_type}: {len(cases)} cases")

    # Validate unseen types
    print(f"\nUnseen fault types: {args.unseen_types}")
    for unseen_type in args.unseen_types:
        if unseen_type not in fault_type_groups:
            print(f"WARNING: Unseen type '{unseen_type}' not found in dataset!")
        else:
            print(f"  - {unseen_type}: {len(fault_type_groups[unseen_type])} cases")

    # Split dataset
    print(f"\nSplitting dataset (train_ratio={args.train_ratio}, seed={args.seed})...")
    seen_train, seen_test, unseen_test = split_dataset(
        all_cases,
        args.unseen_types,
        args.train_ratio,
        args.seed
    )

    # Save splits
    print("\nSaving splits...")
    save_split(seen_train, output_dir / 'seen_train.jsonl')
    save_split(seen_test, output_dir / 'seen_test.jsonl')
    save_split(unseen_test, output_dir / 'unseen_test.jsonl')

    # Save UUID lists for easy reference
    with open(output_dir / 'seen_train_uuids.txt', 'w') as f:
        for case in seen_train:
            f.write(case['uuid'] + '\n')

    with open(output_dir / 'seen_test_uuids.txt', 'w') as f:
        for case in seen_test:
            f.write(case['uuid'] + '\n')

    with open(output_dir / 'unseen_test_uuids.txt', 'w') as f:
        for case in unseen_test:
            f.write(case['uuid'] + '\n')

    print(f"  - Seen-Train: {output_dir / 'seen_train.jsonl'}")
    print(f"  - Seen-Test:  {output_dir / 'seen_test.jsonl'}")
    print(f"  - Unseen-Test: {output_dir / 'unseen_test.jsonl'}")

    # Print statistics
    print_statistics(all_cases, seen_train, seen_test, unseen_test)

    print(f"\n✓ Dataset split completed!")
    print(f"\nNext steps:")
    print(f"  1. Review the split statistics above")
    print(f"  2. Generate prompts ONLY for Seen-Train:")
    print(f"     python3 generate_prompts.py \\")
    print(f"       --gt-file {output_dir / 'seen_train.jsonl'} \\")
    print(f"       --results-file output/result.jsonl \\")
    print(f"       --logs-dir logs \\")
    print(f"       --output-dir prompts \\")
    print(f"       --include-full-log")
    print(f"  3. Build knowledge base from Seen-Train reasoning policies")
    print(f"  4. Evaluate on Seen-Test and Unseen-Test")


if __name__ == '__main__':
    main()

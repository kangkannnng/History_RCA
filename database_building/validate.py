#!/usr/bin/env python3
"""
Validate Knowledge Base Entries Against Ground Truth (Revised)
使用更合理的标准验证知识库条目与Ground Truth的一致性
"""

import json
import argparse
from pathlib import Path
from typing import Dict, List, Tuple, Any


def load_groundtruth(gt_file: str) -> Dict[str, Dict]:
    """加载Ground Truth数据"""
    groundtruths = {}
    with open(gt_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            if 'uuid' in data:
                groundtruths[data['uuid']] = data
    return groundtruths


def load_knowledge_base(kb_file: str) -> Dict[str, Dict]:
    """加载知识库条目"""
    kb_entries = {}
    with open(kb_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            if 'uuid' in entry:
                kb_entries[entry['uuid']] = entry
    return kb_entries


def normalize_text(text: str) -> str:
    """标准化文本用于比较"""
    return text.lower().strip().replace(' ', '').replace('-', '').replace('_', '')


def check_instance_match(kb_entry: Dict, gt: Dict) -> Tuple[float, str]:
    """
    检查故障组件是否匹配（必须匹配至少一个）

    Returns:
        (score_0_to_40, reason)
    """
    gt_instance = gt.get('instance', '')

    # 处理instance可能是列表的情况
    if isinstance(gt_instance, list):
        if not gt_instance:
            return 40.0, "GT specifies no fault component, giving full score"
        gt_instances = gt_instance
    else:
        gt_instances = [gt_instance] if gt_instance else []

    if not gt_instances:
        return 40.0, "GT specifies no fault component, giving full score"

    # Extract component info from KB entry
    root_cause = kb_entry['expert_knowledge']['root_cause_desc']
    reasoning_chain = ' '.join(kb_entry['expert_knowledge']['reasoning_chain'])

    # Normalize comparisons
    root_cause_norm = normalize_text(root_cause)
    reasoning_norm = normalize_text(reasoning_chain)

    # Check each GT component
    matched_instances = []
    for gt_inst in gt_instances:
        gt_inst_str = str(gt_inst)
        gt_inst_norm = normalize_text(gt_inst_str)

        # Check if correct component is mentioned
        if gt_inst_norm in root_cause_norm or gt_inst_norm in reasoning_norm:
            matched_instances.append(gt_inst_str)
            continue

        # Special case: Node fault
        if gt_inst_str.startswith('aiops-k8s-'):
            if 'node' in root_cause or 'node' in root_cause_norm:
                matched_instances.append(gt_inst_str)
                continue

    if matched_instances:
        return 40.0, f"✓ Component matched: {matched_instances}"

    return 0.0, f"✗ Component mismatch: GT={gt_instances}, not explicitly mentioned in KB"


def check_key_metrics_coverage(kb_entry: Dict, gt: Dict) -> Tuple[float, List[str]]:
    """
    Check coverage of fault cause keywords
    key_metrics are keywords for the fault cause, full score (40) if any is hit

    Returns:
        (score_0_to_40, details)
    """
    gt_metrics = gt.get('key_metrics', [])
    if not gt_metrics:
        return 40.0, ["GT specifies no fault cause keywords, giving full score"]

    # Extract text from KB reasoning_chain
    reasoning_chain = ' '.join(kb_entry['expert_knowledge']['reasoning_chain'])
    reasoning_norm = normalize_text(reasoning_chain)

    # Check if any GT keyword appears in reasoning
    matched_metrics = []
    details = []

    for gt_metric in gt_metrics:
        gt_metric_norm = normalize_text(str(gt_metric))

        if gt_metric_norm in reasoning_norm:
            matched_metrics.append(gt_metric)
            details.append(f"  ✓ {gt_metric}")
        else:
            details.append(f"  ✗ {gt_metric}")

    # Full score (40) if any match
    if matched_metrics:
        score = 40.0
    else:
        score = 0.0

    return score, details


def check_observation_coverage(kb_entry: Dict, gt: Dict) -> Tuple[float, List[str]]:
    """
    Check coverage of key_observations (proportion appearing in reasoning_chain)

    Returns:
        (score_0_to_20, details)
    """
    gt_observations = gt.get('key_observations', [])
    if not gt_observations:
        return 20.0, ["GT specifies no observations, giving full score"]

    # Extract text from KB reasoning_chain
    reasoning_chain = ' '.join(kb_entry['expert_knowledge']['reasoning_chain'])
    reasoning_norm = normalize_text(reasoning_chain)

    # Collect all keywords from GT
    all_keywords = []
    for obs in gt_observations:
        keywords = obs.get('keyword', [])
        all_keywords.extend(keywords)

    if not all_keywords:
        return 20.0, ["GT specifies no specific keywords, giving full score"]

    # Check if each keyword appears in reasoning
    matched_keywords = []
    details = []

    for keyword in all_keywords:
        keyword_norm = normalize_text(str(keyword))

        if keyword_norm in reasoning_norm:
            matched_keywords.append(keyword)
            details.append(f"  ✓ {keyword}")
        else:
            details.append(f"  ✗ {keyword}")

    # Calculate score: match ratio * 20
    coverage_rate = len(matched_keywords) / len(all_keywords)
    score = coverage_rate * 20.0

    return score, details


def validate_entry(uuid: str, kb_entry: Dict, gt: Dict) -> Dict:
    """
    验证单个知识库条目
    新评分标准：组件40分 + 故障原因关键词40分 + 特征20分 = 100分

    Returns:
        验证结果字典
    """
    result = {
        'uuid': uuid,
        'checks': {},
        'scores': {}
    }

    # 1. 检查组件匹配（40分）
    instance_score, instance_msg = check_instance_match(kb_entry, gt)
    result['checks']['instance_match'] = {
        'score': instance_score,
        'message': instance_msg
    }
    result['scores']['instance'] = instance_score

    # 2. 检查故障原因关键词覆盖（40分）
    # key_metrics是故障原因的关键词，不是指标
    metrics_score, metrics_details = check_key_metrics_coverage(kb_entry, gt)
    result['checks']['key_metrics'] = {
        'score': metrics_score,
        'details': metrics_details
    }
    result['scores']['metrics'] = metrics_score

    # 3. 检查观测特征覆盖（20分）
    obs_score, obs_details = check_observation_coverage(kb_entry, gt)
    result['checks']['observation_coverage'] = {
        'score': obs_score,
        'details': obs_details
    }
    result['scores']['observation'] = obs_score

    # 计算总分（满分100）
    total_score = instance_score + metrics_score + obs_score
    result['scores']['total'] = total_score

    # 判断是否通过（60分及格）
    result['overall_valid'] = total_score >= 60.0

    return result


def main():
    parser = argparse.ArgumentParser(
        description='Validate knowledge base entries against ground truth (Revised)'
    )
    parser.add_argument(
        '--kb-file',
        default='knowledge_base_data/knowledge_base.jsonl',
        help='Path to knowledge_base.jsonl'
    )
    parser.add_argument(
        '--gt-file',
        default='output/groundtruth.jsonl',
        help='Path to groundtruth.jsonl'
    )
    parser.add_argument(
        '--output',
        default='knowledge_base_data/validation_result.json',
        help='Output validation report file'
    )
    parser.add_argument(
        '--show-all',
        action='store_true',
        help='Show all entries in output (including valid ones)'
    )
    parser.add_argument(
        '--cases',
        nargs='+',
        help='Validate specific cases only'
    )

    args = parser.parse_args()

    print("="*80)
    print("Knowledge Base Validation Against Ground Truth (100分制)")
    print("="*80)
    print()

    # 加载数据
    print(f"Loading ground truth from: {args.gt_file}")
    groundtruths = load_groundtruth(args.gt_file)
    print(f"Loaded {len(groundtruths)} ground truth entries")

    print(f"Loading knowledge base from: {args.kb_file}")
    kb_entries = load_knowledge_base(args.kb_file)
    print(f"Loaded {len(kb_entries)} knowledge base entries")
    print()

    # 确定要验证的cases
    if args.cases:
        uuids_to_validate = args.cases
    else:
        uuids_to_validate = list(kb_entries.keys())

    print(f"Validating {len(uuids_to_validate)} entries...")
    print()

    # 验证每个条目
    validation_results = {}
    valid_count = 0
    invalid_count = 0
    missing_gt_count = 0

    score_distribution = {
        '90-100': 0,
        '80-89': 0,
        '70-79': 0,
        '60-69': 0,
        '50-59': 0,
        '<50': 0
    }

    for uuid in uuids_to_validate:
        if uuid not in kb_entries:
            print(f"Warning: {uuid} not found in knowledge base")
            continue

        if uuid not in groundtruths:
            print(f"Warning: {uuid} not found in ground truth")
            missing_gt_count += 1
            continue

        kb_entry = kb_entries[uuid]
        gt = groundtruths[uuid]

        result = validate_entry(uuid, kb_entry, gt)
        validation_results[uuid] = result

        # 统计
        score = result['scores']['total']
        if result['overall_valid']:  # >= 60分
            valid_count += 1
        else:
            invalid_count += 1

        # 分数分布（100分制）
        if score >= 90:
            score_distribution['90-100'] += 1
        elif score >= 80:
            score_distribution['80-89'] += 1
        elif score >= 70:
            score_distribution['70-79'] += 1
        elif score >= 60:
            score_distribution['60-69'] += 1
        elif score >= 50:
            score_distribution['50-59'] += 1
        else:
            score_distribution['<50'] += 1

    # 输出统计
    print("="*80)
    print("VALIDATION SUMMARY")
    print("="*80)
    total = len(validation_results)
    print(f"Total validated: {total}")
    print(f"✓ Valid (score >= 60): {valid_count} ({valid_count/total*100:.1f}%)")
    print(f"✗ Invalid (score < 60): {invalid_count} ({invalid_count/total*100:.1f}%)")
    if missing_gt_count > 0:
        print(f"⚠ Missing GT: {missing_gt_count}")
    print()

    print("Score Distribution (100分制):")
    for range_label, count in score_distribution.items():
        pct = count / total * 100 if total > 0 else 0
        bar = '█' * int(pct / 2)
        print(f"  {range_label}: {count:3d} ({pct:5.1f}%) {bar}")
    print()

    # 计算平均分数
    avg_scores = {
        'total': sum(r['scores']['total'] for r in validation_results.values()) / total,
        'instance': sum(r['scores']['instance'] for r in validation_results.values()) / total,
        'metrics': sum(r['scores']['metrics'] for r in validation_results.values()) / total,
        'observation': sum(r['scores']['observation'] for r in validation_results.values()) / total
    }

    print("Average Scores:")
    print(f"  Total Score: {avg_scores['total']:.1f} / 100")
    print(f"  Instance (组件): {avg_scores['instance']:.1f} / 40")
    print(f"  Key Metrics (故障原因关键词): {avg_scores['metrics']:.1f} / 40")
    print(f"  Observation (特征): {avg_scores['observation']:.1f} / 20")
    print()

    # 显示无效的条目
    if invalid_count > 0:
        print("="*80)
        print(f"INVALID ENTRIES (showing top 10)")
        print("="*80)

        # 按分数排序，显示最差的10个
        sorted_invalid = sorted(
            [(uuid, r) for uuid, r in validation_results.items()
             if not r['overall_valid']],
            key=lambda x: x[1]['scores']['total']
        )[:10]

        for uuid, result in sorted_invalid:
            print(f"\n{uuid} (Total: {result['scores']['total']:.1f}/100):")
            print(f"  组件: {result['scores']['instance']:.1f}/40")
            print(f"  故障原因关键词: {result['scores']['metrics']:.1f}/40")
            print(f"  特征: {result['scores']['observation']:.1f}/20")

            # 显示详细信息
            for check_name, check_result in result['checks'].items():
                if check_result['score'] < 40 and check_name == 'instance_match':
                    print(f"  {check_result['message']}")
                elif check_result['score'] < 40 and check_name in ['key_metrics', 'observation_coverage']:
                    if 'details' in check_result and len(check_result['details']) <= 5:
                        for detail in check_result['details']:
                            print(f"  {detail}")

    # 保存验证报告
    report = {
        'summary': {
            'total': total,
            'valid': valid_count,
            'invalid': invalid_count,
            'missing_gt': missing_gt_count,
            'valid_rate': valid_count / total if total > 0 else 0,
            'score_distribution': score_distribution,
            'average_scores': avg_scores
        },
        'results': validation_results if args.show_all else {
            uuid: result for uuid, result in validation_results.items()
            if not result['overall_valid']
        }
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\nValidation report saved to: {output_path}")

    # 返回状态
    if valid_count / total >= 0.8:  # 80%以上通过
        print(f"\n✓ Validation passed! {valid_count/total*100:.1f}% of entries are valid.")
        return 0
    else:
        print(f"\n⚠ Warning: Only {valid_count/total*100:.1f}% of entries passed validation.")
        print("Consider reviewing and regenerating low-scoring entries.")
        return 1


if __name__ == '__main__':
    exit(main())

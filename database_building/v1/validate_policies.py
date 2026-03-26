#!/usr/bin/env python3
"""
Validate reasoning policy quality

Can be used by:
1. Automated validation (rule-based)
2. LLM-based validation (send to another model for review)
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional


def validate_policy_automated(policy: str, uuid: str) -> Tuple[bool, List[str], Dict[str, any]]:
    """
    Automated rule-based validation

    Returns:
        (is_valid, issues_list, metrics_dict)
    """
    issues = []
    metrics = {
        'length': len(policy),
        'line_count': len(policy.split('\n')),
        'has_all_sections': True,
        'has_gt_leakage': False,
        'has_instruction_leakage': False,
        'has_code_fences': False,
        'has_repetition': False
    }

    # Check 1: Not empty
    if not policy or len(policy.strip()) < 100:
        issues.append("CRITICAL: Policy is empty or too short")
        return False, issues, metrics

    # Check 2: No error messages
    if policy.startswith("ERROR:"):
        issues.append(f"CRITICAL: API error - {policy[:100]}")
        return False, issues, metrics

    # Check 3: Has required sections
    required_sections = ['[Trigger]', '[Focus Evidence]', '[Reasoning]', '[Conclusion]', '[Next Action]']
    missing_sections = [s for s in required_sections if s not in policy]
    if missing_sections:
        issues.append(f"CRITICAL: Missing sections - {', '.join(missing_sections)}")
        metrics['has_all_sections'] = False

    # Check 4: No GT leakage
    gt_keywords = ['GT', 'fault_type', 'fault_category', 'key_observations', 'Quality Level', 'Semantic Match']
    found_leakage = []
    for kw in gt_keywords:
        # Use word boundary to avoid false positives
        if re.search(r'\b' + re.escape(kw) + r'\b', policy):
            found_leakage.append(kw)

    if found_leakage:
        issues.append(f"HIGH: GT leakage detected - {', '.join(found_leakage)}")
        metrics['has_gt_leakage'] = True

    # Check 5: No instruction text leakage
    instruction_patterns = [
        (r'DO NOT mention', 'DO NOT mention'),
        (r'DO NOT use', 'DO NOT use'),
        (r'DO NOT say', 'DO NOT say'),
        (r'CRITICAL RULES', 'CRITICAL RULES'),
        (r'Describe initial observable', 'section description'),
        (r'Explain which evidence', 'section description'),
        (r'Build a single coherent', 'instruction text')
    ]

    for pattern, label in instruction_patterns:
        if re.search(pattern, policy, re.IGNORECASE):
            issues.append(f"HIGH: Instruction text leakage - {label}")
            metrics['has_instruction_leakage'] = True
            break

    # Check 6: No excessive repetition (corrupted output)
    lines = policy.split('\n')
    if len(lines) > 50:
        # Check last 20 lines for repetitive patterns
        last_lines = ' '.join(lines[-20:])
        repetition_indicators = [
            ('upstream', 15),
            ('I knew', 10),
            ('unable to', 10),
            ('and so on', 8)
        ]

        for word, threshold in repetition_indicators:
            count = last_lines.count(word)
            if count > threshold:
                issues.append(f"CRITICAL: Excessive repetition - '{word}' appears {count} times in last 20 lines")
                metrics['has_repetition'] = True
                break

    # Check 7: No code fence markers
    if policy.strip().startswith('```') or policy.strip().endswith('```'):
        issues.append("MEDIUM: Code fence markers present")
        metrics['has_code_fences'] = True

    # Check 8: Reasonable length
    if len(policy) < 500:
        issues.append("MEDIUM: Policy too short (< 500 chars)")
    elif len(policy) > 10000:
        issues.append(f"MEDIUM: Policy too long ({len(policy)} chars)")

    # Check 9: No fault type labels
    fault_labels = [
        'network delay', 'pod crash', 'pod failure', 'cpu stress',
        'memory stress', 'jvm fault', 'jvm gc', 'jvm cpu'
    ]
    found_labels = [label for label in fault_labels if label in policy.lower()]
    if found_labels:
        issues.append(f"MEDIUM: Fault type labels detected - {', '.join(found_labels)}")

    # Determine severity
    has_critical = any('CRITICAL' in issue for issue in issues)
    has_high = any('HIGH' in issue for issue in issues)

    is_valid = not has_critical and not has_high

    return is_valid, issues, metrics


def generate_llm_validation_prompt(policy: str, uuid: str) -> str:
    """
    Generate a prompt for LLM to validate policy quality

    This can be sent to another LLM (like Claude or GPT-4) for review
    """
    return f"""# Reasoning Policy Quality Review

Please review this reasoning policy and identify any quality issues.

**Case UUID:** {uuid}

**Policy Content:**
```
{policy}
```

---

## Review Checklist

Please check for the following issues:

### 1. Structural Issues
- [ ] Missing required sections ([Trigger], [Focus Evidence], [Reasoning], [Conclusion], [Next Action])
- [ ] Sections are out of order or malformed
- [ ] Policy is too short (< 500 chars) or too long (> 10000 chars)

### 2. Content Leakage
- [ ] Contains GT/fault_type/fault_category/key_observations references
- [ ] Contains instruction text (e.g., "DO NOT mention", "Describe initial observable")
- [ ] Contains quality metadata (Level 1/2/3/4, Semantic Match scores)
- [ ] Contains code fence markers (```)

### 3. Fault Type Labels
- [ ] Uses fault type labels instead of abstract descriptions:
  - ❌ "network delay" → ✅ "communication path experiencing abnormal latency"
  - ❌ "pod crash" → ✅ "service instance became unstable"
  - ❌ "cpu stress" → ✅ "computational resource exhaustion"

### 4. Reasoning Quality
- [ ] Reasoning flows naturally from evidence to conclusion
- [ ] Uses "expected vs actual" comparison logic
- [ ] Includes elimination of alternative hypotheses
- [ ] Avoids working backwards from the answer

### 5. Evidence Attribution
- [ ] Evidence is concrete and observable
- [ ] Primary vs secondary evidence is clearly distinguished
- [ ] No fabricated evidence

### 6. Next Actions
- [ ] Suggests diagnostic verification (not operational commands)
- [ ] No kubectl/traceroute/remediation commands
- [ ] Actions are specific and actionable

### 7. Corruption Indicators
- [ ] Excessive repetition of words/phrases
- [ ] Incoherent or nonsensical text
- [ ] Incomplete sentences or truncated output

---

## Output Format

Please provide your review in this format:

**Overall Assessment:** [PASS / NEEDS_REVISION / FAIL]

**Issues Found:**
- [Issue 1 with severity: CRITICAL/HIGH/MEDIUM/LOW]
- [Issue 2 with severity: CRITICAL/HIGH/MEDIUM/LOW]
- ...

**Recommendations:**
- [Specific recommendation 1]
- [Specific recommendation 2]
- ...

**Summary:**
[Brief 1-2 sentence summary of the policy quality]
"""


def validate_policies_in_directory(
    policies_dir: str,
    output_report: Optional[str] = None,
    generate_llm_prompts: bool = False,
    llm_prompts_dir: Optional[str] = None
) -> Dict:
    """
    Validate all policies in a directory

    Args:
        policies_dir: Directory containing policy files
        output_report: Path to save validation report JSON
        generate_llm_prompts: Whether to generate LLM validation prompts
        llm_prompts_dir: Directory to save LLM validation prompts

    Returns:
        Dictionary with validation results
    """
    policies_path = Path(policies_dir)

    if not policies_path.exists():
        raise FileNotFoundError(f"Policies directory not found: {policies_dir}")

    results = {}

    # Process each policy file
    policy_files = list(policies_path.glob("*_policy.txt"))

    print(f"Validating {len(policy_files)} policies...")
    print()

    for policy_file in sorted(policy_files):
        uuid = policy_file.stem.replace('_policy', '')

        # Read policy
        policy = policy_file.read_text(encoding='utf-8')

        # Validate
        is_valid, issues, metrics = validate_policy_automated(policy, uuid)

        # Store results
        results[uuid] = {
            'file': str(policy_file),
            'valid': is_valid,
            'issues': issues,
            'metrics': metrics
        }

        # Print status
        status = "✓" if is_valid else "✗"
        print(f"{status} {uuid}: {'PASS' if is_valid else 'FAIL'}")
        if issues:
            for issue in issues:
                severity = issue.split(':')[0]
                print(f"    [{severity}] {issue}")

        # Generate LLM validation prompt if requested
        if generate_llm_prompts and llm_prompts_dir:
            llm_prompts_path = Path(llm_prompts_dir)
            llm_prompts_path.mkdir(exist_ok=True)

            llm_prompt = generate_llm_validation_prompt(policy, uuid)
            llm_prompt_file = llm_prompts_path / f"{uuid}_validation_prompt.txt"
            llm_prompt_file.write_text(llm_prompt, encoding='utf-8')

    # Summary statistics
    total = len(results)
    valid = sum(1 for r in results.values() if r['valid'])
    invalid = total - valid

    critical_issues = sum(1 for r in results.values()
                         if any('CRITICAL' in issue for issue in r['issues']))
    high_issues = sum(1 for r in results.values()
                     if any('HIGH' in issue for issue in r['issues']))

    summary = {
        'total': total,
        'valid': valid,
        'invalid': invalid,
        'critical_issues': critical_issues,
        'high_issues': high_issues,
        'results': results
    }

    # Save report
    if output_report:
        report_path = Path(output_report)
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        print(f"\nValidation report saved to: {report_path}")

    return summary


def main():
    """Main execution"""
    import argparse

    parser = argparse.ArgumentParser(description='Validate reasoning policy quality')
    parser.add_argument('--policies-dir', required=True, help='Directory containing policy files')
    parser.add_argument('--output-report', help='Path to save validation report JSON')
    parser.add_argument('--generate-llm-prompts', action='store_true',
                       help='Generate prompts for LLM-based validation')
    parser.add_argument('--llm-prompts-dir', default='validation_prompts',
                       help='Directory to save LLM validation prompts')

    args = parser.parse_args()

    print("="*80)
    print("Reasoning Policy Quality Validator")
    print("="*80)
    print()

    # Validate policies
    summary = validate_policies_in_directory(
        args.policies_dir,
        args.output_report,
        args.generate_llm_prompts,
        args.llm_prompts_dir
    )

    # Print summary
    print("\n" + "="*80)
    print("VALIDATION SUMMARY")
    print("="*80)
    print(f"\nTotal policies: {summary['total']}")
    print(f"✓ Valid: {summary['valid']} ({summary['valid']/summary['total']*100:.1f}%)")
    print(f"✗ Invalid: {summary['invalid']} ({summary['invalid']/summary['total']*100:.1f}%)")
    print(f"\nCritical issues: {summary['critical_issues']}")
    print(f"High severity issues: {summary['high_issues']}")

    # List invalid cases
    if summary['invalid'] > 0:
        print("\n" + "-"*80)
        print("INVALID POLICIES")
        print("-"*80)

        for uuid, result in sorted(summary['results'].items()):
            if not result['valid']:
                print(f"\n{uuid}:")
                for issue in result['issues']:
                    print(f"  - {issue}")

    if args.generate_llm_prompts:
        print(f"\n✓ LLM validation prompts saved to: {args.llm_prompts_dir}")
        print("  Send these prompts to another LLM for detailed review")

    print()


if __name__ == '__main__':
    main()

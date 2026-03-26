#!/usr/bin/env python3
"""
Parallel LLM API caller with automatic quality checking

Features:
1. Parallel API calls using asyncio
2. Automatic quality validation
3. Retry failed/corrupted cases
"""

import json
import os
import asyncio
from pathlib import Path
from typing import Optional, Dict, List, Tuple
import re
from dotenv import load_dotenv

# Load environment variables
load_dotenv(Path(__file__).parent.parent.parent / "history_rca" / ".env")


def load_prompt_files(prompts_dir: str = "prompts_examples"):
    """Load system prompt and case prompts"""
    prompts_path = Path(prompts_dir)

    # Load system prompt
    system_prompt_file = prompts_path / "system_prompt.txt"
    if not system_prompt_file.exists():
        raise FileNotFoundError(f"System prompt not found: {system_prompt_file}")

    system_prompt = system_prompt_file.read_text(encoding='utf-8')

    # Load case prompts
    case_prompts = {}
    for prompt_file in prompts_path.glob("*.txt"):
        if prompt_file.name == "system_prompt.txt" or prompt_file.name == "all_cases_combined.txt":
            continue

        uuid = prompt_file.stem
        case_prompts[uuid] = prompt_file.read_text(encoding='utf-8')

    return system_prompt, case_prompts


async def call_deepseek_api_async(
    system_prompt: str,
    case_prompt: str,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None
) -> str:
    """
    Call DeepSeek API asynchronously

    Requires: pip install openai
    """
    try:
        import openai
    except ImportError:
        return "ERROR: openai package not installed. Run: pip install openai"

    if not api_key:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("API key not provided and OPENAI_API_KEY not set in environment")

    if not base_url:
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.huiyan-ai.cn/v1")

    client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)

    try:
        response = await client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": case_prompt}
            ],
            temperature=0.3,
            max_tokens=4096
        )

        return response.choices[0].message.content
    except Exception as e:
        return f"ERROR: {str(e)}"


def validate_policy_quality(policy: str, uuid: str) -> Tuple[bool, List[str]]:
    """
    Validate reasoning policy quality

    Returns:
        (is_valid, issues_list)
    """
    issues = []

    # Check 1: Not empty
    if not policy or len(policy.strip()) < 100:
        issues.append("Policy is empty or too short")
        return False, issues

    # Check 2: No error messages
    if policy.startswith("ERROR:"):
        issues.append(f"API error: {policy}")
        return False, issues

    # Check 3: Has required sections
    required_sections = ['[Trigger]', '[Focus Evidence]', '[Reasoning]', '[Conclusion]', '[Next Action]']
    missing_sections = [s for s in required_sections if s not in policy]
    if missing_sections:
        issues.append(f"Missing sections: {', '.join(missing_sections)}")

    # Check 4: No GT leakage
    gt_keywords = ['GT', 'fault_type', 'fault_category', 'key_observations', 'Quality Level', 'Semantic Match']
    found_leakage = [kw for kw in gt_keywords if kw in policy]
    if found_leakage:
        issues.append(f"GT leakage detected: {', '.join(found_leakage)}")

    # Check 5: No instruction text leakage
    instruction_patterns = [
        r'DO NOT mention',
        r'DO NOT use',
        r'DO NOT say',
        r'CRITICAL RULES',
        r'Describe initial observable',
        r'Explain which evidence'
    ]
    for pattern in instruction_patterns:
        if re.search(pattern, policy, re.IGNORECASE):
            issues.append(f"Instruction text leakage: '{pattern}'")
            break

    # Check 6: No excessive repetition (corrupted output)
    lines = policy.split('\n')
    if len(lines) > 50:
        # Check last 20 lines for repetitive patterns
        last_lines = ' '.join(lines[-20:])
        if last_lines.count('upstream') > 15 or last_lines.count('I knew') > 10:
            issues.append("Excessive repetition detected (corrupted output)")

    # Check 7: No code fence markers at start/end
    if policy.strip().startswith('```') or policy.strip().endswith('```'):
        issues.append("Code fence markers present")

    # Check 8: Reasonable length
    if len(policy) > 10000:
        issues.append(f"Policy too long ({len(policy)} chars)")

    # Determine if valid
    is_valid = len(issues) == 0

    return is_valid, issues


def save_reasoning_policy(uuid: str, policy: str, output_dir: str = "reasoning_policies"):
    """Save reasoning policy to file"""
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)

    policy_file = output_path / f"{uuid}_policy.txt"
    with open(policy_file, 'w', encoding='utf-8') as f:
        f.write(policy)

    return policy_file


async def process_case(
    uuid: str,
    case_prompt: str,
    system_prompt: str,
    api_key: Optional[str],
    base_url: Optional[str],
    output_dir: str,
    semaphore: asyncio.Semaphore
) -> Dict:
    """Process a single case with rate limiting"""
    async with semaphore:
        try:
            # Call API
            policy = await call_deepseek_api_async(system_prompt, case_prompt, api_key, base_url)

            # Validate quality
            is_valid, issues = validate_policy_quality(policy, uuid)

            # Save policy
            policy_file = save_reasoning_policy(uuid, policy, output_dir)

            return {
                'uuid': uuid,
                'status': 'success' if is_valid else 'needs_retry',
                'valid': is_valid,
                'issues': issues,
                'file': str(policy_file),
                'length': len(policy)
            }

        except Exception as e:
            return {
                'uuid': uuid,
                'status': 'error',
                'valid': False,
                'issues': [str(e)],
                'file': None,
                'length': 0
            }


async def process_all_cases(
    case_prompts: Dict[str, str],
    system_prompt: str,
    api_key: Optional[str],
    base_url: Optional[str],
    output_dir: str,
    max_concurrent: int = 20
):
    """Process all cases in parallel"""
    semaphore = asyncio.Semaphore(max_concurrent)

    tasks = [
        process_case(uuid, prompt, system_prompt, api_key, base_url, output_dir, semaphore)
        for uuid, prompt in case_prompts.items()
    ]

    results = await asyncio.gather(*tasks)

    return {r['uuid']: r for r in results}


def main():
    """Main execution"""
    import argparse

    parser = argparse.ArgumentParser(description='Parallel LLM API caller with quality checking')
    parser.add_argument('--api-key', help='API key (or set via environment variable)')
    parser.add_argument('--base-url', help='Base URL for API')
    parser.add_argument('--prompts-dir', default='prompts_examples', help='Directory containing prompts')
    parser.add_argument('--output-dir', default='reasoning_policies', help='Directory to save policies')
    parser.add_argument('--cases', nargs='+', help='Specific cases to process (default: all)')
    parser.add_argument('--max-concurrent', type=int, default=20, help='Max concurrent API calls')
    parser.add_argument('--retry-failed', action='store_true', help='Retry failed/invalid cases')
    parser.add_argument('--max-retries', type=int, default=3, help='Max retry attempts')

    args = parser.parse_args()

    print("="*80)
    print("Parallel Reasoning Policy Generator with Quality Checking")
    print("="*80)
    print()

    # Load prompts
    print(f"Loading prompts from: {args.prompts_dir}")
    try:
        system_prompt, case_prompts = load_prompt_files(args.prompts_dir)
        print(f"✓ Loaded system prompt ({len(system_prompt)} chars)")
        print(f"✓ Loaded {len(case_prompts)} case prompts")
        print()
    except Exception as e:
        print(f"✗ Error loading prompts: {e}")
        return

    # Filter cases if specified
    if args.cases:
        case_prompts = {uuid: prompt for uuid, prompt in case_prompts.items() if uuid in args.cases}
        print(f"Filtering to {len(case_prompts)} specified cases")
        print()

    # Process cases
    print(f"Processing {len(case_prompts)} cases with max {args.max_concurrent} concurrent calls...")
    print()

    retry_count = 0
    all_results = {}

    while retry_count <= args.max_retries:
        if retry_count > 0:
            print(f"\n{'='*80}")
            print(f"RETRY ATTEMPT {retry_count}/{args.max_retries}")
            print(f"{'='*80}\n")

        # Run async processing
        results = asyncio.run(process_all_cases(
            case_prompts,
            system_prompt,
            args.api_key,
            args.base_url,
            args.output_dir,
            args.max_concurrent
        ))

        # Update all results
        all_results.update(results)

        # Check for cases that need retry
        if args.retry_failed:
            failed_cases = {
                uuid: case_prompts[uuid]
                for uuid, result in results.items()
                if result['status'] in ['error', 'needs_retry']
            }

            if failed_cases and retry_count < args.max_retries:
                print(f"\n{len(failed_cases)} cases need retry")
                case_prompts = failed_cases
                retry_count += 1
                continue

        break

    # Summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)

    valid_count = sum(1 for r in all_results.values() if r['valid'])
    needs_retry_count = sum(1 for r in all_results.values() if r['status'] == 'needs_retry')
    error_count = sum(1 for r in all_results.values() if r['status'] == 'error')

    print(f"\nTotal cases: {len(all_results)}")
    print(f"✓ Valid: {valid_count}")
    print(f"⚠ Needs manual review: {needs_retry_count}")
    print(f"✗ Errors: {error_count}")

    if valid_count > 0:
        print(f"\nReasoning policies saved to: {Path(args.output_dir).absolute()}")

    # Show cases that need attention
    if needs_retry_count > 0 or error_count > 0:
        print("\n" + "-"*80)
        print("CASES NEEDING ATTENTION")
        print("-"*80)

        for uuid, result in sorted(all_results.items()):
            if not result['valid']:
                print(f"\n{uuid}:")
                print(f"  Status: {result['status']}")
                print(f"  Issues:")
                for issue in result['issues']:
                    print(f"    - {issue}")
                if result['file']:
                    print(f"  File: {result['file']}")

    # Save validation report
    report_file = Path(args.output_dir) / "validation_report.json"
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"\nValidation report saved to: {report_file}")

    print()
    print("Next steps:")
    print("  1. Review cases marked as 'needs manual review'")
    print("  2. Retry failed cases if needed")
    print("  3. Validate policy quality manually for edge cases")


if __name__ == '__main__':
    main()

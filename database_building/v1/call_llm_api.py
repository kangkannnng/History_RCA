#!/usr/bin/env python3
"""
Example: Send prompts to LLM and collect reasoning policies

This script demonstrates how to:
1. Load generated prompts
2. Send them to an LLM (OpenAI, Anthropic, or local)
3. Parse and save the reasoning policies
"""

import json
import os
from pathlib import Path
from typing import Optional


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


def call_openai_api(system_prompt: str, case_prompt: str, api_key: Optional[str] = None) -> str:
    """
    Call OpenAI API (GPT-4)

    Requires: pip install openai
    """
    try:
        import openai
    except ImportError:
        return "ERROR: openai package not installed. Run: pip install openai"

    if not api_key:
        api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        return "ERROR: OPENAI_API_KEY not set"

    client = openai.OpenAI(api_key=api_key)

    response = client.chat.completions.create(
        model="gpt-4-turbo-preview",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": case_prompt}
        ],
        temperature=0.3,
        max_tokens=4096
    )

    return response.choices[0].message.content


def call_anthropic_api(system_prompt: str, case_prompt: str, api_key: Optional[str] = None) -> str:
    """
    Call Anthropic API (Claude)

    Requires: pip install anthropic
    """
    try:
        import anthropic
    except ImportError:
        return "ERROR: anthropic package not installed. Run: pip install anthropic"

    if not api_key:
        api_key = os.getenv("ANTHROPIC_API_KEY")

    if not api_key:
        return "ERROR: ANTHROPIC_API_KEY not set"

    client = anthropic.Anthropic(api_key=api_key)

    message = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=4096,
        system=system_prompt,
        messages=[
            {"role": "user", "content": case_prompt}
        ],
        temperature=0.3
    )

    return message.content[0].text


def call_deepseek_api(system_prompt: str, case_prompt: str, api_key: Optional[str] = None, base_url: Optional[str] = None) -> str:
    """
    Call DeepSeek API (or any OpenAI-compatible API)

    Requires: pip install openai
    """
    try:
        import openai
    except ImportError:
        return "ERROR: openai package not installed. Run: pip install openai"

    if not api_key:
        api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        return "ERROR: OPENAI_API_KEY not set in environment"

    if not base_url:
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.huiyan-ai.cn/v1")

    client = openai.OpenAI(api_key=api_key, base_url=base_url)

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": case_prompt}
        ],
        temperature=0.3,
        max_tokens=4096
    )

    return response.choices[0].message.content


def call_ollama_local(system_prompt: str, case_prompt: str, model: str = "llama3") -> str:
    """
    Call local Ollama instance

    Requires: Ollama running locally (ollama serve)
    """
    try:
        import requests
    except ImportError:
        return "ERROR: requests package not installed. Run: pip install requests"

    try:
        response = requests.post(
            "http://localhost:11434/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": case_prompt}
                ],
                "stream": False
            },
            timeout=300
        )

        if response.status_code == 200:
            return response.json()["message"]["content"]
        else:
            return f"ERROR: Ollama returned status {response.status_code}"

    except requests.exceptions.ConnectionError:
        return "ERROR: Cannot connect to Ollama. Is it running? (ollama serve)"


def save_reasoning_policy(uuid: str, policy: str, output_dir: str = "reasoning_policies"):
    """Save reasoning policy to file"""
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)

    policy_file = output_path / f"{uuid}_policy.txt"
    with open(policy_file, 'w', encoding='utf-8') as f:
        f.write(policy)

    return policy_file


def main():
    """Main execution"""
    import argparse

    parser = argparse.ArgumentParser(description='Send prompts to LLM and collect reasoning policies')
    parser.add_argument('--provider', choices=['openai', 'anthropic', 'deepseek', 'ollama'],
                        default='deepseek', help='LLM provider to use')
    parser.add_argument('--api-key', help='API key (or set via environment variable)')
    parser.add_argument('--base-url', help='Base URL for API (for DeepSeek or custom endpoints)')
    parser.add_argument('--model', default='llama3', help='Model name for Ollama')
    parser.add_argument('--prompts-dir', default='prompts_examples', help='Directory containing prompts')
    parser.add_argument('--output-dir', default='reasoning_policies', help='Directory to save policies')
    parser.add_argument('--cases', nargs='+', help='Specific cases to process (default: all)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be sent without calling API')

    args = parser.parse_args()

    print("="*80)
    print("Reasoning Policy Generator - LLM API Caller")
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

    # Select API caller
    if args.provider == 'openai':
        api_caller = lambda cp: call_openai_api(system_prompt, cp, args.api_key)
    elif args.provider == 'anthropic':
        api_caller = lambda cp: call_anthropic_api(system_prompt, cp, args.api_key)
    elif args.provider == 'deepseek':
        api_caller = lambda cp: call_deepseek_api(system_prompt, cp, args.api_key, args.base_url)
    elif args.provider == 'ollama':
        api_caller = lambda cp: call_ollama_local(system_prompt, cp, args.model)

    # Process each case
    print(f"Provider: {args.provider}")
    print(f"Processing {len(case_prompts)} cases...")
    print()

    results = {}

    for idx, (uuid, case_prompt) in enumerate(case_prompts.items(), 1):
        print(f"[{idx}/{len(case_prompts)}] Processing case: {uuid}")

        if args.dry_run:
            print(f"  [DRY RUN] Would send {len(case_prompt)} chars to {args.provider}")
            print(f"  System prompt: {len(system_prompt)} chars")
            print(f"  Case prompt preview: {case_prompt[:200]}...")
            print()
            continue

        try:
            # Call LLM
            print(f"  Calling {args.provider} API...")
            policy = api_caller(case_prompt)

            if policy.startswith("ERROR:"):
                print(f"  ✗ {policy}")
                results[uuid] = {'status': 'error', 'message': policy}
                continue

            # Save policy
            policy_file = save_reasoning_policy(uuid, policy, args.output_dir)
            print(f"  ✓ Saved policy to: {policy_file}")

            # Show preview
            lines = policy.split('\n')
            preview = '\n'.join(lines[:10])
            print(f"  Preview:\n{preview}")
            if len(lines) > 10:
                print(f"  ... ({len(lines) - 10} more lines)")

            results[uuid] = {'status': 'success', 'file': str(policy_file)}

        except Exception as e:
            print(f"  ✗ Error: {e}")
            results[uuid] = {'status': 'error', 'message': str(e)}

        print()

    # Summary
    print("="*80)
    print("SUMMARY")
    print("="*80)

    if args.dry_run:
        print("DRY RUN - No API calls were made")
        print(f"Would process {len(case_prompts)} cases with {args.provider}")
    else:
        success_count = sum(1 for r in results.values() if r['status'] == 'success')
        error_count = len(results) - success_count

        print(f"Total cases: {len(results)}")
        print(f"Successful: {success_count}")
        print(f"Errors: {error_count}")

        if success_count > 0:
            print(f"\nReasoning policies saved to: {Path(args.output_dir).absolute()}")

        if error_count > 0:
            print("\nFailed cases:")
            for uuid, result in results.items():
                if result['status'] == 'error':
                    print(f"  - {uuid}: {result['message']}")

    print()
    print("Next steps:")
    print("  1. Review generated reasoning policies")
    print("  2. Validate policy quality")
    print("  3. Add to experience database")


if __name__ == '__main__':
    main()

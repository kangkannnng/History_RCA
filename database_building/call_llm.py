#!/usr/bin/env python3
"""
Call LLM API to generate knowledge base entries from prompts
支持并行调用、进度条、自动重试、数据集分割
"""

import json
import asyncio
import argparse
import os
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from tqdm.asyncio import tqdm
import re
from dotenv import load_dotenv

# Load environment variables
load_dotenv(Path(__file__).parent.parent / "history_rca" / ".env")


def load_split_uuids(split_file: str) -> List[str]:
    """加载数据集分割文件"""
    split_path = Path(split_file)
    if not split_path.exists():
        raise FileNotFoundError(f"Split file not found: {split_file}")

    with open(split_path, 'r', encoding='utf-8') as f:
        uuids = [line.strip() for line in f if line.strip()]

    return uuids


def load_prompt_file(uuid: str, prompts_dir: str) -> Optional[str]:
    """加载单个prompt文件"""
    prompt_path = Path(prompts_dir) / f"{uuid}.txt"

    if not prompt_path.exists():
        return None

    with open(prompt_path, 'r', encoding='utf-8') as f:
        return f.read()


async def call_deepseek_api_async(
    prompt: str,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: str = "deepseek-v3.2",
    temperature: float = 0.3,
    max_tokens: int = 8192
) -> str:
    """异步调用DeepSeek API"""
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
            model=model,
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=temperature,
            max_tokens=max_tokens
        )

        return response.choices[0].message.content
    except Exception as e:
        return f"ERROR: {str(e)}"


def extract_json_from_response(response: str) -> Optional[Dict]:
    """从LLM响应中提取JSON"""
    # 尝试直接解析
    try:
        return json.loads(response)
    except:
        pass

    # 尝试提取代码块中的JSON
    json_pattern = r'```(?:json)?\s*(\{.*?\})\s*```'
    matches = re.findall(json_pattern, response, re.DOTALL)
    if matches:
        try:
            return json.loads(matches[0])
        except:
            pass

    # 尝试查找第一个完整的JSON对象
    try:
        start = response.find('{')
        if start != -1:
            # 简单的括号匹配
            count = 0
            for i in range(start, len(response)):
                if response[i] == '{':
                    count += 1
                elif response[i] == '}':
                    count -= 1
                    if count == 0:
                        return json.loads(response[start:i+1])
    except:
        pass

    return None


def validate_knowledge_entry(entry: Dict, uuid: str) -> Tuple[bool, List[str]]:
    """验证知识库条目的质量"""
    issues = []

    # 检查必需字段
    required_fields = ['uuid', 'fault_type', 'symptom_vector', 'expert_knowledge']
    for field in required_fields:
        if field not in entry:
            issues.append(f"Missing required field: {field}")

    if 'expert_knowledge' in entry:
        expert_knowledge = entry['expert_knowledge']

        # 检查expert_knowledge的子字段
        required_subfields = ['root_cause_desc', 'reasoning_chain', 'critical_checks']
        for field in required_subfields:
            if field not in expert_knowledge:
                issues.append(f"Missing expert_knowledge.{field}")

        # 检查reasoning_chain
        if 'reasoning_chain' in expert_knowledge:
            chain = expert_knowledge['reasoning_chain']
            if not isinstance(chain, list) or len(chain) < 2:
                issues.append("reasoning_chain should be a list with at least 2 steps")

        # 检查critical_checks
        if 'critical_checks' in expert_knowledge:
            checks = expert_knowledge['critical_checks']
            if not isinstance(checks, list) or len(checks) == 0:
                issues.append("critical_checks should be a non-empty list")
            else:
                for i, check in enumerate(checks):
                    if not isinstance(check, dict):
                        issues.append(f"critical_checks[{i}] should be a dict")
                        continue

                    # 检查modality是否合法
                    if 'modality' in check:
                        if check['modality'] not in ['Trace', 'Log', 'Metric']:
                            issues.append(f"critical_checks[{i}].modality must be Trace/Log/Metric")
                    else:
                        issues.append(f"critical_checks[{i}] missing modality")

                    # 检查其他必需字段
                    for field in ['target', 'expected_pattern', 'instruction']:
                        if field not in check:
                            issues.append(f"critical_checks[{i}] missing {field}")

    # 检查UUID是否匹配
    if 'uuid' in entry and entry['uuid'] != uuid:
        issues.append(f"UUID mismatch: expected {uuid}, got {entry['uuid']}")

    is_valid = len(issues) == 0
    return is_valid, issues


async def process_single_case(
    uuid: str,
    prompt: str,
    api_key: Optional[str],
    base_url: Optional[str],
    output_dir: str,
    semaphore: asyncio.Semaphore,
    pbar: tqdm
) -> Dict:
    """处理单个case"""
    async with semaphore:
        try:
            # 调用API
            response = await call_deepseek_api_async(prompt, api_key, base_url)

            # 更新进度条
            pbar.update(1)

            # 检查是否有错误
            if response.startswith("ERROR:"):
                return {
                    'uuid': uuid,
                    'status': 'error',
                    'valid': False,
                    'issues': [response],
                    'response': response,
                    'entry': None
                }

            # 提取JSON
            entry = extract_json_from_response(response)

            if entry is None:
                return {
                    'uuid': uuid,
                    'status': 'parse_error',
                    'valid': False,
                    'issues': ['Failed to extract JSON from response'],
                    'response': response,
                    'entry': None
                }

            # 验证质量
            is_valid, issues = validate_knowledge_entry(entry, uuid)

            # 保存结果
            if is_valid:
                # 保存到JSON文件
                output_path = Path(output_dir)
                output_path.mkdir(exist_ok=True)

                json_file = output_path / f"{uuid}.json"
                with open(json_file, 'w', encoding='utf-8') as f:
                    json.dump(entry, f, indent=2, ensure_ascii=False)

            # 保存原始响应（用于调试）
            raw_dir = Path(output_dir) / "raw_responses"
            raw_dir.mkdir(exist_ok=True)
            raw_file = raw_dir / f"{uuid}.txt"
            with open(raw_file, 'w', encoding='utf-8') as f:
                f.write(response)

            return {
                'uuid': uuid,
                'status': 'success' if is_valid else 'needs_review',
                'valid': is_valid,
                'issues': issues,
                'response': response[:500],  # 只保存前500字符
                'entry': entry
            }

        except Exception as e:
            pbar.update(1)
            return {
                'uuid': uuid,
                'status': 'exception',
                'valid': False,
                'issues': [str(e)],
                'response': None,
                'entry': None
            }


async def process_all_cases(
    uuids: List[str],
    prompts_dir: str,
    api_key: Optional[str],
    base_url: Optional[str],
    output_dir: str,
    max_concurrent: int = 10
) -> Dict[str, Dict]:
    """并行处理所有cases"""
    semaphore = asyncio.Semaphore(max_concurrent)

    # 加载所有prompts
    print(f"Loading prompts for {len(uuids)} cases...")
    case_prompts = {}
    missing_prompts = []

    for uuid in uuids:
        prompt = load_prompt_file(uuid, prompts_dir)
        if prompt:
            case_prompts[uuid] = prompt
        else:
            missing_prompts.append(uuid)

    if missing_prompts:
        print(f"Warning: {len(missing_prompts)} prompts not found")
        if len(missing_prompts) <= 10:
            print(f"Missing: {', '.join(missing_prompts)}")

    print(f"Processing {len(case_prompts)} cases with max {max_concurrent} concurrent calls...")

    # 创建进度条
    pbar = tqdm(total=len(case_prompts), desc="Processing cases", unit="case")

    # 创建任务
    tasks = [
        process_single_case(uuid, prompt, api_key, base_url, output_dir, semaphore, pbar)
        for uuid, prompt in case_prompts.items()
    ]

    # 执行所有任务
    results = await asyncio.gather(*tasks)

    pbar.close()

    # Merge results into a single JSONL file
    jsonl_file = Path(output_dir) / "knowledge_base.jsonl"
    print(f"Merging results into {jsonl_file}...")
    
    success_count = 0
    with open(jsonl_file, 'w', encoding='utf-8') as f:
        for res in results:
            if res['status'] == 'success' and res['entry']:
                # Ensure it's written as a single line
                f.write(json.dumps(res['entry'], ensure_ascii=False) + '\n')
                success_count += 1
    
    print(f"Merged {success_count} valid entries into JSONL.")

    return {r['uuid']: r for r in results}


def main():
    parser = argparse.ArgumentParser(
        description='Call LLM API to generate knowledge base entries'
    )
    parser.add_argument(
        '--prompts-dir',
        default='knowledge_base_prompts',
        help='Directory containing prompt files'
    )
    parser.add_argument(
        '--output-dir',
        default='knowledge_base_data',
        help='Directory to save generated entries'
    )
    parser.add_argument(
        '--split-file',
        default='output/splits/seen_train_uuids.txt',
        help='Use specific split file (default: seen_train_uuids.txt)'
    )
    parser.add_argument(
        '--cases',
        nargs='+',
        help='Specific case UUIDs to process'
    )
    parser.add_argument(
        '--api-key',
        help='DeepSeek API key'
    )
    parser.add_argument(
        '--base-url',
        help='API base URL'
    )
    parser.add_argument(
        '--max-concurrent',
        type=int,
        default=10,
        help='Maximum concurrent API calls'
    )
    parser.add_argument(
        '--retry-failed',
        action='store_true',
        help='Retry failed cases'
    )
    parser.add_argument(
        '--max-retries',
        type=int,
        default=2,
        help='Maximum retry attempts'
    )

    args = parser.parse_args()

    print("="*80)
    print("Knowledge Base Entry Generator")
    print("="*80)
    print()

    # 确定要处理的cases
    if args.cases:
        uuids = args.cases
        print(f"Processing {len(uuids)} specified cases")
    elif args.split_file:
        uuids = load_split_uuids(args.split_file)
        print(f"Loaded {len(uuids)} cases from split file: {args.split_file}")
    else:
        # 处理所有prompt文件
        prompts_path = Path(args.prompts_dir)
        if not prompts_path.exists():
            print(f"Error: Prompts directory not found: {args.prompts_dir}")
            return

        prompt_files = list(prompts_path.glob("*.txt"))
        uuids = [f.stem for f in prompt_files]
        print(f"Found {len(uuids)} prompt files in {args.prompts_dir}")

    print()

    # 处理cases（支持重试）
    retry_count = 0
    all_results = {}
    current_uuids = uuids

    while retry_count <= args.max_retries:
        if retry_count > 0:
            print(f"\n{'='*80}")
            print(f"RETRY ATTEMPT {retry_count}/{args.max_retries}")
            print(f"{'='*80}\n")

        # 运行异步处理
        results = asyncio.run(process_all_cases(
            current_uuids,
            args.prompts_dir,
            args.api_key,
            args.base_url,
            args.output_dir,
            args.max_concurrent
        ))

        # 更新结果
        all_results.update(results)

        # 检查是否需要重试
        if args.retry_failed and retry_count < args.max_retries:
            failed_uuids = [
                uuid for uuid, result in results.items()
                if result['status'] in ['error', 'parse_error', 'exception']
            ]

            if failed_uuids:
                print(f"\n{len(failed_uuids)} cases failed, will retry...")
                current_uuids = failed_uuids
                retry_count += 1
                continue

        break

    # 统计结果
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)

    valid_count = sum(1 for r in all_results.values() if r['valid'])
    needs_review_count = sum(1 for r in all_results.values() if r['status'] == 'needs_review')
    error_count = sum(1 for r in all_results.values() if r['status'] in ['error', 'parse_error', 'exception'])

    print(f"\nTotal cases: {len(all_results)}")
    print(f"✓ Valid entries: {valid_count}")
    print(f"⚠ Needs review: {needs_review_count}")
    print(f"✗ Errors: {error_count}")

    if valid_count > 0:
        print(f"\nKnowledge base entries saved to: {Path(args.output_dir).absolute()}")

    # 显示需要关注的cases
    if needs_review_count > 0 or error_count > 0:
        print("\n" + "-"*80)
        print("CASES NEEDING ATTENTION")
        print("-"*80)

        for uuid, result in sorted(all_results.items()):
            if not result['valid']:
                print(f"\n{uuid}:")
                print(f"  Status: {result['status']}")
                if result['issues']:
                    print(f"  Issues:")
                    for issue in result['issues'][:5]:  # 只显示前5个问题
                        print(f"    - {issue}")

    # 保存验证报告
    report_file = Path(args.output_dir) / "validation_report.json"
    with open(report_file, 'w', encoding='utf-8') as f:
        # 移除response字段以减小文件大小
        compact_results = {
            uuid: {k: v for k, v in result.items() if k != 'response'}
            for uuid, result in all_results.items()
        }
        json.dump(compact_results, f, indent=2, ensure_ascii=False)

    print(f"\nValidation report saved to: {report_file}")

    # 保存合并的知识库文件
    valid_entries = [r['entry'] for r in all_results.values() if r['valid'] and r['entry']]
    if valid_entries:
        kb_file = Path(args.output_dir) / "knowledge_base.jsonl"
        with open(kb_file, 'w', encoding='utf-8') as f:
            for entry in valid_entries:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        print(f"Combined knowledge base saved to: {kb_file}")

    print("\nNext steps:")
    print("  1. Review cases marked as 'needs review'")
    print("  2. Check raw_responses/ for debugging failed cases")
    print("  3. Use knowledge_base.jsonl for downstream tasks")


if __name__ == '__main__':
    main()

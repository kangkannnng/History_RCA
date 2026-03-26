#!/usr/bin/env python3
"""
Test Pipeline: Generation -> Build -> Simulated Recall
Verify the effect of "Structured Reasoning" in actual retrieval
"""

import json
import os
import random
import shutil
import asyncio
from pathlib import Path
from typing import List, Dict
from dotenv import load_dotenv

# Load environment variables
load_dotenv(Path(__file__).parent.parent / "history_rca" / ".env")

# Import existing modules
import generate_prompt
import call_llm
import build_chromadb

# Configuration
TEST_SIZE = 3
TEST_DIR = Path("test_output")
GT_FILE = "output/splits/seen_train.jsonl"
LOGS_DIR = "logs"
API_KEY = os.getenv("OPENAI_API_KEY")
BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.huiyan-ai.cn/v1")

def setup_test_env():
    """Clean up and create test directory"""
    if TEST_DIR.exists():
        shutil.rmtree(TEST_DIR)
    TEST_DIR.mkdir()
    (TEST_DIR / "prompts").mkdir()
    (TEST_DIR / "kb_data").mkdir()
    (TEST_DIR / "chroma_db").mkdir()
    print(f"Initialized test directory: {TEST_DIR}")

def load_test_cases() -> List[Dict]:
    """Randomly select test cases"""
    cases = []
    with open(GT_FILE, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        # Select high-quality cases containing key_observations
        valid_lines = [l for l in lines if '"key_observations":' in l]
        selected_lines = random.sample(valid_lines, min(TEST_SIZE, len(valid_lines)))
        
        for line in selected_lines:
            cases.append(json.loads(line))
    
    print(f"Selected {len(cases)} test cases:")
    for case in cases:
        print(f"  - [{case['uuid']}] {case.get('fault_type', 'unknown')}")
    return cases

def step_1_generate_prompts(cases: List[Dict]):
    """Generate Prompts"""
    print("\n[Step 1] Generating Prompts with STRICT structure...")
    
    # Load historical results if available (optional)
    results = {} 
    
    for case in cases:
        uuid = case['uuid']
        full_log = generate_prompt.load_run_log(uuid, LOGS_DIR)
        
        prompt = generate_prompt.generate_prompt(
            uuid=uuid,
            groundtruth=case,
            past_result=None, # Ignore historical conclusion, force reconstruction using GT
            full_log=full_log
        )
        
        output_file = TEST_DIR / "prompts" / f"{uuid}.txt"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(prompt)
            
    print("Prompts generated.")

async def step_2_call_llm(cases: List[Dict]):
    """Call LLM to generate Knowledge Base Entries"""
    print("\n[Step 2] Calling LLM to extract Structured Knowledge...")
    
    uuids = [c['uuid'] for c in cases]
    prompts_dir = str(TEST_DIR / "prompts")
    output_dir = str(TEST_DIR / "kb_data")
    
    # Directly call the async process function
    await call_llm.process_all_cases(
        uuids=uuids,
        prompts_dir=prompts_dir,
        api_key=API_KEY, 
        base_url=BASE_URL,
        output_dir=output_dir,
        max_concurrent=5
    )
    
    # Merge into jsonl for ChromaDB
    jsonl_path = TEST_DIR / "knowledge_base.jsonl"
    with open(jsonl_path, 'w', encoding='utf-8') as outfile:
        for uuid in uuids:
            json_file = Path(output_dir) / f"{uuid}.json"
            if json_file.exists():
                try:
                    with open(json_file, 'r', encoding='utf-8') as infile:
                        # Read indented JSON
                        data = json.load(infile)
                        # Convert to single-line JSON and write
                        outfile.write(json.dumps(data, ensure_ascii=False) + '\n')
                except json.JSONDecodeError:
                    print(f"Error: Invalid JSON format in {json_file}")
            else:
                print(f"Warning: Failed to generate entry for {uuid}")

    print(f"Knowledge Base compiled at: {jsonl_path}")

def step_3_build_db():
    """Build ChromaDB"""
    print("\n[Step 3] Building Vector Database...")
    
    kb = build_chromadb.KnowledgeBaseDB(
        persist_directory=str(TEST_DIR / "chroma_db"),
        collection_name="test_kb",
        use_openai_embeddings=False # Use default embedding to simplify testing
    )
    
    stats = kb.build_from_jsonl(
        jsonl_file=str(TEST_DIR / "knowledge_base.jsonl"),
        overwrite=True
    )
    print(f"DB Build Stats: {stats}")
    return kb

def step_4_simulate_retrieval(kb, cases: List[Dict]):
    """
    Simulate Retrieval Test
    Assumption: Monitoring system/Small model has outputted key metrics or abnormal log keywords
    Verification: Can the corresponding knowledge base entry be retrieved at this time
    """
    print("\n[Step 4] Simulating Retrieval from Monitoring Inputs...")
    print("="*60)
    
    score = 0
    
    for case in cases:
        uuid = case['uuid']
        print(f"\nTarget Case: {uuid}")
        print(f"Ground Truth Fault: {case.get('fault_type')}")
        
        # Simulation 1: Only Metric Input (Metric Query)
        # E.g. Prometheus alert says: "pod_cpu_usage" abnormal
        metrics = case.get('key_metrics', [])
        metric_query = f"Issue with metrics: {', '.join(metrics)}"
        print(f"  > Query (Metric): '{metric_query}'")
        
        results_m = kb.retrieve(metric_query, n_results=1)
        if results_m and results_m[0]['uuid'] == uuid:
            print("    [SUCCESS] Metric Query retrieved correct document.")
            score += 0.5
        else:
            retrieved_id = results_m[0]['uuid'] if results_m else "None"
            print(f"    [FAIL] Retrieved {retrieved_id} instead.")

        # Simulation 2: Only Log Keyword Input (Log Query)
        # E.g. Log clustering algorithm outputted keywords
        observations = case.get('key_observations', [])
        keywords = []
        for obs in observations:
            keywords.extend(obs.get('keyword', []))
        
        # Simulate a mixed query
        log_query = f"Log contains keywords: {', '.join(keywords[:3])}" 
        print(f"  > Query (Log/Obs): '{log_query}'")
        
        results_l = kb.retrieve(log_query, n_results=1)
        if results_l and results_l[0]['uuid'] == uuid:
            print("    [SUCCESS] Log/Obs Query retrieved correct document.")
            score += 0.5
        else:
            retrieved_id = results_l[0]['uuid'] if results_l else "None"
            print(f"    [FAIL] Retrieved {retrieved_id} instead.")
            
    print("="*60)
    print(f"Final Recall Score: {score}/{len(cases)} ({score/len(cases)*100:.1f}%)")
    
    # Print one of the generated entries for manual inspection
    print("\n[Sample Generated Entry]")
    sample_file = list((TEST_DIR / "kb_data").glob("*.json"))[0]
    with open(sample_file, 'r', encoding='utf-8') as f:
        print(f.read())

if __name__ == "__main__":
    setup_test_env()
    cases = load_test_cases()
    step_1_generate_prompts(cases)
    asyncio.run(step_2_call_llm(cases))
    kb = step_3_build_db()
    step_4_simulate_retrieval(kb, cases)

#!/bin/bash
# Complete Knowledge Base Construction Workflow
# Uses improved prompt, default processing for seen_train dataset

set -e  # Exit immediately if a command exits with a non-zero status

echo "================================================================================"
echo "Knowledge Base Construction Workflow (Improved Version)"
echo "================================================================================"
echo ""

# Step 1: Generate Improved Prompts
echo "Step 1/4: Generating improved prompts (Default: seen_train dataset)"
echo "--------------------------------------------------------------------------------"
python generate_prompt.py \
  --output-dir knowledge_base_prompt

echo ""
echo "✓ Prompts generation completed"
echo ""

# Step 2: Call LLM to Generate Knowledge Base Entries
echo "Step 2/4: Calling LLM to generate knowledge base entries"
echo "--------------------------------------------------------------------------------"
python call_llm.py \
  --prompts-dir knowledge_base_prompt \
  --output-dir knowledge_base_data \
  --split-file output/splits/seen_train_uuids.txt \
  --max-concurrent 80

echo ""
echo "✓ Knowledge base entries generation completed (Merged to knowledge_base_data/knowledge_base.jsonl)"
echo ""

# Step 3: Validate Knowledge Base Quality
echo "Step 3/4: Validating knowledge base quality"
echo "--------------------------------------------------------------------------------"
python validate.py \
  --kb-file knowledge_base_data/knowledge_base.jsonl \
  --output knowledge_base_data/validation_report.json

echo ""
echo "✓ Validation completed"
echo ""

# Step 4: Build ChromaDB Vector Database
echo "Step 4/4: Building ChromaDB vector database"
echo "--------------------------------------------------------------------------------"
python build_chromadb.py \
  --action build \
  --jsonl-file knowledge_base_data/knowledge_base.jsonl \
  --db-path chroma_kb \
  --collection-name fault_diagnosis_kb

echo ""
echo "================================================================================"
echo "Workflow Completed!"
echo "================================================================================"
echo ""
echo "Output Files:"
echo "  - Prompts: knowledge_base_prompt/"
echo "  - Knowledge Base Entries: knowledge_base_data/"
echo "  - Validation Report: knowledge_base_data/validation_report.json"
echo "  - Vector Database: chroma_kb/"
echo ""

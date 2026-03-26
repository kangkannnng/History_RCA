#!/usr/bin/env python3
"""
Build ChromaDB Knowledge Base from Knowledge Base Entries
将知识库条目导入ChromaDB向量数据库
"""

import json
from pathlib import Path
from typing import List, Dict, Optional
import chromadb
from chromadb.config import Settings


class KnowledgeBaseDB:
    """ChromaDB-based Knowledge Base for fault diagnosis rules"""

    def __init__(
        self,
        persist_directory: str = "./chroma_kb",
        collection_name: str = "fault_diagnosis_kb",
        use_openai_embeddings: bool = False,
        openai_api_key: Optional[str] = None,
        openai_api_base: Optional[str] = None
    ):
        """
        Initialize ChromaDB client

        Args:
            persist_directory: Directory to persist the database
            collection_name: Name of the collection
            use_openai_embeddings: If True, use OpenAI embeddings
            openai_api_key: OpenAI API key
            openai_api_base: OpenAI API base URL
        """
        self.persist_directory = persist_directory
        self.collection_name = collection_name

        # Initialize ChromaDB client with persistence
        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )

        # Choose embedding function
        if use_openai_embeddings:
            import os
            api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OpenAI API key required when use_openai_embeddings=True")

            from chromadb.utils import embedding_functions
            self.embedding_function = embedding_functions.OpenAIEmbeddingFunction(
                api_key=api_key,
                model_name="text-embedding-3-small",
                api_base=openai_api_base
            )
        else:
            # Use default local embedding model
            self.embedding_function = None

        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"description": "Fault diagnosis knowledge base with expert reasoning"},
            embedding_function=self.embedding_function
        )

    def build_from_jsonl(
        self,
        jsonl_file: str,
        overwrite: bool = False
    ) -> Dict[str, int]:
        """
        Build knowledge base from knowledge_base.jsonl

        Args:
            jsonl_file: Path to knowledge_base.jsonl
            overwrite: If True, clear existing collection first

        Returns:
            Statistics dict with counts
        """
        if overwrite:
            self.client.delete_collection(self.collection_name)
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"description": "Fault diagnosis knowledge base with expert reasoning"},
                embedding_function=self.embedding_function
            )

        # Load entries
        entries = []
        with open(jsonl_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))

        documents = []
        metadatas = []
        ids = []

        added_count = 0
        error_count = 0

        for entry in entries:
            try:
                uuid = entry['uuid']
                expert_knowledge = entry['expert_knowledge']

                # Build document text for embedding
                # Combine symptom, root cause, and reasoning chain
                # Enhanced for Structured Reasoning: explicitly include critical checks
                
                reasoning_text = " ".join(expert_knowledge['reasoning_chain'])
                
                checks_text = []
                for check in expert_knowledge.get('critical_checks', []):
                    checks_text.append(f"Check {check.get('modality', 'Unknown')}: {check.get('instruction', '')}")
                
                doc_parts = [
                    f"Fault Type: {entry.get('fault_type', 'Unknown')}",
                    f"Symptom: {entry.get('symptom_vector', '')}",
                    f"Root Cause: {expert_knowledge.get('root_cause_desc', '')}",
                    f"Reasoning: {reasoning_text}",
                    "Actionable Checks:",
                    "\n".join(checks_text)
                ]
                document = "\n".join(doc_parts)

                # Build metadata
                metadata = {
                    'uuid': uuid,
                    'fault_type': entry['fault_type'],
                    'symptom_vector': entry['symptom_vector'],
                    'root_cause_desc': expert_knowledge['root_cause_desc'],
                    'num_reasoning_steps': len(expert_knowledge['reasoning_chain']),
                    'num_checks': len(expert_knowledge['critical_checks']),
                    # Store modalities used
                    'modalities': ','.join(set(check['modality'] for check in expert_knowledge['critical_checks']))
                }

                documents.append(document)
                metadatas.append(metadata)
                ids.append(uuid)
                added_count += 1

            except Exception as e:
                print(f"Error processing entry {entry.get('uuid', 'unknown')}: {e}")
                error_count += 1

        # Add to ChromaDB in batch
        if documents:
            self.collection.add(
                documents=documents,
                metadatas=metadatas,
                ids=ids
            )

        return {
            'added': added_count,
            'errors': error_count,
            'total': len(entries)
        }

    def retrieve(
        self,
        query: str,
        n_results: int = 3,
        filter_metadata: Optional[Dict] = None
    ) -> List[Dict]:
        """
        Retrieve similar knowledge base entries

        Args:
            query: Query text (symptom description, fault description, etc.)
            n_results: Number of results to return
            filter_metadata: Optional metadata filters (e.g., {'fault_type': 'cpu stress'})

        Returns:
            List of dicts with 'uuid', 'metadata', 'distance'
        """
        results = self.collection.query(
            query_texts=[query],
            n_results=n_results,
            where=filter_metadata
        )

        # Format results
        retrieved = []
        for i in range(len(results['ids'][0])):
            retrieved.append({
                'uuid': results['ids'][0][i],
                'document': results['documents'][0][i],
                'metadata': results['metadatas'][0][i],
                'distance': results['distances'][0][i] if 'distances' in results else None
            })

        return retrieved

    def get_by_uuid(self, uuid: str) -> Optional[Dict]:
        """
        Get a specific entry by UUID

        Args:
            uuid: Case UUID

        Returns:
            Entry dict or None if not found
        """
        try:
            result = self.collection.get(ids=[uuid])

            if result['ids']:
                return {
                    'uuid': result['ids'][0],
                    'document': result['documents'][0],
                    'metadata': result['metadatas'][0]
                }
            return None
        except Exception:
            return None

    def get_full_entry(self, uuid: str, jsonl_file: str) -> Optional[Dict]:
        """
        Get full entry with all details from original JSONL

        Args:
            uuid: Case UUID
            jsonl_file: Path to knowledge_base.jsonl

        Returns:
            Full entry dict or None if not found
        """
        with open(jsonl_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    entry = json.loads(line)
                    if entry['uuid'] == uuid:
                        return entry
        return None

    def get_stats(self) -> Dict:
        """Get knowledge base statistics"""
        count = self.collection.count()

        # Get all metadata to compute stats
        all_data = self.collection.get()

        fault_types = {}
        modalities = {}

        for metadata in all_data['metadatas']:
            ft = metadata.get('fault_type', 'unknown')
            fault_types[ft] = fault_types.get(ft, 0) + 1

            mods = metadata.get('modalities', '').split(',')
            for mod in mods:
                if mod:
                    modalities[mod] = modalities.get(mod, 0) + 1

        return {
            'total_entries': count,
            'fault_types': fault_types,
            'modalities': modalities
        }

    def reset(self):
        """Clear all data from the knowledge base"""
        self.client.delete_collection(self.collection_name)
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"description": "Fault diagnosis knowledge base with expert reasoning"},
            embedding_function=self.embedding_function
        )


def main():
    """Command-line interface"""
    import argparse

    parser = argparse.ArgumentParser(
        description='Build and query ChromaDB knowledge base'
    )
    parser.add_argument(
        '--action',
        choices=['build', 'query', 'stats', 'reset', 'get'],
        required=True,
        help='Action to perform'
    )
    parser.add_argument(
        '--jsonl-file',
        default='knowledge_base_data/knowledge_base.jsonl',
        help='Path to knowledge_base.jsonl file'
    )
    parser.add_argument(
        '--db-path',
        default='./chroma_kb',
        help='ChromaDB persistence directory'
    )
    parser.add_argument(
        '--collection-name',
        default='fault_diagnosis_kb',
        help='Collection name'
    )
    parser.add_argument(
        '--query',
        help='Query text for retrieval'
    )
    parser.add_argument(
        '--uuid',
        help='UUID for get action'
    )
    parser.add_argument(
        '--n-results',
        type=int,
        default=3,
        help='Number of results to retrieve'
    )
    parser.add_argument(
        '--overwrite',
        action='store_true',
        help='Overwrite existing database'
    )
    parser.add_argument(
        '--use-openai',
        action='store_true',
        help='Use OpenAI embeddings instead of local model'
    )
    parser.add_argument(
        '--openai-api-key',
        help='OpenAI API key'
    )
    parser.add_argument(
        '--openai-api-base',
        help='OpenAI API base URL'
    )

    args = parser.parse_args()

    kb = KnowledgeBaseDB(
        persist_directory=args.db_path,
        collection_name=args.collection_name,
        use_openai_embeddings=args.use_openai,
        openai_api_key=args.openai_api_key,
        openai_api_base=args.openai_api_base
    )

    if args.action == 'build':
        print(f"Building knowledge base from: {args.jsonl_file}")
        print(f"Database path: {args.db_path}")
        print(f"Overwrite: {args.overwrite}")
        print()

        stats = kb.build_from_jsonl(
            args.jsonl_file,
            overwrite=args.overwrite
        )

        print("\n" + "="*80)
        print("BUILD COMPLETE")
        print("="*80)
        print(f"✓ Added: {stats['added']}")
        print(f"✗ Errors: {stats['errors']}")
        print(f"Total entries: {stats['total']}")
        print(f"\nDatabase saved to: {args.db_path}")

    elif args.action == 'query':
        if not args.query:
            print("Error: --query required for query action")
            return

        print(f"Querying: {args.query}\n")
        results = kb.retrieve(args.query, n_results=args.n_results)

        if not results:
            print("No results found.")
            return

        for i, result in enumerate(results, 1):
            print(f"\n{'='*80}")
            print(f"Result {i}: {result['uuid']}")
            print(f"{'='*80}")
            print(f"Similarity: {1 - result['distance']:.2%}")
            print(f"Fault Type: {result['metadata'].get('fault_type')}")
            print()

            # Get full entry from JSONL
            full_entry = kb.get_full_entry(result['uuid'], args.jsonl_file)
            if full_entry:
                print(f"Symptom Vector:")
                print(f"  {full_entry['symptom_vector']}")
                print()

                print(f"Expert Knowledge:")
                print(f"  Root Cause: {full_entry['expert_knowledge']['root_cause_desc']}")
                print()

                print(f"  Reasoning Chain:")
                for j, step in enumerate(full_entry['expert_knowledge']['reasoning_chain'], 1):
                    print(f"    {j}. {step}")
                print()

                print(f"  Critical Checks ({len(full_entry['expert_knowledge']['critical_checks'])} checks):")
                for j, check in enumerate(full_entry['expert_knowledge']['critical_checks'], 1):
                    print(f"    Check {j} [{check['modality']}]:")
                    print(f"      Target: {check['target']}")
                    print(f"      Pattern: {check['expected_pattern']}")
                    print(f"      Instruction: {check['instruction']}")
                    print()
            else:
                print(f"Warning: Full entry not found in {args.jsonl_file}")
                print(f"Showing metadata only:")
                print(f"  Symptom: {result['metadata'].get('symptom_vector')}")
                print(f"  Root Cause: {result['metadata'].get('root_cause_desc')}")
                print(f"  Modalities: {result['metadata'].get('modalities')}")

    elif args.action == 'get':
        if not args.uuid:
            print("Error: --uuid required for get action")
            return

        # Get from ChromaDB
        result = kb.get_by_uuid(args.uuid)
        if not result:
            print(f"UUID {args.uuid} not found in database")
            return

        print(f"\n{'='*80}")
        print(f"Entry: {args.uuid}")
        print(f"{'='*80}")
        print(f"Fault Type: {result['metadata'].get('fault_type')}")
        print(f"Symptom: {result['metadata'].get('symptom_vector')}")
        print(f"Root Cause: {result['metadata'].get('root_cause_desc')}")
        print(f"Reasoning Steps: {result['metadata'].get('num_reasoning_steps')}")
        print(f"Critical Checks: {result['metadata'].get('num_checks')}")
        print(f"Modalities: {result['metadata'].get('modalities')}")

        # Get full entry from JSONL
        full_entry = kb.get_full_entry(args.uuid, args.jsonl_file)
        if full_entry:
            print(f"\nFull Entry:")
            print(json.dumps(full_entry, indent=2, ensure_ascii=False))

    elif args.action == 'stats':
        stats = kb.get_stats()
        print("\n" + "="*80)
        print("KNOWLEDGE BASE STATISTICS")
        print("="*80)
        print(f"\nTotal entries: {stats['total_entries']}")

        print(f"\nFault Types:")
        for ft, count in sorted(stats['fault_types'].items(), key=lambda x: -x[1]):
            print(f"  {ft}: {count}")

        print(f"\nModalities:")
        for mod, count in sorted(stats['modalities'].items(), key=lambda x: -x[1]):
            print(f"  {mod}: {count}")

    elif args.action == 'reset':
        confirm = input("Are you sure you want to reset the knowledge base? (yes/no): ")
        if confirm.lower() == 'yes':
            kb.reset()
            print("✓ Knowledge base reset successfully")
        else:
            print("Reset cancelled")


if __name__ == '__main__':
    main()

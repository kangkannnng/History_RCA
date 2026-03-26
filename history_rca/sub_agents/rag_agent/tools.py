#!/usr/bin/env python3
"""
Knowledge Base using ChromaDB for fault diagnosis rules

This module provides:
1. Build knowledge base from expert knowledge entries
2. Retrieve similar cases based on query
3. Tool interface for agent integration
"""
import os
import json
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
                doc_parts = [
                    f"Symptom: {entry['symptom_vector']}",
                    f"Root Cause: {expert_knowledge['root_cause_desc']}",
                    "Reasoning: " + " ".join(expert_knowledge['reasoning_chain'])
                ]

                # Format Critical Checks if available
                if 'critical_checks' in expert_knowledge and expert_knowledge['critical_checks']:
                    checks_str = ["Critical Checks:"]
                    for check in expert_knowledge['critical_checks']:
                        # Skip if check format is invalid
                        if not isinstance(check, dict): continue
                        
                        modality = check.get('modality', 'Unknown')
                        target = check.get('target', 'N/A')
                        instruction = check.get('instruction', '')
                        expected = check.get('expected_pattern', '')
                        
                        check_line = f"- [{modality}] Check '{target}': {instruction}"
                        if expected:
                            check_line += f" (Expected: {expected})"
                        checks_str.append(check_line)
                    
                    doc_parts.append("\n".join(checks_str))

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


# Tool interface for agent integration
def rag_analysis_tool(query: str) -> dict:
    """
    Tool interface for retrieving similar historical cases from knowledge base

    This function is exposed to agents for querying the fault diagnosis knowledge base.

    Args:
        query: Symptom description or fault description (free text)

    Returns:
        Dictionary containing:
        - status: "success" or "error"
        - message: Status message
        - results: List of retrieved results from ChromaDB
    """
    try:
        # Get paths from environment
        PROJECT_DIR = os.getenv('PROJECT_DIR', '.')
        kb_path = os.path.join(PROJECT_DIR, 'chroma_kb')

        # Initialize knowledge base
        kb = KnowledgeBaseDB(persist_directory=kb_path)

        # Retrieve similar cases
        results = kb.retrieve(query, n_results=3)

        if not results:
            return {
                "status": "success",
                "message": "No similar cases found in knowledge base",
                "results": []
            }

        return {
            "status": "success",
            "message": f"Found {len(results)} similar cases",
            "results": results
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Error querying knowledge base: {str(e)}",
            "results": []
        }
#!/usr/bin/env python3
"""
Reasoning Policy Knowledge Base using ChromaDB

This module provides:
1. Build knowledge base from reasoning policies
2. Retrieve similar policies based on query
3. Tool interface for agent integration
"""
import os
import json
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import chromadb
from chromadb.config import Settings
from google.adk.tools.tool_context import ToolContext

class ReasoningPolicyKB:
    """Knowledge Base for historical reasoning policies"""

    def __init__(
        self,
        persist_directory: str = "./chroma_db",
        use_openai_embeddings: bool = False,
        openai_api_key: Optional[str] = None,
        openai_api_base: Optional[str] = None
    ):
        """
        Initialize ChromaDB client

        Args:
            persist_directory: Directory to persist the database
            use_openai_embeddings: If True, use OpenAI embeddings instead of local model
            openai_api_key: OpenAI API key (or set OPENAI_API_KEY env var)
            openai_api_base: OpenAI API base URL (for custom endpoints)
        """
        self.persist_directory = persist_directory

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
            name="reasoning_policies",
            metadata={"description": "Historical RCA reasoning trajectories"},
            embedding_function=self.embedding_function
        )

    def build_from_policies(
        self,
        policies_dir: str,
        gt_file: str,
        overwrite: bool = False
    ) -> Dict[str, int]:
        """
        Build knowledge base from reasoning policy files

        Args:
            policies_dir: Directory containing policy files
            gt_file: Ground truth JSONL file for metadata
            overwrite: If True, clear existing collection first

        Returns:
            Statistics dict with counts
        """
        if overwrite:
            self.client.delete_collection("reasoning_policies")
            self.collection = self.client.get_or_create_collection(
                name="reasoning_policies",
                metadata={"description": "Historical RCA reasoning trajectories"},
                embedding_function=self.embedding_function
            )

        # Load ground truth for metadata
        gt_data = {}
        with open(gt_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    case = json.loads(line)
                    gt_data[case['uuid']] = case

        # Process policy files
        policies_path = Path(policies_dir)
        policy_files = list(policies_path.glob("*_policy.txt"))

        documents = []
        metadatas = []
        ids = []

        added_count = 0
        discard_count = 0
        error_count = 0

        for policy_file in policy_files:
            uuid = policy_file.stem.replace('_policy', '')

            # Read policy content
            policy_content = policy_file.read_text(encoding='utf-8')

            # Skip DISCARD cases
            if policy_content.strip().startswith('[Decision: DISCARD]'):
                discard_count += 1
                continue

            # Skip error cases
            if policy_content.startswith('ERROR:'):
                error_count += 1
                continue

            # Parse policy sections
            sections = self._parse_policy(policy_content)

            # Skip if missing critical sections
            if not sections.get('trigger') or not sections.get('conclusion'):
                error_count += 1
                continue

            # Get metadata from GT
            gt = gt_data.get(uuid, {})

            # Prepare metadata
            metadata = {
                'uuid': uuid,
                'service': gt.get('service', 'unknown'),
                'fault_type': gt.get('fault_type', 'unknown'),
                'fault_category': gt.get('fault_category', 'unknown'),
                # Store section lengths for filtering
                'has_trigger': bool(sections.get('trigger')),
                'has_reasoning': bool(sections.get('reasoning')),
                'has_conclusion': bool(sections.get('conclusion')),
            }

            # Add to batch
            documents.append(policy_content)
            metadatas.append(metadata)
            ids.append(uuid)
            added_count += 1

        # Add to ChromaDB in batch
        if documents:
            self.collection.add(
                documents=documents,
                metadatas=metadatas,
                ids=ids
            )

        return {
            'added': added_count,
            'discarded': discard_count,
            'errors': error_count,
            'total': len(policy_files)
        }

    def _parse_policy(self, policy_content: str) -> Dict[str, str]:
        """Parse policy content into sections"""
        sections = {}
        current_section = None
        current_content = []

        for line in policy_content.split('\n'):
            if line.startswith('[') and line.endswith(']'):
                # Save previous section
                if current_section:
                    sections[current_section] = '\n'.join(current_content).strip()

                # Start new section
                section_name = line[1:-1].lower().replace(' ', '_')
                current_section = section_name
                current_content = []
            else:
                current_content.append(line)

        # Save last section
        if current_section:
            sections[current_section] = '\n'.join(current_content).strip()

        return sections

    def retrieve(
        self,
        query: str,
        n_results: int = 5,
        filter_metadata: Optional[Dict] = None
    ) -> List[Dict]:
        """
        Retrieve similar reasoning policies

        Args:
            query: Query text (can be anomaly description, symptoms, etc.)
            n_results: Number of results to return
            filter_metadata: Optional metadata filters (e.g., {'fault_type': 'network delay'})

        Returns:
            List of dicts with 'uuid', 'policy', 'metadata', 'distance'
        """
        # Query ChromaDB
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
                'policy': results['documents'][0][i],
                'metadata': results['metadatas'][0][i],
                'distance': results['distances'][0][i] if 'distances' in results else None
            })

        return retrieved

    def retrieve_by_symptoms(
        self,
        symptoms: Dict[str, List[str]],
        n_results: int = 5
    ) -> List[Dict]:
        """
        Retrieve policies based on symptom description

        Args:
            symptoms: Dict with keys like 'logs', 'metrics', 'traces'
                     Example: {
                         'logs': ['connection refused', 'timeout'],
                         'metrics': ['high CPU', 'memory spike'],
                         'traces': ['latency increase']
                     }
            n_results: Number of results to return

        Returns:
            List of similar policies
        """
        # Build query from symptoms
        query_parts = []

        if symptoms.get('logs'):
            query_parts.append("Log anomalies: " + ", ".join(symptoms['logs']))

        if symptoms.get('metrics'):
            query_parts.append("Metric anomalies: " + ", ".join(symptoms['metrics']))

        if symptoms.get('traces'):
            query_parts.append("Trace anomalies: " + ", ".join(symptoms['traces']))

        query = ". ".join(query_parts)

        return self.retrieve(query, n_results)

    def get_by_uuid(self, uuid: str) -> Optional[Dict]:
        """
        Get a specific policy by UUID

        Args:
            uuid: Case UUID

        Returns:
            Policy dict or None if not found
        """
        try:
            result = self.collection.get(ids=[uuid])

            if result['ids']:
                return {
                    'uuid': result['ids'][0],
                    'policy': result['documents'][0],
                    'metadata': result['metadatas'][0]
                }
            return None
        except Exception:
            return None

    def get_stats(self) -> Dict:
        """Get knowledge base statistics"""
        count = self.collection.count()

        # Get all metadata to compute stats
        all_data = self.collection.get()

        fault_types = {}
        services = {}

        for metadata in all_data['metadatas']:
            ft = metadata.get('fault_type', 'unknown')
            fault_types[ft] = fault_types.get(ft, 0) + 1

            svc = metadata.get('service', 'unknown')
            services[svc] = services.get(svc, 0) + 1

        return {
            'total_policies': count,
            'fault_types': fault_types,
            'services': services
        }

    def reset(self):
        """Clear all data from the knowledge base"""
        self.client.delete_collection("reasoning_policies")
        self.collection = self.client.get_or_create_collection(
            name="reasoning_policies",
            metadata={"description": "Historical RCA reasoning trajectories"},
            embedding_function=self.embedding_function
        )


# Tool interface for agent integration
def _retrieve_similar_cases_tool(
    symptoms: str,
    n_results: int = 3,
    kb_path: str = "./chroma_db"
) -> str:
    """
    Tool function for agent to retrieve similar historical cases

    Args:
        symptoms: Description of current symptoms (free text)
        n_results: Number of similar cases to retrieve
        kb_path: Path to ChromaDB database

    Returns:
        Formatted string with retrieved cases
    """
    kb = ReasoningPolicyKB(persist_directory=kb_path)

    results = kb.retrieve(symptoms, n_results=n_results)

    if not results:
        return "No similar cases found in knowledge base."

    output = f"Found {len(results)} similar historical cases:\n\n"

    for i, result in enumerate(results, 1):
        output += f"--- Case {i}: {result['uuid']} ---\n"
        output += f"Service: {result['metadata'].get('service', 'unknown')}\n"
        output += f"Similarity: {1 - result['distance']:.2%}\n\n"

        # Extract key sections
        policy = result['policy']
        sections = {}
        current_section = None
        current_content = []

        for line in policy.split('\n'):
            if line.startswith('[') and line.endswith(']'):
                if current_section:
                    sections[current_section] = '\n'.join(current_content).strip()
                current_section = line[1:-1]
                current_content = []
            else:
                current_content.append(line)

        if current_section:
            sections[current_section] = '\n'.join(current_content).strip()

        # Show key sections
        if 'Trigger' in sections:
            output += f"Trigger:\n{sections['Trigger'][:300]}...\n\n"

        if 'Conclusion' in sections:
            output += f"Conclusion:\n{sections['Conclusion']}\n\n"

        output += "-" * 60 + "\n\n"

    return output


def rag_analysis_tool(query: str) -> dict:
    """
    Tool interface for retrieving similar historical cases

    Args:
        query: Symptom description
    
    Returns:
        Results with retrieved cases
    """
    PROJECT_DIR = os.getenv('PROJECT_DIR', '.')
    kb_path = os.path.join(PROJECT_DIR, 'chroma_db')
    results = _retrieve_similar_cases_tool(
        symptoms=query,
        n_results=3,
        kb_path=kb_path
    )

    return results
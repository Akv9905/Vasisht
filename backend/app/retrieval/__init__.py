"""Retrieval package (P7 & P8).

Structured retrieval, local semantic retrieval, and combined retrieval.
"""

from app.retrieval.combined import CombinedRetrievalResult, CombinedRetriever
from app.retrieval.embeddings import (
    DeterministicEmbeddingProvider,
    EmbeddingProvider,
    NoOpEmbeddingProvider,
    cosine_similarity,
    get_embedding_provider,
)
from app.retrieval.indexer import IndexingSummary, index_analysis_run
from app.retrieval.semantic import SemanticRetriever, SemanticSearchResult
from app.retrieval.structured import (
    FlowStep,
    RetrievedCallerCallee,
    RetrievedClass,
    RetrievedDatabaseReference,
    RetrievedEndpoint,
    RetrievedFile,
    RetrievedMethod,
    RetrievedPackage,
    SourceLocation,
    StructuredFlowRetrievalResult,
    StructuredRetriever,
)

__all__ = [
    # Structured Retrieval (P7)
    "FlowStep",
    "RetrievedCallerCallee",
    "RetrievedClass",
    "RetrievedDatabaseReference",
    "RetrievedEndpoint",
    "RetrievedFile",
    "RetrievedMethod",
    "RetrievedPackage",
    "SourceLocation",
    "StructuredFlowRetrievalResult",
    "StructuredRetriever",
    # Embeddings (P8)
    "EmbeddingProvider",
    "NoOpEmbeddingProvider",
    "DeterministicEmbeddingProvider",
    "get_embedding_provider",
    "cosine_similarity",
    # Indexer (P8)
    "IndexingSummary",
    "index_analysis_run",
    # Semantic Retrieval (P8)
    "SemanticSearchResult",
    "SemanticRetriever",
    # Combined Retrieval (P8)
    "CombinedRetrievalResult",
    "CombinedRetriever",
]

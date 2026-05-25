"""
Document embedding generation for vector search.

For Gemini embeddings (EMBEDDING_PROVIDER=gemini) this module calls Google's
native REST API directly instead of the OpenAI-compatible endpoint, because
text-embedding-004 is not available through the /v1beta/openai/embeddings path.

For any other provider it falls back to the OpenAI-compatible client.
"""

import os
import asyncio
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

import httpx
from openai import RateLimitError, APIError
from dotenv import load_dotenv

from .chunker import DocumentChunk

# Import flexible providers
try:
    from ..agent.providers import get_embedding_client, get_embedding_model, get_embedding_provider
except ImportError:
    import sys
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from agent.providers import get_embedding_client, get_embedding_model, get_embedding_provider

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

# Initialize client and model name from environment
embedding_client = get_embedding_client()
EMBEDDING_MODEL = get_embedding_model()
EMBEDDING_PROVIDER = get_embedding_provider()

# Gemini native REST endpoint base (not the OpenAI-compat one)
_GEMINI_EMBED_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class EmbeddingGenerator:
    """Generates embeddings for document chunks."""

    def __init__(
        self,
        model: str = EMBEDDING_MODEL,
        batch_size: int = 100,
        max_retries: int = 3,
        retry_delay: float = 1.0
    ):
        self.model = model
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        # Dimensions and max input length per model.
        # For Gemini models we request 768 dims via outputDimensionality to match the DB schema.
        self.model_configs = {
            "gemini-embedding-001":        {"dimensions": 768,  "max_tokens": 2048, "output_dimensionality": 768},
            "gemini-embedding-2":          {"dimensions": 768,  "max_tokens": 2048, "output_dimensionality": 768},
            "gemini-embedding-2-preview":  {"dimensions": 768,  "max_tokens": 2048, "output_dimensionality": 768},
            "text-embedding-3-small":      {"dimensions": 1536, "max_tokens": 8191},
            "text-embedding-3-large":      {"dimensions": 3072, "max_tokens": 8191},
            "text-embedding-ada-002":      {"dimensions": 1536, "max_tokens": 8191},
        }

        self.config = self.model_configs.get(model, {"dimensions": 768, "max_tokens": 2048})
        if model not in self.model_configs:
            logger.warning(f"Unknown embedding model '{model}', assuming 768-dim output")

        # API key used only for direct Gemini calls
        self._gemini_api_key = os.getenv("EMBEDDING_API_KEY", "")

    # ------------------------------------------------------------------
    # Internal helpers: Gemini native REST API
    # ------------------------------------------------------------------

    async def _gemini_embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Call Gemini batchEmbedContents endpoint directly.

        Gemini's OpenAI-compat /embeddings path does not support the new embedding
        models, so we use the native REST API instead. We set outputDimensionality=768
        to match the pgvector schema (vector(768)).
        """
        out_dims = self.config.get("output_dimensionality")
        url = f"{_GEMINI_EMBED_BASE}/{self.model}:batchEmbedContents"
        request_item = {"model": f"models/{self.model}", "content": {"parts": [{"text": ""}]}}
        if out_dims:
            request_item["outputDimensionality"] = out_dims

        payload = {
            "requests": [
                {**request_item, "content": {"parts": [{"text": t}]}}
                for t in texts
            ]
        }
        params = {"key": self._gemini_api_key}

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=payload, params=params)
            response.raise_for_status()
            data = response.json()

        # Response shape: {"embeddings": [{"values": [...]}, ...]}
        return [item["values"] for item in data["embeddings"]]

    async def _gemini_embed_single(self, text: str) -> List[float]:
        """Call Gemini embedContent endpoint for a single text."""
        out_dims = self.config.get("output_dimensionality")
        url = f"{_GEMINI_EMBED_BASE}/{self.model}:embedContent"
        payload = {
            "model": f"models/{self.model}",
            "content": {"parts": [{"text": text}]}
        }
        if out_dims:
            payload["outputDimensionality"] = out_dims
        params = {"key": self._gemini_api_key}

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=payload, params=params)
            response.raise_for_status()
            data = response.json()

        return data["embedding"]["values"]

    # ------------------------------------------------------------------
    # Public API (same interface regardless of provider)
    # ------------------------------------------------------------------

    @staticmethod
    def _is_rate_limit(exc: Exception) -> bool:
        """Return True when exc is a 429 Too Many Requests response."""
        if isinstance(exc, RateLimitError):
            return True
        if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429:
            return True
        return False

    async def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for a single text."""
        max_chars = self.config["max_tokens"] * 4
        if len(text) > max_chars:
            text = text[:max_chars]

        for attempt in range(self.max_retries):
            try:
                if EMBEDDING_PROVIDER == "gemini":
                    return await self._gemini_embed_single(text)

                response = await embedding_client.embeddings.create(
                    model=self.model, input=text
                )
                return response.data[0].embedding

            except Exception as e:
                if attempt == self.max_retries - 1:
                    raise
                if self._is_rate_limit(e):
                    # 429: wait long enough for the per-minute window to reset
                    delay = 30.0 * (attempt + 1)
                    logger.warning(f"Rate limit hit, waiting {delay}s before retry {attempt + 1}")
                else:
                    logger.error(f"Embedding API error: {e}")
                    delay = self.retry_delay * (2 ** attempt)
                await asyncio.sleep(delay)

    async def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a batch of texts."""
        max_chars = self.config["max_tokens"] * 4
        processed = []
        for text in texts:
            if not text or not text.strip():
                processed.append(" ")  # Gemini rejects empty strings; single space is fine
                continue
            processed.append(text[:max_chars] if len(text) > max_chars else text)

        for attempt in range(self.max_retries):
            try:
                if EMBEDDING_PROVIDER == "gemini":
                    return await self._gemini_embed_batch(processed)

                response = await embedding_client.embeddings.create(
                    model=self.model, input=processed
                )
                return [d.embedding for d in response.data]

            except Exception as e:
                is_rate_limit = self._is_rate_limit(e)
                if attempt == self.max_retries - 1:
                    if is_rate_limit:
                        # Last retry after rate limit — fall back to individual with spacing
                        logger.warning("Batch rate limited after all retries, switching to individual mode")
                        return await self._process_individually(processed)
                    logger.error(f"Embedding API error in batch: {e}")
                    return await self._process_individually(processed)
                if is_rate_limit:
                    delay = 30.0 * (attempt + 1)
                    logger.warning(f"Batch rate limited, waiting {delay}s before retry {attempt + 1}")
                else:
                    logger.error(f"Embedding API error in batch: {e}")
                    delay = self.retry_delay * (2 ** attempt)
                await asyncio.sleep(delay)
    
    async def _process_individually(
        self,
        texts: List[str]
    ) -> List[List[float]]:
        """
        Process texts individually as fallback.
        
        Args:
            texts: List of texts to embed
        
        Returns:
            List of embedding vectors
        """
        embeddings = []
        
        for text in texts:
            try:
                if not text or not text.strip():
                    embeddings.append([0.0] * self.config["dimensions"])
                    continue
                
                embedding = await self.generate_embedding(text)
                embeddings.append(embedding)
                # 0.7s between calls → ~85 req/min, safely below the 100 RPM free-tier limit
                await asyncio.sleep(0.7)
                
            except Exception as e:
                logger.error(f"Failed to embed text: {e}")
                # Use zero vector as fallback
                embeddings.append([0.0] * self.config["dimensions"])
        
        return embeddings
    
    async def embed_chunks(
        self,
        chunks: List[DocumentChunk],
        progress_callback: Optional[callable] = None
    ) -> List[DocumentChunk]:
        """
        Generate embeddings for document chunks.
        
        Args:
            chunks: List of document chunks
            progress_callback: Optional callback for progress updates
        
        Returns:
            Chunks with embeddings added
        """
        if not chunks:
            return chunks
        
        logger.info(f"Generating embeddings for {len(chunks)} chunks")
        
        # Process chunks in batches
        embedded_chunks = []
        total_batches = (len(chunks) + self.batch_size - 1) // self.batch_size
        
        for i in range(0, len(chunks), self.batch_size):
            batch_chunks = chunks[i:i + self.batch_size]
            batch_texts = [chunk.content for chunk in batch_chunks]
            
            try:
                # Generate embeddings for this batch
                embeddings = await self.generate_embeddings_batch(batch_texts)
                
                # Add embeddings to chunks
                for chunk, embedding in zip(batch_chunks, embeddings):
                    # Create a new chunk with embedding
                    embedded_chunk = DocumentChunk(
                        content=chunk.content,
                        index=chunk.index,
                        start_char=chunk.start_char,
                        end_char=chunk.end_char,
                        metadata={
                            **chunk.metadata,
                            "embedding_model": self.model,
                            "embedding_generated_at": datetime.now().isoformat()
                        },
                        token_count=chunk.token_count
                    )
                    
                    # Add embedding as a separate attribute
                    embedded_chunk.embedding = embedding
                    embedded_chunks.append(embedded_chunk)
                
                # Progress update
                current_batch = (i // self.batch_size) + 1
                if progress_callback:
                    progress_callback(current_batch, total_batches)
                
                logger.info(f"Processed batch {current_batch}/{total_batches}")
                
            except Exception as e:
                logger.error(f"Failed to process batch {i//self.batch_size + 1}: {e}")
                
                # Add chunks without embeddings as fallback
                for chunk in batch_chunks:
                    chunk.metadata.update({
                        "embedding_error": str(e),
                        "embedding_generated_at": datetime.now().isoformat()
                    })
                    chunk.embedding = [0.0] * self.config["dimensions"]
                    embedded_chunks.append(chunk)
        
        logger.info(f"Generated embeddings for {len(embedded_chunks)} chunks")
        return embedded_chunks
    
    async def embed_query(self, query: str) -> List[float]:
        """
        Generate embedding for a search query.
        
        Args:
            query: Search query
        
        Returns:
            Query embedding
        """
        return await self.generate_embedding(query)
    
    def get_embedding_dimension(self) -> int:
        """Get the dimension of embeddings for this model."""
        return self.config["dimensions"]


# Cache for embeddings
class EmbeddingCache:
    """Simple in-memory cache for embeddings."""
    
    def __init__(self, max_size: int = 1000):
        """Initialize cache."""
        self.cache: Dict[str, List[float]] = {}
        self.access_times: Dict[str, datetime] = {}
        self.max_size = max_size
    
    def get(self, text: str) -> Optional[List[float]]:
        """Get embedding from cache."""
        text_hash = self._hash_text(text)
        if text_hash in self.cache:
            self.access_times[text_hash] = datetime.now()
            return self.cache[text_hash]
        return None
    
    def put(self, text: str, embedding: List[float]):
        """Store embedding in cache."""
        text_hash = self._hash_text(text)
        
        # Evict oldest entries if cache is full
        if len(self.cache) >= self.max_size:
            oldest_key = min(self.access_times.keys(), key=lambda k: self.access_times[k])
            del self.cache[oldest_key]
            del self.access_times[oldest_key]
        
        self.cache[text_hash] = embedding
        self.access_times[text_hash] = datetime.now()
    
    def _hash_text(self, text: str) -> str:
        """Generate hash for text."""
        import hashlib
        return hashlib.md5(text.encode()).hexdigest()


# Factory function
def create_embedder(
    model: str = EMBEDDING_MODEL,
    use_cache: bool = True,
    **kwargs
) -> EmbeddingGenerator:
    """
    Create embedding generator with optional caching.
    
    Args:
        model: Embedding model to use
        use_cache: Whether to use caching
        **kwargs: Additional arguments for EmbeddingGenerator
    
    Returns:
        EmbeddingGenerator instance
    """
    embedder = EmbeddingGenerator(model=model, **kwargs)
    
    if use_cache:
        # Add caching capability
        cache = EmbeddingCache()
        original_generate = embedder.generate_embedding
        
        async def cached_generate(text: str) -> List[float]:
            cached = cache.get(text)
            if cached is not None:
                return cached
            
            embedding = await original_generate(text)
            cache.put(text, embedding)
            return embedding
        
        embedder.generate_embedding = cached_generate
    
    return embedder


# Example usage
async def main():
    """Example usage of the embedder."""
    from .chunker import ChunkingConfig, create_chunker
    
    # Create chunker and embedder
    config = ChunkingConfig(chunk_size=200, use_semantic_splitting=False)
    chunker = create_chunker(config)
    embedder = create_embedder()
    
    sample_text = """
    Google's AI initiatives include advanced language models, computer vision,
    and machine learning research. The company has invested heavily in
    transformer architectures and neural network optimization.
    
    Microsoft's partnership with OpenAI has led to integration of GPT models
    into various products and services, making AI accessible to enterprise
    customers through Azure cloud services.
    """
    
    # Chunk the document
    chunks = chunker.chunk_document(
        content=sample_text,
        title="AI Initiatives",
        source="example.md"
    )
    
    print(f"Created {len(chunks)} chunks")
    
    # Generate embeddings
    def progress_callback(current, total):
        print(f"Processing batch {current}/{total}")
    
    embedded_chunks = await embedder.embed_chunks(chunks, progress_callback)
    
    for i, chunk in enumerate(embedded_chunks):
        print(f"Chunk {i}: {len(chunk.content)} chars, embedding dim: {len(chunk.embedding)}")
    
    # Test query embedding
    query_embedding = await embedder.embed_query("Google AI research")
    print(f"Query embedding dimension: {len(query_embedding)}")


if __name__ == "__main__":
    asyncio.run(main())
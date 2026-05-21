"""
Document embedding generation for vector search.
Adapted for scientific paper ingestion (PubMed / PDF articles).

Relevance tagging uses a configurable keyword dictionary grouped by concept.
You can add terms manually at the bottom of this file, or run the
suggest_new_terms() helper after ingesting new PDFs to surface candidate
terms found in your actual documents.
"""

import os
import asyncio
import logging
import re
from typing import List, Dict, Any, Optional, Set
from datetime import datetime
import json
from collections import Counter

from openai import RateLimitError, APIError
from dotenv import load_dotenv

from .chunker import DocumentChunk

# Import flexible providers
try:
    from ..agent.providers import get_embedding_client, get_embedding_model
except ImportError:
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from agent.providers import get_embedding_client, get_embedding_model

load_dotenv()
logger = logging.getLogger(__name__)

embedding_client = get_embedding_client()
EMBEDDING_MODEL = get_embedding_model()


# =============================================================================
# RELEVANCE KEYWORD DICTIONARY
# =============================================================================
#
# This is the main place you edit when you encounter new terminology in your
# PDFs.  Each key is a concept label that becomes a metadata flag on every
# chunk (e.g. "serum_free" → chunk.metadata["tag_serum_free"] = True/False).
#
# Rules:
#   - All terms are matched case-insensitively against chunk text.
#   - Partial matches count: "serum-free" matches "serum-free medium".
#   - Add a term to a group by appending it to the list.
#   - Add a whole new concept group by adding a new key + list.
#
# Where do new terms come from?
#   - You spot them while reading a new PDF → add manually here.
#   - Run suggest_new_terms() after ingestion → it prints candidates for you
#     to review and paste in.
#
# MeSH note: MeSH preferred terms are marked with [MeSH] in comments where
# known, but we also include the free-text variants authors actually use.
# =============================================================================

RELEVANCE_KEYWORDS: Dict[str, List[str]] = {

    # --- Serum-free conditions -------------------------------------------
    # MeSH: "Culture Media, Serum-Free"
    "serum_free": [
        "serum-free",
        "serum free",
        "without serum",
        "no serum",
        "absence of serum",
        "serum-free conditions",
        "serum-free culture",
        "serum withdrawal",
        "serum-free medium",
        "serum-free media",
    ],

    # --- Xeno-free / animal-component-free --------------------------------
    # MeSH: no single preferred term; often "animal component-free"
    "xeno_free": [
        "xeno-free",
        "xeno free",
        "xenofree",
        "animal-free",
        "animal component-free",
        "animal component free",
        "animal-derived component-free",
        "free of animal",
        "no animal-derived",
        "animal-product-free",
        "humanized medium",
    ],

    # --- Chemically / fully defined media ---------------------------------
    # MeSH: "Culture Media" + adjective "defined"
    "defined_medium": [
        "defined medium",
        "defined media",
        "chemically defined",
        "cdm",                          # common abbreviation
        "fully defined",
        "protein-free defined",
        "serum-free defined",
        "chemically defined medium",
        "chemically defined media",
        "synthetic medium",
        "fully chemically defined",
    ],

    # --- FBS / FCS presence (articles that USE it — useful as negative) ---
    # MeSH: "Serum"
    "uses_fbs": [
        "fbs",
        "fetal bovine serum",
        "foetal bovine serum",          # British spelling
        "fcs",
        "fetal calf serum",
        "foetal calf serum",
        "bovine serum",
        "calf serum",
        "newborn calf serum",
        "ncs",
    ],

    # --- Specific commercial serum-free / defined media products ----------
    # Add new product names here as you encounter them in your PDFs.
    "commercial_defined_media": [
        "stemmaCS",                     # Miltenyi Biotec
        "mscgm-cd",                     # Lonza
        "stempro msc",                  # Gibco / Thermo
        "mesencult-xf",                 # STEMCELL Technologies
        "nutristem",                    # Biological Industries
        "pluriton",
        "e8 medium",                    # Essential 8, Thermo
        "essential 8",
        "tesar medium",
        "b8 medium",
        "knock-out serum replacement",
        "kosr",
        "knockout serum replacement",
        "n2 supplement",
        "b27 supplement",
        "b-27",
        "n-2",
        "albumax",
    ],

    # --- Cell types commonly cultured in defined media --------------------
    # Helps you later filter "which cell type was this method used for?"
    "cell_type_stem": [
        "mesenchymal stem cell",
        "msc",
        "induced pluripotent",
        "ipsc",
        "ips cell",
        "embryonic stem cell",
        "esc",
        "hematopoietic stem",
        "neural stem",
        "adipose-derived stem",
        "bone marrow-derived",
        "stromal cell",
    ],

    # --- General culture media mention ------------------------------------
    # Broad flag — useful to filter out chunks with no media content at all
    "mentions_media": [
        "medium",
        "media",
        "dmem",
        "rpmi",
        "mem ",
        "f-12",
        "f12",
        "imdm",
        "alpha-mem",
        "mccoy",
        "l-15",
        "ham's",
        "leibovitz",
        "williams e",
        "cell culture",
        "culture condition",
    ],
}


# =============================================================================
# OPTIONAL: terms to ignore even if they match above
# (e.g. "medium" in "medium-sized" — add false-positive phrases here)
# =============================================================================
IGNORE_PHRASES: List[str] = [
    "medium-sized",
    "medium term",
    "medium risk",
    "medium throughput",   # not a culture medium
]


def _clean_text(text: str) -> str:
    """Lowercase and collapse whitespace for reliable matching."""
    return " ".join(text.lower().split())


def tag_chunk(chunk_text: str, keywords: Dict[str, List[str]] = RELEVANCE_KEYWORDS) -> Dict[str, bool]:
    """
    Scan chunk text against the keyword dictionary and return boolean flags.

    One flag per concept group, prefixed with "tag_" so they are easy to
    identify in the metadata dict (e.g. "tag_serum_free", "tag_xeno_free").

    Args:
        chunk_text: Raw text of the chunk
        keywords:   Keyword dictionary to use (defaults to RELEVANCE_KEYWORDS)

    Returns:
        Dict of "tag_<concept>": bool
    """
    cleaned = _clean_text(chunk_text)

    # Remove ignore phrases before matching
    for phrase in IGNORE_PHRASES:
        cleaned = cleaned.replace(phrase.lower(), "")

    flags: Dict[str, bool] = {}
    for concept, terms in keywords.items():
        flags[f"tag_{concept}"] = any(term.lower() in cleaned for term in terms)

    return flags


# =============================================================================
# TERM SUGGESTION HELPER
# =============================================================================
# Run this after ingesting a batch of new PDFs to surface candidate terms
# you might want to add to RELEVANCE_KEYWORDS.
#
# Usage (from your project root):
#   from ingestion.embedder import suggest_new_terms
#   suggest_new_terms(your_list_of_chunk_texts, top_n=40)
#
# It prints multi-word phrases that appear frequently but are NOT yet in
# RELEVANCE_KEYWORDS — review the list and paste useful ones above.
# =============================================================================

def suggest_new_terms(
    chunk_texts: List[str],
    top_n: int = 30,
    min_count: int = 3,
    ngram_range: tuple = (2, 4)
) -> List[str]:
    """
    Scan a list of chunk texts and suggest frequent phrases not already
    covered by RELEVANCE_KEYWORDS.  Returns a ranked list of candidates
    for you to review.

    Args:
        chunk_texts:  List of raw chunk text strings (from your ingested docs)
        top_n:        How many candidates to return
        min_count:    Minimum times a phrase must appear to be suggested
        ngram_range:  Min and max word-count for candidate phrases

    Returns:
        List of candidate phrase strings, printed and returned
    """
    # Flatten all existing keywords into a set for fast lookup
    existing: Set[str] = set()
    for terms in RELEVANCE_KEYWORDS.values():
        for t in terms:
            existing.add(t.lower())

    # Extract n-grams from all chunk texts
    phrase_counts: Counter = Counter()

    for text in chunk_texts:
        cleaned = _clean_text(text)
        words = cleaned.split()
        for n in range(ngram_range[0], ngram_range[1] + 1):
            for i in range(len(words) - n + 1):
                phrase = " ".join(words[i:i + n])
                # Only keep phrases that look biological / methodological
                # (contain at least one alpha word, skip pure numbers)
                if re.search(r'[a-z]{3,}', phrase):
                    phrase_counts[phrase] += 1

    # Filter: frequent enough AND not already covered
    candidates = [
        phrase for phrase, count in phrase_counts.most_common(top_n * 5)
        if count >= min_count and phrase not in existing
    ][:top_n]

    if candidates:
        print("\n=== Suggested terms to review for RELEVANCE_KEYWORDS ===")
        for i, phrase in enumerate(candidates, 1):
            print(f"  {i:2d}.  \"{phrase}\"  (seen {phrase_counts[phrase]}x)")
        print("\nReview the list above and paste useful ones into RELEVANCE_KEYWORDS in embedder.py")
    else:
        print("No new candidate terms found above the frequency threshold.")

    return candidates


# =============================================================================
# EmbeddingGenerator
# =============================================================================

class EmbeddingGenerator:
    """Generates embeddings for document chunks."""

    def __init__(
        self,
        model: str = EMBEDDING_MODEL,
        batch_size: int = 100,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        extra_keywords: Optional[Dict[str, List[str]]] = None
    ):
        """
        Initialize embedding generator.

        Args:
            model:          Embedding model to use
            batch_size:     Number of texts to process in parallel
            max_retries:    Maximum number of retry attempts
            retry_delay:    Delay between retries in seconds
            extra_keywords: Optional extra keyword groups to merge into
                            RELEVANCE_KEYWORDS at runtime (useful for
                            per-run customisation without editing this file)
        """
        self.model = model
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        # Merge any runtime keyword additions with the file-level dictionary
        self.keywords = dict(RELEVANCE_KEYWORDS)
        if extra_keywords:
            for concept, terms in extra_keywords.items():
                if concept in self.keywords:
                    # Extend existing concept with new terms
                    self.keywords[concept] = list(set(self.keywords[concept] + terms))
                else:
                    # Brand-new concept group
                    self.keywords[concept] = terms

        self.model_configs = {
            "text-embedding-3-small": {"dimensions": 1536, "max_tokens": 8191},
            "text-embedding-3-large": {"dimensions": 3072, "max_tokens": 8191},
            "text-embedding-ada-002":  {"dimensions": 1536, "max_tokens": 8191},
        }

        if model not in self.model_configs:
            logger.warning(f"Unknown model {model}, using default config")
            self.config = {"dimensions": 1536, "max_tokens": 8191}
        else:
            self.config = self.model_configs[model]

    async def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for a single text."""
        if len(text) > self.config["max_tokens"] * 4:
            text = text[:self.config["max_tokens"] * 4]

        for attempt in range(self.max_retries):
            try:
                response = await embedding_client.embeddings.create(
                    model=self.model,
                    input=text
                )
                return response.data[0].embedding

            except RateLimitError:
                if attempt == self.max_retries - 1:
                    raise
                delay = self.retry_delay * (2 ** attempt)
                logger.warning(f"Rate limit hit, retrying in {delay}s")
                await asyncio.sleep(delay)

            except APIError as e:
                logger.error(f"OpenAI API error: {e}")
                if attempt == self.max_retries - 1:
                    raise
                await asyncio.sleep(self.retry_delay)

            except Exception as e:
                logger.error(f"Unexpected error generating embedding: {e}")
                if attempt == self.max_retries - 1:
                    raise
                await asyncio.sleep(self.retry_delay)

    async def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a batch of texts."""
        processed_texts = []
        for text in texts:
            if not text or not text.strip():
                processed_texts.append("")
                continue
            if len(text) > self.config["max_tokens"] * 4:
                text = text[:self.config["max_tokens"] * 4]
            processed_texts.append(text)

        for attempt in range(self.max_retries):
            try:
                response = await embedding_client.embeddings.create(
                    model=self.model,
                    input=processed_texts
                )
                return [data.embedding for data in response.data]

            except RateLimitError:
                if attempt == self.max_retries - 1:
                    raise
                delay = self.retry_delay * (2 ** attempt)
                logger.warning(f"Rate limit hit, retrying batch in {delay}s")
                await asyncio.sleep(delay)

            except APIError as e:
                logger.error(f"OpenAI API error in batch: {e}")
                if attempt == self.max_retries - 1:
                    return await self._process_individually(processed_texts)
                await asyncio.sleep(self.retry_delay)

            except Exception as e:
                logger.error(f"Unexpected error in batch embedding: {e}")
                if attempt == self.max_retries - 1:
                    return await self._process_individually(processed_texts)
                await asyncio.sleep(self.retry_delay)

    async def _process_individually(self, texts: List[str]) -> List[List[float]]:
        """Process texts individually as fallback when batch call fails."""
        embeddings = []
        for text in texts:
            try:
                if not text or not text.strip():
                    embeddings.append([0.0] * self.config["dimensions"])
                    continue
                embedding = await self.generate_embedding(text)
                embeddings.append(embedding)
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"Failed to embed text: {e}")
                embeddings.append([0.0] * self.config["dimensions"])
        return embeddings

    async def embed_chunks(
        self,
        chunks: List[DocumentChunk],
        progress_callback: Optional[callable] = None
    ) -> List[DocumentChunk]:
        """
        Generate embeddings for document chunks.
        Each chunk also receives relevance tags from RELEVANCE_KEYWORDS.

        Args:
            chunks:            List of document chunks
            progress_callback: Optional callback for progress updates

        Returns:
            Chunks with embeddings and relevance tags in metadata
        """
        if not chunks:
            return chunks

        logger.info(f"Generating embeddings for {len(chunks)} chunks")

        embedded_chunks = []
        total_batches = (len(chunks) + self.batch_size - 1) // self.batch_size

        for i in range(0, len(chunks), self.batch_size):
            batch_chunks = chunks[i:i + self.batch_size]
            batch_texts = [chunk.content for chunk in batch_chunks]

            try:
                embeddings = await self.generate_embeddings_batch(batch_texts)

                for chunk, embedding in zip(batch_chunks, embeddings):
                    embedded_chunk = DocumentChunk(
                        content=chunk.content,
                        index=chunk.index,
                        start_char=chunk.start_char,
                        end_char=chunk.end_char,
                        metadata={
                            **chunk.metadata,
                            **tag_chunk(chunk.content, self.keywords),  # relevance flags
                            "embedding_model": self.model,
                            "embedding_generated_at": datetime.now().isoformat()
                        },
                        token_count=chunk.token_count
                    )
                    embedded_chunk.embedding = embedding
                    embedded_chunks.append(embedded_chunk)

                current_batch = (i // self.batch_size) + 1
                if progress_callback:
                    progress_callback(current_batch, total_batches)
                logger.info(f"Processed batch {current_batch}/{total_batches}")

            except Exception as e:
                logger.error(f"Failed to process batch {i//self.batch_size + 1}: {e}")
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
        """Generate embedding for a search query."""
        return await self.generate_embedding(query)

    def get_embedding_dimension(self) -> int:
        """Get the dimension of embeddings for this model."""
        return self.config["dimensions"]


# =============================================================================
# EmbeddingCache — unchanged
# =============================================================================

class EmbeddingCache:
    """Simple in-memory cache for embeddings."""

    def __init__(self, max_size: int = 1000):
        self.cache: Dict[str, List[float]] = {}
        self.access_times: Dict[str, datetime] = {}
        self.max_size = max_size

    def get(self, text: str) -> Optional[List[float]]:
        text_hash = self._hash_text(text)
        if text_hash in self.cache:
            self.access_times[text_hash] = datetime.now()
            return self.cache[text_hash]
        return None

    def put(self, text: str, embedding: List[float]):
        text_hash = self._hash_text(text)
        if len(self.cache) >= self.max_size:
            oldest_key = min(self.access_times.keys(), key=lambda k: self.access_times[k])
            del self.cache[oldest_key]
            del self.access_times[oldest_key]
        self.cache[text_hash] = embedding
        self.access_times[text_hash] = datetime.now()

    def _hash_text(self, text: str) -> str:
        import hashlib
        return hashlib.md5(text.encode()).hexdigest()


# =============================================================================
# Factory function
# =============================================================================

def create_embedder(
    model: str = EMBEDDING_MODEL,
    use_cache: bool = True,
    extra_keywords: Optional[Dict[str, List[str]]] = None,
    **kwargs
) -> EmbeddingGenerator:
    """
    Create embedding generator with optional caching and extra keywords.

    Args:
        model:          Embedding model to use
        use_cache:      Whether to use embedding cache
        extra_keywords: Additional keyword groups to add at runtime.
                        Example:
                          extra_keywords={
                              "serum_free": ["platelet lysate"],   # extend existing group
                              "my_new_concept": ["term1", "term2"] # new group
                          }
        **kwargs: Additional arguments for EmbeddingGenerator

    Returns:
        EmbeddingGenerator instance
    """
    embedder = EmbeddingGenerator(model=model, extra_keywords=extra_keywords, **kwargs)

    if use_cache:
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


# =============================================================================
# Smoke-test  (python embedder.py)
# =============================================================================

async def main():
    """Quick smoke-test — replace sample_text with a real PDF excerpt."""
    from .chunker import ChunkingConfig, create_chunker

    config = ChunkingConfig(chunk_size=300, use_semantic_splitting=False)
    chunker = create_chunker(config)
    embedder = create_embedder()

    sample_text = """
    Cell Culture
    Human adipose-derived stem cells (hASCs) were cultured in StemMACS
    MSC Expansion Media XF (Miltenyi Biotec), a xeno-free, serum-free,
    chemically defined medium. No fetal bovine serum (FBS) or animal-derived
    components were used. Cultures were maintained at 37 degrees C, 5% CO2.

    Passaging
    At 80% confluency cells were detached using TrypLE Express (Gibco) and
    replated at 5000 cells/cm2 in fresh defined medium.
    """

    chunks = chunker.chunk_document(
        content=sample_text,
        title="Xeno-Free hASC Culture",
        source="test_article.pdf"
    )

    print(f"Created {len(chunks)} chunks\n")

    embedded_chunks = await embedder.embed_chunks(chunks)

    for i, chunk in enumerate(embedded_chunks):
        print(f"Chunk {i}  |  dim: {len(chunk.embedding)}")
        for key, val in chunk.metadata.items():
            if key.startswith("tag_"):
                print(f"  {key}: {val}")

    # --- demonstrate suggest_new_terms ---
    all_texts = [c.content for c in embedded_chunks]
    suggest_new_terms(all_texts, top_n=10, min_count=1)


if __name__ == "__main__":
    asyncio.run(main())
"""
Main ingestion script for processing documents into vector DB and knowledge graph.
"""

import os
import asyncio
import inspect
import logging
import json
import glob
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import argparse

import asyncpg
from dotenv import load_dotenv

from .chunker import ChunkingConfig, create_chunker, DocumentChunk
from .embedder import create_embedder
from .graph_builder import GraphBuilder
# PDF parser: converts PDF files to structured text with section detection
from .pdf_parser import parse_pdf, ParsedPaper

# Import agent utilities
try:
    from ..agent.db_utils import initialize_database, close_database, db_pool
    from ..agent.models import IngestionConfig, IngestionResult
except ImportError:
    # For direct execution or testing
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from agent.db_utils import initialize_database, close_database, db_pool
    from agent.models import IngestionConfig, IngestionResult

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


class DocumentIngestionPipeline:
    """Pipeline for ingesting documents into vector DB and knowledge graph."""
    
    def __init__(
        self,
        config: IngestionConfig,
        documents_folder: str = "documents",
        clean_before_ingest: bool = False
    ):
        """
        Initialize ingestion pipeline.
        
        Args:
            config: Ingestion configuration
            documents_folder: Folder containing markdown documents
            clean_before_ingest: Whether to clean existing data before ingestion
        """
        self.config = config
        self.documents_folder = documents_folder
        self.clean_before_ingest = clean_before_ingest
        
        # Initialize components
        self.chunker_config = ChunkingConfig(
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap,
            max_chunk_size=config.max_chunk_size,
            use_semantic_splitting=config.use_semantic_chunking
        )
        
        self.chunker = create_chunker(self.chunker_config)
        self.embedder = create_embedder()
        self.graph_builder: Optional[GraphBuilder] = None
        self._initialized = False

    async def initialize(self):
        """Initialize the PostgreSQL database connection."""
        if self._initialized:
            return
        logger.info("Initializing ingestion pipeline...")
        await initialize_database()

        if self.config.use_knowledge_graph:
            neo4j_uri = os.getenv("NEO4J_URI")
            neo4j_password = os.getenv("NEO4J_PASSWORD")
            if not neo4j_uri or not neo4j_password:
                logger.warning(
                    "NEO4J_URI or NEO4J_PASSWORD not set in .env — "
                    "skipping knowledge graph. Add them or use --no-graph to suppress this warning."
                )
            else:
                try:
                    self.graph_builder = GraphBuilder()
                    await self.graph_builder.initialize()
                    logger.info("Knowledge graph initialized")
                except Exception as e:
                    logger.warning(f"Knowledge graph unavailable, graph building will be skipped: {e}")
                    self.graph_builder = None

        self._initialized = True
        logger.info("Ingestion pipeline initialized")

    async def close(self):
        """Close the database connection and knowledge graph client."""
        if self._initialized:
            await close_database()
            if self.graph_builder is not None:
                await self.graph_builder.close()
                self.graph_builder = None
            self._initialized = False
    
    async def ingest_documents(
        self,
        progress_callback: Optional[callable] = None
    ) -> List[IngestionResult]:
        """
        Ingest all documents from the documents folder.
        
        Args:
            progress_callback: Optional callback for progress updates
        
        Returns:
            List of ingestion results
        """
        if not self._initialized:
            await self.initialize()
        
        # Clean existing data if requested
        if self.clean_before_ingest:
            await self._clean_databases()

        # Find all supported documents (PDFs + markdown/text)
        document_files = self._find_document_files()

        if not document_files:
            logger.warning(f"No documents found in {self.documents_folder}")
            return []

        # Log a breakdown of file types found
        pdf_count = sum(1 for f in document_files if f.lower().endswith(".pdf"))
        md_count = len(document_files) - pdf_count
        logger.info(f"Found {len(document_files)} documents: {pdf_count} PDF(s), {md_count} text/markdown")

        results = []

        for i, file_path in enumerate(document_files):
            try:
                logger.info(f"Processing file {i+1}/{len(document_files)}: {file_path}")
                
                result = await self._ingest_single_document(file_path)
                results.append(result)
                
                if progress_callback:
                    progress_callback(i + 1, len(document_files))
                
            except Exception as e:
                logger.error(f"Failed to process {file_path}: {e}")
                results.append(IngestionResult(
                    document_id="",
                    title=os.path.basename(file_path),
                    chunks_created=0,
                    entities_extracted=0,
                    processing_time_ms=0,
                    errors=[str(e)]
                ))
        
        # Log summary
        total_chunks = sum(r.chunks_created for r in results)
        total_errors = sum(len(r.errors) for r in results)
        
        logger.info(f"Ingestion complete: {len(results)} documents, {total_chunks} chunks, {total_errors} errors")
        
        return results
    
    async def _ingest_single_document(self, file_path: str) -> IngestionResult:
        """
        Ingest one document — PDF or plain text/markdown.

        For PDFs:
            - Parse with PyMuPDF via pdf_parser.parse_pdf()
            - Detect IMRaD sections (Abstract, Methods, Results, etc.)
            - Chunk each section independently so chunks never span section boundaries
            - Store DOI, year, and detected sections in metadata

        For markdown / text files:
            - Read as plain text
            - Chunk with the standard chunker (semantic or simple)

        Args:
            file_path: Path to the document file

        Returns:
            IngestionResult with counts of chunks, entities, and any errors
        """
        start_time = datetime.now()
        document_source = os.path.relpath(file_path, self.documents_folder)

        # ---- Branch: PDF vs plain text ----
        is_pdf = file_path.lower().endswith(".pdf")

        if is_pdf:
            # PDF path: structured parsing with section detection
            parsed_paper = self._read_pdf_document(file_path)
            document_content = parsed_paper.full_text
            document_title = parsed_paper.title

            # Merge paper-level metadata (DOI, year, etc.) into base metadata
            document_metadata = {
                **parsed_paper.metadata,
                "ingestion_date": datetime.now().isoformat(),
                "file_size": len(document_content),
                "word_count": len(document_content.split()),
                "line_count": document_content.count("\n"),
                "document_type": "pdf",
            }
            # Add DOI and year as top-level fields for easy filtering later
            if parsed_paper.doi:
                document_metadata["doi"] = parsed_paper.doi
            if parsed_paper.year:
                document_metadata["year"] = parsed_paper.year
        else:
            # Plain text / markdown path
            document_content = self._read_document(file_path)
            document_title = self._extract_title(document_content, file_path)
            document_metadata = self._extract_document_metadata(document_content, file_path)
            document_metadata["document_type"] = "text"
            parsed_paper = None  # No section data for text files

        logger.info(f"Processing document: {document_title}")

        # ---- Chunking ----
        if is_pdf and parsed_paper and parsed_paper.sections:
            # Section-aware chunking: each chunk stays within its section
            logger.info(
                f"Using section-aware chunking for PDF "
                f"(sections: {[s.name for s in parsed_paper.sections]})"
            )
            chunks = await self.chunker.chunk_document_sections(
                sections=parsed_paper.sections,
                title=document_title,
                source=document_source,
                metadata=document_metadata,
            )
        else:
            # Standard chunking for text files (or PDFs with no detected sections)
            result = self.chunker.chunk_document(
                content=document_content,
                title=document_title,
                source=document_source,
                metadata=document_metadata,
            )
            chunks = await result if inspect.isawaitable(result) else result
        
        if not chunks:
            logger.warning(f"No chunks created for {document_title}")
            return IngestionResult(
                document_id="",
                title=document_title,
                chunks_created=0,
                entities_extracted=0,
                episodes_created=0,
                processing_time_ms=(datetime.now() - start_time).total_seconds() * 1000,
                errors=["No chunks created"]
            )
        
        logger.info(f"Created {len(chunks)} chunks")
        
        # Generate embeddings
        embedded_chunks = await self.embedder.embed_chunks(chunks)
        logger.info(f"Generated embeddings for {len(embedded_chunks)} chunks")

        # Annotate chunks with biomedical entities before saving and graph building
        entities_extracted = 0
        graph_chunks = embedded_chunks
        if self.config.extract_entities and self.graph_builder is not None:
            try:
                graph_chunks = await self.graph_builder.extract_entities_from_chunks(embedded_chunks)
                entities_extracted = sum(
                    sum(len(v) for v in chunk.metadata.get("entities", {}).values())
                    for chunk in graph_chunks
                )
                logger.info(f"Extracted {entities_extracted} entity mentions across {len(graph_chunks)} chunks")
            except Exception as e:
                logger.warning(f"Entity extraction failed, proceeding without entities: {e}")
                graph_chunks = embedded_chunks

        # Save to PostgreSQL
        document_id = await self._save_to_postgres(
            document_title,
            document_source,
            document_content,
            graph_chunks,
            document_metadata
        )

        logger.info(f"Saved document to PostgreSQL with ID: {document_id}")

        # Build knowledge graph episodes from the enriched chunks
        episodes_created = 0
        if self.graph_builder is not None:
            try:
                graph_result = await self.graph_builder.add_document_to_graph(
                    chunks=graph_chunks,
                    document_title=document_title,
                    document_source=document_source,
                    document_metadata=document_metadata,
                )
                episodes_created = graph_result.get("episodes_created", 0)
                graph_errors = graph_result.get("errors", [])
                logger.info(f"Added {episodes_created} episodes to knowledge graph")
                if graph_errors:
                    logger.warning(f"Graph building had {len(graph_errors)} errors: {graph_errors}")
            except Exception as e:
                logger.error(f"Graph building failed for {document_title}: {e}")

        processing_time = (datetime.now() - start_time).total_seconds() * 1000

        return IngestionResult(
            document_id=document_id,
            title=document_title,
            chunks_created=len(chunks),
            entities_extracted=entities_extracted,
            episodes_created=episodes_created,
            processing_time_ms=processing_time,
            errors=[]
        )
    
    def _find_document_files(self) -> List[str]:
        """
        Find all supported documents in the documents folder.

        Supported formats:
        - .pdf  — scientific papers (parsed with section detection)
        - .md / .markdown / .txt — plain text / markdown documents
        """
        if not os.path.exists(self.documents_folder):
            logger.error(f"Documents folder not found: {self.documents_folder}")
            return []

        patterns = ["*.pdf", "*.md", "*.markdown", "*.txt"]
        files = []

        for pattern in patterns:
            files.extend(
                glob.glob(os.path.join(self.documents_folder, "**", pattern), recursive=True)
            )

        return sorted(files)
    
    def _read_document(self, file_path: str) -> str:
        """Read plain-text document content from a markdown or text file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except UnicodeDecodeError:
            with open(file_path, 'r', encoding='latin-1') as f:
                return f.read()

    def _read_pdf_document(self, file_path: str) -> ParsedPaper:
        """
        Parse a PDF file into a structured ParsedPaper object.

        Uses pdf_parser.parse_pdf() which extracts text via PyMuPDF and
        detects IMRaD sections (Abstract, Introduction, Methods, Results,
        Discussion, Conclusion, References).

        Args:
            file_path: Path to the PDF file

        Returns:
            ParsedPaper with full_text, sections, title, DOI, year, etc.
        """
        logger.info(f"Reading PDF: {os.path.basename(file_path)}")
        return parse_pdf(file_path)
    
    def _extract_title(self, content: str, file_path: str) -> str:
        """Extract title from document content or filename."""
        # Try to find markdown title
        lines = content.split('\n')
        for line in lines[:10]:  # Check first 10 lines
            line = line.strip()
            if line.startswith('# '):
                return line[2:].strip()
        
        # Fallback to filename
        return os.path.splitext(os.path.basename(file_path))[0]
    
    def _extract_document_metadata(self, content: str, file_path: str) -> Dict[str, Any]:
        """Extract metadata from document content."""
        metadata = {
            "file_path": file_path,
            "file_size": len(content),
            "ingestion_date": datetime.now().isoformat()
        }
        
        # Try to extract YAML frontmatter
        if content.startswith('---'):
            try:
                import yaml
                end_marker = content.find('\n---\n', 4)
                if end_marker != -1:
                    frontmatter = content[4:end_marker]
                    yaml_metadata = yaml.safe_load(frontmatter)
                    if isinstance(yaml_metadata, dict):
                        metadata.update(yaml_metadata)
            except ImportError:
                logger.warning("PyYAML not installed, skipping frontmatter extraction")
            except Exception as e:
                logger.warning(f"Failed to parse frontmatter: {e}")
        
        # Extract some basic metadata from content
        lines = content.split('\n')
        metadata['line_count'] = len(lines)
        metadata['word_count'] = len(content.split())
        
        return metadata
    
    async def _save_to_postgres(
        self,
        title: str,
        source: str,
        content: str,
        chunks: List[DocumentChunk],
        metadata: Dict[str, Any]
    ) -> str:
        """Save document and chunks to PostgreSQL."""
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                # Insert document
                document_result = await conn.fetchrow(
                    """
                    INSERT INTO documents (title, source, content, metadata)
                    VALUES ($1, $2, $3, $4)
                    RETURNING id::text
                    """,
                    title,
                    source,
                    content,
                    json.dumps(metadata)
                )
                
                document_id = document_result["id"]
                
                # Insert chunks
                for chunk in chunks:
                    # Convert embedding to PostgreSQL vector string format
                    embedding_data = None
                    if hasattr(chunk, 'embedding') and chunk.embedding:
                        # PostgreSQL vector format: '[1.0,2.0,3.0]' (no spaces after commas)
                        embedding_data = '[' + ','.join(map(str, chunk.embedding)) + ']'
                    
                    await conn.execute(
                        """
                        INSERT INTO chunks (document_id, content, embedding, chunk_index, metadata, token_count)
                        VALUES ($1::uuid, $2, $3::vector, $4, $5, $6)
                        """,
                        document_id,
                        chunk.content,
                        embedding_data,
                        chunk.index,
                        json.dumps(chunk.metadata),
                        chunk.token_count
                    )
                
                return document_id
    
    async def _clean_databases(self):
        """Clean existing data from databases."""
        logger.warning("Cleaning existing data from databases...")
        
        # Clean PostgreSQL
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("DELETE FROM messages")
                await conn.execute("DELETE FROM sessions")
                await conn.execute("DELETE FROM chunks")
                await conn.execute("DELETE FROM documents")
        
        logger.info("Cleaned PostgreSQL database")


async def main():
    """Main function for running ingestion."""
    parser = argparse.ArgumentParser(description="Ingest PDF/markdown documents into the vector database")
    parser.add_argument("--documents", "-d", default="documents", help="Documents folder path")
    parser.add_argument("--clean", "-c", action="store_true", help="Clean existing data before ingestion")
    parser.add_argument("--chunk-size", type=int, default=1000, help="Chunk size for splitting documents")
    parser.add_argument("--chunk-overlap", type=int, default=200, help="Chunk overlap size")
    parser.add_argument("--semantic", action="store_true", help="Enable LLM-based semantic chunking (slower, hits rate limits on free tier)")
    parser.add_argument("--no-graph", action="store_true", help="Skip knowledge graph building (useful if Neo4j is not running)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    config = IngestionConfig(
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
        use_semantic_chunking=args.semantic,
        use_knowledge_graph=not args.no_graph,
    )
    
    # Create and run pipeline
    pipeline = DocumentIngestionPipeline(
        config=config,
        documents_folder=args.documents,
        clean_before_ingest=args.clean
    )
    
    def progress_callback(current: int, total: int):
        print(f"Progress: {current}/{total} documents processed")
    
    try:
        start_time = datetime.now()
        
        results = await pipeline.ingest_documents(progress_callback)
        
        end_time = datetime.now()
        total_time = (end_time - start_time).total_seconds()
        
        # Print summary
        print("\n" + "="*50)
        print("INGESTION SUMMARY")
        print("="*50)
        print(f"Documents processed: {len(results)}")
        print(f"Total chunks created: {sum(r.chunks_created for r in results)}")
        print(f"Total graph episodes: {sum(r.episodes_created for r in results)}")
        print(f"Total errors: {sum(len(r.errors) for r in results)}")
        print(f"Total processing time: {total_time:.2f} seconds")
        print()
        
        # Print individual results
        for result in results:
            status = "OK" if not result.errors else "FAIL"
            print(f"{status} {result.title}: {result.chunks_created} chunks, {result.episodes_created} graph episodes")
            
            if result.errors:
                for error in result.errors:
                    print(f"  Error: {error}")
        
    except KeyboardInterrupt:
        print("\nIngestion interrupted by user")
    except Exception as e:
        logger.error(f"Ingestion failed: {e}")
        raise
    finally:
        await pipeline.close()


if __name__ == "__main__":
    asyncio.run(main())
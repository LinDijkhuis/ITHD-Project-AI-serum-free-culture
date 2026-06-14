"""
Knowledge graph builder for extracting biomedical entities and relationships
from cell culture research papers.
"""

import logging
import re
import asyncio
import traceback
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from dotenv import load_dotenv

from .chunker import DocumentChunk

try:
    from ..agent.graph_utils import GraphitiClient
except ImportError:
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from agent.graph_utils import GraphitiClient

load_dotenv()

logger = logging.getLogger(__name__)


class GraphBuilder:
    """Builds a knowledge graph from cell culture research paper chunks."""

    def __init__(self):
        self.graph_client = GraphitiClient()
        self._initialized = False

    async def initialize(self):
        if not self._initialized:
            await self.graph_client.initialize()
            self._initialized = True

    async def close(self):
        if self._initialized:
            await self.graph_client.close()
            self._initialized = False

    async def add_document_to_graph(
        self,
        chunks: List[DocumentChunk],
        document_title: str,
        document_source: str,
        document_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Add document chunks to the knowledge graph one by one.

        Returns:
            Dict with episodes_created, total_chunks, and errors.
        """
        if not self._initialized:
            await self.initialize()

        if not chunks:
            return {"episodes_created": 0, "errors": []}

        logger.info(f"Adding {len(chunks)} chunks to knowledge graph: {document_title}")

        oversized = [i for i, c in enumerate(chunks) if len(c.content) > 6000]
        if oversized:
            logger.warning(f"{len(oversized)} chunks exceed 6000 chars and will be truncated: {oversized}")

        episodes_created = 0
        errors = []

        for i, chunk in enumerate(chunks):
            try:
                episode_id = f"{document_source}_{chunk.index}_{datetime.now().timestamp()}"
                episode_content = self._prepare_episode_content(chunk, document_title)

                await self.graph_client.add_episode(
                    episode_id=episode_id,
                    content=episode_content,
                    source=f"Document: {document_title} (Chunk: {chunk.index})",
                    timestamp=datetime.now(timezone.utc),
                    metadata={
                        "document_title": document_title,
                        "document_source": document_source,
                        "chunk_index": chunk.index,
                        "original_length": len(chunk.content),
                        "processed_length": len(episode_content),
                        **(document_metadata or {}),
                    },
                )

                episodes_created += 1
                logger.info(f"Added episode {episodes_created}/{len(chunks)}: {episode_id}")

                if i < len(chunks) - 1:
                    await asyncio.sleep(0.5)

            except Exception as e:
                error_msg = f"Failed to add chunk {chunk.index}: {e}"
                logger.error(error_msg)
                logger.error(traceback.format_exc())
                errors.append(error_msg)

        logger.info(f"Graph building complete: {episodes_created} episodes, {len(errors)} errors")
        return {"episodes_created": episodes_created, "total_chunks": len(chunks), "errors": errors}

    def _prepare_episode_content(self, chunk: DocumentChunk, document_title: str) -> str:
        """
        Truncate chunk to Graphiti's effective token limit (~6000 chars)
        and prepend a short document tag.
        """
        max_length = 6000
        content = chunk.content

        if len(content) > max_length:
            truncated = content[:max_length]
            cut = max(truncated.rfind(". "), truncated.rfind("! "), truncated.rfind("? "))
            if cut > max_length * 0.7:
                content = truncated[:cut + 1] + " [TRUNCATED]"
            else:
                content = truncated + "... [TRUNCATED]"
            logger.warning(
                f"Truncated chunk {chunk.index} from {len(chunk.content)} to {len(content)} chars"
            )

        if document_title and len(content) < max_length - 100:
            return f"[Doc: {document_title[:50]}]\n\n{content}"
        return content

    async def extract_entities_from_chunks(
        self,
        chunks: List[DocumentChunk],
        extract_suppliers: bool = True,
        extract_cell_types: bool = True,
        extract_culture_conditions: bool = True,
        extract_assay_methods: bool = True,
        extract_institutions: bool = True,
    ) -> List[DocumentChunk]:
        """
        Annotate each chunk's metadata with detected biomedical entities.

        Entity categories:
          suppliers          — reagent/media vendors (Lonza, Gibco, …)
          cell_types         — cell lines and primary cell types (CHO, NSC, …)
          culture_conditions — media classification and key supplements
          assay_methods      — measurement techniques used (trypan blue, flow cytometry, …)
          institutions       — research organisations mentioned

        Returns:
            The same chunks with an 'entities' key added to their metadata.
        """
        logger.info(f"Extracting biomedical entities from {len(chunks)} chunks")
        enriched = []

        for chunk in chunks:
            entities: Dict[str, List[str]] = {
                "suppliers": [],
                "cell_types": [],
                "culture_conditions": [],
                "assay_methods": [],
                "institutions": [],
            }

            content = chunk.content

            if extract_suppliers:
                entities["suppliers"] = self._extract_suppliers(content)
            if extract_cell_types:
                entities["cell_types"] = self._extract_cell_types(content)
            if extract_culture_conditions:
                entities["culture_conditions"] = self._extract_culture_conditions(content)
            if extract_assay_methods:
                entities["assay_methods"] = self._extract_assay_methods(content)
            if extract_institutions:
                entities["institutions"] = self._extract_institutions(content)

            enriched_chunk = DocumentChunk(
                content=chunk.content,
                index=chunk.index,
                start_char=chunk.start_char,
                end_char=chunk.end_char,
                metadata={
                    **chunk.metadata,
                    "entities": entities,
                    "entity_extraction_date": datetime.now().isoformat(),
                },
                token_count=chunk.token_count,
            )

            if hasattr(chunk, "embedding"):
                enriched_chunk.embedding = chunk.embedding

            enriched.append(enriched_chunk)

        logger.info("Entity extraction complete")
        return enriched

    # ------------------------------------------------------------------
    # Biomedical entity extractors
    # ------------------------------------------------------------------

    def _extract_suppliers(self, text: str) -> List[str]:
        """Reagent and cell culture media suppliers."""
        suppliers = {
            "Lonza", "Gibco", "Corning", "Nunc", "Falcon", "BD Biosciences",
            "Cellgenix", "Novoprotein", "SAFC", "Merck", "Sigma Aldrich", "Sigma-Aldrich",
            "ThermoFisher", "Thermo Fisher", "Millipore", "GE Healthcare",
            "Fujifilm", "Wako", "PeproTech", "Stemcell Technologies",
            "BioLegend", "R&D Systems", "Invitrogen", "Life Technologies",
        }
        found = set()
        text_lower = text.lower()
        for supplier in suppliers:
            if re.search(r"\b" + re.escape(supplier.lower()) + r"\b", text_lower):
                found.add(supplier)
        return sorted(found)

    def _extract_cell_types(self, text: str) -> List[str]:
        """Cell lines, primary cells, and stem cell types."""
        cell_types = {
            "CHO", "CHO-S", "CHO-K1", "HEK293", "HEK293T", "HEK 293",
            "Vero", "BHK", "BHK-21", "NSC", "MSC", "iPSC", "ESC",
            "neural stem cells", "mesenchymal stem cells",
            "induced pluripotent stem cells", "embryonic stem cells",
            "hematopoietic stem cells", "T cells", "NK cells",
            "fibroblasts", "keratinocytes", "hepatocytes",
            "mammalian cells", "human cells", "murine cells", "PC12", "B104", 
            "Rat-1", "NIH 3T3", "A549", "MCF-7", "Jurkat", "Rat-2", "HepG2",
            "H9c2", "NRK-52E", "NRK", "HEK293FT", "HEK293F", "HEK293E", "HEK293A",
            "THP-1", "CACO-2", "C2C12", "Hela", "DAOY", "Daoy", "Be2C", "BE2C", 
            "Beas2b", "BEAS-2B",  
        }
        found = set()
        text_lower = text.lower()
        for ct in cell_types:
            if re.search(r"\b" + re.escape(ct.lower()) + r"\b", text_lower):
                found.add(ct)
        return sorted(found)

    def _extract_culture_conditions(self, text: str) -> List[str]:
        """Media classifications, serum status, and key supplements."""
        conditions = {
            "FBS", "FCS", "fetal bovine serum", "fetal calf serum",
            "serum-free", "serum free", "xeno-free", "xenogeneic-free",
            "defined medium", "chemically defined", "protein-free",
            "animal-free", "animal component-free",
            "basal medium", "complete medium",
            "suspension culture", "adherent culture", "anchorage-independent",
            "EGF", "bFGF", "FGF", "IGF", "insulin", "transferrin", "selenium",
            "B27", "N2 supplement", "knockout serum replacement", "KSR",
            "L-glutamine", "GlutaMAX", "NAM", "coating", "culture plastic",
            "novel approach", "custom medium", "horse serum", "HS", "gelatin",
            "collagen", "fibronectin", "vitronectin", "Matrigel", "trypsin", "accutase",
            "laminin", "poly-L-lysine", "PLL", "poly-D-lysine", "PDL",
        }
        found = set()
        text_lower = text.lower()
        for cond in conditions:
            if re.search(r"\b" + re.escape(cond.lower()) + r"\b", text_lower):
                found.add(cond)
        return sorted(found)

    def _extract_assay_methods(self, text: str) -> List[str]:
        """Viability, proliferation, and characterisation assays."""
        assays = {
            "trypan blue", "propidium iodide", "PI staining",
            "flow cytometry", "FACS", "fluorescence microscopy",
            "phase contrast microscopy", "bright field microscopy",
            "MTT assay", "MTS assay", "WST-1", "CCK-8", "alamarBlue",
            "LDH assay", "BrdU", "Ki67", "EdU incorporation",
            "ELISA", "Western blot", "immunofluorescence", "ICC", "IHC",
            "qPCR", "RT-PCR", "RNA sequencing", "transcriptomics",
            "coulter counter", "hemocytometer", "Vi-CELL", "Cedex",
            "differentiation", "morphology", "cell growth", "proliferation", 
            "doubling time", "metabolic activity", "protein expression", 
            "gene expression", "cell viability", "cell counting", "cell cycle analysis",
            "proteomics", "metabolomics", "single-cell analysis", "live/dead staining",
            "transfection efficiency", "reporter assay", "luciferase assay", "apoptosis assay",
        }
        found = set()
        text_lower = text.lower()
        for assay in assays:
            if re.search(r"\b" + re.escape(assay.lower()) + r"\b", text_lower):
                found.add(assay)
        return sorted(found)

    def _extract_institutions(self, text: str) -> List[str]:
        """Research institutions and funding bodies."""
        institutions = {
            "NIH", "FDA", "EMA", "WHO",
            "MIT", "Stanford", "Harvard", "Oxford", "Cambridge",
            "Max Planck", "ETH Zurich", "UC Berkeley", "Caltech",
            "Johns Hopkins", "Karolinska Institute", "Pasteur Institute", "EMBL",
            "Wellcome Trust", "BBSRC", "NWO", "DFG", "Three R Centers", "Horizon 2020",
            "3R Center", "3Rs Center", "3Rs Research Foundation", "3R Research Foundation",
            "Ombion", "Cell Culture Company", "CC-Pharming", "Cell Culture Technologies",
            "Realise", "REALISE", "TPI", "TPI - The Protein Index", "Ncad", 
            "Ncad - The Cell Culture Company",
        }
        found = set()
        for inst in institutions:
            if inst in text:
                found.add(inst)
        return sorted(found)

    async def clear_graph(self):
        """Remove all data from the knowledge graph."""
        if not self._initialized:
            await self.initialize()
        logger.warning("Clearing knowledge graph...")
        await self.graph_client.clear_graph()
        logger.info("Knowledge graph cleared")


class BiomedicalEntityExtractor:
    """
    Lightweight rule-based extractor for quick entity detection
    without a full Graphiti connection — useful for testing or pre-filtering.
    """

    def __init__(self):
        self.supplier_pattern = re.compile(
            r"\b(Lonza|Gibco|Corning|Cellgenix|ThermoFisher|Thermo Fisher|Merck|"
            r"Sigma-Aldrich|Millipore|PeproTech|Invitrogen|BioLegend)\b",
            re.IGNORECASE,
        )
        self.cell_type_pattern = re.compile(
            r"\b(CHO(?:-S|-K1)?|HEK293T?|Vero|BHK(?:-21)?|NSC|MSC|iPSC|ESC|"
            r"neural stem cells?|mesenchymal stem cells?|T cells?|NK cells?)\b",
            re.IGNORECASE,
        )
        self.condition_pattern = re.compile(
            r"\b(FBS|FCS|fetal bovine serum|serum.free|xeno.free|"
            r"chemically defined|defined medium|protein.free)\b",
            re.IGNORECASE,
        )
        self.assay_pattern = re.compile(
            r"\b(trypan blue|flow cytometry|FACS|MTT|LDH|ELISA|BrdU|Ki67|"
            r"propidium iodide|Vi-CELL|hemocytometer)\b",
            re.IGNORECASE,
        )

    def extract_entities(self, text: str) -> Dict[str, List[str]]:
        """Return deduplicated entity lists for each biomedical category."""
        return {
            "suppliers": list(set(self.supplier_pattern.findall(text))),
            "cell_types": list(set(self.cell_type_pattern.findall(text))),
            "culture_conditions": list(set(self.condition_pattern.findall(text))),
            "assay_methods": list(set(self.assay_pattern.findall(text))),
        }


def create_graph_builder() -> GraphBuilder:
    """Create a GraphBuilder instance."""
    return GraphBuilder()


async def main():
    """Smoke-test: chunk a sample cell culture abstract and extract entities."""
    from .chunker import ChunkingConfig, create_chunker

    config = ChunkingConfig(chunk_size=300, use_semantic_splitting=False)
    chunker = create_chunker(config)
    graph_builder = create_graph_builder()

    sample_text = """
    We evaluated a serum-free, xeno-free medium (Cellgenix GMP Medium) for the
    expansion of neural stem cells (NSC) isolated from human cortex. Cells were
    maintained in suspension culture and viability was assessed daily by trypan blue
    exclusion and flow cytometry using propidium iodide staining.

    After 7 days, NSC cultured in the defined medium showed a viability of 92 ± 3%,
    comparable to the FBS-containing control (94 ± 2%). Doubling time was 36 h in
    serum-free conditions versus 32 h with FBS. Morphology was assessed by phase
    contrast microscopy: cells maintained characteristic neurosphere morphology in
    both conditions. Lonza and Gibco EGF and bFGF supplements were used at 20 ng/mL.
    """

    chunks = await chunker.chunk_document(
        content=sample_text,
        title="NSC expansion in serum-free medium",
        source="test_abstract.txt",
    )

    print(f"Created {len(chunks)} chunks")

    enriched_chunks = await graph_builder.extract_entities_from_chunks(chunks)

    for chunk in enriched_chunks:
        print(f"\nChunk {chunk.index} entities:")
        for category, values in chunk.metadata.get("entities", {}).items():
            if values:
                print(f"  {category}: {values}")

    try:
        result = await graph_builder.add_document_to_graph(
            chunks=enriched_chunks,
            document_title="NSC expansion in serum-free medium",
            document_source="test_abstract.txt",
            document_metadata={"cell_type": "NSC", "media_type": "xeno-free"},
        )
        print(f"\nGraph result: {result}")
    except Exception as e:
        print(f"Graph building failed (Neo4j may not be running): {e}")
    finally:
        await graph_builder.close()


if __name__ == "__main__":
    asyncio.run(main())

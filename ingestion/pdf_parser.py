"""
PDF parsing with IMRaD section detection for scientific papers.

Reads a PDF file page by page (PyMuPDF), cleans extraction artifacts,
then identifies standard scientific sections (Abstract, Introduction,
Methods, Results, Discussion, Conclusion, References) by matching
heading lines against known patterns.

Main entry point:
    paper = parse_pdf("path/to/article.pdf")
    for section in paper.sections:
        print(section.name, section.content[:200])
"""

import re
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Section heading patterns (IMRaD + common variants)
# Key = normalized name that ends up in chunk metadata
# Values = regex patterns matched case-insensitively against each line
# ---------------------------------------------------------------------------
SECTION_PATTERNS: Dict[str, List[str]] = {
    "abstract": [
        r"abstract",
        r"summary",
    ],
    "introduction": [
        r"introduction",
        r"background",
    ],
    "methods": [
        r"methods?",
        r"materials?\s+and\s+methods?",
        r"experimental\s+(?:procedures?|design)",
        r"patients?\s+and\s+methods?",
        r"study\s+design",
        r"cell\s+culture\s+(?:methods?|conditions?)",
    ],
    "results": [
        r"results?",
        r"results?\s+and\s+discussion",
        r"findings?",
    ],
    "discussion": [
        r"discussion",
        r"interpretation",
    ],
    "conclusion": [
        r"conclusions?",
        r"concluding\s+remarks?",
        r"summary\s+and\s+conclusions?",
    ],
    "references": [
        r"references?",
        r"bibliography",
        r"works?\s+cited",
    ],
}

# Optional numeric/Roman numeral prefix before a heading: "2. Methods" or "II. Results"
_NUMBER_PREFIX = r"(?:\d+\.?\s+|[IVX]+\.?\s+)?"

# Sections shorter than this character count are treated as false positives and dropped
_MIN_SECTION_CHARS = 100


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class PaperSection:
    """One detected section from a scientific paper."""
    name: str       # Normalized label: "abstract", "methods", "results", etc.
    heading: str    # Original heading text as found in the PDF
    content: str    # Full body text of the section
    page_start: int # 0-indexed page number where this section begins


@dataclass
class ParsedPaper:
    """All structured information extracted from one scientific PDF."""
    title: str
    authors: List[str]
    doi: Optional[str]
    year: Optional[int]
    journal: Optional[str]
    abstract: str                  # Convenience shortcut to the abstract section text
    sections: List[PaperSection]   # All detected sections in document order
    full_text: str                 # Complete cleaned text of the whole paper
    metadata: Dict                 # Extra: file_path, page_count, doi, year, sections_detected


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def parse_pdf(file_path: str) -> ParsedPaper:
    """
    Parse a scientific PDF into structured content with section detection.

    Pipeline:
        1. Open PDF and extract plain text per page (PyMuPDF / fitz)
        2. Clean text: fix ligatures, rejoin hyphenated line breaks, strip lone page numbers
        3. Detect section boundaries by scanning for known heading patterns
        4. Extract title, DOI, and year from the first page

    Args:
        file_path: Path to the PDF file (absolute or relative)

    Returns:
        ParsedPaper with full_text, sections list, and header metadata

    Raises:
        ImportError:      PyMuPDF not installed — run: pip install pymupdf
        FileNotFoundError: File does not exist
        RuntimeError:     PDF has no pages
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise ImportError(
            "PyMuPDF is required for PDF parsing.\n"
            "Install it with:  pip install pymupdf"
        )

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {file_path}")

    logger.info(f"Parsing PDF: {path.name}")
    doc = fitz.open(str(path))

    if doc.page_count == 0:
        raise RuntimeError(f"PDF has no pages: {file_path}")

    page_count = doc.page_count  # Save before closing

    # Step 1: Extract raw text from every page
    pages_text = _extract_pages(doc)
    doc.close()

    # Step 2: Join all pages and clean artifacts
    full_text = _clean_text("\n\n".join(pages_text))

    # Step 3: Detect section boundaries
    sections = _detect_sections(full_text, pages_text)

    # Step 4: Pull title/DOI/year from the first page
    title, authors, doi, year, journal = _extract_header_metadata(
        pages_text[0] if pages_text else ""
    )
    if not title:
        title = path.stem  # Filename without extension as fallback

    # Shortcut to abstract text for quick access
    abstract_section = next((s for s in sections if s.name == "abstract"), None)
    abstract = abstract_section.content if abstract_section else full_text[:2000]

    return ParsedPaper(
        title=title,
        authors=authors,
        doi=doi,
        year=year,
        journal=journal,
        abstract=abstract,
        sections=sections,
        full_text=full_text,
        metadata={
            "file_path": str(path),
            "file_name": path.name,
            "page_count": page_count,
            "sections_detected": [s.name for s in sections],
            "doi": doi,
            "year": year,
        },
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_pages(doc) -> List[str]:
    """Extract plain text from each PDF page, one string per page."""
    return [page.get_text("text") for page in doc]


def _clean_text(text: str) -> str:
    """
    Remove common PDF text extraction artifacts.

    Fixes:
    - Typographic ligatures (ﬁ → fi, ﬂ → fl, etc.)
    - Hyphenated word breaks across lines ("prolif-\\neration" → "proliferation")
    - Lone page-number lines (lines containing only digits, e.g. "12" or "– 3 –")
    - Three or more consecutive blank lines collapsed to two
    - Multiple spaces/tabs collapsed to one
    """
    # Ligatures that some PDF fonts encode as single characters
    for lig, rep in [("ﬁ", "fi"), ("ﬂ", "fl"), ("ﬀ", "ff"), ("ﬃ", "ffi"), ("ﬄ", "ffl")]:
        text = text.replace(lig, rep)

    # Rejoin words split across lines by a hyphen: "prolif-\neration" → "proliferation"
    text = re.sub(r'(\w+)-\n(\w+)', r'\1\2', text)

    # Remove lines that contain only a page number (possibly wrapped in dashes)
    text = re.sub(r'^\s*[–\-]?\s*\d{1,4}\s*[–\-]?\s*$', '', text, flags=re.MULTILINE)

    # Collapse three or more blank lines into two (preserve paragraph spacing)
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Collapse runs of spaces and tabs into a single space
    text = re.sub(r'[ \t]{2,}', ' ', text)

    return text.strip()


def _detect_sections(full_text: str, pages_text: List[str]) -> List[PaperSection]:
    """
    Scan the full text line by line and detect section headings.

    A line is classified as a heading when:
    - It matches one of the known section name patterns (case-insensitive)
    - It is short (≤ 80 characters) — avoids accidentally matching body sentences
    - An optional number prefix is allowed: "2. Methods" or "II. Results"

    The content of each section is the text between its heading and the next heading.
    Returns a single "body" section if no headings are found.
    """
    lines = full_text.split("\n")

    # Pre-compile one regex per (section_name, pattern) pair for efficiency
    compiled: List[Tuple[str, re.Pattern]] = []
    for section_name, patterns in SECTION_PATTERNS.items():
        for pat in patterns:
            full_pat = r"^" + _NUMBER_PREFIX + r"(?:" + pat + r")\s*$"
            compiled.append((section_name, re.compile(full_pat, re.IGNORECASE)))

    # Walk every line looking for heading matches
    # Store: (line_index, section_name, original_heading_text)
    found_headings: List[Tuple[int, str, str]] = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or len(stripped) > 80:
            continue  # Skip blank lines and lines too long to be headings
        for section_name, pattern in compiled:
            if pattern.match(stripped):
                found_headings.append((i, section_name, stripped))
                break  # One section name per line

    if not found_headings:
        # No recognizable headings — wrap everything in a generic "body" section
        logger.warning(
            "No IMRaD section headings detected in this PDF. "
            "Treating the entire document as a single 'body' section."
        )
        return [PaperSection(name="body", heading="", content=full_text, page_start=0)]

    # Build PaperSection objects: content = all lines between this heading and the next
    sections: List[PaperSection] = []
    for idx, (line_i, name, heading_text) in enumerate(found_headings):
        body_start = line_i + 1
        body_end = found_headings[idx + 1][0] if idx + 1 < len(found_headings) else len(lines)
        content = "\n".join(lines[body_start:body_end]).strip()

        # Estimate which PDF page this heading falls on
        chars_before = len("\n".join(lines[:line_i]))
        page_start = _estimate_page(chars_before, pages_text)

        if len(content) >= _MIN_SECTION_CHARS:
            sections.append(PaperSection(
                name=name,
                heading=heading_text,
                content=content,
                page_start=page_start,
            ))

    logger.info(f"Detected sections: {[s.name for s in sections]}")
    return sections


def _estimate_page(chars_before: int, pages_text: List[str]) -> int:
    """
    Estimate the 0-indexed page number for a given character offset.

    Walks cumulative page character counts until the offset is reached.
    """
    cumulative = 0
    for i, page in enumerate(pages_text):
        cumulative += len(page)
        if cumulative >= chars_before:
            return i
    return max(0, len(pages_text) - 1)


def _extract_header_metadata(
    first_page: str,
) -> Tuple[str, List[str], Optional[str], Optional[int], Optional[str]]:
    """
    Heuristically extract title, DOI, and publication year from the first page.

    Title  = the longest line in the first 10 non-empty lines (rough but effective
             for most journal formats where the title is the dominant text block).
    DOI    = standard "10.XXXX/..." pattern.
    Year   = 4-digit year in range 1990–2030.
    Authors and journal name are left empty — too format-dependent to parse reliably
    without knowing the publisher's layout.
    """
    lines = [ln.strip() for ln in first_page.split("\n") if ln.strip()]

    # DOI: standard registry pattern
    doi_match = re.search(r'10\.\d{4,9}/[^\s\]\[,;:]+', first_page)
    doi = doi_match.group(0) if doi_match else None

    # Year: plausible publication year range
    year_match = re.search(r'\b(199\d|20[0-3]\d)\b', first_page)
    year = int(year_match.group(0)) if year_match else None

    # Title: longest line among the first 10 (journal PDFs put the title prominently)
    title = max(lines[:10], key=len, default="") if lines else ""

    return title, [], doi, year, None

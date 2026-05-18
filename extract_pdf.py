def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Open a PDF file and extract all its text page by page.
 
    Args:
        pdf_path: Full path to the .pdf file.
 
    Returns:
        A single string containing the text of every page,
        with page breaks marked so we know where pages start.
    """
     full_text = []
 
    with pdfplumber.open(pdf_path) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            page_text = page.extract_text()
            if page_text:  # some pages are pure images and return None
                # Tag each page so we can include page numbers in citations later
                full_text.append(f"\n--- Page {page_number} ---\n{page_text}")
 
    return "\n".join(full_text)
 
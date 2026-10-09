from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from docx import Document as WordDocument
from docx.table import Table
from docx.text.paragraph import Paragraph
from pypdf import PdfReader

MAX_BYTES = 5 * 1024 * 1024
MAX_TEXT = 100000


class DocumentError(ValueError):
    def __init__(self, message, status=422):
        super().__init__(message)
        self.status = status


def validate_text(text):
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    if not text.strip():
        raise DocumentError(
            "No readable text. Scanned PDFs need OCR; paste text or use a text PDF."
        )
    if len(text) > MAX_TEXT:
        raise DocumentError("Extracted text exceeds 100,000 characters.", 413)
    return text


def extract_file(filename, data):
    if len(data) > MAX_BYTES:
        raise DocumentError("File exceeds the 5 MB limit.", 413)
    if not data:
        raise DocumentError("The file is empty.")
    extension = Path(filename).suffix.lower()
    if extension not in {".pdf", ".docx", ".txt"}:
        raise DocumentError("Use a PDF, DOCX, or UTF-8 TXT document.", 415)
    warnings = []
    try:
        if extension == ".txt":
            text = data.decode("utf-8-sig")
        elif extension == ".pdf":
            if not data.startswith(b"%PDF-"):
                raise DocumentError("The PDF header is invalid.")
            pdf = PdfReader(BytesIO(data))
            if pdf.is_encrypted:
                raise DocumentError("Password-protected PDFs are not supported.")
            if len(pdf.pages) > 30:
                raise DocumentError("Use a document with at most 30 pages.", 413)
            pages = []
            for page in pdf.pages:
                # Bound decoded stream work, not just the compressed upload size.
                contents = page.get_contents()
                if contents and len(contents.get_data()) > 5 * 1024 * 1024:
                    raise DocumentError("PDF page content is too large.", 413)
                pages.append(page.extract_text() or "")
                if sum(map(len, pages)) > MAX_TEXT:
                    raise DocumentError("Extracted text exceeds 100,000 characters.", 413)
            text = "\n".join(pages)
            warnings.append("Review PDF reading order, dates, and split lines before confirming.")
        else:
            with ZipFile(BytesIO(data)) as archive:
                if sum(info.file_size for info in archive.infolist()) > 20 * 1024 * 1024:
                    raise DocumentError("Expanded DOCX exceeds 20 MB.", 413)
                if "word/document.xml" not in archive.namelist():
                    raise DocumentError("This is not a valid DOCX document.")
            word = WordDocument(BytesIO(data))
            blocks = []
            for block in word.iter_inner_content():
                if isinstance(block, Paragraph):
                    blocks.append(block.text)
                elif isinstance(block, Table):
                    blocks.extend(" | ".join(cell.text for cell in row.cells) for row in block.rows)
            text = "\n".join(blocks)
            warnings.append(
                "DOCX body and tables extracted; check headers, text boxes, and reading order."
            )
    except DocumentError:
        raise
    except Exception as exc:
        raise DocumentError(
            "Cannot read this document. It may be malformed or use an unsupported encoding."
        ) from exc
    return validate_text(text), warnings

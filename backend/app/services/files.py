"""Uploaded-document text extraction with validation (FR-3 / 8.15 file upload validation)."""
import io
from pathlib import PurePath

from pypdf import PdfReader
from pypdf.errors import PdfReadError

MAX_PDF_PAGES = 60


class FileFormatError(ValueError):
    pass


def extract_text(filename: str, data: bytes, allowed: set[str], max_bytes: int) -> tuple[str, str]:
    """Returns (text, suggested_title). Raises FileFormatError with a user-friendly message."""
    ext = PurePath(filename or "").suffix.lower().lstrip(".")
    if ext not in allowed:
        raise FileFormatError(f"Invalid file format '.{ext or '?'}'. Supported formats: {', '.join(sorted(allowed))}.")
    if len(data) == 0:
        raise FileFormatError("The uploaded file is empty.")
    if len(data) > max_bytes:
        raise FileFormatError(f"The file is too large (maximum {max_bytes // (1024 * 1024)} MB).")
    title = PurePath(filename).stem[:200]
    if ext == "txt":
        if b"\x00" in data[:2048]:
            raise FileFormatError("This does not look like a plain text file.")
        for enc in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                return data.decode(enc), title
            except UnicodeDecodeError:
                continue
    if ext == "pdf":
        if not data.startswith(b"%PDF"):
            raise FileFormatError("This file is not a valid PDF document.")
        try:
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted and not reader.decrypt(""):
                raise FileFormatError("This PDF is password-protected and cannot be read.")
            text = "\n".join((pg.extract_text() or "") for pg in reader.pages[:MAX_PDF_PAGES])
        except FileFormatError:
            raise
        except (PdfReadError, Exception) as e:           # noqa: BLE001
            raise FileFormatError(f"The PDF could not be read: {e}")
        if not text.strip():
            raise FileFormatError("No text could be extracted from this PDF (scanned/image-only PDFs are not supported).")
        return text, title
    raise FileFormatError("Unsupported file type.")

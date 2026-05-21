import io


class DocParseError(Exception):
    pass


_TEXT_EXTS = {"md", "markdown", "txt", ""}


def parse(content: bytes, filename: str) -> str:
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext in _TEXT_EXTS:
        return content.decode("utf-8", errors="replace")
    if ext == "pdf":
        return _parse_pdf(content)
    if ext == "docx":
        return _parse_docx(content)
    raise DocParseError(f"Unsupported file type: .{ext}")


def _parse_pdf(content: bytes) -> str:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(content))
    except Exception as exc:
        raise DocParseError(f"Could not read PDF: {exc}") from exc

    parts: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if text.strip():
            parts.append(text.strip())
    if not parts:
        raise DocParseError("PDF contains no extractable text.")
    return "\n\n".join(parts)


def _parse_docx(content: bytes) -> str:
    from docx import Document

    try:
        doc = Document(io.BytesIO(content))
    except Exception as exc:
        raise DocParseError(f"Could not read DOCX: {exc}") from exc

    parts: list[str] = []
    for para in doc.paragraphs:
        text = para.text
        if not text.strip():
            continue
        style = (para.style.name if para.style else "") or ""
        style_lower = style.lower()
        if style_lower.startswith("heading"):
            level_digits = "".join(c for c in style if c.isdigit())
            level = int(level_digits) if level_digits else 1
            parts.append("#" * max(1, min(6, level)) + " " + text)
        elif "list" in style_lower:
            parts.append("- " + text)
        else:
            parts.append(text)
    if not parts:
        raise DocParseError("DOCX contains no extractable text.")
    return "\n\n".join(parts)


__all__ = ["DocParseError", "parse"]

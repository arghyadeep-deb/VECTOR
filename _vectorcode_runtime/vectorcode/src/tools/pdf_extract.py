"""Small PDF parsing worker: bounded input/output and per-process decompression limits.

The caller owns the process deadline. This is not an OS security sandbox.
"""

import argparse
import io
import json
import logging
import sys

MAX_PAGES = 100


def extract(body, max_chars, max_bytes):
    from pypdf import PdfReader, filters

    # This worker is isolated: do not alter library-wide limits in the live assistant process.
    for name in (
        "ZLIB_MAX_OUTPUT_LENGTH",
        "LZW_MAX_OUTPUT_LENGTH",
        "RUN_LENGTH_MAX_OUTPUT_LENGTH",
        "MAX_ARRAY_BASED_STREAM_OUTPUT_LENGTH",
        "MAX_DECLARED_STREAM_LENGTH",
    ):
        if hasattr(filters, name):
            setattr(filters, name, max_bytes)
    if len(body) > max_bytes:
        return {"error": "PDF exceeds the download limit", "text": "", "truncated": True}
    try:
        reader = PdfReader(io.BytesIO(body))
        if reader.is_encrypted:
            return {"error": "PDF is encrypted; a password-protected document cannot be extracted", "text": ""}
        chunks, count, truncated = [], 0, False

        class EnoughTextError(Exception):
            pass

        def visit(text, *args):
            nonlocal count, truncated
            remaining = max_chars - count
            chunks.append(text[:remaining])
            count += min(len(text), remaining)
            if len(text) > remaining:
                truncated = True
                raise EnoughTextError()

        pages = reader.pages
        total_pages = len(pages)
        try:
            for page in pages[:MAX_PAGES]:
                page.extract_text(visitor_text=visit)
                if count < max_chars:
                    chunks.append("\n")
                    count += 1
        except EnoughTextError:
            pass
        text = "".join(chunks).strip()
        truncated = truncated or total_pages > MAX_PAGES
        if not text:
            return {"error": "PDF has no extractable text; scanned documents require OCR", "text": ""}
        return {"text": text, "truncated": truncated, "pages": total_pages}
    except Exception:
        return {"error": "PDF could not be parsed within the extraction limits", "text": ""}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-chars", type=int, required=True)
    parser.add_argument("--max-bytes", type=int, required=True)
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    result = extract(sys.stdin.buffer.read(args.max_bytes + 1), args.max_chars, args.max_bytes)
    sys.stdout.write(json.dumps(result))

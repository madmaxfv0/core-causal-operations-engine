"""A document registry written on one machine must still open on another."""
from __future__ import annotations

from backend.archive import extraction
from backend.config import DOCS_DIR


def test_stale_absolute_path_falls_back_to_the_documents_folder():
    bundled = next(p for p in sorted(DOCS_DIR.glob("*.txt")))
    record = {"stored_path": "/somewhere/else/entirely/" + bundled.name, "file_name": bundled.name}
    assert extraction.stored_file(record) == bundled


def test_existing_path_is_used_as_is():
    bundled = next(p for p in sorted(DOCS_DIR.glob("*.txt")))
    assert extraction.stored_file({"stored_path": str(bundled), "file_name": bundled.name}) == bundled


def test_every_bundled_document_resolves_to_a_real_file():
    documents = extraction._load()["documents"]
    assert documents, "the demo registry should list the bundled documents"
    for record in documents.values():
        if record.get("bundled"):
            assert extraction.stored_file(record).exists(), record["file_name"]

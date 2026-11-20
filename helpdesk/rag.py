"""
RAG (Retrieval-Augmented Generation) — find the policy text that answers a question.

Two phases:

  INGESTION (run once, via `python ingest.py`)
     markdown files --> split into chunks (one per "## Section") --> embed each chunk
     with Gemini --> store vector + text + {document, section} in ChromaDB on disk.

  RETRIEVAL (every question, via search_policies)
     question --> embed it --> ChromaDB finds the closest chunk vectors -->
     drop chunks that are too far away (not relevant) --> return the rest WITH
     their document name and section, so the answer can cite them.

Debug retrieval:  python -m helpdesk.rag "how many sick days do I get?"
"""

import re
import sys
from pathlib import Path

import chromadb

from helpdesk import llm
from helpdesk.config import CHROMA_DIR, COLLECTION_NAME, MAX_DISTANCE, POLICIES_DIR, TOP_K

MAX_CHUNK_CHARS = 1500   # sections longer than this are split further by paragraph


# ---------------------------------------------------------------- chunking
def chunk_markdown(path: Path) -> list[dict]:
    """Split one policy file into chunks, one per '## ' section.

    Why split by section instead of every N characters?
      - each chunk is a complete idea (e.g. "5. Carry Forward and Encashment")
      - we get the section name for free, which we need for citations
    """
    text = path.read_text(encoding="utf-8")
    title_match = re.search(r"^# (.+)$", text, flags=re.MULTILINE)
    doc_title = title_match.group(1).strip() if title_match else path.stem

    # re.split with a capture group keeps the headings: [intro, heading1, body1, heading2, body2, ...]
    parts = re.split(r"^## (.+)$", text, flags=re.MULTILINE)
    chunks = []
    for i in range(1, len(parts), 2):
        section = parts[i].strip()
        body = parts[i + 1].strip()
        for n, piece in enumerate(_split_long(body)):
            chunks.append({
                "id": f"{path.stem}::{i // 2 + 1}::{n}",
                "document": doc_title,
                "file": path.name,
                "section": section,
                # Putting the title + section into the text helps the embedding
                # understand what the chunk is about.
                "text": f"{doc_title} — {section}\n\n{piece}",
            })
    return chunks


def _split_long(body: str) -> list[str]:
    """Keep short sections whole; split long ones on blank lines (paragraphs)."""
    if len(body) <= MAX_CHUNK_CHARS:
        return [body]
    pieces, current = [], ""
    for para in body.split("\n\n"):
        if current and len(current) + len(para) > MAX_CHUNK_CHARS:
            pieces.append(current.strip())
            current = ""
        current += para + "\n\n"
    if current.strip():
        pieces.append(current.strip())
    return pieces


def load_all_chunks(folder: Path = POLICIES_DIR) -> list[dict]:
    chunks = []
    for path in sorted(folder.glob("*.md")):
        chunks.extend(chunk_markdown(path))
    return chunks


# ---------------------------------------------------------------- vector store
def _collection(create_fresh: bool = False):
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    if create_fresh:
        try:
            client.delete_collection(COLLECTION_NAME)   # re-ingest from scratch
        except Exception:
            pass
    # embedding_function=None: we create embeddings ourselves with Gemini.
    # "cosine" distance: 0 = identical meaning, larger = less related.
    return client.get_or_create_collection(
        COLLECTION_NAME, metadata={"hnsw:space": "cosine"}, embedding_function=None
    )


def build_index() -> int:
    """Chunk + embed + store every policy document. Returns number of chunks."""
    chunks = load_all_chunks()
    vectors = llm.embed([c["text"] for c in chunks], task_type="RETRIEVAL_DOCUMENT")
    col = _collection(create_fresh=True)
    col.add(
        ids=[c["id"] for c in chunks],
        embeddings=vectors,
        documents=[c["text"] for c in chunks],
        metadatas=[{"document": c["document"], "file": c["file"], "section": c["section"]}
                   for c in chunks],
    )
    return len(chunks)


def search_policies(query: str, k: int = TOP_K, max_distance: float = MAX_DISTANCE) -> list[dict]:
    """Return the most relevant policy chunks for `query`.
    Chunks with distance > max_distance are dropped, so an EMPTY list means
    'nothing relevant found' and the agent must not guess."""
    col = _collection()
    if col.count() == 0:
        raise RuntimeError("The policy index is empty. Run `python ingest.py` first.")

    query_vec = llm.embed([query], task_type="RETRIEVAL_QUERY")[0]
    res = col.query(query_embeddings=[query_vec], n_results=k,
                    include=["documents", "metadatas", "distances"])

    results = []
    for text, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
        if dist <= max_distance:
            results.append({
                "document": meta["document"],
                "section": meta["section"],
                "text": text,
                "distance": round(dist, 3),
            })
    return results


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "How many sick leave days do I get?"
    print(f"Query: {q}\n(showing ALL top-{TOP_K} results; cut-off is {MAX_DISTANCE})\n")
    for r in search_policies(q, max_distance=2.0):
        flag = "KEEP" if r["distance"] <= MAX_DISTANCE else "DROP"
        print(f"[{flag}] {r['distance']:.3f}  {r['document']} > {r['section']}")

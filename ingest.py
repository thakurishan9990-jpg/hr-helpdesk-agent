"""
Step 1 of RAG: read the policy documents, embed them, and save them in ChromaDB.

Run:  python ingest.py
Re-run it any time you edit a file in data/policies/.
"""

from helpdesk.config import CHROMA_DIR, POLICIES_DIR
from helpdesk.rag import build_index, load_all_chunks

if __name__ == "__main__":
    chunks = load_all_chunks()
    print(f"Found {len(list(POLICIES_DIR.glob('*.md')))} policy files -> {len(chunks)} chunks")
    for c in chunks:
        print(f"  - {c['document']} > {c['section']}  ({len(c['text'])} chars)")

    print("\nEmbedding chunks with Gemini and storing them in ChromaDB...")
    n = build_index()
    print(f"Done. Stored {n} chunks in {CHROMA_DIR}")

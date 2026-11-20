"""
CONFIG — one place for all settings, read from the .env file.
Every other module imports from here instead of calling os.getenv itself.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Project root folder (the folder that contains main.py)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# --- Gemini ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
CHAT_MODEL = os.getenv("GEMINI_CHAT_MODEL", "gemini-3.1-flash-lite")
EMBED_MODEL = os.getenv("GEMINI_EMBED_MODEL", "gemini-embedding-001")

# --- RAG ---
POLICIES_DIR = PROJECT_ROOT / "data" / "policies"
CHROMA_DIR = PROJECT_ROOT / "chroma_db"
COLLECTION_NAME = "hr_policies"
TOP_K = 4                 # how many chunks to retrieve per question
# Cosine distance cut-off: chunks further than this are "not relevant".
# Tuned on real Gemini embeddings: answerable questions scored 0.23-0.35,
# unrelated ones (e.g. "capital of France") ~0.50. Check with: python -m helpdesk.rag "<question>"
MAX_DISTANCE = 0.45

# --- Database (used by the MCP server) ---
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://helpdesk:helpdesk_pw@localhost:5433/helpdesk"
)


def require_api_key() -> str:
    """Stop with a friendly message if the Gemini key is missing."""
    if not GEMINI_API_KEY or GEMINI_API_KEY.startswith("your-"):
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Copy .env.example to .env and add your key "
            "(free at https://aistudio.google.com/apikey)."
        )
    return GEMINI_API_KEY

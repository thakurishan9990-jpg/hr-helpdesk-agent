"""
LLM HELPERS — the only file that talks to Google Gemini directly.

  - get_client()   : creates the Gemini client once and reuses it
  - generate(...)  : calls the chat model, retrying if we hit rate limits
  - embed(...)     : turns a list of texts into embedding vectors

Run `python -m helpdesk.llm` to list the models your API key can use
(handy if a default model name has been retired by Google).
"""

import time
from functools import lru_cache

from google import genai
from google.genai import errors, types

from helpdesk.config import CHAT_MODEL, EMBED_MODEL, require_api_key

EMBED_DIM = 768        # smaller vectors = faster search, still very accurate
EMBED_BATCH = 50       # how many texts to embed per API call
REQUEST_TIMEOUT_MS = 60_000   # give up on any single request after 60 s (then retry)


@lru_cache(maxsize=1)
def get_client() -> genai.Client:
    # Without a timeout, a request to an overloaded model can hang for minutes.
    return genai.Client(api_key=require_api_key(),
                        http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS))


def _with_retry(fn, attempts: int = 4):
    """Call fn(); if Gemini is rate-limited (429), busy (500/503) or timed out (504),
    wait and retry. The free tier has low per-minute limits, so this matters in tests."""
    for i in range(attempts):
        try:
            return fn()
        except errors.APIError as e:
            if e.code in (429, 500, 503, 504) and i < attempts - 1:
                wait = 10 * (i + 1)
                print(f"  [gemini busy/rate-limited ({e.code}), retrying in {wait}s]")
                time.sleep(wait)
            else:
                raise


def generate(contents, system_instruction: str | None = None, tools=None,
             json_schema: dict | None = None, temperature: float = 0.1):
    """Call the chat model.

    contents          : a string, or a list of types.Content (the conversation so far)
    system_instruction: the "rules" for the model
    tools             : function declarations the model may call
    json_schema       : if given, force the model to reply with JSON matching this schema
    """
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        temperature=temperature,
        tools=tools,
        # We run tools ourselves inside the LangGraph "tools" node, so turn off
        # the SDK's automatic function calling.
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    if json_schema:
        config.response_mime_type = "application/json"
        config.response_json_schema = json_schema

    return _with_retry(
        lambda: get_client().models.generate_content(
            model=CHAT_MODEL, contents=contents, config=config
        )
    )


def embed(texts: list[str], task_type: str) -> list[list[float]]:
    """Embed texts. task_type is 'RETRIEVAL_DOCUMENT' for chunks we store,
    and 'RETRIEVAL_QUERY' for the user's question (Gemini optimises each differently)."""
    vectors: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH):
        batch = texts[start:start + EMBED_BATCH]
        resp = _with_retry(
            lambda: get_client().models.embed_content(
                model=EMBED_MODEL,
                contents=batch,
                config=types.EmbedContentConfig(
                    task_type=task_type, output_dimensionality=EMBED_DIM
                ),
            )
        )
        vectors.extend(e.values for e in resp.embeddings)
    return vectors


if __name__ == "__main__":
    print(f"Configured chat model : {CHAT_MODEL}")
    print(f"Configured embed model: {EMBED_MODEL}\n")
    print("Models available to your key:")
    for m in get_client().models.list():
        actions = getattr(m, "supported_actions", None) or []
        if "generateContent" in actions or "embedContent" in actions:
            print(f"  {m.name.removeprefix('models/'):40s} {', '.join(actions)}")

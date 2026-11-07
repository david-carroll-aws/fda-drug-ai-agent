import os
import time
from pymongo import MongoClient
import certifi

_collection = None
_model = None


def _get_collection():
    global _collection
    if _collection is None:
        client = MongoClient(
            os.environ["MONGO_URL"],  # your existing connection string
            tlsCAFile=certifi.where(),
            retryReads=True,
            serverSelectionTimeoutMS=10000,  # was effectively 30s; fail faster
            connectTimeoutMS=10000,
            socketTimeoutMS=20000,
        )
        _collection = client["druglabels"]["chunks"]
    return _collection


def _get_model():
    """Same local model that embed_load.py used to embed the stored chunks."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def search_label_passages(question: str, drug_name: str = "") -> dict:
    """Search FDA drug label text by meaning and return the most relevant passages.

    Use this for open-ended questions about what a label says, for example food,
    alcohol, pregnancy, or other specific situations. It searches warnings,
    side effects and indications sections.

    Args:
        question: The user's question, in plain language.
        drug_name: Optional drug name to focus the search on one drug.

    Returns:
        A dict with a list of passages, each with drug, section, text and score.
    """
    try:
        vector = _get_model().encode(question, normalize_embeddings=True).tolist()

        # Pull extra candidates, then filter by drug name here, because the stored
        # drug field is free text and needs a case-insensitive partial match.
        pipeline = [
            {"$vectorSearch": {
                "index": "vector_index",
                "path": "embedding",
                "queryVector": vector,
                "numCandidates": 400 if drug_name else 100,
                "limit": 100 if drug_name else 5,
            }},
            {"$project": {
                "_id": 0,
                "drug": 1,
                "section": 1,
                "text": 1,
                "score": {"$meta": "vectorSearchScore"},
            }},
        ]
        rows = list(_get_collection().aggregate(pipeline))

        if drug_name:
            wanted = drug_name.lower()
            rows = [r for r in rows if wanted in str(r.get("drug", "")).lower()]
            rows = rows[:5]

        if not rows:
            return {"found": False, "message": "No matching label passages found."}

        for r in rows:
            r["score"] = round(r["score"], 3)

        return {
            "found": True,
            "note": "Passages matched by meaning, not exact keywords.",
            "passages": rows,
        }
    except Exception as e:
        return {"found": False, "error": f"Label search failed: {e}"}


def _warm_up():
    """Load the embedding model and open the Mongo connection at startup, so the
    first visitor's question does not pay for them. Never raises: if warm-up
    fails, the lazy getters above still work on the first real search."""
    t0 = time.time()
    try:
        _get_model().encode("warm up", normalize_embeddings=True)
        print(f"TIMING warm-up model ready in {time.time() - t0:.2f}s", flush=True)
    except Exception as e:
        print(f"warm-up model failed: {e}", flush=True)

    t1 = time.time()
    try:
        # MongoClient connects lazily, so run a real command to force the
        # connection and TLS handshake now.
        _get_collection().database.command("ping")
        print(f"TIMING warm-up mongo ready in {time.time() - t1:.2f}s", flush=True)
    except Exception as e:
        print(f"warm-up mongo failed: {e}", flush=True)


##_warm_up()        

"""Step 4: embed warnings, side-effect and indication chunks and load into MongoDB Atlas.
pip install pymongo sentence-transformers
export MONGODB_URI="mongodb+srv://..."
Usage: python embed_load.py [chunks/labels.jsonl]
"""
import json, os, sys, time
from pymongo import MongoClient
from pymongo.operations import SearchIndexModel
from sentence_transformers import SentenceTransformer

PATH = sys.argv[1] if len(sys.argv) > 1 else "chunks/labels.jsonl"
MAX_LABELS = 5000        # cap counted in whole labels, so no drug is cut off halfway
BATCH = 64
PROGRESS_EVERY = 1000    # print a progress line every this many chunks

KEY_WORDS = ["warning", "adverse", "indication"]   # warnings, side effects, what the drug is for


def is_key(section):
    s = (section or "").lower()
    return any(w in s for w in KEY_WORDS)


def label_id(c):
    return c.get("label_id") or c.get("id") or c.get("drug")


def read_chunks(quiet=False):
    kept, skipped = 0, 0
    seen_set = set()
    with open(PATH, encoding="utf-8") as f:
        for line in f:
            c = json.loads(line)
            lid = label_id(c)
            if lid not in seen_set:
                if len(seen_set) >= MAX_LABELS:
                    break
                seen_set.add(lid)
            if is_key(c.get("section")):
                kept += 1
                yield c
            else:
                skipped += 1
    if not quiet:
        print(f"Labels read: {len(seen_set)}  kept chunks: {kept}  skipped: {skipped}")


def main():
    print("Counting chunks to load (quick pass)...")
    expected = sum(1 for _ in read_chunks(quiet=True))
    print(f"Will embed and load {expected} chunks.")

    col = MongoClient(os.environ["MONGODB_URI"])["druglabels"]["chunks"]
    model = SentenceTransformer("all-MiniLM-L6-v2")

    batch, total, t0 = [], 0, time.time()
    next_report = PROGRESS_EVERY

    def flush():
        nonlocal batch, total, next_report
        if not batch:
            return
        vecs = model.encode([b["text"] for b in batch], normalize_embeddings=True)
        for b, v in zip(batch, vecs):
            b["embedding"] = v.tolist()
        col.insert_many(batch)
        total += len(batch)
        batch = []
        if total >= next_report or total >= expected:
            el = time.time() - t0
            rate = total / el if el else 0
            left = (expected - total) / rate if rate else 0
            print(f"  {total}/{expected} ({100*total/expected:.0f}%)  "
                  f"{rate:.0f} chunks/s  about {left/60:.1f} min left")
            while next_report <= total:
                next_report += PROGRESS_EVERY

    for c in read_chunks():
        batch.append(c)
        if len(batch) >= BATCH:
            flush()
    flush()

    stats = col.database.command("collstats", "chunks")
    print(f"Done. {col.count_documents({})} chunks, "
          f"data {stats['size']/1e6:.0f} MB, storage {stats['storageSize']/1e6:.0f} MB "
          f"(free tier limit is 512 MB)")

    try:
        col.create_search_index(SearchIndexModel(
            name="vector_index", type="vectorSearch",
            definition={"fields": [{"type": "vector", "path": "embedding",
                                    "numDimensions": 384, "similarity": "cosine"}]}))
        print("Vector index requested. It takes a minute or two to become ready.")
    except Exception as e:
        print("Index not created (may already exist, or create it in the Atlas UI):", e)


if __name__ == "__main__":
    main()
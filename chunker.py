import json, re, sys
from pathlib import Path
import ijson

OUT_DIR = Path("chunks")
CHUNK_WORDS, OVERLAP_WORDS = 300, 40
SKIP_KEYS = {"id", "set_id", "version", "effective_time", "openfda", "spl_id", "spl_product_data_elements"}


def drug_name(label):
    ofda = label.get("openfda") or {}
    for key in ("generic_name", "brand_name", "substance_name"):
        v = ofda.get(key)
        if v:
            return v[0] if isinstance(v, list) else str(v)
    spl = label.get("spl_product_data_elements")
    if spl:
        text = spl[0] if isinstance(spl, list) else str(spl)
        return " ".join(text.split()[:3])
    return "unknown"


def field_text(value):
    if isinstance(value, list):
        return " ".join(str(v) for v in value)
    return value if isinstance(value, str) else ""


def split_text(text, size=CHUNK_WORDS, overlap=OVERLAP_WORDS):
    text = re.sub(r"\s+", " ", text).strip()
    if len(text.split()) <= size:
        return [text] if text else []
    sents = []
    for s in re.split(r"(?<=[.!?])\s+", text):
        w = s.split()
        sents += [" ".join(w[i:i + size]) for i in range(0, len(w), size)] if len(w) > size else [s]
    chunks, cur, n = [], [], 0
    for s in sents:
        k = len(s.split())
        if cur and n + k > size:
            chunks.append(" ".join(cur))
            tail, tn = [], 0
            for prev in reversed(cur):
                pk = len(prev.split())
                if tn + pk > overlap:
                    break
                tail.insert(0, prev); tn += pk
            cur, n = tail, tn
        cur.append(s); n += k
    if cur:
        chunks.append(" ".join(cur))
    return chunks


def main(path):
    OUT_DIR.mkdir(exist_ok=True)
    labels = chunks = 0
    with open(path, "rb") as f, open(OUT_DIR / "labels.jsonl", "w", encoding="utf-8") as out:
        # streams each label under "results" one at a time, never loads the whole file
        for label in ijson.items(f, "results.item", use_float=True):
            labels += 1
            drug = drug_name(label)
            for key, value in label.items():
                if key in SKIP_KEYS:
                    continue
                for piece in split_text(field_text(value)):
                    rec = {"drug": drug, "section": key.replace("_", " "), "text": piece}
                    out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    chunks += 1
            if labels % 1000 == 0:
                print(f"{labels} labels, {chunks} chunks so far...", file=sys.stderr)
    print(f"Done: {labels} labels -> {chunks} chunks in {OUT_DIR / 'labels.jsonl'}")


if __name__ == "__main__":
    main(sys.argv[1])
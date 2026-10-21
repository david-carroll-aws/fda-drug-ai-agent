import os
import requests

OPENFDA_LABEL_URL = "https://api.fda.gov/drug/label.json"

FIELDS = [
    "indications_and_usage",
    "dosage_and_administration",
    "warnings",
    "boxed_warning",
    "adverse_reactions",
    "contraindications",
]


def get_drug_label(drug_name: str, max_chars: int = 1500) -> dict:
    """Look up the FDA drug label for a brand or generic drug name."""

    name = drug_name.strip().lower()
    query = f'openfda.brand_name:"{name}" OR openfda.generic_name:"{name}"'
    try:
        resp = requests.get(
            OPENFDA_LABEL_URL,
            params={"search": query, "limit": 1, "api_key": os.environ.get("OPENFDA_API_KEY")},
            timeout=10,
        )
        if resp.status_code == 404:
            return {"found": False, "drug": drug_name, "message": "No label found."}
        resp.raise_for_status()
        label = resp.json()["results"][0]
    except requests.RequestException as e:
        return {"found": False, "drug": drug_name, "error": str(e)}

    openfda = label.get("openfda", {})
    result = {
        "found": True,
        "drug": drug_name,
        "brand_name": openfda.get("brand_name", []),
        "generic_name": openfda.get("generic_name", []),
        "manufacturer": openfda.get("manufacturer_name", []),
    }
    for field in FIELDS:
        if field in label:
            result[field] = " ".join(label[field])[:max_chars]
    return result


if __name__ == "__main__":
    import json
    print(json.dumps(get_drug_label("ibuprofen"), indent=2))

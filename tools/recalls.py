import requests

OPENFDA_RECALL_URL = "https://api.fda.gov/drug/enforcement.json"


def get_drug_recalls(drug_name: str, limit: int = 5) -> dict:
    """Get the most recent FDA recalls for a drug. Use this when the user asks
    whether a drug has been recalled, or about recall reasons or safety actions."""
    name = drug_name.strip().lower()
    query = (
        f'openfda.brand_name:"{name}" OR openfda.generic_name:"{name}" '
        f'OR product_description:"{name}"'
    )
    try:
        resp = requests.get(
            OPENFDA_RECALL_URL,
            params={"search": query, "sort": "report_date:desc", "limit": limit},
            timeout=15,
        )
        if resp.status_code == 404:
            return {"found": False, "drug": drug_name, "message": "No recalls found."}
        resp.raise_for_status()
        results = resp.json().get("results", [])
    except requests.RequestException as e:
        return {"found": False, "drug": drug_name, "error": str(e)}

    return {
        "found": True,
        "drug": drug_name,
        "recalls": [
            {
                "date": r.get("report_date"),
                "classification": r.get("classification"),
                "status": r.get("status"),
                "firm": r.get("recalling_firm"),
                "reason": (r.get("reason_for_recall") or "")[:400],
                "product": (r.get("product_description") or "")[:200],
            }
            for r in results
        ],
    }


if __name__ == "__main__":
    import json
    print(json.dumps(get_drug_recalls("ibuprofen"), indent=2))
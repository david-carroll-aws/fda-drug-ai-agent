import requests

OPENFDA_EVENT_URL = "https://api.fda.gov/drug/event.json"


def get_adverse_events(drug_name: str, top_n: int = 10) -> dict:
    """Get the most commonly reported side effects (adverse events) for a drug
    from FDA's FAERS database. Use this when the user asks what problems or
    side effects people have actually reported with a drug."""
    name = drug_name.strip().lower()
    query = (
        f'patient.drug.openfda.brand_name:"{name}" '
        f'OR patient.drug.openfda.generic_name:"{name}"'
    )
    try:
        resp = requests.get(
            OPENFDA_EVENT_URL,
            params={
                "search": query,
                "count": "patient.reaction.reactionmeddrapt.exact",
                "limit": top_n,
            },
            timeout=15,
        )
        if resp.status_code == 404:
            return {"found": False, "drug": drug_name, "message": "No adverse event reports found."}
        resp.raise_for_status()
        results = resp.json().get("results", [])
    except requests.RequestException as e:
        return {"found": False, "drug": drug_name, "error": str(e)}

    return {
        "found": True,
        "drug": drug_name,
        "note": "Counts are voluntary reports to FDA, not proof the drug caused the reaction.",
        "top_reported_reactions": [
            {"reaction": r["term"].title(), "reports": r["count"]} for r in results
        ],
    }


if __name__ == "__main__":
    import json
    print(json.dumps(get_adverse_events("ibuprofen"), indent=2))
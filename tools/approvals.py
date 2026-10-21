import requests

OPENFDA_APPROVAL_URL = "https://api.fda.gov/drug/drugsfda.json"


def get_drug_approvals(drug_name: str, limit: int = 3) -> dict:
    """Get FDA approval history for a drug: who makes it, when it was first
    approved, and its forms and marketing status. Use this when the user asks
    when a drug was approved, who makes it, or whether it is prescription or OTC."""
    name = drug_name.strip().lower()
    query = f'openfda.brand_name:"{name}" OR openfda.generic_name:"{name}"'
    try:
        resp = requests.get(
            OPENFDA_APPROVAL_URL,
            params={"search": query, "limit": limit},
            timeout=15,
        )
        if resp.status_code == 404:
            return {"found": False, "drug": drug_name, "message": "No approval records found."}
        resp.raise_for_status()
        results = resp.json().get("results", [])
    except requests.RequestException as e:
        return {"found": False, "drug": drug_name, "error": str(e)}

    applications = []
    for app in results:
        original = next(
            (s for s in app.get("submissions", [])
             if s.get("submission_type") == "ORIG" and s.get("submission_status") == "AP"),
            {},
        )
        applications.append({
            "application_number": app.get("application_number"),
            "sponsor": app.get("sponsor_name"),
            "original_approval_date": original.get("submission_status_date"),
            "products": [
                {
                    "brand_name": p.get("brand_name"),
                    "dosage_form": p.get("dosage_form"),
                    "route": p.get("route"),
                    "marketing_status": p.get("marketing_status"),
                }
                for p in app.get("products", [])[:5]
            ],
        })

    return {"found": True, "drug": drug_name, "applications": applications}


if __name__ == "__main__":
    import json
    print(json.dumps(get_drug_approvals("ibuprofen"), indent=2))
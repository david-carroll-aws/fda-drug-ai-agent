import os
import requests

OPENFDA_APPROVAL_URL = "https://api.fda.gov/drug/drugsfda.json"


def get_drug_approvals(drug_name: str, limit: int = 3) -> dict:
    """Get FDA approval history for a drug: who makes it, when it was first//
    approved, and its forms and marketing status. Use this when the user asks
    when a drug was approved, who makes it, or whether it is prescription or OTC."""
    name = drug_name.strip().lower()
    base = f'(openfda.brand_name:"{name}" OR openfda.generic_name:"{name}")'
    key = os.environ.get("OPENFDA_API_KEY")
    results = []
    try:
        # Brand-name (NDA) approvals first; fall back to everything if none
        for query in (f"{base} AND application_number:NDA*", base):
            resp = requests.get(
                OPENFDA_APPROVAL_URL,
                params={"search": query, "limit": 50, "api_key": key},
                timeout=15,
            )
            if resp.status_code == 200:
                results = resp.json().get("results", [])
                if results:
                    break
        if not results:
            return {"found": False, "drug": drug_name, "message": "No approval records found."}
    except requests.RequestException as e:
        return {"found": False, "drug": drug_name, "error": str(e)}

    applications = []
    for app in results:
        original = next(
            (s for s in app.get("submissions", [])
             if s.get("submission_type") == "ORIG" and s.get("submission_status") == "AP"),
            {},
        )
        products, seen = [], set()
        for p in app.get("products", []):
            strength = ", ".join(i.get("strength", "") for i in p.get("active_ingredients", []))
            key_ = (p.get("brand_name"), p.get("dosage_form"), strength)
            if key_ in seen:
                continue
            seen.add(key_)
            products.append({
                "brand_name": p.get("brand_name"),
                "dosage_form": p.get("dosage_form"),
                "strength": strength,
                "marketing_status": p.get("marketing_status"),
            })
        ingredients = {i.get("name") for p in app.get("products", [])
                       for i in p.get("active_ingredients", [])}
        applications.append({
            "application_number": app.get("application_number"),
            "sponsor": app.get("sponsor_name"),
            "original_approval_date": original.get("submission_status_date"),
            "single_ingredient": len(ingredients) == 1,
            "products": products[:5],
        })

    # Brand-name (NDA) single-ingredient approvals first, oldest first
    applications.sort(key=lambda a: (
        not (a["application_number"] or "").startswith("NDA"),
        not a["single_ingredient"],
        a["original_approval_date"] or "99999999",
    ))

    return {"found": True, "drug": drug_name, "applications": applications[:limit]}


if __name__ == "__main__":
    import json
    print(json.dumps(get_drug_approvals("amlodipine"), indent=2))
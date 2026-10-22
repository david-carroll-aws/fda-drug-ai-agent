import os
import requests

def get_drug_interactions(drug_name: str) -> dict:
    """Get the official FDA label section on drug interactions for a medicine:
    other drugs, foods or substances it should not be combined with.
    Use this when the user asks whether a drug can be taken with something else. 
    Always use this for questions like “can I take X with Y”, including food, grapefruit and alcohol."""
    r = requests.get(
        "https://api.fda.gov/drug/label.json",
        params={
            "search": f'openfda.brand_name:"{drug_name}" OR openfda.generic_name:"{drug_name}"',
            "limit": 1,
            "api_key": os.environ.get("OPENFDA_API_KEY"),
        },
        timeout=15,
    )
    if r.status_code != 200:
        return {"drug": drug_name, "error": "No label found"}
    label = r.json()["results"][0]
    return {
        "drug": drug_name,
        "interactions": label.get("drug_interactions", ["No interactions section on this label"]),
    }
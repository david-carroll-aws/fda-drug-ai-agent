# FDA Drug AI Agent

**[View it live here](https://fda-drug-ai-agent-988398630438.us-east1.run.app/)**

You can view the application from my website, [davidcarroll.cloud](https://davidcarroll.cloud), or directly on the Google Cloud Run server at the link above.

<!-- Demo video placeholder: replace PASTE_VIDEO_LINK_HERE with your short video link -->
[Watch the demo video](PASTE_VIDEO_LINK_HERE)

---

A tool-calling AI agent that answers plain-English questions about medicines using live data from the FDA's public openFDA API (drug labels, reported side effects, recalls, approvals and interactions) plus a semantic search over FDA label text stored in MongoDB. Every answer comes with an **Agent decision trail** showing which tools the agent chose, what it searched for, and exactly what came back.

**Stack:** Python, Flask, Gemini on Vertex AI (Google GenAI SDK), openFDA, MongoDB Atlas Vector Search, sentence-transformers, Google Cloud Run.

> Not medical advice. Answers summarise public FDA records and can be incomplete or out of date.

---

## Why this is an agent, not just an API wrapper

There are no routing rules in the code. Nothing says "if the question mentions recalls, call the recalls endpoint". The model reads each question and decides for itself:

- **which** tools to call (one, several, or none),
- **what** to pass them (the drug name it extracted),
- and **how** to turn the results into an answer.

The decision trail makes those choices visible. Some examples from testing:

| Input | What the agent did |
|---|---|
| "Have there been any recalls?" (Lipitor selected) | Called the recalls tool only, for Lipitor |
| "What are the official warnings, and what side effects have people actually reported?" | Called two tools: label and adverse events |
| Just the word "Tylenol" | Decided on its own to call four tools at once |
| "Can I take it with grapefruit?" (Lipitor selected) | Called the interactions tool only, for Lipitor |
| "Is coffee bad for you?" | Called no tools and explained it only covers FDA-regulated drugs |

---

## Architecture

```mermaid
flowchart LR
    U[Browser<br/>index.html] -->|question + current drug| F[Flask app<br/>app.py on Cloud Run]
    F -->|prompt + tool definitions| G[Gemini<br/>Vertex AI]
    G -->|tool calls| T[Python tools]
    T -->|HTTPS| O[(openFDA API)]
    O --> T
    T -->|vector search| M[(MongoDB Atlas<br/>label chunks)]
    M --> T
    T -->|results| G
    G -->|answer| F
    F -->|answer + decision trail| U
```

1. The browser sends the question plus the **current drug**, the only state carried between questions.
2. Flask passes the question to Gemini along with the six tool functions. The SDK turns each function's signature and docstring into a tool definition the model can see.
3. Gemini decides which tools to call. Each call is wrapped by a small `logged` decorator that records the tool name, arguments and result.
4. Flask returns the answer and the recorded calls, and the page renders them as the decision trail.

---

## The tools

| Tool | Data source | Answers |
|---|---|---|
| `get_drug_label` | openFDA `/drug/label.json` | Uses, dosage, warnings, boxed warnings, contraindications |
| `get_adverse_events` | openFDA `/drug/event.json` | Most-reported side effects, with counts |
| `get_drug_recalls` | openFDA `/drug/enforcement.json` | Recall history: date, class, firm, reason |
| `get_drug_approvals` | openFDA `/drug/drugsfda.json` | Original approval date, sponsor, products and strengths |
| `get_drug_interactions` | openFDA `/drug/label.json` | Drugs, foods and drinks to avoid combining it with |
| `search_label_passages` | MongoDB Atlas vector index (`druglabels.chunks`) | Open-ended questions about what a label says, matched by meaning rather than keywords |

Each tool is a plain Python function in `tools/`. Its docstring tells the model when to use it.

---

## Semantic label search (MongoDB vector search)

The first five tools call openFDA live. The sixth, `search_label_passages`, searches FDA label text that was prepared ahead of time and stored in MongoDB Atlas. It suits open-ended questions such as food, alcohol, pregnancy or other specific situations, where a keyword lookup would miss the relevant passage.

**How the data was prepared**

1. Label text was split into chunks with plain Python. Each chunk records its drug, label section and text.
2. Each chunk was embedded with the `all-MiniLM-L6-v2` sentence-transformers model (384 dimensions) and loaded into the `chunks` collection of the `druglabels` database.
3. An Atlas Vector Search index named `vector_index` (cosine similarity) was created on the `embedding` field.

The collection holds roughly 49,000 chunks covering about 4,900 distinct drugs.

**How a search runs**

1. The question is embedded with the same local model that embedded the stored chunks, so the vectors are comparable.
2. A `$vectorSearch` aggregation returns the closest chunks, searching the warnings, side effects and indications sections.
3. If the agent passes a drug name, the tool pulls extra candidates and then filters them with a case-insensitive partial match. The stored drug field is free text, so an exact filter inside the index would miss variants.
4. The top five passages come back with drug, section, text and a similarity score, and show up in the decision trail like any other tool result.

If nothing matches, or the database call fails, the tool returns a plain message instead of raising an error, so the agent can still answer.

---

## Design decisions

**Only the drug name is kept as state.** The model itself is stateless, so "memory" means resending context with each request. Resending the full conversation made a small model answer from earlier replies instead of calling tools. Now each question starts a fresh chat and carries only the current drug, so follow-ups like "any recalls?" still work, and every answer is grounded in a new tool call.

**The decision trail is logged at the tool, not read from model history.** Wrapping each tool in a `logged` decorator records exactly what ran, independently of what the SDK chooses to expose.

**Docstrings steer tool choice.** The label and interactions tools both read the drug label, so at first the agent answered grapefruit questions with the general label tool. One sentence in each docstring, telling the model which tool owns interaction questions, fixed it, with no routing code.

**Readable results first, raw JSON second.** The trail renders each tool's output in plain form (reaction bars, colour-coded recall classes, approval cards), with the raw FDA response one click away.

**Approvals favour the original brand.** Popular drugs have hundreds of generic approvals, so the approvals tool asks for brand-name (NDA) applications first, sorts single-ingredient and oldest approvals to the top, and removes duplicate product lines.

**Friendly failure.** If Gemini's rate limit is hit (HTTP 429), visitors see "please wait a minute" instead of a stack trace. Other errors return a generic message, and details stay in the server logs.

**Secrets stay out of the repo.** The openFDA API key and the MongoDB connection string live in a local `.env` file (git-ignored) and as environment variables on Cloud Run.

**Model choice.** Built on Gemini first because it was immediately available on Vertex AI. The tool layer is model-agnostic, and a move to Claude on Amazon Bedrock is planned.

---

## Known limitations

- **Misspellings can be silently "corrected".** In testing, "lbuterol" was searched as *levalbuterol*, a different drug. The decision trail exposes this, which is part of why it exists.
- **openFDA data is uneven.** Older drugs approved before modern records (levothyroxine, for example) may not show their original brand approval.
- **The vector index covers a subset of labels.** It holds a sample of FDA label data, not every label, so a drug missing from it returns no passages. The live openFDA tools are not limited this way.
- **Semantic matches are approximate.** Passages are ranked by similarity of meaning, so a result can be related to the question without answering it directly. The score and source section are shown so you can judge.
- **Speed and quotas.** A question can involve several model round trips. Heavy use can hit Vertex AI rate limits.

---

## Running locally

```bash
git clone https://github.com/david-carroll-aws/fda-drug-ai-agent.git
cd fda-drug-ai-agent
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```
OPENFDA_API_KEY=your-openfda-key
MONGO_URL=your-mongodb-atlas-connection-string
```

A free key is available from [open.fda.gov](https://open.fda.gov/apis/authentication/). The app works without one, at a lower daily limit. `MONGO_URL` is needed for the label passage search and must point to an Atlas cluster containing the `druglabels.chunks` collection with its `vector_index`. The embedding model downloads automatically the first time a passage search runs. You also need Google Cloud credentials with Vertex AI access (`gcloud auth application-default login`).

```bash
python app.py
```

Then open http://localhost:8080 (or whatever port app.py prints).

## Deploying to Cloud Run

```bash
gcloud run deploy fda-drug-ai-agent --source . --region us-east1 \
  --allow-unauthenticated \
  --set-env-vars OPENFDA_API_KEY=your-openfda-key,MONGO_URL=your-mongodb-atlas-connection-string
```

---

## Roadmap

- Switch the model to Claude on Amazon Bedrock
- Ask the user to confirm misspelt drug names instead of guessing
- Stream the decision trail live as each tool runs
- Auto-deploy to Cloud Run from GitHub Actions
- Move the API key and MongoDB connection string to Google Secret Manager

## Data source

Drug data comes from [openFDA](https://open.fda.gov/), a public service of the U.S. Food and Drug Administration, including the label text stored in the MongoDB vector index. This project is not affiliated with or endorsed by the FDA.

## Licence

MIT

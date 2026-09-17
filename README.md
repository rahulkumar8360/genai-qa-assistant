# Document Q&A Assistant

An end-to-end assistant that answers questions about a folder of documents (`.txt`, `.md`, `.pdf`). Every answer cites the passage it came from, and when the documents don't hold the answer it says so instead of guessing. The answers come from Claude, steered by a designed system prompt and few-shot examples. An evaluation harness scores each version of the prompt so every prompt change is backed by a measurement.

It ships with a small fictional company handbook in `data/docs/` (leave, expenses, IT security, remote work) and 24 evaluation questions about it.

```
question ──► retriever (BM25) ──► top 4 passages ──► prompt builder ──► Claude ──► answer + [n] citations
               │                                     (system prompt,               │
               └── heading-aware chunks              few-shot, history)            └── parsed back to file › section
```

## Quick start

```bash
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and set `ANTHROPIC_API_KEY`. Without a key everything still runs in **offline mode**, described below.

| What | Command |
|---|---|
| Web app (chat, citations, upload) | `python app.py`, then open http://127.0.0.1:8000 |
| Terminal chat | `python cli.py` |
| One question | `python cli.py "How long must passwords be?"` |
| Your own documents | `python cli.py --docs path/to/folder` |
| Tests (under 10 s, no key needed) | `pip install -r requirements-dev.txt` then `python -m pytest -q` |
| In Docker | `docker build -t genai-qa-assistant . && docker run -p 8000:8000 genai-qa-assistant` |
| Evaluation, offline | `python evaluate.py` |
| Evaluation, Claude, all prompt versions | `python evaluate.py --backend claude` |

## How it works

Each step is one module in `qa/`. A module only knows about the step before it, so any step can be replaced without touching the others.

| Module | Job | Key decision |
|---|---|---|
| `loader.py` | Reads files into pages of text | PDFs keep their real page numbers so citations can say "page 3" |
| `chunker.py` | Cuts pages into ~120-word passages with a 30-word overlap | Markdown is split at headings first, so a passage never mixes two topics. The heading travels with the passage. |
| `retriever.py` | Ranks passages against the question with BM25 | Keyword search needs no second model and is deterministic, which keeps the eval repeatable. The heading is indexed too, which is how "sick days" finds a paragraph that only says "10 days". |
| `prompts.py` | Builds the system prompt and message list | Three prompt versions kept side by side (see below) |
| `llm.py` | Sends the request to a backend | Claude, or the offline stand-in. Both return the same shape. |
| `assistant.py` | Wires it together and parses `[n]` citations back to passages | Skips the model call entirely when no passage matches, because an answer then could only come from general knowledge |

The web app (`app.py` + `static/index.html`), the CLI (`cli.py`) and the evaluator (`evaluate.py`) all call the same `Assistant.ask(question, history)`. Conversation history is owned by the caller, so one assistant serves many browser sessions.

### Follow-up questions

"And for international trips?" has no topic of its own. When a question has at most one content word, or uses a referring word (*it, that, those…*) or opening (*and…, what about…*), the previous question's words are added **to the search only**. The model still sees the question as asked, plus the last three turns of conversation.

## Prompt engineering

The prompts in `qa/prompts.py` are the refinement history of this assistant, kept as three versions:

| Version | What it adds | The problem it addresses |
|---|---|---|
| **v1** baseline | One line: "Answer the user's question using the documents provided." | Starting point |
| **v2** grounded | A full system prompt: use only the passages; cite each fact as `[n]`; when the answer is missing, reply with one fixed sentence; answer partially covered questions partially; report disagreements; lead with the answer and keep it short; use history only to resolve what a follow-up means | Invented details, answers that don't say where a fact came from, and hedged non-answers the UI can't detect |
| **v3** few-shot | v2 plus two worked examples: one answered with citations, one correctly declined | A rule saying "decline when unsure" is followed less reliably than an example of declining |

Design choices worth knowing:

- **Passages go in XML tags, numbered from 1, question last.** `<document index="2" source="expense-policy.md > Hotels">`. The number is what the model cites, and the parser maps it straight back to a file and section. Passage text is escaped so a document can't close its own tag.
- **The few-shot examples use a made-up library lending policy**, not the company documents. They teach the format without leaking any answer the eval checks.
- **The refusal is one exact sentence** (`config.NOT_FOUND_ANSWER`). The UI highlights it and the evaluator scores it by matching that sentence.
- **Past turns are replayed without their old passages.** That's enough to resolve "what about contractors?" and stops the request from growing by four passages every turn.

### Model settings

`claude-opus-5` through the official `anthropic` SDK (`qa/llm.py`). Thinking is left at the model's default (adaptive), with `effort: medium`, since grounded Q&A over four passages is routine work. Raise it in `config.py` if the eval shows better answers at `high`. The request also enables server-side refusal fallbacks: if Claude's safety classifier declines, the API re-runs the request on `claude-opus-4-8` in the same call. A refusal or a truncated answer is detected from `stop_reason` and never shown as a normal answer. API errors (bad key, rate limit, network) become one plain message in the UI.

## Evaluation

`python evaluate.py [--backend claude] [--versions v1 v3]` runs every question in `eval/eval_set.json` through the assistant, once per prompt version, each question on its own with no history. It writes `eval/reports/<time>-<backend>.md` and a `.json` copy for diffing runs.

The Claude run asks for confirmation first, because it makes 24 × 3 = 72 API calls.

| Column | Meaning |
|---|---|
| Overall | Correct answers plus correct refusals, over all 24 questions |
| Answer acc. | Answerable questions whose answer has every expected keyword and isn't a refusal |
| Retrieval hit | The expected **file** is among the 4 passages retrieved. This measures the retriever alone, with no model involved. |
| Cited right file | At least one `[n]` in the answer points into the expected file |
| False refusals | Answerable questions the assistant declined |
| Refusal acc. | Of the 6 questions the documents don't cover, how many were declined |
| Invented cites | `[n]` markers pointing at a passage that doesn't exist. Should always be 0. |

The report then lists every failure with the question, the answer, and why it failed (not retrieved / declined / missing keyword / answered when it should have declined).

**Results so far are in [FINDINGS.md](FINDINGS.md).**

## Offline mode

With no API key (or `QA_BACKEND=offline`), `OfflineBackend` stands in for the model. It quotes the one or two retrieved sentences that share at least half of the question's content words and declines otherwise. It exists so the app, the CLI and the tests run on any machine. **It is not an LLM and it ignores the prompt**, so it tells you nothing about prompt quality. The evaluator runs it once, not once per prompt version.

## Deploying

`Dockerfile` + `render.yaml` deploy it to Render's free plan as a container, in
offline mode (no API key, no cost) with uploads switched off because the URL is
public. Full steps, how to switch on real Claude answers, and what was verified
locally: **[DEPLOY.md](DEPLOY.md)**.

## Configuration

Every path, model name, size and threshold is in `config.py`, and nothing is hardcoded elsewhere. The ones you're most likely to change:

| Setting | Default | Env override |
|---|---|---|
| `BACKEND` | `auto` (Claude if a key is set, otherwise offline) | `QA_BACKEND` |
| `MODEL` | `claude-opus-5` | `QA_MODEL` |
| `EFFORT` | `medium` | `QA_EFFORT` |
| `PROMPT_VERSION` | `v3` | `QA_PROMPT_VERSION` |
| `ALLOW_UPLOADS` | on locally, off on the deployment | `QA_ALLOW_UPLOADS` |
| `TOP_K` | 4 passages per question | |
| `CHUNK_WORDS` / `CHUNK_OVERLAP_WORDS` | 120 / 30 | |
| `HISTORY_TURNS` | 3 | |

## Tests

`python -m pytest -q` runs 51 tests in a few seconds. The suite forces the offline backend (see `tests/conftest.py`), so it never calls the API even when a key is set.

| File | Covers |
|---|---|
| `test_chunker.py` | Heading splits, window overlap, chunks never crossing a heading |
| `test_retriever.py` | Stemming, hyphenated words, ranking, heading search, empty cases |
| `test_prompts.py` | Passage numbering and escaping, what each version contains, message order, history cap |
| `test_assistant.py` | Citation parsing incl. invented numbers, refusal detection, follow-ups, end-to-end on the sample docs |
| `test_claude_backend.py` | The exact API request (model, effort, fallbacks), thinking blocks dropped from the answer, refusal and truncation handling. Uses a fake client, no network. |
| `test_loader.py` | PDF pages (from a PDF built inside the test), folder filtering |
| `test_app.py` | Web API: ask, per-session history, upload → ask → delete, file-type and sample-doc protections, uploads switched off |

## Project layout

```
Dockerfile           container image
render.yaml          Render blueprint
config.py            all settings
qa/                  the pipeline (loader, chunker, retriever, prompts, llm, assistant)
app.py               FastAPI server  ─┐
static/index.html    chat page       ─┴─ web app
cli.py               terminal chat
evaluate.py          scoring harness
data/docs/           sample documents (fictional company)
data/uploads/        files uploaded through the web app (git-ignored)
eval/eval_set.json   24 questions with expected keywords and source file
eval/reports/        evaluation reports
tests/               pytest suite
```

## What this does not prove

- **No Claude results have been measured yet.** The machine it was built on had no API key. The prompt-version comparison (v1 vs v2 vs v3) is built and runs with one command, but no numbers for it exist until that command is run. [FINDINGS.md](FINDINGS.md) only reports what was actually run.
- **24 questions is a smoke test, not a benchmark.** One question is about 4 points of accuracy, so a difference of one or two questions between prompt versions is noise.
- **The same person wrote the documents and the questions**, so they share vocabulary. That flatters keyword retrieval. Real users say "vacation" where the policy says "annual leave", and BM25 has no notion of synonyms.
- **Retrieval hit is file-level**: it counts a hit if any passage from the right file is retrieved, not necessarily the passage holding the answer.
- **Keyword grading is coarse.** It fails a correct "twenty-four days" and passes a wrong answer that happens to contain "24". Read the failure list in the report, not just the percentages.
- **One index, in memory, rebuilt on every upload.** Fine for a handful of documents, not a document store.
- **The web app has no authentication.** The public deployment is safe only because it runs offline (nothing to spend) with uploads disabled (nothing to write). Adding an API key to a public URL without an access gate means strangers can spend your credit - see [DEPLOY.md](DEPLOY.md).

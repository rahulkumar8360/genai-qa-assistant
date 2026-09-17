# The testing harness: runs every question in eval/eval_set.json through the
# assistant, once per prompt version, and scores the answers.
#
#   python evaluate.py                      # offline backend, no key needed
#   python evaluate.py --backend claude     # all prompt versions against Claude
#   python evaluate.py --backend claude --versions v2 v3
#
# What is scored, per question:
#   retrieval hit   the expected file is among the passages retrieved
#                   (measures the retriever alone - no model involved)
#   correct         every expected keyword is in the answer and it is not a refusal
#   cited source    at least one [n] citation points into the expected file
#   invented cite   a [n] that points at no passage at all
#   refusal         for questions the documents do not cover, declining is correct
#
# A report is written to eval/reports/ as JSON (for diffing runs) and markdown
# (for reading). How to read it is in README.md.

import argparse
import json
import os
import sys
import time

import config
from qa.assistant import build_default_assistant
from qa.llm import has_api_credentials
from qa.prompts import PROMPTS


def load_eval_set(path=None):
    with open(path or config.EVAL_FILE, encoding="utf-8") as f:
        return json.load(f)["questions"]


def keyword_found(keyword, answer):
    lowered = answer.lower()
    return any(option.strip().lower() in lowered for option in keyword.split("|"))


def score_one(item, result):
    sources = [r["source"] for r in result["retrieved"]]
    cited = [c["source"] for c in result["citations"]]
    row = {
        "id": item["id"],
        "question": item["question"],
        "answerable": item["answerable"],
        "answer": result["answer"],
        "refused": result["refused"],
        "retrieved": sources,
        "cited": cited,
        "invented_citations": result["invalid_citations"],
        "usage": result["usage"],
        "latency_ms": result["latency_ms"],
    }

    if item["answerable"]:
        missing = [k for k in item["keywords"] if not keyword_found(k, result["answer"])]
        row["missing_keywords"] = missing
        row["retrieval_hit"] = item["source"] in sources
        row["cited_source"] = item["source"] in cited
        row["correct"] = not missing and not result["refused"]
    else:
        row["correct"] = result["refused"]
    return row


def summarise(rows):
    answerable = [r for r in rows if r["answerable"]]
    unanswerable = [r for r in rows if not r["answerable"]]

    def share(items, key):
        return round(sum(1 for r in items if r[key]) / len(items), 3) if items else None

    return {
        "questions": len(rows),
        "overall_accuracy": share(rows, "correct"),
        "answer_accuracy": share(answerable, "correct"),
        "retrieval_hit_rate": share(answerable, "retrieval_hit"),
        "cited_source_rate": share(answerable, "cited_source"),
        "false_refusal_rate": share(answerable, "refused"),
        "refusal_accuracy": share(unanswerable, "correct"),
        "invented_citations": sum(len(r["invented_citations"]) for r in rows),
        "input_tokens": sum(r["usage"]["input_tokens"] for r in rows),
        "output_tokens": sum(r["usage"]["output_tokens"] for r in rows),
        "avg_latency_ms": int(sum(r["latency_ms"] for r in rows) / len(rows)) if rows else 0,
    }


def run_version(backend_name, version, questions, top_k):
    assistant = build_default_assistant(backend_name, prompt_version=version)
    if top_k:
        assistant.top_k = top_k

    rows = []
    for i, item in enumerate(questions, start=1):
        # each question is asked on its own, with no history, so one answer
        # can never leak into the next
        result = assistant.ask(item["question"], history=None)
        row = score_one(item, result)
        rows.append(row)
        mark = "ok  " if row["correct"] else "FAIL"
        print("  [%s] %2d/%d %s" % (mark, i, len(questions), item["id"]))
    return {"version": version, "prompt_name": PROMPTS[version]["name"],
            "backend": assistant.backend.name, "model": getattr(assistant.backend, "model", None),
            "summary": summarise(rows), "rows": rows}


def pct(value):
    return "-" if value is None else "%.0f%%" % (value * 100)


def markdown_report(runs, started_at):
    lines = ["# Evaluation report", "",
             "Run at %s. Backend: %s. Model: %s. Top-k passages: %s." % (
                 started_at, runs[0]["backend"], runs[0]["model"], runs[0].get("top_k")), ""]

    lines += ["| Prompt | Overall | Answer acc. | Retrieval hit | Cited right file | False refusals | Refusal acc. | Invented cites | Tokens in/out |",
              "|---|---|---|---|---|---|---|---|---|"]
    for run in runs:
        s = run["summary"]
        lines.append("| %s (%s) | %s | %s | %s | %s | %s | %s | %d | %d / %d |" % (
            run["version"], run["prompt_name"], pct(s["overall_accuracy"]), pct(s["answer_accuracy"]),
            pct(s["retrieval_hit_rate"]), pct(s["cited_source_rate"]), pct(s["false_refusal_rate"]),
            pct(s["refusal_accuracy"]), s["invented_citations"], s["input_tokens"], s["output_tokens"]))

    for run in runs:
        failures = [r for r in run["rows"] if not r["correct"]]
        lines += ["", "## Failures - %s (%d)" % (run["version"], len(failures)), ""]
        if not failures:
            lines.append("None.")
        for r in failures:
            why = []
            if r["answerable"]:
                if not r["retrieval_hit"]:
                    why.append("expected file not retrieved")
                if r["refused"]:
                    why.append("declined an answerable question")
                elif r["missing_keywords"]:
                    why.append("missing: %s" % ", ".join(r["missing_keywords"]))
            else:
                why.append("answered a question the documents do not cover")
            lines += ["- **%s** - %s" % (r["id"], "; ".join(why)),
                      "  - Q: %s" % r["question"],
                      "  - A: %s" % r["answer"].replace("\n", " ")]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Score the Q&A assistant against eval/eval_set.json")
    parser.add_argument("--backend", default="offline", choices=["offline", "claude"])
    parser.add_argument("--versions", nargs="+", choices=sorted(PROMPTS), default=None,
                        help="prompt versions to compare (default: all for claude)")
    parser.add_argument("--top-k", type=int, default=None)
    parser.add_argument("--yes", action="store_true", help="skip the API cost confirmation")
    args = parser.parse_args()

    questions = load_eval_set()

    if args.backend == "offline":
        # the offline backend never reads the prompt, so scoring v1/v2/v3
        # separately would print three identical tables
        versions = args.versions or [config.PROMPT_VERSION]
        print("Offline backend: prompt versions do not affect its answers; "
              "this run measures retrieval and the pipeline only.")
    else:
        if not has_api_credentials():
            sys.exit("No ANTHROPIC_API_KEY found. Put it in .env or the environment.")
        versions = args.versions or sorted(PROMPTS)
        calls = len(questions) * len(versions)
        print("This makes up to %d calls to %s." % (calls, config.MODEL))
        if not args.yes and input("Continue? [y/N] ").strip().lower() != "y":
            sys.exit("Cancelled.")

    started_at = time.strftime("%Y-%m-%d %H:%M:%S")
    runs = []
    for version in versions:
        print("\nPrompt %s (%s)" % (version, PROMPTS[version]["name"]))
        run = run_version(args.backend, version, questions, args.top_k)
        run["top_k"] = args.top_k or config.TOP_K
        runs.append(run)

    os.makedirs(config.REPORTS_DIR, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    base = os.path.join(config.REPORTS_DIR, "%s-%s" % (stamp, args.backend))
    with open(base + ".json", "w", encoding="utf-8") as f:
        json.dump({"started_at": started_at, "runs": runs}, f, indent=2)
    report = markdown_report(runs, started_at)
    with open(base + ".md", "w", encoding="utf-8") as f:
        f.write(report)

    print()
    for run in runs:
        s = run["summary"]
        print("%s  overall %s | answers %s | retrieval %s | refusals %s | invented cites %d" % (
            run["version"], pct(s["overall_accuracy"]), pct(s["answer_accuracy"]),
            pct(s["retrieval_hit_rate"]), pct(s["refusal_accuracy"]), s["invented_citations"]))
    print("\nReport: %s.md" % base)


if __name__ == "__main__":
    main()

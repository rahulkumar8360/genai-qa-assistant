# Findings

Only results that were actually run are reported here. Last run: 2026-09-15.

## 1. Offline pipeline: measured

`python evaluate.py` on the 24 questions in `eval/eval_set.json` (18 answerable, 6 not covered by the documents). Backend: offline extractive baseline. Top-4 passages.

| Metric | Result |
|---|---|
| Overall (correct answers + correct refusals) | **22 / 24 (92%)** |
| Retrieval hit (right file in top 4) | 18 / 18 (100%) |
| Answer accuracy | 17 / 18 (94%) |
| Cited the right file | 17 / 18 (94%) |
| Refusal accuracy (questions the documents don't cover) | 5 / 6 (83%) |
| Invented citations | 0 |

Both failures are in the answer step. Retrieval got them right, and both are exactly the kind of question the offline stand-in can't handle:

| Question | What happened | Why |
|---|---|---|
| "How much paid time off do I get when someone in my immediate family dies?" | Declined, but the answer exists | The *Bereavement leave* passage **was ranked first**. The offline backend matches words, and the passage says "death" and "bereavement" where the question says "dies" and "paid time off". Recognising those as the same thing is language understanding, which is what the LLM is for. |
| "How much is the relocation allowance for new employees?" | Answered with the home-office allowance | The documents have no relocation allowance. The nearest passage, "New employees receive a one-time home office allowance of 400 dollars", shares "new", "employees" and "allowance". Saying it's a different allowance takes understanding; word overlap can't. v2/v3 tell the model to decline in exactly this case. |

What this measures: the plumbing (loading, chunking, retrieval, citation parsing, refusal detection, scoring) works end to end, and retrieval finds the right file for every answerable question in this set.

What it does not measure: anything about prompt quality. The offline backend never reads the prompt.

## 2. Claude and the prompt versions: not measured yet

No API key was available on the build machine, so v1 / v2 / v3 have not been run against Claude. To produce the numbers (72 calls):

```bash
python evaluate.py --backend claude
```

What the run is designed to test. These are **hypotheses, not results**:

1. v1 will fail more "not covered" questions than v2/v3 by answering from general knowledge (e.g. inventing a typical notice period), and will cite less often, because nothing asks it to.
2. v2 and v3 should decline the relocation question, which the offline baseline gets wrong.
3. v3 should decline more consistently than v2, because it has seen an example of declining.

Paste the report's summary table here when it runs, and replace the hypotheses with what happened, including any that turned out wrong.

## 3. Bugs found while building, and their fixes

| Found by | Problem | Fix |
|---|---|---|
| A unit test | The follow-up rule "≤ 3 content words means follow-up" also caught standalone questions: "How long must passwords be?" has 2, so after a hotel question its search was "hotel limit per night … passwords" | A question counts as a follow-up only with ≤ 1 content word, a referring word (*it, that, those…*), or a continuing opening (*and…, what about…*). Covered by `test_follow_up_detection`. |
| Trying the CLI | "Is it ok to use public wifi…" never retrieved the rule about "Public Wi-Fi": the tokenizer split *Wi-Fi* into "wi" + "fi" | Hyphenated words are indexed both joined and as parts, so "wifi" and "part time" both match. The Wi-Fi passage now ranks first. Eval unchanged at 22/24. |

One gap is known and left alone: after the Wi-Fi fix, the offline backend still declines that question. The right passage is retrieved, but its best sentence shares only 2 of 6 question words, under the 50% bar. Teaching the stemmer "remotely" → "remote" would fix this one question and break "family"/"families". It isn't worth distorting a baseline that exists only to run without a key.

## 4. Limits of these numbers

See "What this does not prove" in [README.md](README.md). In short: 24 questions is a smoke test, questions and documents share an author and vocabulary, retrieval hit is file-level, and keyword grading is coarse.

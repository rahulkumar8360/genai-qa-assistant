# The prompt templates, and the code that fills them in.
#
# Three versions are kept side by side on purpose. They are the refinement
# history of this assistant, and evaluate.py scores them against each other so
# every change to the prompt is justified by a number rather than a feeling:
#
#   v1  baseline   one line of instruction. Answers, but invents details when
#                  the passages are silent and rarely says where a fact came from.
#   v2  grounded   a real system prompt: answer only from the passages, cite
#                  each fact as [n], use one fixed sentence when the answer is
#                  missing, keep it short.
#   v3  few-shot   v2 plus two worked examples - one answered with citations,
#                  one correctly declined. Showing the refusal is what makes the
#                  model actually use it instead of hedging.
#
# The few-shot examples use a made-up library lending policy, not the company
# documents, so they teach the FORMAT without leaking any answer the eval checks.

import config

BASELINE_SYSTEM = "Answer the user's question using the documents provided."

GROUNDED_SYSTEM = """You are a question-answering assistant for a company's internal documents.

Each request contains numbered passages inside <documents> tags, followed by a question. The passages are the only source of truth: they were retrieved from the company's policy files for this question.

How to answer:
- Use only facts stated in the passages. Do not add figures, names, or rules from general knowledge, even if they seem likely to be true.
- After each sentence that uses a passage, cite it with its number in square brackets, like [2]. Cite every passage a sentence relies on, like [1][3].
- If the passages do not contain the answer, reply with exactly: "%s" Then, in one short sentence, say what the passages do cover, if anything related.
- If the passages answer only part of the question, answer that part with citations and say plainly which part is not covered.
- If passages disagree, report both and cite each.
- Keep answers short: one to four sentences, or a short list when the question asks for several items. Lead with the direct answer.
- Earlier turns of the conversation may be included. Use them to understand what a follow-up question refers to, but take facts only from the passages in the current request.""" % config.NOT_FOUND_ANSWER

# Worked examples for v3. Each is (passages, question, ideal answer).
FEW_SHOT_EXAMPLES = [
    (
        [
            {"source": "library-lending.md", "section": "Loan periods", "page": 1,
             "text": "Members may borrow up to 8 items at a time. Books are "
                     "loaned for 21 days and can be renewed twice online."},
            {"source": "library-lending.md", "section": "Late returns", "page": 1,
             "text": "A late fee of 0.25 per item per day is charged, capped at "
                     "5.00 per item."},
        ],
        "How long can I keep a book, and what happens if I return it late?",
        "Books are loaned for 21 days and can be renewed online twice [1]. "
        "Late returns cost 0.25 per item per day, up to a maximum of 5.00 per item [2].",
    ),
    (
        [
            {"source": "library-lending.md", "section": "Loan periods", "page": 1,
             "text": "Members may borrow up to 8 items at a time. Books are "
                     "loaned for 21 days and can be renewed twice online."},
        ],
        "Can I reserve a study room?",
        "%s The passages cover loan limits and loan periods, but not study "
        "rooms." % config.NOT_FOUND_ANSWER,
    ),
]

PROMPTS = {
    "v1": {"name": "baseline", "system": BASELINE_SYSTEM, "few_shot": False},
    "v2": {"name": "grounded", "system": GROUNDED_SYSTEM, "few_shot": False},
    "v3": {"name": "grounded + few-shot", "system": GROUNDED_SYSTEM, "few_shot": True},
}


def escape(text):
    # passages are wrapped in XML-style tags; a passage containing "</document>"
    # must not be able to close its own tag early
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def format_passages(chunks):
    # numbered from 1 so the [n] the model writes maps straight back to a chunk
    parts = []
    for n, chunk in enumerate(chunks, start=1):
        where = chunk["source"]
        if chunk.get("section"):
            where += " > " + chunk["section"]
        if chunk.get("page", 1) > 1:
            where += " (page %d)" % chunk["page"]
        parts.append('<document index="%d" source="%s">\n%s\n</document>'
                     % (n, escape(where), escape(chunk["text"])))
    return "\n".join(parts)


def format_question(chunks, question):
    # passages first, question last: with long context the model answers
    # better when the question comes after the material it is about
    return "<documents>\n%s\n</documents>\n\nQuestion: %s" % (format_passages(chunks), question)


def build_request(question, chunks, history=None, version=None):
    version = version or config.PROMPT_VERSION
    if version not in PROMPTS:
        raise ValueError("unknown prompt version %r (have: %s)" % (version, ", ".join(PROMPTS)))
    spec = PROMPTS[version]

    messages = []

    # Order matters: examples first, then past turns, then the new question.
    # The examples never change, so they always sit at the front of the request.
    if spec["few_shot"]:
        for example_chunks, example_question, example_answer in FEW_SHOT_EXAMPLES:
            messages.append({"role": "user", "content": format_question(example_chunks, example_question)})
            messages.append({"role": "assistant", "content": example_answer})

    # Past turns are replayed as plain question/answer pairs without their old
    # passages. That is enough to resolve "what about contractors?" and keeps
    # the request from growing by four passages every turn.
    for turn in (history or [])[-config.HISTORY_TURNS:]:
        messages.append({"role": "user", "content": turn["question"]})
        messages.append({"role": "assistant", "content": turn["answer"]})

    messages.append({"role": "user", "content": format_question(chunks, question)})

    return {"system": spec["system"], "messages": messages,
            "question": question, "chunks": chunks, "version": version}

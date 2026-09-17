# Wires the pipeline together.
#
#   KnowledgeBase  holds the loaded documents and the search index over them.
#   Assistant      answers one question: retrieve -> build prompt -> generate
#                  -> pull the [n] citations back out of the answer.
#
# The assistant keeps no conversation state of its own. The caller passes the
# history in and appends the result, which is what lets the web app serve many
# browser sessions from one assistant and one index.

import re
import time

import config
from qa import chunker, loader, prompts
from qa.llm import make_backend
from qa.retriever import BM25Index, tokenize

# Phrases that mean "the documents don't say". v2 and v3 are told to use
# NOT_FOUND_ANSWER word for word; v1 never is, so its refusals are caught by
# these looser phrases instead.
REFUSAL_MARKERS = (
    "couldn't find", "could not find", "not mentioned", "does not contain",
    "do not contain", "don't contain", "doesn't contain", "no information",
    "not specified", "not covered", "not provided in", "does not say",
    "doesn't say", "do not say", "don't say",
)

CITATION_PATTERN = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")

# Words that point back at an earlier turn ("is IT paid?", "does THAT need
# approval?") and openings that continue one ("and for contractors?").
FOLLOWUP_WORDS = set("it its that this they them those these there same".split())
FOLLOWUP_OPENINGS = ("and ", "what about", "how about", "also ", "but ", "what if")


class KnowledgeBase:
    def __init__(self):
        self.docs = []
        self.chunks = []
        self.index = BM25Index([])

    def add_documents(self, docs):
        # a file uploaded again under the same name replaces the old copy
        # instead of being indexed twice
        names = set(d["source"] for d in docs)
        self.docs = [d for d in self.docs if d["source"] not in names] + list(docs)
        self.rebuild()

    def remove(self, source):
        before = len(self.docs)
        self.docs = [d for d in self.docs if d["source"] != source]
        self.rebuild()
        return len(self.docs) < before

    def rebuild(self):
        # the whole index is rebuilt on every change. For a few hundred pages
        # this takes milliseconds and is far simpler than updating in place.
        self.chunks = chunker.chunk_documents(self.docs)
        self.index = BM25Index(self.chunks)

    def load_folder(self, folder):
        self.add_documents(loader.load_folder(folder))

    def add_file(self, path):
        self.add_documents([loader.load_file(path)])

    def search(self, query, top_k):
        return self.index.search(query, top_k)

    def summary(self):
        counts = {}
        for chunk in self.chunks:
            counts[chunk["source"]] = counts.get(chunk["source"], 0) + 1
        return [{"source": d["source"], "pages": len(d["pages"]),
                 "chunks": counts.get(d["source"], 0)} for d in self.docs]


def parse_citations(answer, chunks):
    # Returns (citations, invalid). A number that points at no passage is kept
    # in `invalid` rather than dropped: it means the model invented a source,
    # which the evaluator counts as a failure.
    numbers = []
    for group in CITATION_PATTERN.findall(answer):
        for part in group.split(","):
            n = int(part.strip())
            if n not in numbers:
                numbers.append(n)

    citations = []
    invalid = []
    for n in numbers:
        if 1 <= n <= len(chunks):
            chunk = chunks[n - 1]
            citations.append({"n": n, "source": chunk["source"], "section": chunk["section"],
                              "page": chunk["page"], "text": chunk["text"]})
        else:
            invalid.append(n)
    return citations, invalid


def is_refusal(answer, citations):
    lowered = answer.lower()
    if lowered.startswith(config.NOT_FOUND_ANSWER.lower()):
        return True
    # a partial answer ("X is 10 days [1]; Y is not covered") carries citations
    # and is an answer, not a refusal
    if citations:
        return False
    return any(marker in lowered for marker in REFUSAL_MARKERS)


def is_follow_up(question):
    lowered = question.lower().strip()
    if len(set(tokenize(question))) <= config.FOLLOWUP_MAX_TERMS:
        return True
    if lowered.startswith(FOLLOWUP_OPENINGS):
        return True
    return any(word in FOLLOWUP_WORDS for word in re.findall(r"[a-z]+", lowered))


class Assistant:
    def __init__(self, knowledge_base, backend=None, prompt_version=None, top_k=None):
        self.kb = knowledge_base
        self.backend = backend or make_backend()
        self.prompt_version = prompt_version or config.PROMPT_VERSION
        self.top_k = top_k or config.TOP_K

    def retrieval_query(self, question, history):
        # "Is it paid?" retrieves nothing useful on its own, so a follow-up
        # borrows the previous question's words for the search. The model still
        # sees the question exactly as asked; this only changes what is searched.
        if history and is_follow_up(question):
            return history[-1]["question"] + " " + question
        return question

    def ask(self, question, history=None):
        question = (question or "").strip()
        if not question:
            raise ValueError("question is empty")

        started = time.perf_counter()
        hits = self.kb.search(self.retrieval_query(question, history), self.top_k)
        chunks = [chunk for chunk, score in hits]

        if chunks:
            request = prompts.build_request(question, chunks, history, self.prompt_version)
            output = self.backend.generate(request)
        else:
            # Not one word of the question appears in the documents. A model
            # call now could only answer from general knowledge, which is the
            # one thing the grounding rule forbids - so skip it and save the cost.
            output = {"text": config.NOT_FOUND_ANSWER, "model": None,
                      "stop_reason": "no_passages", "usage": {"input_tokens": 0, "output_tokens": 0}}

        answer = output["text"]
        citations, invalid = parse_citations(answer, chunks)

        return {
            "question": question,
            "answer": answer,
            "refused": is_refusal(answer, citations),
            "citations": citations,
            "invalid_citations": invalid,
            "retrieved": [{"n": n, "source": c["source"], "section": c["section"],
                           "page": c["page"], "score": round(score, 3), "text": c["text"]}
                          for n, (c, score) in enumerate(hits, start=1)],
            "backend": self.backend.name,
            "model": output["model"],
            "prompt_version": self.prompt_version,
            "stop_reason": output["stop_reason"],
            "usage": output["usage"],
            "latency_ms": int((time.perf_counter() - started) * 1000),
        }


def build_default_assistant(backend_name=None, prompt_version=None):
    # the sample documents plus anything uploaded through the web app earlier
    kb = KnowledgeBase()
    kb.load_folder(config.DOCS_DIR)
    kb.load_folder(config.UPLOADS_DIR)
    return Assistant(kb, backend=make_backend(backend_name), prompt_version=prompt_version)

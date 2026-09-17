# Every setting the assistant uses lives in this file. Nothing else in the
# project hardcodes a path, a model name, a chunk size or a threshold, so a
# change made here is the whole change.

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# .env support without an extra dependency. Only KEY=VALUE lines are read and a
# variable that is already set in the shell wins, so a real environment is never
# overwritten by a stale file.
def load_env_file(path):
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env_file(os.path.join(BASE_DIR, ".env"))


# ---- where things are -------------------------------------------------------

DOCS_DIR = os.path.join(BASE_DIR, "data", "docs")
UPLOADS_DIR = os.path.join(BASE_DIR, "data", "uploads")
EVAL_FILE = os.path.join(BASE_DIR, "eval", "eval_set.json")
REPORTS_DIR = os.path.join(BASE_DIR, "eval", "reports")
STATIC_DIR = os.path.join(BASE_DIR, "static")

SUPPORTED_EXTENSIONS = (".txt", ".md", ".pdf")
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

# Uploading documents is on for local use and off on a public deployment, where
# anyone with the URL could otherwise push files onto the server. Set
# QA_ALLOW_UPLOADS=1 on a deployment only if the URL is not shared.
ALLOW_UPLOADS = os.environ.get("QA_ALLOW_UPLOADS", "1") == "1"


# ---- which model answers ----------------------------------------------------

# "claude" calls the Anthropic API. "offline" is an extractive stand-in that
# needs no key: it is there so the pipeline, the UI and the tests all run on a
# machine without credentials. It is NOT an LLM (see README, "What this does not
# prove"). "auto" picks claude when a key is present, otherwise offline.
BACKEND = os.environ.get("QA_BACKEND", "auto")

MODEL = os.environ.get("QA_MODEL", "claude-opus-5")

# If Claude's safety classifier declines a request, the API re-runs it on this
# model inside the same call instead of handing back an empty answer.
FALLBACK_MODEL = "claude-opus-4-8"

# Effort controls how much the model thinks before answering. Grounded Q&A over
# a few retrieved passages is routine work, so medium is the starting point;
# raise it only if the eval shows answers getting better at the higher setting.
EFFORT = os.environ.get("QA_EFFORT", "medium")

MAX_TOKENS = 16000


# ---- chunking and retrieval -------------------------------------------------

# Chunks are measured in words. 120 words is roughly one policy paragraph, small
# enough that a retrieved chunk is about one thing. The overlap keeps a sentence
# that straddles a boundary whole in at least one chunk.
CHUNK_WORDS = 120
CHUNK_OVERLAP_WORDS = 30

# How many chunks are handed to the model per question.
TOP_K = 4

# A follow-up such as "and international?" has too few words of its own to
# retrieve anything useful, so a question with this many content words or
# fewer borrows the previous question's words for the search. Kept at 1 on
# purpose: at 3, "How long must passwords be?" (2 content words) was treated as
# a follow-up and dragged the previous topic into its search.
FOLLOWUP_MAX_TERMS = 1


# ---- prompting and conversation ---------------------------------------------

# Which prompt template is live. v1 -> v2 -> v3 is the refinement history, kept
# side by side so the evaluator can score them against each other.
PROMPT_VERSION = os.environ.get("QA_PROMPT_VERSION", "v3")

# How many earlier question/answer pairs are replayed to the model.
HISTORY_TURNS = 3

# The exact sentence the model is told to use when the documents do not hold
# the answer. The evaluator and the UI both key on it.
NOT_FOUND_ANSWER = "I couldn't find this in the provided documents."


# ---- offline backend --------------------------------------------------------

# A sentence is only quoted if it contains at least this share of the question's
# content words; below that the offline backend declines instead of guessing.
OFFLINE_MIN_OVERLAP = 0.5
OFFLINE_MAX_SENTENCES = 2

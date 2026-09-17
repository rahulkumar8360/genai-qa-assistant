# The part that produces the answer text. Two backends share one method,
# generate(request), where request is what prompts.build_request returns:
#
#   ClaudeBackend   sends the system prompt and messages to the Anthropic API.
#   OfflineBackend  needs no key. It quotes the passage sentences that best match
#                   the question and declines when nothing matches well. It is a
#                   baseline for running the app and the tests without
#                   credentials - it ignores the prompt entirely, so it cannot be
#                   used to judge prompt versions.
#
# Both return the same dict, so the assistant, the CLI, the web app and the
# evaluator never need to know which one is running.

import os
import re

import config
from qa.retriever import tokenize


class LLMError(Exception):
    # raised with a message that is safe to show in the UI as-is
    pass


class ClaudeBackend:
    name = "claude"

    # client can be passed in so the tests can check the request without a
    # network call; normally it is built from the environment
    def __init__(self, model=None, effort=None, client=None):
        self.model = model or config.MODEL
        self.effort = effort or config.EFFORT
        if client is None:
            import anthropic
            # reads ANTHROPIC_API_KEY from the environment (or .env via config)
            client = anthropic.Anthropic()
        self.client = client

    def generate(self, request):
        import anthropic

        try:
            # Thinking is left at the model default (adaptive on Opus 5): it
            # decides how much to reason per question, and effort caps the spend.
            # The fallbacks beta re-runs a declined request on FALLBACK_MODEL
            # inside the same call rather than returning nothing.
            response = self.client.beta.messages.create(
                model=self.model,
                max_tokens=config.MAX_TOKENS,
                system=request["system"],
                messages=request["messages"],
                output_config={"effort": self.effort},
                betas=["server-side-fallback-2026-06-01"],
                fallbacks=[{"model": config.FALLBACK_MODEL}],
            )
        except anthropic.AuthenticationError:
            raise LLMError("The Anthropic API key was rejected. Check ANTHROPIC_API_KEY in .env.")
        except anthropic.PermissionDeniedError:
            raise LLMError("This API key is not allowed to use %s." % self.model)
        except anthropic.NotFoundError:
            raise LLMError("Model %s was not found. Check QA_MODEL." % self.model)
        except anthropic.RateLimitError:
            raise LLMError("Rate limited by the Anthropic API. Wait a moment and try again.")
        except anthropic.BadRequestError as e:
            raise LLMError("The API rejected the request: %s" % e.message)
        except anthropic.APIStatusError as e:
            raise LLMError("The Anthropic API returned an error (%s). Try again shortly." % e.status_code)
        except anthropic.APIConnectionError:
            raise LLMError("Could not reach the Anthropic API. Check the internet connection.")

        usage = {"input_tokens": response.usage.input_tokens,
                 "output_tokens": response.usage.output_tokens}

        # a refusal comes back as HTTP 200 with no usable text, so it has to be
        # checked before reading content - only reached if the fallback model
        # declined as well
        if response.stop_reason == "refusal":
            return {"text": "The model declined to answer this question.",
                    "model": response.model, "stop_reason": "refusal", "usage": usage}

        # content can hold thinking blocks as well as text; only text is the answer
        text = "".join(block.text for block in response.content if block.type == "text").strip()

        if response.stop_reason == "max_tokens":
            text += "\n\n(Answer cut off at the length limit.)"

        return {"text": text, "model": response.model,
                "stop_reason": response.stop_reason, "usage": usage}


class OfflineBackend:
    name = "offline"
    model = "extractive-baseline"

    def split_sentences(self, text):
        # chunk text has its newlines flattened, so list items only survive as
        # " - " separators; treat those as sentence breaks too
        parts = re.split(r"(?<=[.!?])\s+|\s+-\s+", text)
        return [p.strip(" -") for p in parts if len(p.strip(" -")) > 3]

    def generate(self, request):
        question_terms = set(tokenize(request["question"]))
        candidates = []

        for n, chunk in enumerate(request["chunks"], start=1):
            # the heading counts as part of every sentence under it, so
            # "sick days" can match "You receive 10 days per year" under
            # "Sick leave"
            heading_terms = set(tokenize(chunk.get("section", "")))
            for sentence in self.split_sentences(chunk["text"]):
                terms = set(tokenize(sentence)) | heading_terms
                if not question_terms:
                    continue
                overlap = len(question_terms & terms) / len(question_terms)
                candidates.append((overlap, n, sentence))

        # best overlap first; on a tie the higher-ranked passage wins
        candidates.sort(key=lambda c: (-c[0], c[1]))

        picked = []
        seen = set()
        for overlap, n, sentence in candidates:
            if overlap < config.OFFLINE_MIN_OVERLAP:
                break
            # overlapping chunks repeat sentences; quote each one once
            if sentence in seen:
                continue
            seen.add(sentence)
            # same shape the prompt asks Claude for: "... fact [n]."
            picked.append("%s [%d]." % (sentence.rstrip(".!?"), n))
            if len(picked) >= config.OFFLINE_MAX_SENTENCES:
                break

        text = " ".join(picked) if picked else config.NOT_FOUND_ANSWER
        return {"text": text, "model": self.model, "stop_reason": "end_turn",
                "usage": {"input_tokens": 0, "output_tokens": 0}}


def has_api_credentials():
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def make_backend(name=None):
    name = (name or config.BACKEND).lower()
    if name == "auto":
        name = "claude" if has_api_credentials() else "offline"
    if name == "claude":
        return ClaudeBackend()
    if name == "offline":
        return OfflineBackend()
    raise ValueError("unknown backend %r (use claude, offline or auto)" % name)

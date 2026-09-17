# End-to-end tests on the real sample documents, using the offline backend.

import pytest

import config
from qa.assistant import Assistant, KnowledgeBase, is_follow_up, is_refusal, parse_citations
from qa.llm import OfflineBackend


@pytest.fixture(scope="module")
def assistant():
    kb = KnowledgeBase()
    kb.load_folder(config.DOCS_DIR)
    return Assistant(kb, backend=OfflineBackend())


CHUNKS = [{"source": "a.md", "section": "S", "page": 1, "text": "one"},
          {"source": "b.md", "section": "T", "page": 1, "text": "two"}]


def test_parse_single_grouped_and_repeated_citations():
    citations, invalid = parse_citations("x [1]. y [1, 2]. z [2][1].", CHUNKS)
    assert [c["n"] for c in citations] == [1, 2]
    assert [c["source"] for c in citations] == ["a.md", "b.md"]
    assert invalid == []


def test_citation_to_a_missing_passage_is_flagged():
    citations, invalid = parse_citations("made up [3] and [0]", CHUNKS)
    assert citations == []
    assert invalid == [3, 0]


def test_refusal_detection():
    assert is_refusal(config.NOT_FOUND_ANSWER + " The passages cover X.", [])
    assert is_refusal("The documents do not contain that.", [])
    # a partial answer with a citation is still an answer
    assert not is_refusal("Hotels are 180 [1]; meals are not covered.", [{"n": 1}])
    assert not is_refusal("You get 24 days.", [])


def test_answers_with_a_citation_to_the_right_file(assistant):
    result = assistant.ask("How long must passwords be?")
    assert "14" in result["answer"]
    assert not result["refused"]
    assert result["citations"][0]["source"] == "it-security.md"
    assert result["invalid_citations"] == []


def test_declines_when_documents_are_silent(assistant):
    result = assistant.ask("Which company provides our dental insurance?")
    assert result["refused"]
    assert result["answer"] == config.NOT_FOUND_ANSWER


def test_no_matching_words_skips_the_model_call():
    class ExplodingBackend:
        name = "explode"
        def generate(self, request):
            raise AssertionError("the backend must not be called when nothing was retrieved")

    kb = KnowledgeBase()
    kb.load_folder(config.DOCS_DIR)
    result = Assistant(kb, backend=ExplodingBackend()).ask("zzzz qqqq")
    assert result["stop_reason"] == "no_passages"
    assert result["refused"]


def test_follow_up_detection():
    assert is_follow_up("And international?")
    assert is_follow_up("What about contractors?")
    assert is_follow_up("Is it paid?")
    assert is_follow_up("Does that need approval from my manager?")
    # short but complete questions stand on their own
    assert not is_follow_up("How long must passwords be?")
    assert not is_follow_up("What is the mileage rate?")


def test_follow_up_borrows_the_previous_question(assistant):
    history = [{"question": "What is the hotel limit per night?", "answer": "..."}]
    assert "hotel" in assistant.retrieval_query("And international?", history)
    assert assistant.retrieval_query("How long must passwords be?", history) == \
        "How long must passwords be?"


def test_follow_up_retrieves_the_earlier_topic(assistant):
    history = [{"question": "What is the hotel limit per night?", "answer": "..."}]
    result = assistant.ask("And for international travel?", history)
    assert "250" in result["answer"]


def test_result_shape(assistant):
    result = assistant.ask("What is the monthly internet allowance?")
    for key in ("answer", "refused", "citations", "retrieved", "backend", "model",
                "prompt_version", "usage", "latency_ms", "invalid_citations"):
        assert key in result
    assert len(result["retrieved"]) <= config.TOP_K


def test_empty_question_is_rejected(assistant):
    with pytest.raises(ValueError):
        assistant.ask("   ")


def test_reuploading_a_file_replaces_it():
    kb = KnowledgeBase()
    kb.add_documents([{"source": "x.md", "pages": ["old text"]}])
    kb.add_documents([{"source": "x.md", "pages": ["new text"]}])
    assert [c["text"] for c in kb.chunks] == ["new text"]
    assert kb.remove("x.md")
    assert kb.chunks == []

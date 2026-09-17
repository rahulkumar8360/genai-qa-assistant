import pytest

from qa.chunker import chunk_document, split_sections, split_words


def test_sections_follow_markdown_headings():
    text = "intro line\n# Title\n\n## Sick leave\nten days\n## Parental leave\n26 weeks"
    sections = split_sections(text)
    assert sections == [("", "intro line"), ("Sick leave", "ten days"), ("Parental leave", "26 weeks")]


def test_heading_with_no_body_produces_no_section():
    assert split_sections("# Only a title\n\n") == []


def test_word_windows_overlap():
    words = [str(i) for i in range(10)]
    pieces = split_words(words, size=4, overlap=1)
    assert pieces == [["0", "1", "2", "3"], ["3", "4", "5", "6"], ["6", "7", "8", "9"]]


def test_short_text_is_one_chunk():
    assert split_words(["a", "b"], size=4, overlap=1) == [["a", "b"]]


def test_overlap_must_be_smaller_than_size():
    with pytest.raises(ValueError):
        split_words(["a"] * 10, size=3, overlap=3)


def test_chunk_keeps_source_page_and_section():
    doc = {"source": "x.md", "pages": ["## A\none two three", "## B\nfour five"]}
    chunks = chunk_document(doc, size=50, overlap=5)
    assert [(c["id"], c["page"], c["section"], c["text"]) for c in chunks] == [
        ("x.md#0", 1, "A", "one two three"),
        ("x.md#1", 2, "B", "four five"),
    ]


def test_chunks_never_cross_a_heading():
    doc = {"source": "x.md", "pages": ["## A\n" + "alpha " * 30 + "\n## B\n" + "beta " * 30]}
    for c in chunk_document(doc, size=20, overlap=5):
        assert ("alpha" in c["text"]) != ("beta" in c["text"])

from qa.retriever import BM25Index, stem, tokenize


def test_stem_maps_word_forms_together():
    assert stem("days") == stem("day")
    assert stem("reimbursed") == stem("reimbursement") == stem("reimburse")
    assert stem("policies") == stem("policy")
    assert stem("leaves") == stem("leave")


def test_tokenize_drops_stopwords_and_punctuation():
    assert tokenize("How many days do I get?") == ["day"]


def test_hyphenated_words_match_joined_and_split_spellings():
    doc = set(tokenize("Public Wi-Fi for part-time staff"))
    assert set(tokenize("wifi")) <= doc
    assert set(tokenize("part time")) <= doc


def make_chunk(source, section, text):
    return {"id": source, "source": source, "section": section, "page": 1, "text": text}


def test_most_relevant_chunk_ranks_first():
    chunks = [
        make_chunk("a", "Hotels", "The nightly hotel limit is 180 dollars."),
        make_chunk("b", "Sick leave", "Employees receive 10 days of paid sick leave."),
        make_chunk("c", "Meals", "Meals are covered up to 60 dollars per day."),
    ]
    results = BM25Index(chunks).search("how many sick days do I get", top_k=3)
    assert results[0][0]["source"] == "b"


def test_heading_words_are_searchable():
    # the body never says "bereavement"; only the heading does
    chunks = [make_chunk("a", "Bereavement leave", "Up to 5 days on the death of a family member."),
              make_chunk("b", "Annual leave", "24 days per year.")]
    results = BM25Index(chunks).search("bereavement", top_k=1)
    assert results[0][0]["source"] == "a"


def test_no_overlap_returns_nothing():
    index = BM25Index([make_chunk("a", "Hotels", "hotel limit 180")])
    assert index.search("dental insurance", top_k=4) == []


def test_empty_index_and_empty_query():
    assert BM25Index([]).search("anything", top_k=4) == []
    assert BM25Index([make_chunk("a", "", "text")]).search("the and of", top_k=4) == []

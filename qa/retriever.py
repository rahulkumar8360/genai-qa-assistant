# Finds the passages most likely to hold the answer, using BM25 - the ranking
# formula behind most keyword search engines.
#
# Why keyword search and not embeddings: it needs no second model or API, it is
# deterministic (the same question always retrieves the same passages, so the
# eval is repeatable), and on policy documents the question usually shares its
# key words with the answer. Its known weakness is synonyms: "vacation" will not
# find a passage that only says "annual leave". The retriever only has to
# provide search(query, top_k), so an embedding index can replace it later
# without touching anything else.

import math
import re
from collections import Counter

# Words that appear in almost every question and carry no topic. Dropping them
# stops "how many days do I get" from matching every passage that says "I".
STOPWORDS = set("""
a an the and or but if of to in on at by for with from as is are was were be
been being do does did doing have has had having i me my we our you your he she
it its they them their this that these those what which who whom whose when
where why how can could should would will shall may might must am not no so
than too very just about into over under again then once there here all any
both each few more most other some such only own same get gets got many much
""".split())


def stem(word):
    # A deliberately crude suffix stripper: it only has to map a word and its
    # plural or tense to the same key ("days"/"day", "reimbursed"/
    # "reimbursement"). It does not need to produce real words.
    if len(word) <= 3:
        return word
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    for suffix in ("ments", "ment", "ings", "ing", "ed", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            word = word[:-len(suffix)]
            break
    # "reimburse" and "reimburs(ed)" should meet, so a trailing e goes too
    if word.endswith("e") and len(word) > 3:
        word = word[:-1]
    return word


def tokenize(text):
    # A hyphenated word is indexed both joined and as its parts, because people
    # write it either way: "Wi-Fi" must match "wifi", and "part-time" must
    # match "part time". Found when "public wifi" missed the Wi-Fi rule.
    tokens = []
    for word in re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", text.lower()):
        forms = word.split("-")
        if len(forms) > 1:
            forms.append(word.replace("-", ""))
        tokens.extend(stem(w) for w in forms if w not in STOPWORDS)
    return tokens


class BM25Index:
    # k1 controls how fast repeating a word stops adding score; b controls how
    # much long passages are penalised. 1.5 and 0.75 are the textbook defaults.
    def __init__(self, chunks, k1=1.5, b=0.75):
        self.chunks = chunks
        self.k1 = k1
        self.b = b

        # the heading is indexed with the body - see chunker.py for why
        self.term_counts = []
        self.lengths = []
        for chunk in chunks:
            tokens = tokenize(chunk["section"] + " " + chunk["text"])
            self.term_counts.append(Counter(tokens))
            self.lengths.append(len(tokens))

        self.avg_length = sum(self.lengths) / len(self.lengths) if chunks else 0.0

        # idf: a word that appears in few passages is a strong signal, a word
        # in every passage is almost none. The +1 keeps it positive.
        doc_freq = Counter()
        for counts in self.term_counts:
            doc_freq.update(counts.keys())
        n = len(chunks)
        self.idf = {}
        for term, df in doc_freq.items():
            self.idf[term] = math.log(1 + (n - df + 0.5) / (df + 0.5))

    def score(self, query_terms, i):
        counts = self.term_counts[i]
        length_norm = self.k1 * (1 - self.b + self.b * self.lengths[i] / self.avg_length)
        total = 0.0
        for term in query_terms:
            tf = counts.get(term, 0)
            if tf:
                total += self.idf[term] * tf * (self.k1 + 1) / (tf + length_norm)
        return total

    def search(self, query, top_k=4):
        # each distinct word counts once, so repeating a word in the question
        # does not drown out the others
        query_terms = set(tokenize(query))
        if not query_terms or not self.chunks:
            return []

        results = []
        for i in range(len(self.chunks)):
            s = self.score(query_terms, i)
            if s > 0:
                results.append((s, i))

        # highest score first; ties keep document order so results are stable
        results.sort(key=lambda pair: (-pair[0], pair[1]))
        return [(self.chunks[i], s) for s, i in results[:top_k]]

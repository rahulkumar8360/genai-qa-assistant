# Cuts documents into passages small enough that each one is about a single
# thing. The model only ever sees a handful of these, so a passage that mixes
# two topics wastes space and invites the wrong answer.
#
# Markdown is split at headings first and only then by word count, so a passage
# never starts in "Sick leave" and ends in "Parental leave". Each passage keeps
# the heading it came from; that heading is shown in citations and also indexed,
# which is what lets "sick days" find a paragraph that only says "10 days".

import config


def split_sections(text):
    # returns [(heading, body), ...]; text before the first heading gets ""
    sections = []
    heading = ""
    lines = []

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            if any(l.strip() for l in lines):
                sections.append((heading, "\n".join(lines)))
            heading = stripped.lstrip("#").strip()
            lines = []
        else:
            lines.append(line)

    if any(l.strip() for l in lines):
        sections.append((heading, "\n".join(lines)))
    return sections


def split_words(words, size, overlap):
    # sliding window over a list of words; the last window may be shorter
    if size <= overlap:
        raise ValueError("chunk size must be larger than the overlap")

    pieces = []
    start = 0
    step = size - overlap
    while True:
        pieces.append(words[start:start + size])
        if start + size >= len(words):
            break
        start += step
    return pieces


def chunk_document(doc, size=None, overlap=None):
    size = size or config.CHUNK_WORDS
    overlap = config.CHUNK_OVERLAP_WORDS if overlap is None else overlap

    chunks = []
    for page_number, page_text in enumerate(doc["pages"], start=1):
        for heading, body in split_sections(page_text):
            words = body.split()
            if not words:
                continue
            for piece in split_words(words, size, overlap):
                chunks.append({
                    # "file#n" is unique across the whole index and stable
                    # between runs, which the tests and the eval rely on
                    "id": "%s#%d" % (doc["source"], len(chunks)),
                    "source": doc["source"],
                    "page": page_number,
                    "section": heading,
                    "text": " ".join(piece),
                })
    return chunks


def chunk_documents(docs, size=None, overlap=None):
    chunks = []
    for doc in docs:
        chunks.extend(chunk_document(doc, size, overlap))
    return chunks

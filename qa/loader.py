# Reads documents from disk into a common shape:
#
#   {"source": "leave-policy.md", "pages": ["page 1 text", "page 2 text", ...]}
#
# Text and markdown files are a single page. PDFs keep their real pages so an
# answer can cite "page 3" instead of just the file name.

import os

import config


def read_text_file(path):
    # errors="replace" so one stray byte in a pasted document does not stop the
    # whole folder from loading
    with open(path, encoding="utf-8", errors="replace") as f:
        return [f.read()]


def read_pdf_file(path):
    # imported here so the rest of the project works even if pypdf is missing
    from pypdf import PdfReader

    reader = PdfReader(path)
    # scanned PDFs have no text layer and come back as empty strings; they are
    # kept as empty pages so page numbers still line up with the original
    return [page.extract_text() or "" for page in reader.pages]


def load_file(path):
    ext = os.path.splitext(path)[1].lower()
    if ext not in config.SUPPORTED_EXTENSIONS:
        raise ValueError("unsupported file type %s (supported: %s)"
                         % (ext, ", ".join(config.SUPPORTED_EXTENSIONS)))

    if ext == ".pdf":
        pages = read_pdf_file(path)
    else:
        pages = read_text_file(path)

    return {"source": os.path.basename(path), "pages": pages}


def load_folder(folder):
    docs = []
    if not os.path.isdir(folder):
        return docs

    # sorted so chunk ids, and therefore test results, are the same on every run
    for name in sorted(os.listdir(folder)):
        path = os.path.join(folder, name)
        if not os.path.isfile(path):
            continue
        if os.path.splitext(name)[1].lower() not in config.SUPPORTED_EXTENSIONS:
            continue
        docs.append(load_file(path))
    return docs

import pytest

from qa.loader import load_file, load_folder


def make_pdf(path, pages):
    # a minimal but valid PDF with one line of text per page, built by hand so
    # the test needs no PDF-writing library
    objs = {}
    n = len(pages)
    objs[1] = "<< /Type /Catalog /Pages 2 0 R >>"
    objs[2] = "<< /Type /Pages /Kids [%s] /Count %d >>" % (
        " ".join("%d 0 R" % (4 + 2 * i) for i in range(n)), n)
    objs[3] = "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    for i, text in enumerate(pages):
        stream = "BT /F1 12 Tf 72 720 Td (%s) Tj ET" % text
        objs[4 + 2 * i] = ("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                           "/Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>" % (5 + 2 * i))
        objs[5 + 2 * i] = "<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream)

    out = b"%PDF-1.4\n"
    offsets = {}
    for num in sorted(objs):
        offsets[num] = len(out)
        out += ("%d 0 obj\n%s\nendobj\n" % (num, objs[num])).encode("latin-1")
    xref_at = len(out)
    out += ("xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)).encode()
    for num in sorted(objs):
        out += ("%010d 00000 n \n" % offsets[num]).encode()
    out += ("trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref_at)).encode()
    path.write_bytes(out)


def test_pdf_keeps_its_pages(tmp_path):
    path = tmp_path / "guide.pdf"
    make_pdf(path, ["First page text", "Second page text"])
    doc = load_file(str(path))
    assert doc["source"] == "guide.pdf"
    assert len(doc["pages"]) == 2
    assert "Second page" in doc["pages"][1]


def test_text_and_markdown_are_one_page(tmp_path):
    (tmp_path / "a.md").write_text("# Title\nbody", encoding="utf-8")
    assert load_file(str(tmp_path / "a.md"))["pages"] == ["# Title\nbody"]


def test_folder_skips_unsupported_files_in_sorted_order(tmp_path):
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    (tmp_path / "a.md").write_text("a", encoding="utf-8")
    (tmp_path / "image.png").write_bytes(b"\x89PNG")
    assert [d["source"] for d in load_folder(str(tmp_path))] == ["a.md", "b.txt"]


def test_missing_folder_is_empty(tmp_path):
    assert load_folder(str(tmp_path / "nope")) == []


def test_unsupported_type_is_rejected(tmp_path):
    (tmp_path / "x.docx").write_bytes(b"")
    with pytest.raises(ValueError):
        load_file(str(tmp_path / "x.docx"))

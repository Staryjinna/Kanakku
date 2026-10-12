import pytest

from app.gst_qa.chunk import chunk_pages


def words(n: int, prefix: str = "w") -> str:
    return " ".join(f"{prefix}{i}" for i in range(n))


def test_short_page_is_one_chunk() -> None:
    (c,) = chunk_pages([(3, "  hello \n world ")])
    assert (c.page, c.ordinal, c.text) == (3, 0, "hello world")


def test_long_page_splits_with_overlap() -> None:
    chunks = chunk_pages([(1, words(25))], size=10, overlap=3)
    assert [len(c.text.split()) for c in chunks] == [10, 10, 10, 4]
    assert chunks[0].text.split()[-3:] == chunks[1].text.split()[:3]
    assert [c.ordinal for c in chunks] == [0, 1, 2, 3]
    assert " ".join(c.text for c in chunks).count("w24") == 1 or "w24" in chunks[-1].text


def test_exact_multiple_has_no_empty_tail() -> None:
    chunks = chunk_pages([(1, words(10))], size=10, overlap=3)
    assert len(chunks) == 1


def test_pages_chunked_separately_and_ordinals_continue() -> None:
    chunks = chunk_pages([(1, "a b c"), (2, ""), (3, "d e")])
    assert [(c.page, c.ordinal) for c in chunks] == [(1, 0), (3, 1)]


def test_everything_is_covered() -> None:
    text = words(1000)
    chunks = chunk_pages([(1, text)])
    covered = set()
    for c in chunks:
        covered |= set(c.text.split())
    assert covered == set(text.split())


def test_bad_overlap() -> None:
    with pytest.raises(ValueError):
        chunk_pages([(1, "a")], size=5, overlap=5)

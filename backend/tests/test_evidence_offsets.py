import copy

from app.interview_evaluation import resolve_evidence_offsets


def sample(quote, start=99, end=100):
    return {"dimensions": [{"evidence": [{"quote": quote, "start": start, "end": end}]}]}


def test_unique_exact_quote_positions_are_resolved_without_mutation():
    original = sample("LEFT JOIN")
    before = copy.deepcopy(original)
    result = resolve_evidence_offsets(original, "Use LEFT JOIN here.")
    assert result["dimensions"][0]["evidence"][0] == {
        "quote": "LEFT JOIN",
        "start": 4,
        "end": 13,
    }
    assert original == before


def test_invented_and_ambiguous_quotes_are_not_repaired():
    for quote, answer in [("invented", "actual"), ("aa", "aaa")]:
        data = sample(quote)
        assert resolve_evidence_offsets(data, answer) == data


def test_valid_duplicate_location_is_preserved():
    data = sample("yes", 4, 7)
    assert resolve_evidence_offsets(data, "yes yes") == data


def test_unicode_and_newlines_use_python_character_offsets():
    result = resolve_evidence_offsets(sample("LEFT JOIN"), "\U0001f600\nLEFT JOIN")
    assert result["dimensions"][0]["evidence"][0]["start"] == 2

from pathlib import Path

from contentkit.reference import Reference


def test_regular_er_forms_missing_from_lexique_are_words() -> None:
    ref = Reference(Path("."))
    ref.words = frozenset({"endommager", "manger"})
    assert ref.is_word("endommagent") and ref.is_word("endommageraient")
    assert not ref.is_word("endommagulent")

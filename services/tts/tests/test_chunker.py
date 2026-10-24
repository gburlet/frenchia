from frenchia_tts.chunker import chunk_text, hard_wrap, normalize, split_sentences


def test_normalize_whitespace_unicode() -> None:
    out = normalize("  Salut !   Ça   va ?\n\n\nL’ami  ")
    assert out == "Salut ! Ça va ?\nL'ami"


def test_nfc() -> None:
    assert normalize("é") == "é"


def test_splits_on_terminators_and_newlines() -> None:
    assert split_sentences("Un. Deux ! Trois ? Quatre… Cinq\nSix") == [
        "Un.", "Deux !", "Trois ?", "Quatre…", "Cinq", "Six",
    ]  # fmt: skip


def test_french_spacing_not_split() -> None:
    assert split_sentences("Il a dit : oui ; non.") == ["Il a dit : oui ; non."]
    assert split_sentences("Comment ? Bien !") == ["Comment ?", "Bien !"]


def test_guillemets_and_apostrophes() -> None:
    s = split_sentences("Il dit : « Ça va ? » Puis l’homme partit. J'arrive.")
    assert s == ["Il dit : « Ça va ? »", "Puis l'homme partit.", "J'arrive."]


def test_abbreviations_kept() -> None:
    assert split_sentences("M. Dupont et Mme. Roy arrivent.") == ["M. Dupont et Mme. Roy arrivent."]
    assert split_sentences("Des fruits, p. ex. des pommes, etc. Merci.") == [
        "Des fruits, p. ex. des pommes, etc.", "Merci.",
    ]  # fmt: skip
    assert split_sentences("Des fruits, etc. et du pain.") == ["Des fruits, etc. et du pain."]


def test_decimals_kept() -> None:
    assert split_sentences("Il coûte 3,5 euros ou 3.5 dollars.") == [
        "Il coûte 3,5 euros ou 3.5 dollars."
    ]


def test_merge_tiny_fragments() -> None:
    assert chunk_text("Oui. Non. Peut-être que demain, on verra bien ce qui arrive.") == [
        "Oui. Non. Peut-être que demain, on verra bien ce qui arrive."
    ]
    assert chunk_text("Une phrase assez longue pour rester seule. Ok.") == [
        "Une phrase assez longue pour rester seule. Ok."
    ]


def test_hard_wrap_at_comma_then_space() -> None:
    s = ", ".join(["mot" * 5] * 40)
    parts = hard_wrap(s, 300)
    assert all(len(p) <= 300 for p in parts) and len(parts) > 1
    assert all(p.endswith(",") for p in parts[:-1])
    spaced = " ".join(["abcdef"] * 200)
    assert all(len(p) <= 300 for p in hard_wrap(spaced, 300))
    assert " ".join(hard_wrap(spaced, 300)) == spaced
    assert all(len(p) <= 300 for p in hard_wrap("x" * 700, 300))


def test_chunk_text_empty() -> None:
    assert chunk_text("  \n ") == []

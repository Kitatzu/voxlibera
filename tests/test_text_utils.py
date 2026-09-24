from voxlibera.text_utils import repair_glued_sentences, split_sentences, strip_overlap


def test_repairs_glued_sentences_seen_in_gemini_output():
    assert repair_glued_sentences("up until World War II.the painting") == "up until World War II. the painting"
    assert repair_glued_sentences("interpret it.So there's lots") == "interpret it. So there's lots"
    assert repair_glued_sentences("arregla el trolecillo.y dice") == "arregla el trolecillo. y dice"


def test_keeps_technical_tokens_intact():
    assert repair_glued_sentences("we use Node.js and next.js") == "we use Node.js and next.js"
    assert repair_glued_sentences("catalog number 1972.145.2 here") == "catalog number 1972.145.2 here"
    assert repair_glued_sentences("for example e.g. this") == "for example e.g. this"


def test_splits_sentences_and_respects_abbreviations():
    text = "It's in the St. Petersburg area of Russia. ¿Por qué? No son influencers."
    assert split_sentences(text) == [
        "It's in the St. Petersburg area of Russia.",
        "¿Por qué?",
        "No son influencers.",
    ]


def test_split_handles_glued_boundary():
    assert split_sentences("Finland up until World War II.the painting is") == [
        "Finland up until World War II.",
        "the painting is",
    ]


def test_strip_overlap_removes_repeated_prefix():
    reference = "They were all different, and you had to understand what it was doing."
    new_text = "understand what it was doing. Every one of them was unique."
    assert strip_overlap(reference, new_text) == "Every one of them was unique."


def test_strip_overlap_tolerates_garbled_first_word():
    reference = "much longer than your software will be."
    new_text = "ware will be. So this is a painting"
    assert strip_overlap(reference, new_text) == "So this is a painting"


def test_strip_overlap_keeps_text_without_overlap():
    assert strip_overlap("Hello world.", "Completely new sentence.") == "Completely new sentence."

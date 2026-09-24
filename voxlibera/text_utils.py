"""Pure text helpers: sentence splitting, normalization and overlap removal.

These encode behaviour observed in gemini-3.5-transcribe-live output:
- interim transcripts contain the whole utterance so far and get revised in place;
- when the model starts a new internal segment it glues it without a space
  ("World War II.the painting", "trolecillo.y dice").
"""

import re

ABBREVIATIONS = {
    "mr.", "mrs.", "ms.", "dr.", "st.", "vs.", "etc.", "e.g.", "i.e.", "sr.", "sra.",
    "dra.", "ej.", "p.ej.", "no.", "approx.", "inc.", "ltd.", "jr.",
}

# Short function words that commonly start a glued segment after a period.
GLUE_WORDS = {
    "the", "and", "so", "but", "a", "an", "i", "we", "you", "it", "this", "that", "they",
    "he", "she", "or", "if", "then", "now", "because",
    "y", "e", "o", "u", "que", "el", "la", "los", "las", "en", "de", "un", "una", "pero",
    "entonces", "bueno", "porque", "yo", "no", "se", "lo", "es",
    "e", "os", "as", "um", "uma", "mas", "então",
}

_GLUED_BOUNDARY = re.compile(r"(?<=[^\W_])([.!?])([^\W\d_][\w']*)")
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?…])[\"'”»)]*\s+")
_WORD = re.compile(r"[\w']+")


def repair_glued_sentences(text: str) -> str:
    """Insert the missing space in "end.Start" joins without breaking "Node.js" or "1972.145"."""

    def replace(match: re.Match) -> str:
        punctuation, next_word = match.group(1), match.group(2)
        preceding_character = text[match.start() - 1]
        starts_capitalized = next_word[0].isupper() and preceding_character.islower()
        if starts_capitalized or next_word.lower() in GLUE_WORDS:
            return f"{punctuation} {next_word}"
        return match.group(0)

    return _GLUED_BOUNDARY.sub(replace, text)


def split_sentences(text: str) -> list[str]:
    """Split a transcript into sentences, keeping abbreviations like "St." intact."""
    text = repair_glued_sentences(" ".join(text.split()))
    if not text:
        return []
    pieces = _SENTENCE_BOUNDARY.split(text)
    sentences: list[str] = []
    for piece in pieces:
        piece = piece.strip()
        if not piece:
            continue
        if sentences and _ends_with_abbreviation(sentences[-1]):
            sentences[-1] = f"{sentences[-1]} {piece}"
        else:
            sentences.append(piece)
    return sentences


def _ends_with_abbreviation(sentence: str) -> bool:
    last_word = sentence.rsplit(" ", 1)[-1].lower()
    return last_word in ABBREVIATIONS


def normalize_words(text: str) -> list[str]:
    return [word.lower() for word in _WORD.findall(text)]


def same_sentence(first: str, second: str) -> bool:
    return normalize_words(first) == normalize_words(second)


def strip_overlap(reference_text: str, new_text: str, min_overlap_words: int = 2,
                  max_skipped_words: int = 3) -> str:
    """Remove the leading words of new_text that repeat the tail of reference_text.

    Used when a fresh Gemini session takes over mid-speech: its first utterance
    re-transcribes a few seconds already covered by the previous session. The new
    session may start mid-word, so up to max_skipped_words garbled leading words
    are tolerated before the overlap.
    """
    reference_words = normalize_words(reference_text)
    new_tokens = new_text.split()
    new_words = [" ".join(normalize_words(token)) for token in new_tokens]
    best_cut = 0
    for skipped in range(0, min(max_skipped_words, len(new_words)) + 1):
        candidate_words = new_words[skipped:]
        longest = min(len(reference_words), len(candidate_words))
        for overlap in range(longest, min_overlap_words - 1, -1):
            if reference_words[-overlap:] == candidate_words[:overlap]:
                best_cut = max(best_cut, skipped + overlap)
                break
    return " ".join(new_tokens[best_cut:])

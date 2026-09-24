from voxlibera.segmenter import SentenceSegmenter


def feed(segmenter: SentenceSegmenter, interims: list[str]) -> list[str]:
    committed = []
    for step, text in enumerate(interims):
        update = segmenter.on_interim(text, audio_time=step * 0.5)
        committed.extend(sentence.text for sentence in update.committed)
    return committed


def test_commits_complete_sentence_once_stable():
    segmenter = SentenceSegmenter()
    committed = feed(segmenter, [
        "So this is a painting",
        "So this is a painting at the Met.",
        "So this is a painting at the Met. On the left",
        "So this is a painting at the Met. On the left is the painting",
    ])
    assert committed == ["So this is a painting at the Met."]
    assert segmenter.pending_text == "On the left is the painting"


def test_does_not_commit_last_sentence_before_final():
    segmenter = SentenceSegmenter()
    committed = feed(segmenter, ["Hello there.", "Hello there.", "Hello there."])
    assert committed == []


def test_waits_while_sentence_is_being_revised():
    segmenter = SentenceSegmenter()
    committed = feed(segmenter, [
        "They actually rename the town. It is",
        "They actually renamed the town. It is in",
        "They actually renamed the town. It is in Russia",
    ])
    assert committed == ["They actually renamed the town."]


def test_final_commits_remainder_and_reports_corrections():
    segmenter = SentenceSegmenter()
    feed(segmenter, [
        "y hasta creándolos. Son formas",
        "y hasta creándolos. Son formas increíbles",
    ])
    update = segmenter.on_final("y hasta creando los tuyos. Son formas increíbles de construir.", audio_time=5)
    assert [correction.text for correction in update.corrections] == ["y hasta creando los tuyos."]
    assert [sentence.text for sentence in update.committed] == ["Son formas increíbles de construir."]
    assert update.utterance_finished
    assert segmenter.pending_text == ""


def test_timestamps_are_monotonic():
    segmenter = SentenceSegmenter()
    feed(segmenter, ["One. Two", "One. Two", "One. Two. Three", "One. Two. Three"])
    update = segmenter.on_final("One. Two. Three. Four.", audio_time=10)
    starts = [sentence.start for sentence in update.committed]
    assert starts == sorted(starts)
    assert all(sentence.end > sentence.start for sentence in update.committed)

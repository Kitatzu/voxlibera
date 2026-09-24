"""Turns a stream of interim/final transcripts into committed sentences.

Gemini only finalizes an utterance when the speaker pauses; a fluent speaker can
go 20-60 s without one. Waiting for finals would delay translations that long, so a
sentence is committed as soon as it is complete (another sentence already started
after it) and unchanged across consecutive interim updates. The final transcript
is then used to correct committed sentences and to commit the remainder.
"""

from dataclasses import dataclass

from voxlibera.text_utils import same_sentence, split_sentences

SPEECH_LEAD_SECONDS = 1.0  # interim text shows up roughly this long after speech starts


@dataclass
class CommittedSentence:
    text: str
    start: float
    end: float


@dataclass
class Correction:
    utterance_index: int
    text: str


@dataclass
class SegmenterUpdate:
    committed: list[CommittedSentence]
    corrections: list[Correction]
    utterance_finished: bool = False


class SentenceSegmenter:
    def __init__(self, stability_updates: int = 2) -> None:
        self.stability_updates = stability_updates
        self.last_commit_end = 0.0
        self._reset_utterance()

    def _reset_utterance(self) -> None:
        self.committed_texts: list[str] = []
        self.first_seen: dict[int, float] = {}
        self.stable_counts: dict[int, int] = {}
        self.previous_sentences: list[str] = []
        self.pending_text = ""

    def on_interim(self, text: str, audio_time: float) -> SegmenterUpdate:
        sentences = split_sentences(text)
        for index in range(len(sentences)):
            self.first_seen.setdefault(index, audio_time)

        committed: list[CommittedSentence] = []
        # Only sentences followed by another one are complete; commit them in order.
        for index in range(len(self.committed_texts), len(sentences) - 1):
            sentence = sentences[index]
            previous = self.previous_sentences[index] if index < len(self.previous_sentences) else None
            if previous is not None and same_sentence(previous, sentence):
                self.stable_counts[index] = self.stable_counts.get(index, 1) + 1
            else:
                self.stable_counts[index] = 1
            if self.stable_counts[index] < self.stability_updates:
                break
            end = self.first_seen.get(index + 1, audio_time)
            committed.append(self._commit(sentence, index, end))

        self.previous_sentences = sentences
        self.pending_text = " ".join(sentences[len(self.committed_texts):])
        return SegmenterUpdate(committed=committed, corrections=[])

    def on_final(self, text: str, audio_time: float) -> SegmenterUpdate:
        sentences = split_sentences(text)
        corrections = [
            Correction(utterance_index=index, text=sentence)
            for index, sentence in enumerate(sentences[: len(self.committed_texts)])
            if not same_sentence(sentence, self.committed_texts[index])
        ]
        remaining = sentences[len(self.committed_texts):]
        committed: list[CommittedSentence] = []
        for offset, sentence in enumerate(remaining):
            index = len(self.committed_texts)
            is_last = offset == len(remaining) - 1
            end = audio_time if is_last else self.first_seen.get(index + 1, audio_time)
            committed.append(self._commit(sentence, index, end))

        self._reset_utterance()
        return SegmenterUpdate(committed=committed, corrections=corrections, utterance_finished=True)

    def flush(self, audio_time: float) -> SegmenterUpdate:
        """Commit whatever is pending, e.g. when the source stops mid-sentence."""
        if not self.previous_sentences:
            self._reset_utterance()
            return SegmenterUpdate(committed=[], corrections=[], utterance_finished=True)
        return self.on_final(" ".join(self.previous_sentences), audio_time)

    def _commit(self, sentence: str, index: int, end: float) -> CommittedSentence:
        start = max(self.last_commit_end, self.first_seen.get(index, end) - SPEECH_LEAD_SECONDS)
        end = max(end, start + 0.5)
        self.committed_texts.append(sentence)
        self.last_commit_end = end
        return CommittedSentence(text=sentence, start=start, end=end)

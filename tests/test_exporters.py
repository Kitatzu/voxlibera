from voxlibera.exporters import to_srt, to_text, to_vtt
from voxlibera.models import Segment

SEGMENTS = [
    Segment(id=2, start=4.0, end=6.5, original="Second sentence.", translations={"es": "Segunda oración."}),
    Segment(id=1, start=0.5, end=3.25, original="First sentence.", translations={}),
]


def test_srt_orders_by_time_and_falls_back_to_original():
    srt = to_srt(SEGMENTS, "es")
    assert srt.startswith("1\n00:00:00,500 --> 00:00:03,250\nFirst sentence.\n")
    assert "2\n00:00:04,000 --> 00:00:06,500\nSegunda oración.\n" in srt


def test_vtt_header_and_dot_separator():
    vtt = to_vtt(SEGMENTS, "original")
    assert vtt.startswith("WEBVTT\n")
    assert "00:00:00.500 --> 00:00:03.250" in vtt


def test_long_sentences_are_split_into_readable_captions():
    long_segment = Segment(id=1, start=0, end=10, original=" ".join(["word"] * 60))
    captions = [block for block in to_srt([long_segment], "original").split("\n\n") if block.strip()]
    assert len(captions) > 1
    assert all(len(block.splitlines()[2]) <= 84 for block in captions)


def test_plain_text():
    assert to_text(SEGMENTS, "original") == "First sentence.\nSecond sentence.\n"

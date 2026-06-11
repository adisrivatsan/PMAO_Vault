import tempfile
from pathlib import Path
from pmao.transcript import preprocess_vtt, preprocess_transcript

def test_preprocess_vtt_strips_timestamps():
    vtt = """WEBVTT

00:00:01.000 --> 00:00:03.000
<v Alex Jordan>Hello everyone</v>

00:00:04.000 --> 00:00:06.000
<v Sam Lee>Thanks for joining</v>
"""
    result = preprocess_vtt(vtt)
    assert "00:00:01" not in result
    assert "Alex Jordan: Hello everyone" in result
    assert "Sam Lee: Thanks for joining" in result

def test_preprocess_transcript_txt_passthrough():
    with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
        f.write("plain text content")
        path = Path(f.name)
    assert preprocess_transcript(path) == "plain text content"

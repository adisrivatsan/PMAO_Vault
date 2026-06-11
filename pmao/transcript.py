import re
from pathlib import Path


def preprocess_vtt(text: str) -> str:
    """Convert WebVTT to plain 'Name: text' lines."""
    lines_out = []
    current_speaker = None
    current_text = []
    prev_was_blank = False

    for line in text.splitlines():
        line = line.strip()
        if not line or line == "WEBVTT":
            if current_speaker and current_text:
                lines_out.append(f"{current_speaker}: {' '.join(current_text)}")
                current_text = []
            prev_was_blank = True
            continue
        if "-->" in line:
            prev_was_blank = False
            continue
        # Cue identifiers appear after a blank line and before a timestamp line.
        # They contain no speaker tags — skip them.
        if prev_was_blank and not line.startswith("<v"):
            prev_was_blank = False
            continue
        prev_was_blank = False
        speaker_match = re.match(r"<v ([^>]+)>(.*)", line)
        if speaker_match:
            if current_speaker and current_text:
                lines_out.append(f"{current_speaker}: {' '.join(current_text)}")
                current_text = []
            current_speaker = speaker_match.group(1).strip()
            rest = re.sub(r"<[^>]+>", "", speaker_match.group(2)).strip()
            if rest:
                current_text.append(rest)
            continue
        if current_speaker:
            current_text.append(re.sub(r"<[^>]+>", "", line).strip())

    if current_speaker and current_text:
        lines_out.append(f"{current_speaker}: {' '.join(current_text)}")

    return "\n".join(lines_out)


def preprocess_transcript(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() == ".vtt":
        return preprocess_vtt(text)
    return text

"""Resolve the client's inconsistently named MP3s to clip numbers.

The folder contains 'Audio 1.mp3', 'Audio4.mp3' and 'Audio10.mp3' — the space
is present for some numbers and absent for others.
"""

import re

AUDIO_FILENAME_RE = re.compile(r"^Audio\s*(\d+)\.mp3$", re.IGNORECASE)


def clip_number_from_filename(filename):
    """Return the clip number for an MP3 filename, or None if unrelated."""
    match = AUDIO_FILENAME_RE.match(filename)
    return int(match.group(1)) if match else None


def map_audio_files(audio_dir):
    """Return {clip_number: Path} for every MP3 in the folder."""
    mapping = {}
    for path in sorted(audio_dir.iterdir()):
        number = clip_number_from_filename(path.name)
        if number is None:
            continue
        if number in mapping:
            raise ValueError(f"Two files claim clip {number}: {mapping[number]}, {path}")
        mapping[number] = path
    return mapping

"""Split the client's listening worksheet markdown into one body per clip.

The file holds 20 worksheets followed by an appendix of base64 image data.
The appendix is discarded — images come from the .docx instead, because the
markdown's copies are lossy re-renders and clip 1's are cropped so badly they
lose the A/B/C option labels.
"""

import re

CLIP_HEADER_RE = re.compile(r"^\**Audio ?[Cc]lip ?(\d+).*$", re.MULTILINE)
IMAGE_DATA_RE = re.compile(r"^\[image\d+\]: <data:", re.MULTILINE)


def strip_image_data(text):
    """Drop the trailing base64 image appendix."""
    match = IMAGE_DATA_RE.search(text)
    return text[: match.start()] if match else text


def split_clips(text):
    """Return {clip_number: body_text} for all clips found in the markdown."""
    body = strip_image_data(text)
    numbers = [int(n) for n in CLIP_HEADER_RE.findall(body)]
    segments = CLIP_HEADER_RE.split(body)

    # re.split with one capturing group yields:
    #   [preamble, num1, body1, num2, body2, ...]
    bodies = segments[2::2]
    return dict(zip(numbers, bodies))

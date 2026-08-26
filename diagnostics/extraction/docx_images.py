"""Pull images out of a .docx in the order they appear in the document.

A .docx stores images as `word/media/imageN.jpg` parts, but those part names
are assigned arbitrarily by the authoring tool — `image6.jpg` is the first
image in this bank's document. The only reliable ordering is the sequence of
`r:embed` references inside `word/document.xml`, resolved through the
relationships file.
"""

import re
import zipfile

RELATIONSHIP_RE = re.compile(r'Id="(rId\d+)"[^>]*Target="(media/[^"]+)"')
EMBED_RE = re.compile(r'r:embed="(rId\d+)"')


def extract_images_in_document_order(docx_path):
    """Return [(part_name, image_bytes)] in document order."""
    with zipfile.ZipFile(docx_path) as archive:
        rels_xml = archive.read("word/_rels/document.xml.rels").decode("utf-8")
        relationships = dict(RELATIONSHIP_RE.findall(rels_xml))

        document_xml = archive.read("word/document.xml").decode("utf-8")

        images = []
        for rel_id in EMBED_RE.findall(document_xml):
            target = relationships.get(rel_id)
            if target is None:
                continue
            images.append((target, archive.read(f"word/{target}")))
    return images

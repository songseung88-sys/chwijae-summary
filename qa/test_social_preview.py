"""Regression tests for public social-preview metadata and binary asset."""
import unittest
from html.parser import HTMLParser
from pathlib import Path

BASE="https://chwijae-api-ejmdmrnztq-du.a.run.app/"
ROOT=Path(__file__).resolve().parents[1]
JPEG=ROOT/"api/static/og-thumbnail-square.jpg"
HTML=ROOT/"api/static/index.html"

class Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags={}
        self.canonical=None
    def handle_starttag(self,tag,attributes):
        attributes=dict(attributes)
        if tag=="meta":
            key=attributes.get("property") or attributes.get("name")
            if key:self.tags[key]=attributes.get("content")
        if tag=="link" and attributes.get("rel")=="canonical":
            self.canonical=attributes.get("href")

def jpeg_dimensions(b):
    if b[:2]!=b"\xff\xd8":
        raise AssertionError("Not a JPEG")
    i=2
    while i<len(b):
        if b[i]!=255:
            i+=1
            continue
        while i<len(b) and b[i]==255:i+=1
        if i>=len(b):break
        marker=b[i];i+=1
        if marker in (0xd8,0xd9,0x01) or 0xd0<=marker<=0xd7:
            continue
        if i+2>len(b):break
        segment_size=int.from_bytes(b[i:i+2],"big")
        if marker in (0xc0,0xc1,0xc2,0xc3,0xc5,0xc6,0xc7,0xc9,0xca,0xcb,0xcd,0xce,0xcf):
            return int.from_bytes(b[i+3:i+5],"big"),int.from_bytes(b[i+5:i+7],"big")
        i+=segment_size
    raise AssertionError("Missing JPEG size frame")

class SocialPreview(unittest.TestCase):
    def test_image_is_square_jpeg_and_under_size_budget(self):
        im=JPEG.read_bytes()
        self.assertGreater(len(im),100000)
        self.assertLess(len(im),400000)
        self.assertEqual(jpeg_dimensions(im),(1254,1254))
    def test_metadata_exactly_matches_public_asset(self):
        p=Tags()
        p.feed(HTML.read_text(encoding="utf-8"))
        self.assertEqual(p.canonical,BASE)
        self.assertEqual(p.tags["og:url"],BASE)
        self.assertEqual(p.tags["og:title"],"취재를 종합하면")
        self.assertEqual(p.tags["og:image"],BASE+"static/og-thumbnail-square.jpg")
        self.assertEqual(p.tags["og:image:secure_url"],p.tags["og:image"])
        self.assertEqual(p.tags["og:image:type"],"image/jpeg")
        self.assertEqual(p.tags["og:image:width"],"1254")
        self.assertEqual(p.tags["og:image:height"],"1254")
        self.assertEqual(p.tags["twitter:image"],p.tags["og:image"])
        self.assertEqual(p.tags["twitter:card"],"summary")
    def test_image_is_served_through_existing_static_mount(self):
        api=(ROOT/"api/main.py").read_text(encoding="utf-8")
        docker=(ROOT/"api/Dockerfile").read_text(encoding="utf-8")
        self.assertIn('app.mount("/static", StaticFiles(directory=STATIC_DIR)',api)
        self.assertIn("COPY static ./static",docker)

if __name__=="__main__":
    unittest.main()

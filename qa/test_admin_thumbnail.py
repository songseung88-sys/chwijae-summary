"""Unit tests for persistent admin-editable Open Graph preview images."""
import io
import pathlib
import sys
import unittest
from PIL import Image

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"api"))
from share_thumbnail import (
    InvalidThumbnail, MAX_STORED_BYTES, image_url,
    image_version, process_thumbnail, render_preview_html,
    THUMBNAIL_SIZE, STATIC_FALLBACK_URL,
)

class ThumbnailUploadTests(unittest.TestCase):
    def make_image(self,kind="PNG",size=(800,800),color=(0,85,170,255)):
        im=Image.new("RGBA",size,color)
        output=io.BytesIO()
        if kind=="JPEG":
            im=im.convert("RGB")
        im.save(output,format=kind)
        return output.getvalue()

    def test_square_png_is_padded_not_cropped_and_saved_as_wide_jpg(self):
        jpeg=process_thumbnail(self.make_image())
        self.assertTrue(jpeg.startswith(bytes((255,216,255))))
        self.assertLessEqual(len(jpeg),MAX_STORED_BYTES)
        with Image.open(io.BytesIO(jpeg)) as im:
            self.assertEqual(im.size,THUMBNAIL_SIZE)
            self.assertEqual(im.mode,"RGB")
            # Corners are the light blue padding; middle retains the art.
            c=im.getpixel((10,10))
            self.assertTrue(all(a>200 for a in c))
            middle=im.getpixel((600,315))
            self.assertGreater(middle[2],middle[0])

    def test_jpeg_and_webp_are_supported(self):
        for fmt in ("JPEG","WEBP"):
            with self.subTest(fmt=fmt):
                result=process_thumbnail(self.make_image(fmt,(1200,630)))
                with Image.open(io.BytesIO(result)) as img:
                    self.assertEqual(img.size,(1200,630))

    def test_invalid_bytes_and_oversized_are_rejected(self):
        with self.assertRaises(InvalidThumbnail):
            process_thumbnail(b"<svg xmlns='http://www.w3.org/2000/svg'></svg>")
        with self.assertRaises(InvalidThumbnail):
            process_thumbnail(b"x"*(5*1024*1024+1))
        with self.assertRaises(InvalidThumbnail):
            process_thumbnail(self.make_image(size=(100,100)))

    def test_image_url_is_unique_and_html_is_rendered_for_crawlers(self):
        raw=process_thumbnail(self.make_image())
        ver=image_version(raw)
        self.assertEqual(len(ver),64)
        url=image_url(ver)
        self.assertIn("/share-images/",url)
        self.assertEqual(image_url(),STATIC_FALLBACK_URL)
        html=(ROOT/"api/static/index.html").read_text(encoding="utf-8")
        rendered=render_preview_html(html,url)
        self.assertEqual(rendered.count(url),3)
        self.assertNotIn('content="'+STATIC_FALLBACK_URL+'"',rendered)
        self.assertIn('property="og:image:width" content="1200"',rendered)
        self.assertIn('property="og:image:height" content="630"',rendered)
        self.assertIn('name="twitter:card" content="summary_large_image"',rendered)
        self.assertEqual(render_preview_html(html,image_url()),html)
        with self.assertRaises(ValueError):
            render_preview_html(html,"https://untrusted.example.com/inject.jpg")

    def test_route_is_password_protected_and_persistent(self):
        main=(ROOT/"api/main.py").read_text(encoding="utf-8")
        for route in ('@app.put("/api/admin/thumbnail")',
                      '@app.delete("/api/admin/thumbnail")',
                      '@app.get("/api/admin/thumbnail")'):
            self.assertIn(route,main)
        self.assertIn('require_admin(x_admin_password)',main)
        self.assertIn('db.collection("share_images").document(version).set',main)
        self.assertIn('db.collection("site_config").document("social_preview").set',main)
        self.assertIn('return HTMLResponse(',main)
        self.assertIn('Cache-Control": "no-cache',main)

if __name__=="__main__":
    unittest.main()

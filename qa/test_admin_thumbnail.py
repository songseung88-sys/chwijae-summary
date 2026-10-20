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
    THUMBNAIL_SIZE, STATIC_FALLBACK_URL, DEFAULT_OG_TITLE,
    DEFAULT_OG_DESCRIPTION, validate_preview_copy,
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

    def test_editable_og_title_description_are_escaped_and_length_checked(self):
        html=(ROOT/"api/static/index.html").read_text(encoding="utf-8")
        content=render_preview_html(
            html,STATIC_FALLBACK_URL,"뉴스 <img onerror=bad> & 분석", '설명 "인용" & 검증'
        )
        self.assertIn('property="og:title" content="뉴스 &lt;img onerror=bad&gt; &amp; 분석"',content)
        self.assertIn('name="twitter:title" content="뉴스 &lt;img onerror=bad&gt; &amp; 분석"',content)
        self.assertIn('property="og:description" content="설명 &quot;인용&quot; &amp; 검증"',content)
        self.assertIn('name="twitter:description" content="설명 &quot;인용&quot; &amp; 검증"',content)
        self.assertIn('name="description" content="설명 &quot;인용&quot; &amp; 검증"',content)
        self.assertIn('<title>취재를 종합하면</title>',content)
        self.assertEqual(validate_preview_copy("  새  제목 "," 상세   설명 "),("새 제목","상세 설명"))
        for title,description in (("","설명"),("제목",""),("a"*101,"설명"),("제목","b"*301),
                                  (None,"설명"),(1,"설명")):
            with self.subTest(title=title,description=description),self.assertRaises(ValueError):
                validate_preview_copy(title,description)

    def test_route_is_password_protected_and_persistent(self):
        main=(ROOT/"api/main.py").read_text(encoding="utf-8")
        for route in ('@app.put("/api/admin/thumbnail/metadata")',
                      '@app.put("/api/admin/thumbnail")',
                      '@app.delete("/api/admin/thumbnail")',
                      '@app.get("/api/admin/thumbnail")'):
            self.assertIn(route,main)
        self.assertIn('require_admin(x_admin_password)',main)
        self.assertIn('db.collection("share_images").document(version).set',main)
        self.assertIn('db.collection("site_config").document("social_preview").set',main)
        self.assertIn('return HTMLResponse(',main)
        self.assertIn('Cache-Control": "no-cache',main)


class SimulatedEndpoints(unittest.TestCase):
    """Exercise the real admin handlers against a tiny local Firestore fake."""
    def test_upload_persists_and_updates_crawler_html_then_resets(self):
        import ast, base64, binascii, copy, hmac, os, re
        from share_thumbnail import process_thumbnail
        class HTTPError(Exception):
            def __init__(self,status_code,detail):
                self.status_code=status_code
                self.detail=detail
        class Snapshot:
            def __init__(self,data):
                self.exists=data is not None
                self.data=data
            def to_dict(self):return self.data
        class Doc:
            def __init__(self,data,key):
                self.data=data;self.key=key
            def get(self):return Snapshot(self.data.get(self.key))
            def set(self,info,merge=False):
                if merge and self.key in self.data:
                    self.data[self.key].update(info)
                else:
                    self.data[self.key]=info
            def delete(self):self.data.pop(self.key,None)
        class Collection:
            def __init__(self,data):self.data=data
            def document(self,key):return Doc(self.data,key)
        class DB:
            def __init__(self):self.data={}
            def collection(self,key):return Collection(self.data.setdefault(key,{}))
        source=(ROOT/"api/main.py").read_text(encoding="utf-8")
        methods={"require_admin","current_thumbnail","admin_thumbnail",
                 "upload_thumbnail","update_thumbnail_metadata",
                 "reset_thumbnail","public_thumbnail","dashboard_page"}
        functions=[]
        for node in ast.parse(source).body:
            if isinstance(node,ast.FunctionDef) and node.name in methods:
                node=copy.deepcopy(node);node.decorator_list=[];functions.append(node)
        database=DB()
        ns=dict(
            db=database,base64=base64,binascii=binascii,hmac=hmac,
            re=re,os=os,open=open,
            ADMIN_EDITOR_PASSWORD="protected",MAX_UPLOAD_BYTES=5*1024*1024,
            Header=lambda default=None:default,HTTPException=HTTPError,
            InvalidThumbnail=InvalidThumbnail,image_url=image_url,
            image_version=image_version,process_thumbnail=process_thumbnail,
            render_preview_html=render_preview_html,
            DEFAULT_OG_TITLE=DEFAULT_OG_TITLE,
            DEFAULT_OG_DESCRIPTION=DEFAULT_OG_DESCRIPTION,
            validate_preview_copy=validate_preview_copy,
            STATIC_DIR=str(ROOT/"api/static"),
            firestore=type("F",(),{"SERVER_TIMESTAMP":"timestamp"})(),
            Response=lambda content,media_type,headers:dict(content=content,media_type=media_type,headers=headers),
            HTMLResponse=lambda content,headers:dict(content=content,headers=headers),
        )
        exec(compile(ast.Module(body=functions,type_ignores=[]),"<thumbnail-functions>","exec"),ns)
        self.assertEqual(ns["current_thumbnail"]()["url"],STATIC_FALLBACK_URL)
        for method,args in (
            ("admin_thumbnail",("bad",)),
            ("upload_thumbnail",({"image_base64":"abcd"},"bad")),
            ("reset_thumbnail",("bad",)),
            ("update_thumbnail_metadata",({"title":"비공개","description":"설명"},"bad")),
        ):
            with self.assertRaises(HTTPError) as error:
                ns[method](*args)
            self.assertEqual(error.exception.status_code,401)
        png=ThumbnailUploadTests().make_image()
        result=ns["upload_thumbnail"]({"image_base64":base64.b64encode(png).decode("ascii")},"protected")
        url=result["url"]
        self.assertIn("/share-images/",url)
        self.assertEqual(ns["admin_thumbnail"]("protected")["title"],DEFAULT_OG_TITLE)
        # Updating text does not replace or invalidate the current image.
        ns["update_thumbnail_metadata"](
            {"title":"연구를 위한 뉴스", "description":"언론  표현의   시계열"}, "protected"
        )
        self.assertEqual(ns["current_thumbnail"]()["url"],url)
        self.assertEqual(ns["current_thumbnail"]()["title"],"연구를 위한 뉴스")
        self.assertEqual(ns["current_thumbnail"]()["description"],"언론 표현의 시계열")
        for invalid in ({"title":"","description":"ok"},
                        {"title":"제목","description":"x"*301}):
            with self.assertRaises(HTTPError) as bad:
                ns["update_thumbnail_metadata"](invalid,"protected")
            self.assertEqual(bad.exception.status_code,400)
        self.assertEqual(ns["current_thumbnail"]()["url"],url)
        page=ns["dashboard_page"]()
        self.assertEqual(page["content"].count(url),3)
        self.assertIn('property="og:title" content="연구를 위한 뉴스"',page["content"])
        self.assertIn('name="twitter:description" content="언론 표현의 시계열"',page["content"])
        self.assertEqual(page["headers"]["Cache-Control"],"no-cache, max-age=0")
        image=ns["public_thumbnail"](result["version"])
        self.assertEqual(image["media_type"],"image/jpeg")
        self.assertEqual(image["content"],process_thumbnail(png))
        self.assertIn("immutable",image["headers"]["Cache-Control"])
        with self.assertRaises(HTTPError) as err:
            ns["upload_thumbnail"]({"image_base64":base64.b64encode(b"not-an-image").decode()},"protected")
        self.assertEqual(err.exception.status_code,400)
        # Image replacement preserves edited text, while image reset restores only the image.
        ns["upload_thumbnail"]({"image_base64":base64.b64encode(png).decode("ascii")},"protected")
        self.assertEqual(ns["current_thumbnail"]()["title"],"연구를 위한 뉴스")
        ns["reset_thumbnail"]("protected")
        self.assertEqual(ns["current_thumbnail"]()["url"],STATIC_FALLBACK_URL)
        self.assertEqual(ns["current_thumbnail"]()["title"],"연구를 위한 뉴스")
        self.assertEqual(ns["dashboard_page"]()["content"].count(STATIC_FALLBACK_URL),3)
        self.assertEqual(ns["public_thumbnail"](result["version"])["content"],image["content"])


if __name__=="__main__":
    unittest.main()

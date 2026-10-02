"""Prepare the title-screen art and embed it into index.html (between the TITLE_IMG markers).

Run:  python assets/embed_title.py <title_art.jpg>
The art's bottom strip carries a placeholder copyright line ("(c) [Year] ..."); it is cropped off and the page
draws its own copyright text instead. Saves assets/title.jpg (1600 px wide) and embeds it as a data URI.
"""
import base64, io, os, re, sys
from PIL import Image

here = os.path.dirname(os.path.abspath(__file__))
html_path = os.path.join(here, '..', 'index.html')
src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, 'title_src.jpg')
im = Image.open(src).convert('RGB')
w, h = im.size
im = im.crop((0, 0, w, round(h * 1068 / 1116)))          # drop the placeholder copyright line
im = im.resize((1600, round(im.size[1] * 1600 / w)), Image.LANCZOS)
out = os.path.join(here, 'title.jpg')
im.save(out, quality=86, optimize=True, progressive=True)
data = base64.b64encode(open(out, 'rb').read()).decode('ascii')
block = '<script id="titleImg">/*TITLE_IMG*/window.TITLE_IMG="data:image/jpeg;base64,' + data + '";/*/TITLE_IMG*/</script>'
html = open(html_path, encoding='utf-8').read()
pattern = re.compile(r'<script id="titleImg">/\*TITLE_IMG\*/.*?/\*/TITLE_IMG\*/</script>', re.S)
if pattern.search(html):
    html = pattern.sub(lambda m: block, html)
else:
    anchor = '/*/NYAN_GLB*/</script>'
    assert anchor in html
    html = html.replace(anchor, anchor + '\n' + block, 1)
open(html_path, 'w', encoding='utf-8', newline='\n').write(html)
print('title art', im.size, os.path.getsize(out), 'bytes')

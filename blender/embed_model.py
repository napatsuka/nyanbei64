"""Embed blender/nyanbee.glb into index.html as base64 (between the NYAN_GLB markers).

Embedding keeps the game working when index.html is opened straight from disk,
where the browser blocks fetching a separate .glb file.
Run after build_nyanbee.py:  python blender/embed_model.py
"""
import base64, os, re

here = os.path.dirname(os.path.abspath(__file__))
html_path = os.path.join(here, '..', 'index.html')
glb = open(os.path.join(here, 'nyanbee.glb'), 'rb').read()
b64 = base64.b64encode(glb).decode('ascii')
html = open(html_path, encoding='utf-8').read()
block = '<script id="nyanGlb">/*NYAN_GLB*/window.NYAN_GLB="' + b64 + '";/*/NYAN_GLB*/</script>'
pattern = re.compile(r'<script id="nyanGlb">/\*NYAN_GLB\*/.*?/\*/NYAN_GLB\*/</script>', re.S)
if pattern.search(html):
    html = pattern.sub(lambda m: block, html)
else:
    anchor = '<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>'
    assert anchor in html
    html = html.replace(anchor, anchor + '\n' + block)
open(html_path, 'w', encoding='utf-8', newline='\n').write(html)
print('embedded', len(glb), 'bytes ->', len(b64), 'chars')

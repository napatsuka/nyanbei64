"""Embed blender/nyanbee_photo.glb and assets/nyanbee_calib.json into index.html (between the NYAN_PHOTO markers).

Run after make_hull.py and blender/build_hull.py:  python assets/embed_photo3d.py
"""
import base64, json, os, re

here = os.path.dirname(os.path.abspath(__file__))
root = os.path.join(here, '..')
html_path = os.path.join(root, 'index.html')
glb = base64.b64encode(open(os.path.join(root, 'blender', 'nyanbee_photo.glb'), 'rb').read()).decode('ascii')
calib = json.load(open(os.path.join(here, 'nyanbee_calib.json')))
block = ('<script id="nyanPhoto">/*NYAN_PHOTO*/window.NYAN_PHOTO={glb:"' + glb + '",calib:' + json.dumps(calib, separators=(',', ':'))
         + '};/*/NYAN_PHOTO*/</script>')
html = open(html_path, encoding='utf-8').read()
pattern = re.compile(r'<script id="nyanPhoto">/\*NYAN_PHOTO\*/.*?/\*/NYAN_PHOTO\*/</script>', re.S)
if pattern.search(html):
    html = pattern.sub(lambda m: block, html)
else:
    anchor = '/*/NYAN_GLB*/</script>'
    assert anchor in html
    html = html.replace(anchor, anchor + '\n' + block, 1)
open(html_path, 'w', encoding='utf-8', newline='\n').write(html)
print('embedded photo 3D', len(glb), 'chars')

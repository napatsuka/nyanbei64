"""Embed the assets/nyanbee_<view>.png sprites into index.html as data URIs (between the NYAN_SPRITES markers).

Run after make_sprites.py:  python assets/embed_sprites.py
"""
import base64, os, re

here = os.path.dirname(os.path.abspath(__file__))
html_path = os.path.join(here, '..', 'index.html')
uri = lambda n: 'data:image/png;base64,' + base64.b64encode(open(os.path.join(here, f'nyanbee_{n}.png'), 'rb').read()).decode('ascii')
VIEWS = ['front', 'back', 'side_r', 'side_l', 'fq_r', 'fq_l', 'bq_l']
block = ('<script id="nyanSprites">/*NYAN_SPRITES*/window.NYAN_SPRITES={'
         + ','.join(f'{v}:"{uri(v)}"' for v in VIEWS) + '};/*/NYAN_SPRITES*/</script>')
html = open(html_path, encoding='utf-8').read()
pattern = re.compile(r'<script id="nyanSprites">/\*NYAN_SPRITES\*/.*?/\*/NYAN_SPRITES\*/</script>', re.S)
if pattern.search(html):
    html = pattern.sub(lambda m: block, html)
else:
    anchor = '/*/NYAN_GLB*/</script>'
    assert anchor in html
    html = html.replace(anchor, anchor + '\n' + block, 1)
open(html_path, 'w', encoding='utf-8', newline='\n').write(html)
print('embedded sprites')

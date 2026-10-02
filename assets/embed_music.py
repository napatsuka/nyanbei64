"""Embed assets/pigment_leap.mp3 into index.html as base64 (between the BGM_MP3 markers).

Embedding keeps the music working when index.html is opened straight from disk.
Run:  python assets/embed_music.py
"""
import base64, os, re

here = os.path.dirname(os.path.abspath(__file__))
html_path = os.path.join(here, '..', 'index.html')
mp3 = open(os.path.join(here, 'pigment_leap.mp3'), 'rb').read()
block = '<script id="bgmData">/*BGM_MP3*/window.BGM_MP3="' + base64.b64encode(mp3).decode('ascii') + '";/*/BGM_MP3*/</script>'
html = open(html_path, encoding='utf-8').read()
pattern = re.compile(r'<script id="bgmData">/\*BGM_MP3\*/.*?/\*/BGM_MP3\*/</script>', re.S)
if pattern.search(html):
    html = pattern.sub(lambda m: block, html)
else:
    anchor = '/*/NYAN_GLB*/</script>'
    assert anchor in html
    html = html.replace(anchor, anchor + '\n' + block, 1)
open(html_path, 'w', encoding='utf-8', newline='\n').write(html)
print('embedded', len(mp3), 'bytes')

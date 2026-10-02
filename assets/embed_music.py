"""Embed the game's music into index.html as base64 (between the BGM_MP3 markers).

  assets/pigment_leap.mp3   -> window.BGM_MP3    (played during play)
  assets/my_river_raft.mp3  -> window.TITLE_MP3  (title screen and menus)

The block goes at the very END of the page: the title screen and the game start as soon as the main script
has run, while the (large) music data keeps downloading behind them; the game picks it up once it arrives.
Embedding keeps the music working when index.html is opened straight from disk.
Run:  python assets/embed_music.py
"""
import base64, os, re

here = os.path.dirname(os.path.abspath(__file__))
html_path = os.path.join(here, '..', 'index.html')
TRACKS = [('BGM_MP3', 'pigment_leap.mp3'), ('TITLE_MP3', 'my_river_raft.mp3')]
parts = []
for var, name in TRACKS:
    data = open(os.path.join(here, name), 'rb').read()
    parts.append(f'window.{var}="' + base64.b64encode(data).decode('ascii') + '";')
    print('embedded', name, len(data), 'bytes')
block = '<script id="bgmData">/*BGM_MP3*/' + ''.join(parts) + 'window.dispatchEvent(new Event("musicdata"));/*/BGM_MP3*/</script>'
html = open(html_path, encoding='utf-8').read()
pattern = re.compile(r'\n?<script id="bgmData">/\*BGM_MP3\*/.*?/\*/BGM_MP3\*/</script>', re.S)
html = pattern.sub('', html).rstrip('\n') + '\n' + block + '\n'
open(html_path, 'w', encoding='utf-8', newline='\n').write(html)

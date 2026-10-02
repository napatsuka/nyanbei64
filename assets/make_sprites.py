"""Cut the 2D player sprites out of the omnidirectional modeling sheet and remove the background.

Run:  python assets/make_sprites.py <sheet.jpg>
Writes assets/nyanbee_<view>.png (transparent, trimmed, feet on the bottom edge, 512 px tall) for
front, back, side_r (faces screen-right), side_l (faces screen-left), fq_r / fq_l (3/4 front, facing
screen-right / -left) and bq_l (3/4 rear, walking away to screen-left; the game mirrors it for the right).

Background removal: flood-fill the bright, colorless studio backdrop and clear acrylic base inward from the
crop border (the lit ear tips and pale ear fur are darker or pinker than the backdrop, so they survive),
drop everything below the feet (the base rim), then keep only the largest connected shape.
"""
import sys, os
from collections import deque
from PIL import Image, ImageFilter

here = os.path.dirname(os.path.abspath(__file__))
sheet = Image.open(sys.argv[1]).convert('RGB')

# crop boxes on the 1116x2000 sheet; the color swatch bar occupies the top 18 px
BOXES = {
    'front': (105, 20, 525, 505), 'back': (600, 20, 1040, 505),
    'side_r': (30, 600, 285, 990), 'side_l': (295, 600, 560, 990),
    'fq_r': (120, 1035, 470, 1420), 'fq_l': (15, 1480, 295, 1900), 'bq_l': (300, 1480, 580, 1900),
}

def lum(p): return 0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2]
def is_bg(p, low=False):
    # near the feet the clear acrylic base reads as mid gray, so be more aggressive there
    if low:
        return lum(p) > 85 and max(p) - min(p) < 30
    return lum(p) > 168 and max(p) - min(p) < 26

def components(mask, w, h):
    seen = [[False] * h for _ in range(w)]
    best = []
    for sx in range(w):
        for sy in range(h):
            if not mask[sx][sy] or seen[sx][sy]:
                continue
            comp, q = [], deque([(sx, sy)]); seen[sx][sy] = True
            while q:
                x, y = q.popleft(); comp.append((x, y))
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if 0 <= nx < w and 0 <= ny < h and mask[nx][ny] and not seen[nx][ny]:
                        seen[nx][ny] = True; q.append((nx, ny))
            if len(comp) > len(best):
                best = comp
    return best

def cut(box):
    im = sheet.crop(box)
    w, h = im.size
    px = im.load()
    bg = [[False] * h for _ in range(w)]
    q = deque([(x, 0) for x in range(w)] + [(x, h - 1) for x in range(w)] + [(0, y) for y in range(h)] + [(w - 1, y) for y in range(h)])
    while q:
        x, y = q.popleft()
        if x < 0 or y < 0 or x >= w or y >= h or bg[x][y] or not is_bg(px[x, y], y > h * 0.72):
            continue
        bg[x][y] = True
        q.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))
    # backdrop pockets enclosed by the tail and body: large bright regions not reached from the border
    # (the studio backdrop is faintly blue; the pale ear fur is faintly pink, so it is never taken)
    holes = [[(not bg[x][y]) and is_bg(px[x, y]) and px[x, y][2] >= px[x, y][0] for y in range(h)] for x in range(w)]
    while True:
        comp = components(holes, w, h)
        if len(comp) < 250:
            break
        for x, y in comp:
            bg[x][y] = True; holes[x][y] = False
    # feet line: lowest row that still has a run of the cat's dark vinyl
    feet = max(y for y in range(h) if sum(1 for x in range(w) if lum(px[x, y]) < 60) >= 4)
    mask = [[(not bg[x][y]) and y <= feet + 2 for y in range(h)] for x in range(w)]
    keep = components(mask, w, h)
    alpha = Image.new('L', (w, h), 0)
    ap = alpha.load()
    for x, y in keep:
        ap[x, y] = 255
    alpha = alpha.filter(ImageFilter.MedianFilter(3)).filter(ImageFilter.GaussianBlur(0.6))
    out = im.convert('RGBA'); out.putalpha(alpha)
    return out.crop(alpha.point(lambda a: 255 if a > 40 else 0).getbbox())

for name, box in BOXES.items():
    img = cut(box)
    scale = 512 / img.size[1]
    img = img.resize((round(img.size[0] * scale), 512), Image.LANCZOS)
    path = os.path.join(here, f'nyanbee_{name}.png')
    img.save(path, optimize=True)
    print(name, img.size, os.path.getsize(path), 'bytes')

"""Build Nyanbee's 3D shape from the 2D sheet cutouts (a visual hull) for the "photo 3D" character.

Run after make_sprites.py:  python assets/make_hull.py
Writes assets/nyanbee_hull.npz (voxel occupancy + tail centerline) and assets/nyanbee_calib.json
(how each sprite maps onto the model, used by the game's projection shader).

Units: feet at y=0, ear tips at y=3.0, cat faces +z, its right side is -x (game frame).
Front view looks along -z (image right = +x), back along +z (image right = -x),
side_r is seen from -x (image right = +z), side_l from +x (image right = -z).
Body = front silhouette x side silhouette with the tail cut out of both; the tail is rebuilt as a tube
whose centerline takes x from the front view and z from the side view, row by row.
"""
import os, json
import numpy as np
from PIL import Image, ImageFilter

here = os.path.dirname(os.path.abspath(__file__))
H_UNITS = 3.0

def load(name):
    im = Image.open(os.path.join(here, f'nyanbee_{name}.png'))
    a = np.asarray(im.getchannel('A')) > 128
    return a, im.size  # mask[v, u], (W, H)

def morph(mask, k, op):
    im = Image.fromarray((mask * 255).astype(np.uint8))
    im = im.filter(ImageFilter.MinFilter(k) if op == 'erode' else ImageFilter.MaxFilter(k))
    return np.asarray(im) > 128

def opening(mask, k): return morph(morph(mask, k, 'erode'), k, 'dilate')

def feet_center(mask):
    h = mask.shape[0]
    rows = mask[int(h * 0.965):int(h * 0.995)]
    us = np.nonzero(rows.any(axis=0))[0]
    return (us.min() + us.max()) / 2

calib, masks = {}, {}
for name in ('front', 'back', 'side_r', 'side_l'):
    m, (w, h) = load(name)
    s = h / H_UNITS
    calib[name] = {'cu': float(feet_center(m)), 'w': w, 'h': h, 's': s}
    masks[name] = m

def split_tail(mask, cu, s, tail_side, symmetric):
    """Return (body_mask, tail_mask). The tail rises beside/behind the body on the image-left side,
    separated from it by a gap: in each row of the tail's height range, a leftmost run that ends before
    the body and lies well left of the feet center is tail."""
    h, w = mask.shape
    clean = opening(mask, 5)                     # drop whiskers and specks
    tail = np.zeros_like(clean)
    for v in range(h):
        y = (h - v) / s
        if not (0.2 < y < 1.75):
            continue
        row = clean[v]
        runs, u = [], 0
        while u < w:
            if row[u]:
                a = u
                while u < w and row[u]: u += 1
                runs.append((a, u - 1))
            u += 1
        if len(runs) >= 2 and runs[0][1] < cu - 0.3 * s:
            tail[v, runs[0][0]:runs[0][1] + 1] = True
    # lower down the tail curls into the body, so there is no gap; cut it at an estimated body edge instead
    sep = [v for v in range(h) if tail[v].any()]
    if sep:
        v_low = sep[0]                         # lowest row of the continuous separate stretch (ignore stray specks)
        for v in sep[1:]:
            if v - v_low > 3:
                break
            v_low = v
        tail[v_low + 1:] = False
        def left_edge(v):
            us = np.nonzero(clean[v] & ~tail[v])[0]; return us.min() if len(us) else cu
        def right_half(v):
            us = np.nonzero(clean[v])[0]; return us.max() - cu if len(us) else 0
        v_leg = int(h - 0.22 * s)
        e_top, e_leg = left_edge(v_low), left_edge(v_leg)
        for v in range(v_low + 1, v_leg):
            if symmetric:
                edge = cu - right_half(v) - 0.03 * s       # the body is left-right symmetric in this view
            else:
                t = (v - v_low) / max(1, v_leg - v_low)
                edge = e_top * (1 - t) + e_leg * t - 0.03 * s
            us = np.nonzero(clean[v])[0]
            cut = us[us < edge]
            tail[v, cut] = True
    return clean & ~tail, tail

f_body, f_tail = split_tail(masks['front'], calib['front']['cu'], calib['front']['s'], -1, True)   # tail at the cat's right = image left
s_body, s_tail = split_tail(masks['side_r'], calib['side_r']['cu'], calib['side_r']['s'], -1, False)  # tail behind = image left

# ---------- voxel hull of the body
R = 0.02
xs = np.arange(-1.3, 1.3, R); ys = np.arange(0, 3.06, R); zs = np.arange(-1.25, 1.25, R)
X, Y, Z = np.meshgrid(xs, ys, zs, indexing='ij')
def sample(mask, c, coord):
    h, w = mask.shape
    u = np.round(c['cu'] + coord * c['s']).astype(int)
    v = np.round(h - Y * c['s']).astype(int)
    ok = (u >= 0) & (u < w) & (v >= 0) & (v < h)
    out = np.zeros(X.shape, bool)
    out[ok] = mask[v[ok], u[ok]]
    return out
# Each height slice is filled with ellipses inscribed in (front-view width) x (side-view depth): cross-sections of a
# round figure are close to ellipses, so this stays round where a plain two-view intersection would be boxy.
def runs_at(mask, c, y, sign):
    h, w = mask.shape
    v = int(round(h - y * c['s']))
    if v < 0 or v >= h:
        return []
    row, out, u = mask[v], [], 0
    while u < w:
        if row[u]:
            a = u
            while u < w and row[u]: u += 1
            lo, hi = (a - 0.5 - c['cu']) / c['s'] * sign, (u - 0.5 - c['cu']) / c['s'] * sign
            out.append((min(lo, hi), max(lo, hi)))
        u += 1
    return out
EXP = 2.3   # a touch fuller than an ellipse, like the figure's soft vinyl shapes
XZx, XZz = np.meshgrid(xs, zs, indexing='ij')
occ = np.zeros(X.shape, bool)
for j, y in enumerate(ys):
    fr = runs_at(f_body, calib['front'], y, 1); sr = runs_at(s_body, calib['side_r'], y, 1)
    for x0, x1 in fr:
        for z0, z1 in sr:
            cx, hx, cz, hz = (x0 + x1) / 2, (x1 - x0) / 2, (z0 + z1) / 2, (z1 - z0) / 2
            if hx < R or hz < R:
                continue
            occ[:, j, :] |= (np.abs((XZx - cx) / hx) ** EXP + np.abs((XZz - cz) / hz) ** EXP) <= 1
def box_blur(a, k, axis):
    pad = [(0, 0)] * a.ndim; pad[axis] = (k, k)
    c = np.cumsum(np.pad(a, pad, mode='edge'), axis=axis)
    hi = np.take(c, range(2 * k, c.shape[axis]), axis=axis); lo = np.take(c, range(0, c.shape[axis] - 2 * k), axis=axis)
    return (hi - lo) / (2 * k)
f = occ.astype(np.float32)
for ax, k in ((0, 2), (1, 4), (2, 2)):   # soften row-to-row steps (mostly vertical) before meshing
    f = box_blur(f, k, ax)
occ = f > 0.5
print('voxels', occ.sum(), 'grid', occ.shape)

# ---------- tail centerline: per image row, x-center from the front tail, z-center from the side tail
def row_centers(tail, c):
    h = tail.shape[0]
    out = {}
    for v in range(h):
        us = np.nonzero(tail[v])[0]
        if len(us) >= 3:
            out[v] = ((us.min() + us.max()) / 2 - c['cu']) / c['s'], (us.max() - us.min()) / 2 / c['s']
    return out
fc = row_centers(f_tail, calib['front']); sc = row_centers(s_tail, calib['side_r'])
pts = []
for v in sorted(set(fc) & set(sc)):
    (x, rx), (z, rz) = fc[v], sc[v]
    y = (calib['front']['h'] - v) / calib['front']['s']
    r = min(0.17, max(0.12 if y < 0.75 else 0.07, rx))   # keep the curl as thick as the tail
    pts.append((x, y, z, r))
pts = pts[::3]
if pts:  # run the root of the tail well into the lower back so it is firmly attached
    x0, y0, z0, r0 = pts[-1]
    for k in range(1, 7):
        t = k / 6
        pts.append((x0 * (1 - t) + (-0.05) * t, y0 * (1 - t) + (y0 + 0.12) * t, z0 * (1 - t) + (-0.18) * t, 0.14))
pts = np.array(pts) if pts else np.zeros((0, 4))
if len(pts) > 6:  # the per-row readings jitter; a moving average gives an even, smooth tube
    k = 5
    padded = np.concatenate([np.repeat(pts[:1], k, 0), pts, np.repeat(pts[-1:], k, 0)])
    kernel = np.ones(2 * k + 1) / (2 * k + 1)
    pts = np.stack([np.convolve(padded[:, i], kernel, mode='valid') for i in range(4)], axis=1)
if len(pts) > 1:  # resample so neighbouring spheres overlap well (a smooth tube rather than a string of beads)
    dense = []
    for p0, p1 in zip(pts[:-1], pts[1:]):
        n = max(1, int(np.linalg.norm(p1[:3] - p0[:3]) / 0.03))
        dense += [p0 + (p1 - p0) * k / n for k in range(n)]
    pts = np.array(dense + [pts[-1]])
print('tail points', len(pts))

np.savez_compressed(os.path.join(here, 'nyanbee_hull.npz'), occ=occ, origin=np.array([xs[0], ys[0], zs[0]]), res=R, tail=pts)
# ---------- joint positions for the game's skeleton, read from the front silhouette
cf = calib['front']
def half_width(y):
    rr = runs_at(f_body, cf, y, 1)
    return max((max(abs(x0), abs(x1)) for x0, x1 in rr), default=0.0)
neck_y = min(np.arange(1.3, 1.9, 0.01), key=lambda y: half_width(y))       # where the outline pinches between head and body
shoulder_y = neck_y - 0.16
feet = runs_at(f_body, cf, 0.05, 1)
leg_x = float(np.mean([abs((x0 + x1) / 2) for x0, x1 in feet])) if feet else 0.24
calib['rig'] = {'neck_y': float(neck_y), 'shoulder': [float(half_width(shoulder_y) * 0.78), float(shoulder_y)],
                'hip': [leg_x, 0.42], 'tail_root': [float(v) for v in pts[-1][:3]] if len(pts) else [-0.05, 0.5, -0.18]}
print('rig', calib['rig'])
json.dump(calib, open(os.path.join(here, 'nyanbee_calib.json'), 'w'), indent=1)
Image.fromarray(np.hstack([(f_body * 255).astype(np.uint8), (f_tail * 160).astype(np.uint8)])).save(os.path.join(here, '..', 'blender', '_debug_front_split.png'))
Image.fromarray(np.hstack([(s_body * 255).astype(np.uint8), (s_tail * 160).astype(np.uint8)])).save(os.path.join(here, '..', 'blender', '_debug_side_split.png'))

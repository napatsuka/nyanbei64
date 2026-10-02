"""Build the Nyanbee (にゃん兵衛) figure in Blender and export it for the game.

Run:
  blender --background --python blender/build_nyanbee.py -- <out_dir> [preview_dir]

Writes <out_dir>/nyanbee.blend and <out_dir>/nyanbee.glb, plus preview PNGs in preview_dir.

Geometry is authored in the game's coordinate frame (Y up, cat faces +Z, feet at y=0),
then rotated into Blender's Z-up frame; the glTF exporter rotates it back.
Each animated part is its own object with its origin at the joint the game rotates around:
Body, Head, Arm_L, Arm_R, Foot_L, Foot_R, Tail.  (The cat's right side is -X.)
"""
import bpy, bmesh, math, sys, os
from mathutils import Vector, Matrix, Euler

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
OUT = os.path.abspath(argv[0] if argv else os.path.dirname(__file__))
PREV = os.path.abspath(argv[1]) if len(argv) > 1 else OUT
os.makedirs(OUT, exist_ok=True); os.makedirs(PREV, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
TO_ZUP = Matrix.Rotation(math.pi / 2, 4, 'X')  # game (Y up, +Z front) -> Blender (Z up, -Y front)

# ---------- materials (colors match the game's palette; game uses linear output, so values are copied as-is)
MATS = [('Fur', 0x1f1f24, 0.7), ('Pink', 0xc98a92, 0.7), ('Eye', 0xf2c200, 0.2), ('Black', 0x08080a, 0.3),
        ('WhiteFur', 0xead6d6, 0.9), ('Tan', 0xc99a6e, 0.7), ('White', 0xffffff, 0.4), ('Whisker', 0x55555c, 0.6)]
FUR, PINK, EYE, BLACK, WFUR, TAN, WHITE, WHISK = range(8)
materials = []
for name, hx, rough in MATS:
    m = bpy.data.materials.new(name)
    rgba = (((hx >> 16) & 255) / 255, ((hx >> 8) & 255) / 255, (hx & 255) / 255, 1.0)
    m.diffuse_color = rgba
    try:
        m.use_nodes = True
    except Exception:
        pass
    bsdf = m.node_tree.nodes.get('Principled BSDF') if m.node_tree else None
    if bsdf:
        bsdf.inputs['Base Color'].default_value = rgba
        bsdf.inputs['Roughness'].default_value = rough
    materials.append(m)

# ---------- helpers (three.js conventions: Euler order XYZ == Blender 'ZYX' matrix order)
def M(pos=(0, 0, 0), rot=(0, 0, 0), scl=(1, 1, 1)):
    return Matrix.Translation(Vector(pos)) @ Euler(rot, 'ZYX').to_matrix().to_4x4() @ Matrix.Diagonal((*scl, 1))

Y_FROM_Z = Matrix.Rotation(-math.pi / 2, 4, 'X')  # bmesh cones run along Z; three's run along Y

def _mi(verts, mi):
    faces = set()
    for v in verts:
        faces.update(v.link_faces)
    for f in faces:
        f.material_index = mi

def sphere(bm, m, mi=FUR, seg=20, rings=14):
    _mi(bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=rings, radius=1.0, matrix=m)['verts'], mi)

def ell(bm, pos, radii, rot=(0, 0, 0), parent=Matrix(), mi=FUR, seg=20, rings=14):
    sphere(bm, parent @ M(pos, rot, radii), mi, seg, rings)

def cone(bm, pos, r, h, rot=(0, 0, 0), seg=8, parent=Matrix(), mi=FUR, rz=None, r2=0.0):
    """three.js ConeGeometry(r, h, seg) centered on its middle; rz squashes depth for flat shapes."""
    s = (r, r if rz is None else rz, h)
    m = parent @ M(pos, rot) @ Y_FROM_Z @ Matrix.Diagonal((*s, 1))
    _mi(bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=True, segments=seg, radius1=1.0, radius2=r2, depth=1.0, matrix=m)['verts'], mi)

def rod(bm, a, b, r, parent=Matrix(), mi=BLACK, seg=6):
    a, b = Vector(a), Vector(b)
    d = b - a
    rot = Vector((0, 0, 1)).rotation_difference(d.normalized()).to_matrix().to_4x4()
    m = parent @ Matrix.Translation((a + b) / 2) @ rot @ Matrix.Diagonal((r, r, d.length, 1))
    _mi(bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=1.0, radius2=1.0, depth=1.0, matrix=m)['verts'], mi)

def catmull(pts, t):
    n = len(pts) - 1
    x = t * n
    i = min(int(x), n - 1)
    u = x - i
    p0, p1, p2, p3 = pts[max(i - 1, 0)], pts[i], pts[i + 1], pts[min(i + 2, n)]
    return 0.5 * ((2 * p1) + (-p0 + p2) * u + (2 * p0 - 5 * p1 + 4 * p2 - p3) * u * u + (-p0 + 3 * p1 - 3 * p2 + p3) * u ** 3)

fur_tex = bpy.data.textures.new('FurStucci', 'STUCCI')
fur_tex.noise_scale = 0.02
fur_tex.turbulence = 4.0
fluff_tex = bpy.data.textures.new('FurClouds', 'CLOUDS')
fluff_tex.noise_scale = 0.06

def sculpt(name, bm, voxel, target_faces, fur=0.008, tex=None, smooth_iter=8):
    """Fuse the fur volumes with a voxel remesh, relax it, carve fur noise, then decimate."""
    me = bpy.data.meshes.new(name + '_vol'); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name + '_vol', me); scene.collection.objects.link(ob)
    r = ob.modifiers.new('Remesh', 'REMESH'); r.mode = 'VOXEL'; r.voxel_size = voxel
    s = ob.modifiers.new('Smooth', 'SMOOTH'); s.factor = 0.6; s.iterations = smooth_iter
    d = ob.modifiers.new('Fur', 'DISPLACE'); d.texture = tex or fur_tex; d.strength = fur; d.mid_level = 0.5
    dg = bpy.context.evaluated_depsgraph_get()
    tmp = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    ratio = min(1.0, target_faces / max(1, len(tmp.polygons)))
    ob.modifiers.clear(); ob.data = tmp
    dec = ob.modifiers.new('Decimate', 'DECIMATE'); dec.ratio = ratio
    dg = bpy.context.evaluated_depsgraph_get()
    final = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    bpy.data.objects.remove(ob); bpy.data.meshes.remove(me)
    out = bmesh.new(); out.from_mesh(final); bpy.data.meshes.remove(final)
    for f in out.faces:
        f.material_index = FUR
    return out

def finish(name, bm, joint, scale=1.0):
    """Place the part: mesh is in joint-local game coords; convert to Blender Z-up."""
    uv = bm.loops.layers.uv.new('UVMap')
    for f in bm.faces:
        us = [math.atan2(l.vert.co.x, l.vert.co.z) / (2 * math.pi) * 3 for l in f.loops]
        if max(us) - min(us) > 1.5:
            us = [u + 3 if u < 0 else u for u in us]
        for l, u in zip(f.loops, us):
            l[uv].uv = (u, l.vert.co.y * 1.5)
    bmesh.ops.transform(bm, matrix=TO_ZUP @ Matrix.Scale(scale, 4), verts=bm.verts)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    for m in materials:
        me.materials.append(m)
    me.polygons.foreach_set('use_smooth', [True] * len(me.polygons))
    ob = bpy.data.objects.new(name, me); scene.collection.objects.link(ob)
    ob.location = TO_ZUP @ Vector(joint)
    return ob

parts = []
# Measured from the omnidirectional modeling sheet (front view, head width incl. cheek tufts = 1.9 units):
#   head height 1.23, body (chin to feet) 1.62 -> head center at y 2.24; body ~0.6x head width, slim pear;
#   eyes: centers +-0.385, 0.16 below head center, sharp almonds with the outer corner raised, slit pupils;
#   two tan brow marks above the inner eye corners; long slim arms with paws at hip level;
#   smooth thick tail rising on the cat's right to shoulder height with a hooked tip. Smooth matte vinyl, no fur grooves.

# ---------- Body (origin at the feet)
bm = bmesh.new()
prof = [Vector(p) for p in [(0.14, 0.33), (0.30, 0.49), (0.50, 0.56), (0.70, 0.56), (0.90, 0.53), (1.10, 0.48),
                            (1.30, 0.42), (1.50, 0.36), (1.72, 0.30)]]
for i in range(56):
    q = catmull(prof, i / 55)
    y, rx = q.x, q.y
    belly = 0.06 * math.exp(-((y - 0.7) / 0.35) ** 2)
    ell(bm, (0, y, belly), (rx, 0.07, rx * 0.85 + belly * 0.5), seg=32, rings=10)
parts.append(finish('Body', sculpt('Body', bm, 0.014, 2400, fur=0.0015, smooth_iter=16), (0, 0, 0)))

# ---------- Head (origin at head center)
HEAD_J = (0, 2.36, 0)
EYE_X, EYE_Y = 0.385, -0.16
EYE_Z = 0.7 * math.sqrt(1 - (EYE_X / 0.82) ** 2 - (EYE_Y / 0.6) ** 2) + 0.035
def ear_m(s): return M((s * 0.5, 0.42, -0.06), (-0.04, -s * 0.15, -s * 0.3))
def eye_m(s): return M((s * EYE_X, EYE_Y, EYE_Z), (0.05, s * 0.5, s * 0.24))
vol = bmesh.new()
ell(vol, (0, 0.06, 0), (0.82, 0.66, 0.7), seg=48, rings=32)                # round dome
for s in (-1, 1):
    ell(vol, (s * 0.44, -0.2, 0.12), (0.47, 0.38, 0.5))                   # full lower cheeks
    for k in range(3):                                                     # a few soft fur tufts on the lower cheeks
        ang = math.pi / 2 + 0.25 + k * 0.32
        cone(vol, (s * (0.82 - 0.06 * k), -0.2 - 0.12 * k, 0.12 - 0.04 * k), 0.15, 0.34, rot=(0, -s * 0.2, -s * ang), seg=6, rz=0.1)
    cone(vol, (0, 0.38, 0), 0.38, 0.82, rot=(0, math.pi / 4, 0), seg=4, parent=ear_m(s), rz=0.1)  # big pointed ears
ell(vol, (0, -0.4, 0.5), (0.2, 0.11, 0.14))                               # small muzzle
bm = sculpt('Head', vol, 0.010, 5000, fur=0.0015, smooth_iter=6)
for s in (-1, 1):
    cone(bm, (0, 0.33, 0.085), 0.25, 0.6, rot=(0, math.pi / 4, 0), seg=4, parent=ear_m(s), rz=0.03, mi=PINK)
    for k in range(4):
        cone(bm, ((k - 1.5) * 0.06, 0.13 + abs(k - 1.5) * 0.02, 0.1), 0.035, 0.18 + (k % 2) * 0.04,
             rot=(0.25, 0, (k - 1.5) * 0.3), seg=5, parent=ear_m(s), mi=WFUR)
    e = eye_m(s)
    ell(bm, (0, 0, 0), (0.275, 0.175, 0.07), parent=e, mi=BLACK, seg=36, rings=20)          # outline
    ell(bm, (0, -0.008, 0.014), (0.255, 0.155, 0.07), parent=e, mi=EYE, seg=36, rings=20)  # iris
    ell(bm, (-s * 0.015, -0.012, 0.07), (0.032, 0.125, 0.022), parent=e, mi=BLACK)          # slit pupil
    ell(bm, (-s * 0.08, 0.055, 0.082), (0.025, 0.025, 0.012), parent=e, mi=WHITE, seg=10, rings=8)
    ell(bm, (0, 0.175, 0.012), (0.3, 0.085, 0.0745), parent=e @ M(rot=(0, 0, -s * 0.16)), mi=FUR, seg=40, rings=24)  # flush lid: flat, sharp top edge
    bx, by = 0.21, 0.225
    bz = 0.7 * math.sqrt(1 - (bx / 0.82) ** 2 - ((by - 0.02) / 0.6) ** 2) + 0.004
    ell(bm, (s * bx, by, bz), (0.063, 0.035, 0.02), rot=(0, s * 0.28, s * 0.4), mi=TAN, seg=16, rings=10)  # brow marks
    for k in range(3):                                                                       # thin dark whiskers
        rod(bm, (s * 0.18, -0.42 + k * 0.035, 0.58), (s * 1.02, -0.4 + k * 0.1, 0.36), 0.004, mi=WHISK)
cone(bm, (0, -0.37, 0.64), 0.05, 0.06, rot=(math.pi / 2, 0, math.pi), seg=3, mi=PINK)         # nose
rod(bm, (0, -0.4, 0.635), (0, -0.44, 0.632), 0.006)                                             # mouth
for s in (-1, 1):
    rod(bm, (0, -0.44, 0.632), (s * 0.055, -0.47, 0.62), 0.006)
parts.append(finish('Head', bm, HEAD_J, scale=1.15))

# ---------- Arms (origin at shoulder; long and slim, paws at hip level) and feet (pink pads underneath)
for s, side in ((-1, 'R'), (1, 'L')):
    bm = bmesh.new()
    ell(bm, (0, -0.38, 0), (0.14, 0.44, 0.14))
    ell(bm, (0, -0.82, 0.04), (0.15, 0.14, 0.16))
    parts.append(finish('Arm_' + side, sculpt('Arm_' + side, bm, 0.01, 700, fur=0.001, smooth_iter=16), (s * 0.44, 1.42, 0.04)))
    bm = bmesh.new()
    ell(bm, (0, 0.2, -0.01), (0.17, 0.2, 0.17))
    ell(bm, (0, 0.08, 0.06), (0.17, 0.09, 0.22))
    for k in (-1, 0, 1):
        ell(bm, (k * 0.075, 0.06, 0.25), (0.055, 0.05, 0.055), seg=14, rings=10)
    bm = sculpt('Foot_' + side, bm, 0.008, 700, fur=0.001, smooth_iter=6)
    ell(bm, (0, 0.006, 0.02), (0.09, 0.012, 0.08), mi=PINK)
    for k in (-1, 0, 1):
        ell(bm, (k * 0.075, 0.008, 0.22), (0.033, 0.01, 0.033), mi=PINK, seg=12, rings=8)
    parts.append(finish('Foot_' + side, bm, (s * 0.24, 0, 0.04)))

# ---------- Tail (origin at the lower back): sweeps to the cat's right, rises to shoulder height, tip hooks outward
bm = bmesh.new()
pts = [Vector(p) for p in [(0, 0, 0), (-0.3, -0.12, -0.12), (-0.62, -0.1, -0.12), (-0.85, 0.12, -0.08),
                           (-0.92, 0.5, -0.04), (-0.88, 0.85, 0.0), (-0.98, 1.05, 0.04)]]
N = 60
for i in range(N + 1):
    t = i / N
    r = 0.14 + 0.03 * math.sin(math.pi * t)
    ell(bm, tuple(catmull(pts, t)), (r, r, r), seg=16, rings=12)
parts.append(finish('Tail', sculpt('Tail', bm, 0.01, 1600, fur=0.001, smooth_iter=10), (-0.12, 0.48, -0.4)))

# ---------- save + export
for o in scene.objects:
    o.select_set(o in parts)
bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, 'nyanbee.glb'), export_format='GLB', use_selection=True,
                          export_yup=True, export_apply=True, export_texcoords=True, export_normals=True,
                          export_materials='EXPORT', export_animations=False)

# acrylic display base (in the .blend only)
bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=1.35, depth=0.07, location=(0, 0, -0.035))
base = bpy.context.active_object; base.name = 'AcrylicBase'
glass = bpy.data.materials.new('Acrylic'); glass.diffuse_color = (0.85, 0.92, 1.0, 0.3)
base.data.materials.append(glass)

# ---------- previews (Workbench)
scene.render.engine = 'BLENDER_WORKBENCH'
sh = scene.display.shading
sh.light = 'STUDIO'; sh.color_type = 'MATERIAL'; sh.show_cavity = True; sh.cavity_type = 'BOTH'
sh.show_shadows = True
scene.render.resolution_x = 640; scene.render.resolution_y = 760
scene.render.film_transparent = False
world = bpy.data.worlds.new('W'); scene.world = world; world.color = (0.82, 0.83, 0.85)
sh.background_type = 'WORLD'
target = bpy.data.objects.new('Target', None); scene.collection.objects.link(target); target.location = (0, 0, 1.6)
cam_data = bpy.data.cameras.new('Cam'); cam_data.lens = 70
cam = bpy.data.objects.new('Cam', cam_data); scene.collection.objects.link(cam); scene.camera = cam
tc = cam.constraints.new('TRACK_TO'); tc.target = target; tc.track_axis = 'TRACK_NEGATIVE_Z'; tc.up_axis = 'UP_Y'
for label, ang in (('front', 0), ('three_quarter', 35), ('side', 90), ('back', 160)):
    a = math.radians(ang)
    cam.location = (10.5 * math.sin(a), -10.5 * math.cos(a), 2.9)
    scene.render.filepath = os.path.join(PREV, f'nyanbee_{label}.png')
    bpy.ops.render.render(write_still=True)

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, 'nyanbee.blend'))
tris = sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in parts)
print('NYANBEE_DONE', {o.name: len(o.data.polygons) for o in parts}, 'tris', tris)

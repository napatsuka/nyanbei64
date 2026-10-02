"""Turn the visual hull (assets/nyanbee_hull.npz from make_hull.py) into a smooth game mesh.

Run:  blender --background --python blender/build_hull.py -- <project_dir> [preview_dir]
Writes blender/nyanbee_photo.glb (one object, "Hull"; the game paints it by projecting the sheet images)
and blender/nyanbee_photo.blend.
"""
import bpy, bmesh, math, sys, os
import numpy as np
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
ROOT = os.path.abspath(argv[0] if argv else os.path.join(os.path.dirname(__file__), '..'))
PREV = os.path.abspath(argv[1]) if len(argv) > 1 else os.path.join(ROOT, 'blender')
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
TO_ZUP = Matrix.Rotation(math.pi / 2, 4, 'X')

d = np.load(os.path.join(ROOT, 'assets', 'nyanbee_hull.npz'))
occ, origin, R, tail = d['occ'], d['origin'], float(d['res']), d['tail']

# ---------- boundary faces of the voxel grid (a closed blocky shell)
pad = np.pad(occ, 1)
core = pad[1:-1, 1:-1, 1:-1]
corner = {  # face corners (unit cube offsets) for each outward direction
    (1, 0, 0): [(1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1)], (-1, 0, 0): [(0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0)],
    (0, 1, 0): [(0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0)], (0, -1, 0): [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)],
    (0, 0, 1): [(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)], (0, 0, -1): [(0, 0, 0), (0, 1, 0), (1, 1, 0), (1, 0, 0)],
}
V_list, F_list, nv = [], [], 0
for (dx, dy, dz), cs in corner.items():
    nb = pad[1 + dx:pad.shape[0] - 1 + dx, 1 + dy:pad.shape[1] - 1 + dy, 1 + dz:pad.shape[2] - 1 + dz]
    idx = np.argwhere(core & ~nb)
    n = len(idx)
    if not n:
        continue
    V_list.append(np.concatenate([origin + (idx + np.array(c) - 0.5) * R for c in cs]))
    F_list.append(np.stack([nv + j * n + np.arange(n) for j in range(4)], axis=1))
    nv += 4 * n
V = np.concatenate(V_list); F = np.concatenate(F_list)
tmpme = bpy.data.meshes.new('vox'); tmpme.from_pydata(V.tolist(), [], F.tolist())
bm = bmesh.new(); bm.from_mesh(tmpme); bpy.data.meshes.remove(tmpme)
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=R * 0.01)
bmesh.ops.transform(bm, matrix=TO_ZUP, verts=bm.verts)

def finish(name, bm, voxel, smooth, faces):
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); scene.collection.objects.link(ob)
    r = ob.modifiers.new('Remesh', 'REMESH'); r.mode = 'VOXEL'; r.voxel_size = voxel
    s = ob.modifiers.new('Smooth', 'SMOOTH'); s.factor = 0.6; s.iterations = smooth
    dg = bpy.context.evaluated_depsgraph_get()
    tmp = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    ob.modifiers.clear(); old = ob.data; ob.data = tmp; bpy.data.meshes.remove(old)
    dec = ob.modifiers.new('Decimate', 'DECIMATE'); dec.ratio = min(1.0, faces / max(1, len(tmp.polygons)))
    dg = bpy.context.evaluated_depsgraph_get()
    final = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    ob.modifiers.clear(); old = ob.data; ob.data = final; bpy.data.meshes.remove(old)
    final.polygons.foreach_set('use_smooth', [True] * len(final.polygons))
    mat = bpy.data.materials.new('Photo'); mat.diffuse_color = (0.12, 0.12, 0.14, 1); final.materials.append(mat)
    print('HULL_DONE', name, 'faces', len(final.polygons))
    return ob

ob = finish('Hull', bm, 0.016, 18, 9000)
# ---------- the tail is its own part (so the game can swing it): spheres along the centerline from the views
tb = bmesh.new()
for x, y, z, r in tail:
    bmesh.ops.create_uvsphere(tb, u_segments=16, v_segments=12, radius=float(r) * 1.05, matrix=Matrix.Translation((float(x), float(y), float(z))))
bmesh.ops.transform(tb, matrix=TO_ZUP, verts=tb.verts)
tail_ob = finish('Tail', tb, 0.014, 22, 2500)

for o in scene.objects: o.select_set(o in (ob, tail_ob))
bpy.ops.export_scene.gltf(filepath=os.path.join(ROOT, 'blender', 'nyanbee_photo.glb'), export_format='GLB', use_selection=True,
                          export_yup=True, export_apply=True, export_texcoords=False, export_normals=True, export_materials='EXPORT')

# ---------- shape previews
scene.render.engine = 'BLENDER_WORKBENCH'
sh = scene.display.shading; sh.light = 'STUDIO'; sh.show_cavity = True; sh.show_shadows = True
scene.render.resolution_x = 520; scene.render.resolution_y = 620
world = bpy.data.worlds.new('W'); scene.world = world; world.color = (0.82, 0.83, 0.85); sh.background_type = 'WORLD'
tgt = bpy.data.objects.new('T', None); scene.collection.objects.link(tgt); tgt.location = (0, 0, 1.5)
cam = bpy.data.objects.new('Cam', bpy.data.cameras.new('Cam')); scene.collection.objects.link(cam); scene.camera = cam
cam.data.lens = 70
tc = cam.constraints.new('TRACK_TO'); tc.target = tgt; tc.track_axis = 'TRACK_NEGATIVE_Z'; tc.up_axis = 'UP_Y'
for label, ang in (('front', 0), ('q', 40), ('side', 90), ('back', 150)):
    a = math.radians(ang); cam.location = (10 * math.sin(a), -10 * math.cos(a), 2.4)
    scene.render.filepath = os.path.join(PREV, f'hull_{label}.png'); bpy.ops.render.render(write_still=True)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(ROOT, 'blender', 'nyanbee_photo.blend'))

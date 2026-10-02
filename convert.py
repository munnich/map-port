"""Convert an ACR (Revelations) MP map forge into an ACB (Brotherhood) one.

    convert.py <acr_map.forge> <acb_multi_dir> <out.forge> [--slot AC2MP_Alhambra]

Pipeline (see NOTES.md for how each rule was established):
  1. Every sub-object is decoded with the ACR schema (anvilforge.fastload),
     ACR-only object types are stripped (from arrays / pointers), and it is
     re-encoded with ACB's schema (placeholders filled from ACR), which drops
     every ACR-added field by construction. Missing ACB-only fields get
     defaults. MeshShape.MoppCodeVersionNumber = 0 makes ACB rebuild ACR's MOPPs at load. Mesh/TextureMap
     UserCategory is reset to 0 like ACB's own copies.
  2. Objects fastload can't decode (Animation, FX, MaterialTemplate, NavMesh,
     ...) are replaced by ACB's own bytes when ACB has the same object id,
     else kept as-is (reported).
  3. Data layers: ACR puts mode objects (spawns, OOB, chests) in per-mode
     ACFE_* layer data blocks; ACB activates only "gamemode_<engine name>"
     layers and keeps spawns/OOB unlayered. Objects of the standard ACR modes
     move into the always-loaded top grid cell with their layer filters
     cleared; chest-only objects move to gamemode_teamwanted (like ACB's
     MtStMichel Spawn_Chest_*); ACR-only layer associations are removed, so
     Deathmatch/CTF/Hijack/Training-only objects are never loaded.
  4. Registration (--slot): the map takes over an existing ACB DLC map slot.
     That map's ContentPackage, MpWorld(s), their images and MpMapsDLCAddons
     are copied from the ACB forge, repointed at the converted World, and the
     World is renamed to the slot's world name. ACR sound-bank DLC addons are
     dropped (their Wwise banks don't exist in ACB).
"""
from __future__ import annotations

import argparse
import io
import json
import os
import pickle
import shutil
import sys
import tempfile
from collections import Counter, defaultdict

sys.path.insert(0, os.path.expanduser("~/Coding/Python/anvilforge-py-acrport/src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from anvilforge.binio import write_string32
from anvilforge.datafile import (DATA_MAGIC, DATA_VERSIONS, Dependency, _build_toc, _extra_from_header,
                                 _read_inline_dependencies, _write_block_set,
                                 _write_inline_dependencies, derive_uid_and_ext,
                                 iter_datafile_subparts, object_id_bytes)
from anvilforge.fastload import Codec, DecodeError, Handle, Obj, Ptr, Ref, Root, walk
from anvilforge.fileset import loose_file_name
from anvilforge.create_entry import create_entry
from anvilforge.forge import repack, unpack
from anvilforge.games import Game
from anvilforge.schema import Schema

ACB = Schema.load_default(Game.BROTHERHOOD)
ACR = Schema.load_default(Game.REVELATIONS)
ACB_T = ACB.with_placeholders_filled(ACR)
ACR_ONLY_TYPES = set(ACR.types_by_hash) - set(ACB.types_by_hash)

STANDARD_MODES = {"ACFE_Wanted", "ACFE_Manhunt", "ACFE_Assassinate", "ACFE_Escort", "ACFE_Corruption"}
CHEST_MODES = {"ACFE_Chest_Capture"}
CHEST_TARGET_LAYER = "gamemode_teamwanted"
NEVER_LAYER = "Test_AI_Detection"  # an ACB DataLayer (DataPC.forge) no MP mode activates


def layer_mode(name: str) -> str:
    """'standard' / 'chest' / 'other' for an ACR layer name: ACFE_<Mode> or <Region>_<Map>_<Mode>."""
    if name.endswith(("Wanted", "Manhunt", "Assassinate", "Escort", "Corruption")):
        return "standard"
    if name.endswith("Chest_Capture"):
        return "chest"
    return "other"
# custom-serialized types whose format ACR and ACB share (checked on maps both games ship) -- safe to keep in ACR form
SHARED_OPAQUE = {"FX", "MaterialTemplate", "NavMeshManager", "PropertyControllerData"}

HERE = os.path.dirname(os.path.abspath(__file__))


def u32(b: bytes) -> int:
    return int.from_bytes(b, "little")


def idb(i: int) -> bytes:
    return (i & 0xFFFFFFFF).to_bytes(4, "little")


def name_hash(schema, name):
    return next(k for k, v in schema.names.items() if v == name)


class Report:
    def __init__(self):
        self.c = Counter()
        self.notes = defaultdict(list)

    def add(self, key, note=None, n=1):
        self.c[key] += n
        if note is not None and len(self.notes[key]) < 12:
            self.notes[key].append(note)

    def text(self):
        out = []
        for k, v in sorted(self.c.items()):
            out.append(f"{v:6d}  {k}")
            for n in self.notes.get(k, []):
                out.append(f"          - {n}")
        return "\n".join(out)


# ------------------------------------------------------------ data files --

class DataFile:
    """One loose .data entry held in memory: dependency table + sub-objects."""

    def __init__(self, fname: str, raw: bytes, game: Game):
        self.fname = fname
        f = io.BytesIO(raw)
        self.deps, self.raw_dep = _read_inline_dependencies(f, game)
        self.subs = []  # [ext, name, payload]
        for _i, ext, name, payload in iter_datafile_subparts(io.BytesIO(raw), game):
            self.subs.append([ext, name, payload])

    def build(self, game: Game) -> bytes:
        version, algorithm, block_size = DATA_VERSIONS[game]
        content = bytearray()
        toc = []
        seen = set()
        for ext, name, raw in self.subs:
            uid, _ = derive_uid_and_ext(raw, True)
            if uid in seen:
                continue
            seen.add(uid)
            nm = "" if name.lower() == "unnamed" else name
            extra = _extra_from_header(raw[:8])
            start = len(content)
            content += ext.to_bytes(4, "little")
            content += (len(raw) - 1 - extra).to_bytes(4, "little", signed=True)
            nb = io.BytesIO(); write_string32(nb, nm); content += nb.getvalue()
            content += raw
            toc.append((uid, len(content) - start))
        out = io.BytesIO()
        _write_inline_dependencies(out, self.deps, self.raw_dep, game)
        out.write(DATA_MAGIC.to_bytes(8, "little"))
        _write_block_set(out, _build_toc(toc, True), version, algorithm, block_size)
        out.write(DATA_MAGIC.to_bytes(8, "little"))
        _write_block_set(out, bytes(content), version, algorithm, block_size)
        return out.getvalue()


def load_forge(path: str, workdir: str, game: Game):
    entries = unpack(path, workdir, game)
    files = {}
    for i, e in enumerate(entries):
        fn = loose_file_name(i, e)
        full = os.path.join(workdir, fn)
        if fn.endswith(".data"):
            files[fn] = DataFile(fn, open(full, "rb").read(), game)
    return entries, files


# ------------------------------------------------------------ conversion --

def activate_objects(blk: Obj, ids):
    """Add objects to a GridCellDataBlock so they get activated. Only the first NumberOfObjectsToActivate entries of
    Objects are activated (most blocks end with a not-activated tail), so insert at the end of that prefix --
    appending to the list would leave them inactive (and activate part of the tail instead)."""
    objs = blk.fields["Objects"]
    n = u32(blk.fields["NumberOfObjectsToActivate"])
    have = {u32(x.id) for x in objs[:n]}
    add = [i for i in dict.fromkeys(ids) if i not in have]
    addset = set(add)
    rest = [x for x in objs[n:] if u32(x.id) not in addset]   # an object already in the tail moves into the prefix
    blk.fields["Objects"] = objs[:n] + [Ref(1, 0, idb(i)) for i in add] + rest
    blk.fields["NumberOfObjectsToActivate"] = idb(n + len(add))


class Converter:
    def __init__(self, args, report: Report):
        self.args = args
        self.r = report
        self.acr = Codec(ACR)
        self.acb = Codec(ACB_T)
        self.acb_idx = pickle.load(open(os.path.join(HERE, "acb_idx.pkl"), "rb"))
        self.acr_idx = pickle.load(open(os.path.join(HERE, "acr_idx.pkl"), "rb"))
        self.trees: dict[int, Root] = {}      # uid -> decoded tree (ACR)
        self.where: dict[int, list] = defaultdict(list)  # uid -> [(DataFile, sub index)], all copies
        self.fallback: set[int] = set()       # uids to take from ACB (encode failed)
        self.id_remap: dict[int, int] = {}    # object id -> ACB object id (templates)
        self.drop_uids: set[int] = set()      # sub-objects removed right before writing (indices stay valid till then)

    # -- helpers --
    def layer_name(self, i: int) -> str:
        v = self.acb_idx.get(i) or self.acr_idx.get(i)
        return v[1] if v else f"?{i:#x}"

    def acb_layer_id(self, name: str) -> int:
        return next(k for k, v in self.acb_idx.items() if v[1] == name and v[0] in ("DataLayer", "<entry>")
                    and k not in self.acr_only_layers_guard)

    # -- 1. decode --
    def decode_all(self, files):
        for df in files.values():
            for i, (ext, name, payload) in enumerate(df.subs):
                uid, _ = derive_uid_and_ext(payload, True)
                first = uid not in self.where
                self.where[uid].append((df, i))
                if not first:
                    self.r.add("duplicate copies (converted once, written to all)")
                    continue
                try:
                    self.trees[uid] = self.acr.decode(payload)
                except DecodeError:
                    self.r.add(f"opaque:{ACR.name_of(ext)}")

    def capture_world_extras(self):
        w = next(t.obj for t in self.trees.values() if ACR.name_of(t.obj.type_hash) == "World")
        self.vip_paths = list(w.fields.get("TeamVIPPaths") or [])
        self.acr_chest_points = list(w.fields.get("chestSpawnPoints") or [])
        self.r.add("world extras: TeamVIP paths captured", n=len(self.vip_paths))

    # -- 3. layers --
    def remap_layers(self):
        wdlm = next(t for t in self.trees.values() if ACR.name_of(t.obj.type_hash) == "WorldDataLayerManager")
        assoc = wdlm.obj.fields["LayersConfig"]
        by_layer = {u32(a.fields["Layer"].id): u32(a.fields["DataBlock"].id) for a in assoc}
        acr_only_layers = {l for l in by_layer if l not in self.acb_idx}
        self.acr_only_layers_guard = acr_only_layers
        names = {l: self.layer_name(l) for l in by_layer}

        def block(i):
            t = self.trees.get(i)
            return t.obj if t else None

        def refs(blk):
            return [u32(x.id) for x in blk.fields["Objects"]] if blk is not None else []

        for l, b in by_layer.items():
            if block(b) is None:  # e.g. Juderia: an association whose data block isn't in the forge
                self.r.add("layers: data block not in forge (layer has no objects here)", note=f"{names[l]} -> {b:#x}")

        std = set()
        for l, n in names.items():
            if n in STANDARD_MODES:
                std |= set(refs(block(by_layer[l])))
        chest = set()
        for l, n in names.items():
            if n in CHEST_MODES:
                chest |= set(refs(block(by_layer[l])))
        chest -= std
        dropped = set()
        for l in acr_only_layers:
            if names[l] not in STANDARD_MODES | CHEST_MODES:
                dropped |= set(refs(block(by_layer[l])))
        dropped -= std | chest
        self.r.add("layers: standard-mode objects -> top grid cell", n=len(std))
        self.r.add("layers: chest-only objects -> " + CHEST_TARGET_LAYER, n=len(chest))
        self.chest_objects = sorted(chest)
        self.r.add("layers: objects only in ACR-only modes (never loaded)", n=len(dropped),
                   note=None)
        for i in sorted(dropped)[:12]:
            self.r.add("layers: objects only in ACR-only modes (never loaded)", note=self.name_of(i), n=0)

        part = next(t.obj for t in self.trees.values() if ACR.name_of(t.obj.type_hash) == "GridPartition")
        top_id = u32(part.fields["Cells"][-1].fields["DataBlock"].id)  # quadtree root = last cell
        top = block(top_id)
        if top is None:
            raise SystemExit("top grid cell has no data block")
        self.r.add("layers: top grid cell = " + self.name_of(top_id))
        self.top_cell_id = top_id
        self._append(top, std)

        tw = next(l for l, n in names.items() if n == CHEST_TARGET_LAYER)
        self._append(block(by_layer[tw]), chest)
        self.moves = [(top_id, sorted(std)), (by_layer[tw], sorted(chest))]

        wdlm.obj.fields["LayersConfig"] = [a for a in assoc if u32(a.fields["Layer"].id) not in acr_only_layers]
        self.r.add("layers: ACR-only layer associations removed", n=len(assoc) - len(wdlm.obj.fields["LayersConfig"]))

        # entity filters. ACB's DataLayerFilter::ShouldAssociatedObjectBeLoaded skips every layer whose handle doesn't
        # resolve, and a filter left with no resolvable layer loads its object in EVERY mode. ACR filters on layers ACB
        # doesn't have: ACFE_<Mode> and, in the shared Rhodes world (Souk/Rhodes/Juderia), <Region>_<Map>_<Mode> plus
        # other maps' layers -- left alone, Knights Hospital's out-of-bounds volume (in Souk's top cell) killed every
        # Souk spawn. So by the mode the dead layers name: standard modes -> filter cleared (always loaded, like the
        # moved mode objects); Chest Capture -> gamemode_teamwanted; anything else -> a layer MP never activates.
        tw_handle = Handle(0, idb(tw))
        global_layers = self.acb_global_layers()
        never_handle = Handle(0, idb(next(i for i, n in global_layers.items() if n == NEVER_LAYER)))

        def retarget(proto, handle):
            new = Obj(proto.type_hash, proto.id, dict(proto.fields), proto.flag)
            new.fields["Layer"] = handle
            new.fields["Action"] = idb(0)
            return new

        for t in self.trees.values():
            for o in walk(t.obj):
                dlf = o.fields.get("DataLayerFilter")
                if not isinstance(dlf, Obj):
                    continue
                acts = dlf.fields["LayerActions"]
                dead = [a for a in acts if u32(a.fields["Layer"].id) not in global_layers]
                if not dead:
                    continue
                keep = [a for a in acts if u32(a.fields["Layer"].id) in global_layers]
                modes = {layer_mode(names.get(u32(a.fields["Layer"].id)) or self.layer_name(u32(a.fields["Layer"].id)))
                         for a in dead if u32(a.fields["Action"]) == 0}
                if "standard" in modes:
                    dlf.fields["LayerActions"] = keep
                    self.r.add("filters: cleared (standard modes)")
                elif "chest" in modes:
                    dlf.fields["LayerActions"] = keep + [retarget(dead[0], tw_handle)]
                    self.r.add("filters: -> " + CHEST_TARGET_LAYER)
                elif modes:
                    dlf.fields["LayerActions"] = keep + [retarget(dead[0], never_handle)]
                    self.r.add("filters: other-mode/other-map only -> never loaded (" + NEVER_LAYER + ")",
                               note=", ".join(sorted({names.get(u32(a.fields["Layer"].id))
                                                      or self.layer_name(u32(a.fields["Layer"].id)) for a in dead}))[:150])
                else:  # only "unload while active" actions on dead layers: they can never fire in ACB either
                    dlf.fields["LayerActions"] = keep
                    self.r.add("filters: dead unload-actions dropped")

    def acb_global_layers(self):
        """{id: name} of the DataLayers ACB can resolve in a match: the ones in DataPC.forge (always mounted)."""
        multi = pickle.load(open(os.path.join(HERE, "acb_multi_idx.pkl"), "rb"))
        return {i: v["DataPC.forge"][1] for i, v in multi.items() if v.get("DataPC.forge", ("",))[0] == "DataLayer"}

    def materialize_moves(self, files):
        """Objects moved into a grid cell / layer block by remap_layers still live in their ACR layer's entry
        (DataBlock_ACFE_Wanted, ...), which nothing loads any more -- the block's Refs would dangle at runtime (no
        spawn point ever registered: the pre-spawn hang). Retail keeps a block's objects in the block's own entry,
        so copy each moved object, plus the objects of its source entry it references (meshes, textures, ...),
        into the target block's entry, and merge the source entries' dependency tables."""
        for block_uid, ids in getattr(self, "moves", []):
            target = self.where[block_uid][0][0]
            have = {derive_uid_and_ext(sub[2], True)[0] for sub in target.subs}
            dep_ids = {d.id & 0xFFFFFFFF for d in target.deps}
            target_eid = derive_uid_and_ext(target.subs[0][2], True)[0]
            sources, todo = set(), list(ids)
            while todo:
                uid = todo.pop()
                if uid in have:
                    continue
                src = next((df for df, _i in self.where.get(uid, []) if df is not target), None)
                if src is None:
                    self.r.add("moved object: NOT found in any entry", note=f"{uid:#x}")
                    continue
                sub = next(sb for sb in src.subs if derive_uid_and_ext(sb[2], True)[0] == uid)
                if ACB_T.name_of(sub[0]) == "GridCellDataBlock":
                    continue
                target.subs.append(list(sub))
                have.add(uid)
                sources.add(id(src))
                self.r.add("moved object copied into its block's entry", note=f"{sub[1]} -> {target.subs[0][1]}")
                local = {derive_uid_and_ext(sb[2], True)[0] for sb in src.subs}
                try:
                    root = self.acb.decode(sub[2])
                except DecodeError:
                    continue
                for o in walk(root.obj):
                    stack = list(o.fields.values()) + [d[3] for d in o.dyn or []]
                    while stack:
                        x = stack.pop()
                        if isinstance(x, list):
                            stack.extend(x)
                        elif isinstance(x, (Ref, Handle)) and getattr(x, "obj", None) is None and u32(x.id) in local:
                            todo.append(u32(x.id))
                        elif isinstance(x, Ptr) and x.link and u32(x.link) in local:
                            todo.append(u32(x.link))
                        elif isinstance(x, (Ptr, Ref)) and getattr(x, "obj", None) is not None:
                            stack.append(x.obj)
            for df in files.values():
                if id(df) in sources:
                    for d in df.deps:
                        lo = d.id & 0xFFFFFFFF
                        if lo not in dep_ids and lo != target_eid:
                            target.deps.append(d)
                            dep_ids.add(lo)

    def _append(self, blk: Obj, ids):
        activate_objects(blk, ids)

    def name_of(self, uid):
        w = self.where.get(uid)
        return w[0][0].subs[w[0][1]][1] if w else f"{uid:#x}"

    # -- 1b. per-object transform --
    def strip(self, v, path):
        if isinstance(v, Obj):
            if v.type_hash in ACR_ONLY_TYPES:
                raise ValueError(f"{path}: embedded ACR-only {ACR.name_of(v.type_hash)}")
            for k, x in list(v.fields.items()):
                v.fields[k] = self.strip(x, f"{path}.{k}")
            if v.dyn:
                v.dyn = [(a, b, c, self.strip(d, path)) for a, b, c, d in v.dyn]
            return v
        if isinstance(v, Ptr):
            if v.obj is not None:
                if v.obj.type_hash in ACR_ONLY_TYPES:
                    self.r.add(f"stripped:{ACR.name_of(v.obj.type_hash)}")
                    return Ptr(3)
                self.strip(v.obj, path)
            return v
        if isinstance(v, Ref):
            if v.obj is not None:
                if v.obj.type_hash in ACR_ONLY_TYPES:
                    raise ValueError(f"{path}: inline ACR-only ref {ACR.name_of(v.obj.type_hash)}")
                self.strip(v.obj, path)
            return v
        if isinstance(v, list):
            out = []
            for i, x in enumerate(v):
                inner = x.obj if isinstance(x, (Ptr, Ref)) else x
                if isinstance(inner, Obj) and inner.type_hash in ACR_ONLY_TYPES:
                    self.r.add(f"stripped:{ACR.name_of(inner.type_hash)}")
                    continue
                out.append(self.strip(x, f"{path}[{i}]"))
            return out
        return v

    # -- template remap --
    # ACR templates with no ACB namesake -> what ACB's own equivalent materials use
    # (ACB GEN_RT_* realtree materials: AC2_Tex1_PixelLit_VertexAnim; Venice's
    # AC2MP_VEN_Water_Sea_01A: AC2MP_VEN_WaterSea_01a). ACFE_FFX is only used by
    # CTF-layer materials, which the port never loads.
    TEMPLATE_FALLBACKS = {"ACFE_Realtree": "AC2_Tex1_PixelLit_VertexAnim",
                          "ACFE_WaterSea": "AC2MP_VEN_WaterSea_01a"}
    TEMPLATE_RENAMES = [("ACFE_Characters_", "AC2MP_Characters_"), ("ACFE_", "AC2_"), ("ACFE_", "AC2MP_")]

    def acb_object_by_name(self, name, types=("MaterialTemplate", "<entry>")):
        hits = [k for k, v in self.acb_idx.items() if v[1] == name and v[0] in types]
        return hits[0] if hits else None

    def remap_templates(self, aggressive: bool):
        """Map ACR-only MaterialTemplates to ACB ones by name. Templates not in
        this forge (ACFE_Characters_Skin/Body live in ACR's DataPC) must be
        remapped; with `aggressive`, templates shipped in this forge are too."""
        referenced = set()
        for root in self.trees.values():
            for o in walk(root.obj):
                if ACR.name_of(o.type_hash) == "Material":
                    referenced.add(u32(o.fields["MaterialTemplate"].id))
        for tid in sorted(referenced):
            if tid in self.acb_idx:
                continue
            in_forge = tid in self.where
            if in_forge and not aggressive:
                continue
            name = (self.acr_idx.get(tid) or (None, self.name_of(tid)))[1].strip()
            target = None
            for a, b in self.TEMPLATE_RENAMES:
                if name.startswith(a):
                    target = self.acb_object_by_name(b + name[len(a):])
                    if target:
                        break
            if not target and name in self.TEMPLATE_FALLBACKS:
                target = self.acb_object_by_name(self.TEMPLATE_FALLBACKS[name])
            if target:
                self.id_remap[tid] = target
                self.r.add("template remapped", note=f"{name} -> {self.acb_idx[target][1]}")
            else:
                self.r.add("template NOT remapped (no ACB equivalent)", note=f"{name} ({'in forge' if in_forge else 'MISSING'})")

    def apply_id_remap(self, v, remap=None):
        remap = self.id_remap if remap is None else remap
        if not remap:
            return
        stack = [v]
        while stack:
            x = stack.pop()
            if isinstance(x, Obj):
                for k, y in x.fields.items():
                    if isinstance(y, (Ref, Handle)) and u32(y.id) in remap:
                        y.id = idb(remap[u32(y.id)])
                    stack.append(y)
                stack.extend(d[3] for d in x.dyn or [])
            elif isinstance(x, list):
                for y in x:
                    if isinstance(y, (Ref, Handle)) and u32(y.id) in remap:
                        y.id = idb(remap[u32(y.id)])
                    stack.append(y)
            elif isinstance(x, Ptr):
                if x.link and u32(x.link) in remap:
                    x.link = idb(remap[u32(x.link)])
                if x.obj is not None:
                    stack.append(x.obj)
            elif isinstance(x, Ref) and x.obj is not None:
                stack.append(x.obj)

    def remap_deps(self, files):
        for df in files.values():
            for d in df.deps:
                lo = d.id & 0xFFFFFFFF
                if lo in self.id_remap:
                    d.id = (d.id & ~0xFFFFFFFF) | self.id_remap[lo]

    def prune(self, v):
        """Drop fields ACB's layout of that type doesn't have (before strip, so
        an ACR-only object inside a dropped field isn't an error)."""
        if isinstance(v, Obj):
            if v.type_hash in ACB.types_by_hash:
                allowed = {ACB_T.name_of(p.name_hash) for _c, ps in self.acb.levels(v.type_hash) for p in ps}
                v.fields = {k: x for k, x in v.fields.items() if k in allowed}
            for x in v.fields.values():
                self.prune(x)
            for d in v.dyn or []:
                self.prune(d[3])
        elif isinstance(v, (Ptr, Ref)) and v.obj is not None:
            self.prune(v.obj)
        elif isinstance(v, list):
            for x in v:
                self.prune(x)

    def patch_fields(self, obj: Obj):
        for o in walk(obj):
            t = ACR.name_of(o.type_hash)
            if t == "MeshShape":
                # ACB's MeshShape::UpdateSDKObject trusts the stored MOPP only when MoppCodeVersionNumber == 5 and
                # otherwise rebuilds it from the triangles with its own Havok compiler. ACR's MOPPs come from a
                # different compiler (159/173 of the shapes both games ship differ) and leave collision holes in
                # ACB (fell through Souk's ground, walked through Rhodes' buildings), so let ACB rebuild them all.
                o.fields["MoppCodeVersionNumber"] = idb(0)
            if t in ("Mesh", "TextureMap") and "UserCategory" in o.fields:
                o.fields["UserCategory"] = idb(0)

    def encode_all(self, skip_types=()):
        for uid, root in self.trees.items():
            locs = self.where[uid]
            df, i = locs[0]
            ext, name, payload = df.subs[i]
            t = ACR.name_of(ext)
            if t in skip_types:
                continue
            try:
                self.apply_id_remap(root.obj)
                self.prune(root.obj)
                self.strip(root.obj, t)
                self.patch_fields(root.obj)
                left = [ACR.name_of(o.type_hash) for o in walk(root.obj) if o.type_hash in ACR_ONLY_TYPES]
                if left:
                    raise ValueError(f"ACR-only {left} left")
                new = self.acb.encode(root)
            except (KeyError, ValueError) as e:
                if uid in self.acb_idx:
                    self.fallback.add(uid)
                    self.r.add(f"encode-failed->ACB copy:{t}", note=f"{name}: {e}")
                else:
                    self.fallback.add(uid)  # still ACR bytes: substitute_opaque drops it if unreferenced, else reports it
                    self.r.add(f"ENCODE-FAIL:{t}", note=f"{name}: {e}")
                continue
            for d, j in locs:
                d.subs[j][2] = new
            self.r.add("converted:" + ("unchanged" if new == payload else "rewritten"))

    # -- 2. opaque substitution --
    def substitute_opaque(self, files, acb_dir):
        need, unsafe = {}, []
        for uid, locs in self.where.items():
            if uid in self.trees and uid not in self.fallback:
                continue
            df, i = locs[0]
            v = self.acb_idx.get(uid)
            if v:
                need[uid] = (locs, v[2])
            elif ACR.name_of(df.subs[i][0]) in SHARED_OPAQUE:
                self.r.add(f"opaque-kept-ACR:{ACR.name_of(df.subs[i][0])}", note=df.subs[i][1])
            else:
                unsafe.append((uid, locs))
        # anything else still in ACR form would be read with ACB's layout when its entry loads (e.g. Constantinople's
        # ACR-only "GameMode Deathmatch" UnlockableGameMode, an unreferenced extra sub-object of the World entry):
        # drop it if nothing refers to it, else report it loudly
        for uid, locs in unsafe:
            b = idb(uid)
            name = locs[0][0].subs[locs[0][1]][1]
            refd = any(b in s_[2] and derive_uid_and_ext(s_[2], True)[0] != uid for df in files.values() for s_ in df.subs) \
                or any(d.id & 0xFFFFFFFF == uid for df in files.values() for d in df.deps)
            if refd and ACR.name_of(locs[0][0].subs[locs[0][1]][0]) == "Animation" and self.unhook(files, uid):
                # ACR-only animations (e.g. jump_corner_spin_beam_left/right_leap, extra moves in the ACR corner spin
                # beam's AnimComponent): ACR's Animation layout differs from ACB's (shared clips are larger in ACR),
                # so take them out of every list that names them -- the object then works with ACB's own moves
                self.r.add("unhooked + dropped ACR-only Animation (ACB can't read ACR's layout)", note=name)
                refd = False
            if refd:
                self.r.add(f"opaque-kept-ACR-UNSAFE (referenced):{ACR.name_of(locs[0][0].subs[locs[0][1]][0])}", note=name)
                continue
            self.drop_uids.add(uid)  # removed right before writing (sub indices in self.where must stay valid)
            self.r.add(f"dropped unreferenced ACR-only-format object:{ACR.name_of(locs[0][0].subs[locs[0][1]][0])}", note=name)
        by_forge = defaultdict(set)
        for uid, (_locs, fg) in need.items():
            by_forge[fg].add(uid)
        from analyze import forge_items
        got = 0
        for fg, ids in by_forge.items():
            for e, subs, _ in forge_items(os.path.join(acb_dir, fg)):
                for ext, name, uid, p in subs:
                    if uid in ids and uid in need:
                        locs, _ = need.pop(uid)
                        if locs[0][0].subs[locs[0][1]][0] != ext:
                            self.r.add("opaque-substitute-type-mismatch", note=name)
                            continue
                        for df, i in locs:
                            df.subs[i][2] = p
                        got += 1
                        self.r.add(f"substituted-from-ACB:{ACR.name_of(ext)}")
        for uid, (locs, fg) in need.items():
            df, i = locs[0]
            self.r.add("substitute-NOT-FOUND", note=f"{df.subs[i][1]} ({fg})")

    def unhook(self, files, uid):
        """Remove every list reference to object `uid` (keeping GridCellDataBlock activation prefixes right) and every
        dependency on it. True if nothing refers to it any more."""
        b = idb(uid)
        for df in files.values():
            df.deps = [d for d in df.deps if d.id & 0xFFFFFFFF != uid]
            for sub in df.subs:
                if b not in sub[2] or derive_uid_and_ext(sub[2], True)[0] == uid:
                    continue
                try:
                    root = self.acb.decode(sub[2])
                except DecodeError:
                    return False
                for o in walk(root.obj):
                    for k, v in list(o.fields.items()):
                        if not isinstance(v, list):
                            continue
                        keep = [x for x in v if not (isinstance(x, (Ref, Handle)) and getattr(x, "obj", None) is None
                                                     and u32(x.id) == uid)]
                        if len(keep) == len(v):
                            continue
                        if k == "Objects" and "NumberOfObjectsToActivate" in o.fields:
                            n = u32(o.fields["NumberOfObjectsToActivate"])
                            gone = sum(1 for x in v[:n] if isinstance(x, (Ref, Handle)) and u32(x.id) == uid)
                            o.fields["NumberOfObjectsToActivate"] = idb(n - gone)
                        o.fields[k] = keep
                sub[2] = self.acb.encode(root)
                if b in sub[2][4:]:
                    return False
        return True

    # -- 4. registration --
    def register_base(self, files, acb_dir, name, world_id, donor, work):
        """Non-DLC map (--base): ACB loads a non-DLC World from multi/DataPC_<LoadInfo name>.forge
        (World::GetWorldAlternateSourcePrefixName -> GameBootstrap::GetObjectName), and the menu lists it from the
        CXB's MapManagerMulti (MpWorld defined inline there). So: no ContentPackage / MpWorld / DLC addons (base
        map forges have none, and base Worlds no DLCWorldComponent), World takes over a LoadInfo world's name + id.
        The donor base map supplies the map sound bank id and the MetaFile."""
        d_entries, d_files = load_forge(os.path.join(acb_dir, f"DataPC_{donor}.forge"), os.path.join(work, "donor"),
                                        Game.BROTHERHOOD)
        acb = self.acb
        world_uid = next(u for u, t in self.trees.items() if ACR.name_of(t.obj.type_hash) == "World")
        wdf, wi = self.where[world_uid][0]
        world = acb.decode(wdf.subs[wi][2])
        dw = next(acb.decode(s[2]).obj for df in d_files.values() for s in df.subs if ACB_T.name_of(s[0]) == "World")
        self.donor_world_id = u32(dw.id)

        def bank_ids(w):
            comps = [c.obj for c in w.fields["Components"]
                     if c.obj is not None and ACB_T.name_of(c.obj.type_hash) == "SoundBankWorldComponent"]
            return [o for c in comps for o in walk(c) if ACB_T.name_of(o.type_hash) == "WwiseID"]
        for ours, theirs in zip(bank_ids(world.obj), bank_ids(dw)):
            if ours.fields.get("ShortID") == bytes(4):
                ours.fields["ShortID"] = theirs.fields["ShortID"]
                self.r.add("registration: sound bank id taken from donor world", note=theirs.fields["ShortID"].hex())

        wdf.subs[wi][1] = name
        world.obj.fields["Components"] = [c for c in world.obj.fields["Components"]
                                          if not (getattr(c, "obj", None) is not None
                                                  and ACB_T.name_of(c.obj.type_hash) == "DLCWorldComponent")]
        wdf.subs[wi][2] = acb.encode(world)
        # drop them at write time: removing subs here would shift the sub indices self.where holds for the rest of
        # the World entry (that once fed 3 wrong objects to the Jerusalem chest list)
        self.drop_uids |= {derive_uid_and_ext(s[2], True)[0] for s in wdf.subs if ACB_T.name_of(s[0]) in
                           ("MpMapsDLCAddon", "SoundBankDLCAddon", "SoundPackagesDLCAddon")}
        for fn in [fn for fn, df in files.items() if any(ACB_T.name_of(s[0]) == "ContentPackage" for s in df.subs)]:
            del files[fn]
        self.world_id = u32(world.obj.id)
        self.slot_world_id = world_id
        self.r.add(f"registration: base map, world renamed to {name}, takes LoadInfo id {world_id:#x}")
        return [e for e in d_entries if e.name == "GlobalMetaFile"]

    def register_slot(self, files, acb_dir, slot, work):
        slot_forge = os.path.join(acb_dir, f"DataPC_{slot}_dlc.forge")
        s_entries, s_files = load_forge(slot_forge, os.path.join(work, "slot"), Game.BROTHERHOOD)
        acb = self.acb

        def find(files_, pred):
            for df in files_.values():
                for i, (ext, name, p) in enumerate(df.subs):
                    if pred(ACB_T.name_of(ext), name):
                        return df, i
            return None

        world_uid = next(u for u, t in self.trees.items() if ACR.name_of(t.obj.type_hash) == "World")
        wdf, wi = self.where[world_uid][0]
        world = acb.decode(wdf.subs[wi][2])  # already converted to ACB layout

        # slot's World object: take its name + MpMapsDLCAddons
        sw = find(s_files, lambda t, n: t == "World")
        slot_world_name = sw[0].subs[sw[1]][1]
        self.slot_world_id = derive_uid_and_ext(sw[0].subs[sw[1]][2], True)[0]
        slot_addons = [(ext, n, p) for ext, n, p in sw[0].subs if ACB_T.name_of(ext) == "MpMapsDLCAddon"]

        # ACR worlds carry an AutoLoad map sound bank with WwiseID 0 (Revelations loads map sound another way);
        # ACB's have the map's bank there -- take the slot's
        slot_world = acb.decode(sw[0].subs[sw[1]][2]).obj
        def bank_ids(w):
            comps = [c.obj for c in w.fields["Components"]
                     if c.obj is not None and ACB_T.name_of(c.obj.type_hash) == "SoundBankWorldComponent"]
            return [o for c in comps for o in walk(c) if ACB_T.name_of(o.type_hash) == "WwiseID"]
        for ours, theirs in zip(bank_ids(world.obj), bank_ids(slot_world)):
            if ours.fields.get("ShortID") == bytes(4):
                ours.fields["ShortID"] = theirs.fields["ShortID"]
                self.r.add("registration: sound bank id taken from slot world", note=theirs.fields["ShortID"].hex())

        # rename world + point DLCWorldComponent at the slot's addons
        wdf.subs[wi][1] = slot_world_name
        for c in world.obj.fields["Components"]:
            if c.obj is not None and ACB_T.name_of(c.obj.type_hash) == "DLCWorldComponent":
                c.obj.fields["DLCAddons"] = [Ref(1, 0, object_id_bytes(p, True)) for _e, _n, p in slot_addons]
                c.obj.fields["WorldInfo"].fields["NonLocalizedWorldName"] = slot_world_name.encode()
        wdf.subs[wi][2] = acb.encode(world)
        # replace our DLC addon objects (in the world .data) with the slot's
        self.drop_uids |= {derive_uid_and_ext(s[2], True)[0] for s in wdf.subs if ACB_T.name_of(s[0]) in
                           ("MpMapsDLCAddon", "SoundBankDLCAddon", "SoundPackagesDLCAddon")}  # see register_base
        wdf.subs += [list(a) for a in slot_addons]
        self.r.add("registration: world renamed to " + slot_world_name)

        # drop our own ContentPackage entry, take the slot's
        for fn in [fn for fn, df in files.items() if any(ACB_T.name_of(s[0]) == "ContentPackage" for s in df.subs)]:
            del files[fn]
        world_id = world.obj.id
        self.world_id = u32(world_id)
        for fn, df in s_files.items():
            types = {ACB_T.name_of(s[0]) for s in df.subs}
            if types & {"ContentPackage", "MpWorld"}:
                for s in df.subs:
                    t = ACB_T.name_of(s[0])
                    if t in ("ContentPackage", "MpWorld"):
                        root = acb.decode(s[2])
                        for o in walk(root.obj):
                            tn = ACB_T.name_of(o.type_hash)
                            if tn == "MpWorld":
                                o.fields["World"] = Handle(0, world_id)
                            if tn == "DLCWorldInfo":
                                o.fields["World"] = Handle(0, world_id)
                        s[2] = acb.encode(root)
                files["slot_" + fn] = df
                self.r.add("registration: took slot entry", note=df.subs[0][1])
        # NOT add_additional_world_data(): AdditionalWorldDataDLCElement::OnPackageLoaded keeps only the *first*
        # loaded element's table (skins DLC packages carry every world's), later ones are freed -- ours would be
        # ignored, or, if loaded first, would wipe the chest/escort data of every other map.

        # images referenced by the MpWorlds
        img_ids = set()
        for fn, df in files.items():
            if fn.startswith("slot_"):
                for s in df.subs:
                    if ACB_T.name_of(s[0]) == "MpWorld":
                        mw = acb.decode(s[2]).obj
                        img_ids |= {u32(mw.fields[k].id) for k in ("TopViewImg", "PreviewImg")}
        for fn, df in s_files.items():
            uid, _ = derive_uid_and_ext(df.subs[0][2], True) if df.subs else (0, 0)
            if uid in img_ids:
                files["slot_" + fn] = df
                self.r.add("registration: took slot image", note=df.subs[0][1])
        return s_entries


def retail_order(fn):
    """Retail map forges are laid out MetaFile, World, Cell00084_DataBlock, ..., ContentPackage, MpWorlds + their
    images: keep the source forge's own order, then entries we added, then the slot's registration entries."""
    head = fn[len("slot_"):] if fn.startswith("slot_") else fn
    idx = head.split("_-_", 1)[0]
    rank = 2 if fn.startswith("slot_") else (0 if idx.isdigit() else 1)
    return (rank, int(idx) if idx.isdigit() else 0, fn)


def renumber_object(conv, files, old, new):
    """Give object `old` the id `new` everywhere: its own id, every reference
    to it, dependency tables. Objects that don't decode (NavMeshManager embeds
    the world id) get a raw 4-byte replace -- retail navmeshes carry it too."""
    oldb, newb = idb(old), idb(new)
    for df in files.values():
        assert not any(derive_uid_and_ext(p, True)[0] == new for _e, _n, p in df.subs), f"{new:#x} already used"
    for df in files.values():
        for d in df.deps:
            if d.id & 0xFFFFFFFF == old:
                d.id = (d.id & ~0xFFFFFFFF) | new
                conv.r.add("renumber: dependency")
        for sub in df.subs:
            if oldb not in sub[2]:
                continue
            try:
                root = conv.acb.decode(sub[2])
            except DecodeError:
                sub[2] = sub[2].replace(oldb, newb)
                conv.r.add(f"renumber: raw replace in {ACB_T.name_of(sub[0])}", note=sub[1])
                continue
            for o in walk(root.obj):
                if o.id == oldb:
                    o.id = newb
                for k, v in o.fields.items():  # raw id fields, e.g. AdditionalWorldDataHolder.AssociatedWorld
                    if v == oldb:
                        o.fields[k] = newb
            conv.apply_id_remap(root.obj, {old: new})
            sub[2] = conv.acb.encode(root)
            conv.r.add(f"renumber: {ACB_T.name_of(sub[0])}" + (" (residual bytes!)" if oldb in sub[2] else ""),
                       note=sub[1])


def add_mp_message_scene(conv, files, acb_dir, slot_forge):
    """Every ACB MP map has one 'Death_Message_Total_<map>_02' Entity: a Scene with the MP kill/ability messages
    (61 MPMessage, 50 MPAbilityMessageMap, 21 MPDeathContextConditionClip -- identical in every map). ACR maps have
    none (Revelations keeps that elsewhere), so copy the slot map's into our top grid cell, together with the
    objects of its retail entry it references; objects in other entries are handled by add_reference_deps()."""
    from analyze import forge_items

    def refs_in(root):
        out = set()
        for o in walk(root.obj):
            stack = list(o.fields.values()) + [d[3] for d in o.dyn or []]
            while stack:
                x = stack.pop()
                if isinstance(x, list):
                    stack.extend(x)
                elif isinstance(x, (Ref, Handle)) and getattr(x, "obj", None) is None:
                    out.add(u32(x.id))
                elif isinstance(x, Ptr) and x.link:
                    out.add(u32(x.link))
        return out

    for e, subs, _deps in forge_items(os.path.join(acb_dir, slot_forge)):
        hit = [s for s in subs if s[1].startswith("Death_Message_Total") and ACB_T.name_of(s[0]) == "Entity"]
        if not hit:
            continue
        by_uid = {uid: (ext, name, p) for ext, name, uid, p in subs}
        cell = next(conv.acb.decode(p) for ext, name, uid, p in subs if ACB_T.name_of(ext) == "GridCellDataBlock")
        listed = {u32(x.id) for x in cell.obj.fields["Objects"]}
        take, todo = [], [hit[0][2]]
        while todo:
            uid = todo.pop()
            if uid in take or uid not in by_uid or ACB_T.name_of(by_uid[uid][0]) == "GridCellDataBlock":
                continue
            take.append(uid)
            todo.extend(refs_in(conv.acb.decode(by_uid[uid][2])))
        break
    else:
        conv.r.add("mp message scene: NOT found in slot forge")
        return
    # the quadtree root's block (remap_layers); its name depends on the grid depth (Cell00084 for 4 levels)
    top, gi = conv.where[conv.top_cell_id][0]
    blk = conv.acb.decode(top.subs[gi][2])
    activate_objects(blk.obj, [u for u in take if u in listed])
    top.subs[gi][2] = conv.acb.encode(blk)
    for uid in take:
        ext, name, p = by_uid[uid]
        top.subs.append([ext, name, p])
        conv.r.add("mp message scene: object copied into top cell", note=f"{ACB_T.name_of(ext)} {name}")


def add_reference_deps(conv, files, slot_forge):
    """Make objects this map references loadable the way retail maps do. At runtime only the map's own forge and
    the global DataPC.forge are loaded, so a Ref / link to an object that lives only in another map's forge (e.g. a
    template-remap target like AC2MP_VEN_WaterSea_01a, SanMarco) never resolves. Retail maps also ship their own
    entry copies of shared templates (AC2MP_Characters_Body/Skin are entries in every map forge, listed with flag 1
    in the users' dependency tables) even though DataPC.forge has them as sub-objects. Add such targets as flag-1
    dependencies; vendor_dependencies() then copies them in."""
    multi = pickle.load(open(os.path.join(HERE, "acb_multi_idx.pkl"), "rb"))
    own = set()
    decoded = []
    for df in files.values():
        for sub in df.subs:
            own.add(derive_uid_and_ext(sub[2], True)[0])
            try:
                root = conv.acb.decode(sub[2])
            except DecodeError:
                continue
            own.update(u32(o.id) for o in walk(root.obj))
            decoded.append((df, root))
    for df, root in decoded:
        targets = set()
        for o in walk(root.obj):
            stack = list(o.fields.values()) + [d[3] for d in o.dyn or []]
            while stack:
                x = stack.pop()
                if isinstance(x, list):
                    stack.extend(x)
                elif isinstance(x, Ref) and x.obj is None and x.tag in (1, 3):
                    targets.add(u32(x.id))
                elif isinstance(x, Ptr) and x.link:
                    targets.add(u32(x.link))
        have = {d.id & 0xFFFFFFFF for d in df.deps}
        for t in sorted(targets - own - have - {0}):
            where = multi.get(t, {})
            if not where:
                continue  # dangling in retail too (validate.py reports these)
            if "DataPC.forge" in where and where.get(slot_forge, ("",))[0] != "<entry>":
                continue  # global, and retail maps don't carry their own copy
            df.deps.append(Dependency(id=t | (1 << 32)))
            conv.r.add("reference dep added (vendored next)", note=f"{where[next(iter(where))][1]} <- {df.subs[0][1]}")


def vendor_dependencies(files, acb_dir, acb_idx, report):
    """Retail map forges are self-contained: every entry's dependency table
    only lists entries of the same forge (checked on retail Alhambra: 0 of
    1749 point elsewhere). A dependency on an entry that lives in another
    forge crashes ACB's loader (the streaming code walks dependency tables at
    entry offset + 0x1b8), so copy every such entry in from the ACB forge that
    has it, repeating until the dependency closure is in-forge."""
    from anvilforge.forge import read_header
    from anvilforge.fileset import iter_fileset_entries, read_entry_payload

    def entry_id(df):
        return derive_uid_and_ext(df.subs[0][2], True)[0] if df.subs else None

    have = {entry_id(df) for df in files.values()}
    while True:
        missing = {}
        for df in list(files.values()):
            for d in df.deps:
                lo = d.id & 0xFFFFFFFF
                if lo not in have:
                    missing.setdefault(lo, df.subs[0][1] if df.subs else "?")
        if not missing:
            return
        by_forge = defaultdict(set)
        for i in missing:
            if i in acb_idx:
                by_forge[acb_idx[i][2]].add(i)
            else:
                report.add("vendor: dependency NOT in ACB (left dangling)", note=f"{i:#x} <- {missing[i]}")
                have.add(i)
        for fg, want in by_forge.items():
            with open(os.path.join(acb_dir, fg), "rb") as f:
                for sidx in range(read_header(f, 25)):
                    for e in list(iter_fileset_entries(f, sidx, True)):
                        if e.id in want and e.id not in have:
                            raw = read_entry_payload(f, e, True)
                            files[f"vendor_-_{e.name}.data"] = DataFile(f"vendor_-_{e.name}.data", raw, Game.BROTHERHOOD)
                            have.add(e.id)
                            report.add("vendor: copied ACB entry into forge", note=f"{e.name} (from {fg})")
            # ids that only exist as a sub-object inside some other entry:
            # wrap a copy in an entry of its own so the dependency resolves
            rest = want - have
            if rest:
                with open(os.path.join(acb_dir, fg), "rb") as f:
                    for sidx in range(read_header(f, 25)):
                        for e in list(iter_fileset_entries(f, sidx, True)):
                            if not rest:
                                break
                            try:
                                src = DataFile("", read_entry_payload(f, e, True), Game.BROTHERHOOD)
                            except Exception:
                                continue
                            for ext, name, payload in src.subs:
                                uid = derive_uid_and_ext(payload, True)[0]
                                if uid in rest:
                                    files[f"vendor_-_{name}.data"] = _new_datafile(
                                        f"vendor_-_{name}.data", [[ext, name, payload]])
                                    rest.discard(uid); have.add(uid)
                                    report.add("vendor: wrapped ACB sub-object as own entry",
                                               note=f"{name} (from {e.name} in {fg})")
            for i in want - have:
                report.add("vendor: NOT found in its forge", note=f"{i:#x} ({fg})")
                have.add(i)


def _with_flag(obj, flag):
    obj.flag = flag
    return obj


def _new_datafile(fname, subs):
    df = DataFile.__new__(DataFile)
    df.fname, df.deps, df.raw_dep, df.subs = fname, [], b"", subs
    return df


def _add_world_data_methods():
    def alloc_id(self):
        if not hasattr(self, "_multi_ids"):
            self._multi_ids = set(pickle.load(open(os.path.join(HERE, "acb_multi_idx.pkl"), "rb")))
        while True:
            self._next_id += 1
            i = self._next_id
            if i not in self.acb_idx and i not in self.acr_idx and i not in self.where and i not in self._multi_ids:
                return i

    def add_additional_world_data(self, files, world_id: bytes):
        """ACB delivers per-map Chest Capture spawn points (mode 2) and Escort
        VIP paths (mode 7) via an AdditionalWorldDataDLCElement in a DLC
        ContentPackage (see DataPC_skins_0002_00000004_dlc); ACR stores the
        same data on World.chestSpawnPoints / World.TeamVIPPaths."""
        self._next_id = u32(world_id) + 0x10000
        acb = self.acb
        H = lambda n: name_hash(ACB, n)
        per_mode = []
        if self.vip_paths:
            vid = self.alloc_id()
            root = Root(b"", 0, Obj(H("AdditionalWorldData_TeamVIP"), idb(vid),
                                    {"TeamVIPPaths": self.vip_paths}, flag=1))
            files["awd_-_AWD_TeamVIP_ACFE_Dyers.data"] = _new_datafile(
                "awd_-_AWD_TeamVIP_ACFE_Dyers.data", [[H("AdditionalWorldData_TeamVIP"), "Unnamed", acb.encode(root)]])
            per_mode.append((7, vid))
            self.r.add("additional world data: Escort (TeamVIP) paths", n=len(self.vip_paths))
        chest_ents = [i for i in self.chest_objects if "chest" in self.name_of(i).lower()]
        if self.acr_chest_points or chest_ents:
            cid = self.alloc_id()
            pts = list(self.acr_chest_points) or [Ref(1, 0, idb(i)) for i in chest_ents]
            root = Root(b"", 0, Obj(H("AdditionalWorldData_ChestCapture"), idb(cid),
                                    {"chestSpawnPoints": pts}, flag=1))
            files["awd_-_AWD_ChestCapture_ACFE_Dyers.data"] = _new_datafile(
                "awd_-_AWD_ChestCapture_ACFE_Dyers.data", [[H("AdditionalWorldData_ChestCapture"), "Unnamed", acb.encode(root)]])
            per_mode.append((2, cid))
            self.r.add("additional world data: Chest Capture spawn points", n=len(pts),
                       note=", ".join(self.name_of(u32(x.id)) for x in pts[:8]))
        if not per_mode:
            return
        # attach to the slot's ContentPackage
        for fn, df in files.items():
            for sub in df.subs:
                if ACB_T.name_of(sub[0]) != "ContentPackage":
                    continue
                cp = acb.decode(sub[2])
                holder = Obj(H("AdditionalWorldDataHolder"), idb(self.alloc_id()), {
                    "AssociatedWorld": world_id,
                    "PerGameModeData": [Obj(H("AdditionalWorldDataPerGameModeHolder"), idb(self.alloc_id()),
                                            {"AssociatedGameModeID": idb(m), "AdditionalWorldData": Handle(0, idb(i))})
                                        for m, i in per_mode]})
                elem = Obj(H("AdditionalWorldDataDLCElement"), idb(self.alloc_id()), {
                    "Package": Handle(0, cp.obj.id),
                    "AdditionalWorldDataHolders": [holder]}, flag=1)
                cp.obj.fields["Elements"] = cp.obj.fields["Elements"] + [Ptr(0, obj=elem)]
                sub[2] = acb.encode(cp)
                self.r.add("additional world data: DLC element added to " + sub[1])

    def override_slot_world_data(self, files, acb_dir):
        """Escort (TeamVIP) paths: ACB looks them up per world id + game mode in the AdditionalWorldDataDLCElement of
        the first loaded package (the skins DLCs; see OnPackageLoaded) and loads the AdditionalWorldData object by id
        through LoadOnDemandManager, which probes sources in order DataPC_extra -> the map forge -> skins DLCs ->
        ... (seen in the lookup trace). So an entry in OUR forge with the id the skins table uses for the slot world
        overrides the slot map's data. Ship Dyers' World.TeamVIPPaths that way (same types in both games; the nodes'
        NavFlow handles point at Dyers' own CrowdFlow entities)."""
        from analyze import forge_items
        want = idb(self.slot_world_id)
        by_mode = {}
        for fg in ("DataPC_skins_0002_00000004_dlc.forge", "DataPC_skins_0001_00000002_dlc.forge",
                   "DataPC_skins_0000_00000001_dlc.forge"):
            path = os.path.join(acb_dir, fg)
            if not os.path.exists(path):
                continue
            for _e, subs, _d in forge_items(path):
                for ext, _name, _uid, pl in subs:
                    if ACB_T.name_of(ext) != "ContentPackage":
                        continue
                    for o in walk(self.acb.decode(pl).obj):
                        if ACB_T.name_of(o.type_hash) == "AdditionalWorldDataHolder" and o.fields["AssociatedWorld"] == want:
                            for pm in o.fields["PerGameModeData"]:
                                by_mode.setdefault(u32(pm.fields["AssociatedGameModeID"]), u32(pm.fields["AdditionalWorldData"].id))
            if by_mode:
                break
        self.r.add("slot world data ids (skins DLC table)", note=", ".join(f"mode {m}: {i:#x}" for m, i in sorted(by_mode.items())))
        files.update(self.build_world_data(by_mode))

    def build_world_data(self, by_mode):
        """Dyers' Escort paths (mode 7) and Chest Capture spawn points (mode 2) as AdditionalWorldData entries
        under the given ids -> {loose file name: DataFile}."""
        files = {}
        H = lambda n: name_hash(ACB, n)
        if self.vip_paths and 7 in by_mode:
            vid = by_mode[7]
            root = Root(b"", 0, Obj(H("AdditionalWorldData_TeamVIP"), idb(vid), {"TeamVIPPaths": self.vip_paths}, flag=1))
            self.prune(root.obj)
            self.strip(root.obj, "AdditionalWorldData_TeamVIP")
            fn = f"awd_-_{vid:016X}.data"
            files[fn] = _new_datafile(fn, [[H("AdditionalWorldData_TeamVIP"), "Unnamed", self.acb.encode(root)]])
            nodes = sum(len(pth.fields["Path"]) for pth in self.vip_paths)
            self.r.add("escort: TeamVIP paths shipped as world data", n=len(self.vip_paths),
                       note=f"{vid:#x}, {nodes} nodes")
        elif self.vip_paths:
            self.r.add("escort: slot world has no TeamVIP entry in the skins table -- paths NOT shipped")

        # Chest Capture (mode 2): retail's AdditionalWorldData_ChestCapture lists the map's chest spawn points --
        # the SpawnType-3 MultiSpawnPlayerComponent entities of the gamemode_teamwanted layer -- and carries copies
        # of those entities inside its own entry so the Refs resolve when it is loaded. Dyers' equivalents are the
        # type-3 entities remap_layers moved into gamemode_teamwanted (Chest_Spawn*).
        if 2 in by_mode:
            cid = by_mode[2]
            chest = []
            cands = self.chest_objects
            if not cands:
                # maps without ACR chest layers (Juderia) keep their chest spawns unlayered in the grid: take every
                # SpawnType-3 spawn entity
                cands = sorted(u for u, t in self.trees.items() if ACR.name_of(t.obj.type_hash) == "Entity" and any(
                    ACR.name_of(o.type_hash) == "MultiSpawnPlayerComponent" and u32(o.fields.get("SpawnType", b"\0" * 4)) == 3
                    for o in walk(t.obj)))
                self.r.add("chest capture: no chest layer, using all SpawnType-3 entities", n=len(cands))
            for uid in cands:
                locs = self.where.get(uid)
                if not locs:
                    continue
                df, i = locs[0]
                sub = df.subs[i]
                if ACB_T.name_of(sub[0]) != "Entity":
                    continue
                ent = self.acb.decode(sub[2]).obj
                if any(ACB_T.name_of(o.type_hash) == "MultiSpawnPlayerComponent" and u32(o.fields["SpawnType"]) == 3
                       for o in walk(ent)):
                    # the AWD's copy is not a plain copy of the map's: retail's differ from their map twins in
                    # exactly IsPhantom=1 and inline component pointers stored as status 0 + flag 1 (instead of
                    # status 4 + flag 0) -- reproduces all 18 Alhambra copies byte for byte from the map copies
                    root = self.acb.decode(sub[2])
                    root.obj.fields["IsPhantom"] = b"\x01"
                    root.obj.fields["Components"] = [Ptr(0, obj=_with_flag(x.obj, 1)) if isinstance(x, Ptr) and x.obj is not None
                                                     else x for x in root.obj.fields["Components"]]
                    chest.append((sub[1], uid, [sub[0], sub[1], self.acb.encode(root)]))
            chest.sort()
            if chest:
                root = Root(b"", 0, Obj(H("AdditionalWorldData_ChestCapture"), idb(cid),
                                        {"chestSpawnPoints": [Ref(1, 0, idb(uid)) for _n, uid, _s in chest]}, flag=1))
                fn = f"awd_-_{cid:016X}.data"
                files[fn] = _new_datafile(fn, [[H("AdditionalWorldData_ChestCapture"), "Unnamed", self.acb.encode(root)]]
                                          + [s_ for _n, _u, s_ in chest])
                self.r.add("chest capture: chest spawn points shipped as world data", n=len(chest),
                           note=f"{cid:#x}: " + ", ".join(n for n, _u, _s in chest))
            else:
                self.r.add("chest capture: no SpawnType-3 entities found -- NOT shipped")
        return files

    def base_world_data(self, out_forge, donor_world_id):
        """Non-DLC map: the skins DLC table (OnlineMenuController+0x5950) has no row for our World, and only those
        packages fill it. Build the world-data entries under fresh ids into <out_forge>.awd/ plus awd.json, from which
        patch_skins.py --awd adds them and a row for our World to the skins forges (retail keeps every map's world data
        as dependency-free entries there). Ids: the data entries are shared by both skins forges like retail's; each
        forge gets its own holder ids (retail's differ per package)."""
        self._next_id = self.slot_world_id + 0x10000
        by_mode = {2: self.alloc_id(), 7: self.alloc_id()}
        awd = self.build_world_data(by_mode)
        out = out_forge + ".awd"
        shutil.rmtree(out, ignore_errors=True)
        os.makedirs(out)
        entries = {}
        for fn, df in awd.items():
            open(os.path.join(out, fn), "wb").write(df.build(Game.BROTHERHOOD))
            entries[fn] = derive_uid_and_ext(df.subs[0][2], True)[0]
        meta = {"world": self.slot_world_id, "donor_world": donor_world_id, "modes": by_mode, "entries": entries,
                "holder_ids": [[self.alloc_id() for _ in range(4)] for _forge in range(2)]}
        json.dump(meta, open(os.path.join(out, "awd.json"), "w"), indent=1)
        self.r.add("base map: world data written for patch_skins.py --awd",
                   note=f"{out}: " + ", ".join(f"mode {m}: {i:#x}" for m, i in sorted(by_mode.items())))

    Converter.alloc_id = alloc_id
    Converter.add_additional_world_data = add_additional_world_data
    Converter.override_slot_world_data = override_slot_world_data
    Converter.build_world_data = build_world_data
    Converter.base_world_data = base_world_data


_add_world_data_methods()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("acr_forge")
    ap.add_argument("acb_multi_dir")
    ap.add_argument("out_forge")
    ap.add_argument("--slot", default="AC2MP_Alhambra", help="DLC map slot to take over (DataPC_<slot>_dlc.forge)")
    ap.add_argument("--base", default=None,
                    help="non-DLC map instead: GameBootstrap LoadInfo world name to take over (bootstrap_worlds.json), "
                         "e.g. AC2MP_ludotest; out_forge must then be named DataPC_<name>.forge")
    ap.add_argument("--donor", default="AC2MP_SanMarco", help="--base: base map giving sound bank, MP messages, MetaFile")
    ap.add_argument("--work", default=None)
    ap.add_argument("--remap-acfe-templates", action="store_true",
                    help="also swap ACR shader templates shipped in the forge for same-named ACB ones")
    args = ap.parse_args()
    if args.base:
        args.slot = None
        base_id = json.load(open(os.path.join(HERE, "bootstrap_worlds.json")))[args.base]
        want = f"DataPC_{args.base[:19]}.forge"  # GetWorldAlternateSourcePrefixName copies the name into char[20]
        if os.path.basename(args.out_forge) != want:
            ap.error(f"--base {args.base}: the game will look for {want}")
    ref_forge = f"DataPC_{args.slot}_dlc.forge" if args.slot else f"DataPC_{args.donor}.forge"

    r = Report()
    work = args.work or tempfile.mkdtemp(prefix="acrport_")
    os.makedirs(work, exist_ok=True)
    conv = Converter(args, r)

    entries, files = load_forge(args.acr_forge, os.path.join(work, "src"), Game.REVELATIONS)
    conv.decode_all(files)
    conv.capture_world_extras()
    conv.remap_layers()
    conv.remap_templates(args.remap_acfe_templates)
    conv.remap_deps(files)
    conv.encode_all(skip_types=("ContentPackage",))
    conv.substitute_opaque(files, args.acb_multi_dir)
    conv.materialize_moves(files)
    if args.slot:
        s_entries = conv.register_slot(files, args.acb_multi_dir, args.slot, work)
        conv.override_slot_world_data(files, args.acb_multi_dir)
    else:
        s_entries = conv.register_base(files, args.acb_multi_dir, args.base, base_id, args.donor, work)
    add_mp_message_scene(conv, files, args.acb_multi_dir, ref_forge)
    add_reference_deps(conv, files, ref_forge)
    vendor_dependencies(files, args.acb_multi_dir, conv.acb_idx, r)
    # the rest of ACB knows the map's World by id (slot: AssassinSoundSettings in DataPC.forge, skins DLC package
    # descriptors; base: GameBootstrap LoadInfo -> forge name), so the ported World must take that id -- otherwise
    # the map never finishes loading
    renumber_object(conv, files, conv.world_id, conv.slot_world_id)
    if args.base:
        conv.base_world_data(args.out_forge, conv.donor_world_id)

    out_dir = os.path.join(work, "out")
    shutil.rmtree(out_dir, ignore_errors=True)
    os.makedirs(out_dir)
    # MetaFile: it carries the package changelist (matches ContentPackage's
    # MinimumChangelistNumber), so take the slot's when we took its package; base maps: the donor's
    src_dir = os.path.join(work, "slot" if args.slot else "donor")
    for fn in os.listdir(src_dir):
        if fn.endswith(".MetaFile"):
            shutil.copy(os.path.join(src_dir, fn), os.path.join(out_dir, fn))
    for df in files.values():
        df.subs = [s_ for s_ in df.subs if derive_uid_and_ext(s_[2], True)[0] not in conv.drop_uids]
    for n, (fn, df) in enumerate(sorted(files.items(), key=lambda kv: retail_order(kv[0]))):
        base = fn[len("slot_"):] if fn.startswith("slot_") else fn
        base = base.split("_-_", 1)[1]
        if df.subs and ACB_T.name_of(df.subs[0][0]) == "World":
            base = df.subs[0][1] + ".data"
        open(os.path.join(out_dir, f"{n + 1}_-_{base}"), "wb").write(df.build(Game.BROTHERHOOD))
    # entries we added have no original metadata; create_entry() would derive a non-zero extension, retail map
    # forges have 0 on every entry
    known = {e.id for e in list(entries) + list(s_entries)}
    added = []
    for fn in os.listdir(out_dir):
        e = create_entry(os.path.join(out_dir, fn), 0, Game.BROTHERHOOD)
        if e is not None and e.id not in known:
            e.extension = 0
            added.append(e)
    repack(out_dir, args.out_forge, Game.BROTHERHOOD, original_entries=list(entries) + list(s_entries) + added,
           align_entries=True)
    rep = r.text()
    open(args.out_forge + ".report.txt", "w").write(rep)
    print(rep)
    print(f"\nWrote {args.out_forge} ({os.path.getsize(args.out_forge) / 1e6:.1f} MB); work dir {work}")


if __name__ == "__main__":
    main()

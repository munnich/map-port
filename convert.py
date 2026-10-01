"""Convert an ACR (Revelations) MP map forge into an ACB (Brotherhood) one.

    convert.py <acr_map.forge> <acb_multi_dir> <out.forge> [--slot AC2MP_Alhambra]

Pipeline (see NOTES.md for how each rule was established):
  1. Every sub-object is decoded with the ACR schema (anvilforge.fastload),
     ACR-only object types are stripped (from arrays / pointers), and it is
     re-encoded with ACB's schema (placeholders filled from ACR), which drops
     every ACR-added field by construction. Missing ACB-only fields get
     defaults (MeshShape.MoppCodeVersionNumber = 5). Mesh/TextureMap
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
import os
import pickle
import shutil
import sys
import tempfile
from collections import Counter, defaultdict

sys.path.insert(0, os.path.expanduser("~/Coding/Python/anvilforge-py-acrport/src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from anvilforge.binio import write_string32
from anvilforge.datafile import (DATA_MAGIC, DATA_VERSIONS, _build_toc, _extra_from_header,
                                 _read_inline_dependencies, _write_block_set,
                                 _write_inline_dependencies, derive_uid_and_ext,
                                 iter_datafile_subparts, object_id_bytes)
from anvilforge.fastload import Codec, DecodeError, Handle, Obj, Ptr, Ref, Root, walk
from anvilforge.fileset import loose_file_name
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
TOP_CELL_NAME_SUFFIX = "Cell00084"  # 4-level quadtree: 64+16+4+1 cells, last = whole map

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
            return [u32(x.id) for x in blk.fields["Objects"]]

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
        self._append(top, std)

        tw = next(l for l, n in names.items() if n == CHEST_TARGET_LAYER)
        self._append(block(by_layer[tw]), chest)

        wdlm.obj.fields["LayersConfig"] = [a for a in assoc if u32(a.fields["Layer"].id) not in acr_only_layers]
        self.r.add("layers: ACR-only layer associations removed", n=len(assoc) - len(wdlm.obj.fields["LayersConfig"]))

        # entity filters
        tw_handle = Handle(0, idb(tw))
        for t in self.trees.values():
            for o in walk(t.obj):
                dlf = o.fields.get("DataLayerFilter")
                if not isinstance(dlf, Obj):
                    continue
                acts = dlf.fields["LayerActions"]
                lids = [u32(a.fields["Layer"].id) for a in acts]
                if not any(l in acr_only_layers for l in lids):
                    continue
                ns = {names.get(l, self.layer_name(l)) for l in lids}
                keep = [a for a in acts if u32(a.fields["Layer"].id) not in acr_only_layers]
                if ns & STANDARD_MODES:
                    dlf.fields["LayerActions"] = keep
                    self.r.add("filters: cleared (standard modes)")
                elif ns & CHEST_MODES:
                    proto = acts[0]
                    new = Obj(proto.type_hash, proto.id, dict(proto.fields), proto.flag)
                    new.fields["Layer"] = tw_handle
                    dlf.fields["LayerActions"] = keep + [new]
                    self.r.add("filters: -> " + CHEST_TARGET_LAYER)
                else:
                    self.r.add("filters: left on ACR-only layers (object never loaded)")

    def _append(self, blk: Obj, ids):
        have = {u32(x.id) for x in blk.fields["Objects"]}
        add = [i for i in sorted(ids) if i not in have]
        blk.fields["Objects"] = blk.fields["Objects"] + [Ref(1, 0, idb(i)) for i in add]
        n = u32(blk.fields["NumberOfObjectsToActivate"]) + len(add)
        blk.fields["NumberOfObjectsToActivate"] = idb(n)

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

    def apply_id_remap(self, v):
        if not self.id_remap:
            return
        stack = [v]
        while stack:
            x = stack.pop()
            if isinstance(x, Obj):
                for k, y in x.fields.items():
                    if isinstance(y, (Ref, Handle)) and u32(y.id) in self.id_remap:
                        y.id = idb(self.id_remap[u32(y.id)])
                    stack.append(y)
                stack.extend(d[3] for d in x.dyn or [])
            elif isinstance(x, list):
                for y in x:
                    if isinstance(y, (Ref, Handle)) and u32(y.id) in self.id_remap:
                        y.id = idb(self.id_remap[u32(y.id)])
                    stack.append(y)
            elif isinstance(x, Ptr):
                if x.link and u32(x.link) in self.id_remap:
                    x.link = idb(self.id_remap[u32(x.link)])
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
            if t == "MeshShape" and "MoppCodeVersionNumber" not in o.fields:
                o.fields["MoppCodeVersionNumber"] = idb(5)
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
                    self.r.add(f"ENCODE-FAIL:{t}", note=f"{name}: {e}")
                continue
            for d, j in locs:
                d.subs[j][2] = new
            self.r.add("converted:" + ("unchanged" if new == payload else "rewritten"))

    # -- 2. opaque substitution --
    def substitute_opaque(self, files, acb_dir):
        need = {}
        for uid, locs in self.where.items():
            if uid in self.trees and uid not in self.fallback:
                continue
            df, i = locs[0]
            v = self.acb_idx.get(uid)
            if v:
                need[uid] = (locs, v[2])
            else:
                self.r.add(f"opaque-kept-ACR:{ACR.name_of(df.subs[i][0])}", note=df.subs[i][1])
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

    # -- 4. registration --
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
        slot_addons = [(ext, n, p) for ext, n, p in sw[0].subs if ACB_T.name_of(ext) == "MpMapsDLCAddon"]

        # rename world + point DLCWorldComponent at the slot's addons
        wdf.subs[wi][1] = slot_world_name
        for c in world.obj.fields["Components"]:
            if c.obj is not None and ACB_T.name_of(c.obj.type_hash) == "DLCWorldComponent":
                c.obj.fields["DLCAddons"] = [Ref(1, 0, object_id_bytes(p, True)) for _e, _n, p in slot_addons]
                c.obj.fields["WorldInfo"].fields["NonLocalizedWorldName"] = slot_world_name.encode()
        wdf.subs[wi][2] = acb.encode(world)
        # replace our DLC addon objects (in the world .data) with the slot's
        wdf.subs = [s for s in wdf.subs if ACB_T.name_of(s[0]) not in
                    ("MpMapsDLCAddon", "SoundBankDLCAddon", "SoundPackagesDLCAddon")]
        wdf.subs += [list(a) for a in slot_addons]
        self.r.add("registration: world renamed to " + slot_world_name)

        # drop our own ContentPackage entry, take the slot's
        for fn in [fn for fn, df in files.items() if any(ACB_T.name_of(s[0]) == "ContentPackage" for s in df.subs)]:
            del files[fn]
        world_id = world.obj.id
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
        self.add_additional_world_data(files, world_id)

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


def _new_datafile(fname, subs):
    df = DataFile.__new__(DataFile)
    df.fname, df.deps, df.raw_dep, df.subs = fname, [], b"", subs
    return df


def _add_world_data_methods():
    def alloc_id(self):
        while True:
            self._next_id += 1
            i = self._next_id
            if i not in self.acb_idx and i not in self.acr_idx and i not in self.where:
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

    Converter.alloc_id = alloc_id
    Converter.add_additional_world_data = add_additional_world_data


_add_world_data_methods()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("acr_forge")
    ap.add_argument("acb_multi_dir")
    ap.add_argument("out_forge")
    ap.add_argument("--slot", default="AC2MP_Alhambra")
    ap.add_argument("--work", default=None)
    ap.add_argument("--remap-acfe-templates", action="store_true",
                    help="also swap ACR shader templates shipped in the forge for same-named ACB ones")
    args = ap.parse_args()

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
    conv.encode_all(skip_types=("ContentPackage",) if args.slot else ())
    conv.substitute_opaque(files, args.acb_multi_dir)
    s_entries = conv.register_slot(files, args.acb_multi_dir, args.slot, work) if args.slot else []
    vendor_dependencies(files, args.acb_multi_dir, conv.acb_idx, r)

    out_dir = os.path.join(work, "out")
    shutil.rmtree(out_dir, ignore_errors=True)
    os.makedirs(out_dir)
    # MetaFile: it carries the package changelist (matches ContentPackage's
    # MinimumChangelistNumber), so take the slot's when we took its package
    src_dir = os.path.join(work, "slot" if args.slot else "src")
    for fn in os.listdir(src_dir):
        if fn.endswith(".MetaFile"):
            shutil.copy(os.path.join(src_dir, fn), os.path.join(out_dir, fn))
    for n, (fn, df) in enumerate(sorted(files.items(), key=lambda kv: kv[0])):
        base = fn[len("slot_"):] if fn.startswith("slot_") else fn
        base = base.split("_-_", 1)[1]
        if df.subs and ACB_T.name_of(df.subs[0][0]) == "World":
            base = df.subs[0][1] + ".data"
        open(os.path.join(out_dir, f"{n + 1}_-_{base}"), "wb").write(df.build(Game.BROTHERHOOD))
    repack(out_dir, args.out_forge, Game.BROTHERHOOD, original_entries=list(entries) + list(s_entries),
           align_entries=True)
    rep = r.text()
    open(args.out_forge + ".report.txt", "w").write(rep)
    print(rep)
    print(f"\nWrote {args.out_forge} ({os.path.getsize(args.out_forge) / 1e6:.1f} MB); work dir {work}")


if __name__ == "__main__":
    main()

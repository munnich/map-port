"""verify_base.py <map.forge> <skins_dir>: the non-DLC build is wired up -- the map's World has the LoadInfo id its file
name maps to (bootstrap_worlds.json) and no DLC registration left, and each patched skins forge has a holder for
that World whose mode-2/7 data entries exist in the same forge."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze import forge_items
from convert import ACB_T, u32, walk
from anvilforge.fastload import Codec

c = Codec(ACB_T)
mp, skins = sys.argv[1], sys.argv[2]
name = os.path.basename(mp)[len("DataPC_"):-len(".forge")]
wid = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "bootstrap_worlds.json")))[name]
bad = 0
types = {}
for e, subs, _d in forge_items(mp):
    for ext, n, uid, p in subs:
        t = ACB_T.name_of(ext) if ext != "ERR" else "ERR"
        types.setdefault(t, []).append((n, uid))
        if t == "World":
            w = c.decode(p).obj
            comps = [ACB_T.name_of(x.obj.type_hash) for x in w.fields["Components"] if getattr(x, "obj", None) is not None]
            print(f"World {n} {uid:#x} (want {wid:#x}) DLCWorldComponent={'DLCWorldComponent' in comps}")
            bad += uid != wid or "DLCWorldComponent" in comps
for t in ("ContentPackage", "MpWorld", "MpMapsDLCAddon", "SoundBankDLCAddon", "SoundPackagesDLCAddon"):
    if t in types:
        print("leftover", t, types[t][:3]); bad += 1
for f in sorted(os.listdir(skins)):
    if not f.endswith(".forge"):
        continue
    ids, holder = set(), None
    for e, subs, _d in forge_items(os.path.join(skins, f)):
        ids.add(e.id)
        for ext, n, uid, p in subs:
            if ext != "ERR" and ACB_T.name_of(ext) == "ContentPackage":
                for o in walk(c.decode(p).obj):
                    if ACB_T.name_of(o.type_hash) == "AdditionalWorldDataHolder" and u32(o.fields["AssociatedWorld"]) == wid:
                        holder = {u32(pm.fields["AssociatedGameModeID"]): u32(pm.fields["AdditionalWorldData"].id)
                                  for pm in o.fields["PerGameModeData"]}
    ok = holder is not None and all(holder.get(m) in ids for m in (2, 7))
    print(f, "holder", {m: hex(i) for m, i in (holder or {}).items()}, "mode 2/7 entries present" if ok else "BROKEN")
    bad += not ok
print("problems:", bad)
sys.exit(1 if bad else 0)

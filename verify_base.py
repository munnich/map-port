"""verify_base.py <map.forge> <skins_dir> [<menu_dir> [mapmanagermulti.xml]]: the non-DLC build is wired up -- the
map's World has the LoadInfo id its file name maps to (bootstrap_worlds.json) and no DLC registration left, each
patched skins forge has a holder for that World whose mode-2/7 data entries exist in the same forge, and (with
menu_dir) every skins forge has the name/description lines in every text package and skins_0001 the menu images, and the CXB XML's entry
for the World uses exactly those ids."""
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
if len(sys.argv) > 3:
    menu = json.load(open(os.path.join(sys.argv[3], "menu.json")))
    lines = set(menu["line_ids"])
    imgs = {v["id"] for v in menu["images"].values()}
    for f in sorted(x for x in os.listdir(skins) if x.endswith(".forge")):
        ids, pk = set(), []
        for e, subs, _d in forge_items(os.path.join(skins, f)):
            ids.add(e.id)
            for ext, n, uid, p in subs:
                if ext != "ERR" and ACB_T.name_of(ext) == "LocalizationPackage":
                    o = c.decode(p).obj
                    if u32(o.fields["Type"]) == 0:
                        pk.append((e.name, {u32(x.fields["TextID"]) for x in o.fields["LocalizedData"]}))
        miss = [n for n, got in pk if not lines <= got]
        # only the highest-priority collection is kept (CleanUpCollections), so every skins forge needs the lines
        print(f, f"lines in {len(pk) - len(miss)}/{len(pk)} text packages", end="")
        bad += len(miss) + (not pk)
        if "0001" in f:  # images are found by id from any source; they live in skins_0001
            print(", menu images", "present" if imgs <= ids else "MISSING", end="")
            bad += not imgs <= ids
        print()
    if len(sys.argv) > 4:
        import xml.etree.ElementTree as ET
        r = ET.parse(sys.argv[4]).getroot()
        for ref in r.iter("Reference"):
            um = ref.find("UnlockableMap")
            if um is None:
                continue
            mw = um.find(".//MpWorld")
            if int(mw.find("Handle[@propertyName='World']").get("objID")) != wid:
                continue
            used = {int(x.get("value")) for x in um.iter("OasisLineID")} - {-1}
            uimg = {int(mw.find(f"Handle[@propertyName='{k}']").get("objID")) for k in ("TopViewImg", "PreviewImg")}
            ok = used == lines and uimg == imgs
            print("XML entry", ref.get("objID"), "lines", sorted(used), "images", sorted(uimg), "OK" if ok else "MISMATCH")
            bad += not ok
            break
        else:
            print("XML: no UnlockableMap for", hex(wid)); bad += 1
print("problems:", bad)
sys.exit(1 if bad else 0)

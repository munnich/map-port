"""verify_maps.py [map ...]: the ported non-DLC maps (maps.json; default all built ones) are wired up end to end.

Per map: its forge is named after its LoadInfo slot and its World has that slot's id, with no DLC registration left
(ContentPackage / MpWorld / DLC addons / DLCWorldComponent). In out/maps/skins: each skins forge has a holder for the
World whose mode-2/7 world data entries exist in that forge; every name/description line is in every text package of
both forges (only the top-priority collection is read); every menu image is in skins_0001. In the server XML: one
UnlockableMap per variant with exactly the menu.json lines, images, World and visibility. Per map also: no MeshShape
keeps ACR's MOPP, no object is filtered only on layers ACB can't resolve (=> loaded in every mode)."""
import json, os, pickle, sys
import xml.etree.ElementTree as ET
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze import forge_items
from convert import ACB_T, HERE, u32, walk
from anvilforge.fastload import Codec

CFG = json.load(open(os.path.join(HERE, "maps.json")))
GLOBAL_LAYERS = {i for i, v in pickle.load(open(os.path.join(HERE, "acb_multi_idx.pkl"), "rb")).items()
                 if v.get("DataPC.forge", ("",))[0] == "DataLayer"}
SKINS = ("DataPC_skins_0001_00000002_dlc.forge", "DataPC_skins_0002_00000004_dlc.forge")
c = Codec(ACB_T)
bad = 0


def problem(msg):
    global bad
    bad += 1
    print("  PROBLEM:", msg)


keys = sys.argv[1:] or [k for k, m in CFG["maps"].items()
                        if os.path.exists(os.path.join(HERE, "out", "maps", k, f"DataPC_{m['slot'][:19]}.forge"))]
worlds = json.load(open(os.path.join(HERE, "bootstrap_worlds.json")))
menus, awds = {}, {}
for k in keys:
    m = CFG["maps"][k]
    d = os.path.join(HERE, "out", "maps", k)
    wid = worlds[m["slot"]]
    menus[k] = json.load(open(os.path.join(d, "menu", "menu.json")))
    awds[k] = json.load(open(os.path.join(d, f"DataPC_{m['slot'][:19]}.forge.awd", "awd.json")))
    types, w, mopp5, deadfilter = {}, None, 0, []
    for e, subs, _d in forge_items(os.path.join(d, f"DataPC_{m['slot'][:19]}.forge")):
        for ext, n, uid, p in subs:
            t = ACB_T.name_of(ext) if ext != "ERR" else "ERR"
            types[t] = types.get(t, 0) + 1
            if t == "World":
                w = (uid, [ACB_T.name_of(x.obj.type_hash) for x in c.decode(p).obj.fields["Components"]
                           if getattr(x, "obj", None) is not None])
            elif t == "MeshShape":  # 5 = "trust ACR's MOPP" -> collision holes (see convert.patch_fields)
                mopp5 += u32(c.decode(p).obj.fields["MoppCodeVersionNumber"]) == 5
            elif t in ("Entity", "EntityGroup"):  # a filter with no resolvable layer loads in every mode
                try:
                    root = c.decode(p).obj
                except Exception:
                    continue
                for o in walk(root):
                    dlf = o.fields.get("DataLayerFilter")
                    if dlf is not None and getattr(dlf, "fields", None) and dlf.fields["LayerActions"]:
                        layers = {u32(a.fields["Layer"].id) for a in dlf.fields["LayerActions"]}
                        if not layers & GLOBAL_LAYERS:
                            deadfilter.append(n)
    print(f"{k}: World {w[0]:#x} (slot {m['slot']} {wid:#x}), {types.get('MeshShape', 0)} MeshShapes")
    if mopp5:
        problem(f"{k}: {mopp5} MeshShapes keep ACR's MOPP (MoppCodeVersionNumber 5)")
    if deadfilter:
        problem(f"{k}: {len(deadfilter)} objects filtered only on layers ACB can't resolve (loaded in every mode): "
                f"{deadfilter[:5]}")
    if w[0] != wid or "DLCWorldComponent" in w[1]:
        problem(f"{k}: World id / DLCWorldComponent")
    for t in ("ContentPackage", "MpWorld", "MpMapsDLCAddon", "SoundBankDLCAddon", "SoundPackagesDLCAddon", "ERR"):
        if t in types:
            problem(f"{k}: leftover {t} x{types[t]}")

lines = {int(l) for mm in menus.values() for l in mm["strings"]}
imgs = {i["id"] for mm in menus.values() for i in mm["images"]}
for f in SKINS:
    ids, holders, pk = set(), {}, []
    for e, subs, _d in forge_items(os.path.join(HERE, "out", "maps", "skins", f)):
        ids.add(e.id)
        for ext, n, uid, p in subs:
            t = ACB_T.name_of(ext) if ext != "ERR" else "ERR"
            if t == "ContentPackage":
                for o in walk(c.decode(p).obj):
                    if ACB_T.name_of(o.type_hash) == "AdditionalWorldDataHolder":
                        holders[u32(o.fields["AssociatedWorld"])] = {u32(pm.fields["AssociatedGameModeID"]):
                            u32(pm.fields["AdditionalWorldData"].id) for pm in o.fields["PerGameModeData"]}
            elif t == "LocalizationPackage":
                o = c.decode(p).obj
                if u32(o.fields["Type"]) == 0:
                    pk.append((e.name, {u32(x.fields["TextID"]) for x in o.fields["LocalizedData"]}))
    miss = [n for n, got in pk if not lines <= got]
    print(f"{f}: {len(lines)} lines in {len(pk) - len(miss)}/{len(pk)} text packages", end="")
    if miss or not pk:
        problem(f"{f}: lines missing in {miss}")
    if "0001" in f:
        print(f", {len(imgs & ids)}/{len(imgs)} menu images", end="")
        if not imgs <= ids:
            problem(f"{f}: menu images missing")
    print()
    for k in keys:
        h = holders.get(awds[k]["world"])
        if h is None or any(h.get(int(mo)) != i or i not in ids for mo, i in awds[k]["modes"].items()):
            problem(f"{f}: {k} holder {h} / world data entries")

r = ET.parse(CFG["server_xml"]).getroot()
xml = {}
for ref in r.iter("Reference"):
    um = ref.find("UnlockableMap")
    if um is not None:
        xml[int(ref.get("objID"))] = um
conds = {int(h.get("objID")) for h in r.iter("Handle") if h.get("propertyName") == "UnlockableRef"}
for k in keys:
    for v in menus[k]["variants"]:
        um = xml.get(v["unlockable"])
        if um is None or v["unlockable"] not in conds:
            problem(f"XML: {k} {v['english']!r} entry / unlock condition missing"); continue
        mw = um.find(".//MpWorld")
        got = ({int(x.get("value")) for x in um.iter("OasisLineID")} - {-1},
               int(mw.find("Handle[@propertyName='World']").get("objID")),
               int(mw.find("Handle[@propertyName='TopViewImg']").get("objID")),
               int(mw.find("Handle[@propertyName='PreviewImg']").get("objID")),
               um.find("InitiallyHidden").get("value") == "true")
        want = ({v["name_line"], v["desc_line"]} - {-1}, menus[k]["world"], v["loading"], v["preview"], v["hidden"])
        print(f"XML {k:18} {v['english']:26} {'OK' if got == want else 'MISMATCH'}")
        if got != want:
            problem(f"XML {k}: {got} != {want}")
for f in ("Array_Size",):
    for tag in ("m_UnlockConditionList", "m_ReferenceList"):
        e = r.find(f".//{tag}")
        if int(e.get(f)) != len(e):
            problem(f"XML {tag} Array_Size {e.get(f)} != {len(e)}")
print("problems:", bad)
sys.exit(1 if bad else 0)

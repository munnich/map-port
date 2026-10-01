"""patch_skins.py [map ...]: everything the ported non-DLC maps (maps.json; default all) need in the skins DLC forges.
Input: the installed skins forges' unpatched originals (<forge>.pre_dyers, left by install_maps.sh; else the live
file) -- skins_0002 there may be a community edit. Output: out/maps/skins/; nothing is installed.

Chest Capture / Escort (convert.py --base -> out/maps/<key>/DataPC_<slot>.forge.awd): ACB looks per-map world data up
  only in OnlineMenuController's table (+0x5950), filled from the first loaded AdditionalWorldDataDLCElement -- the
  skins DLC packages (skins_0001: modes 2/7, skins_0002: modes 2/7/6). Which of the two loads first isn't fixed, so
  both get every map's AdditionalWorldData entries (dependency-free, like retail's) and a holder for its World: a copy
  of the donor map's holder with fresh ids, modes 2 and 7 pointed at our entries, mode 6 left on the donor's data.
Menu (menu_assets.py -> out/maps/<key>/menu): CharacterSkinsDLCElement::OnPackageLoaded makes each skins forge a
  LoadOnDemand source and registers its localization packages as a collection.
  - images (CXB PreviewImg / TopViewImg): skins_0001 only -- found by id from any source;
  - name/description lines, in the plain LocalizedData array of every text (Type 0) LocalizationPackage, which
    GetLocalizedStringRaw searches before the compressed blob -- in BOTH forges, per package language (English
    where ACR has no translation): LocalizationManager::CleanUpCollections keeps only the highest-priority collection
    (skins_0002: 14 > skins_0001: 12 > skins_0000: 11; each a full copy), so skins_0002's packages are the ones read."""
import argparse, copy, json, os, shutil, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from convert import ACB, ACB_T, HERE, Game, create_entry, idb, load_forge, name_hash, repack, u32, walk
from anvilforge.fastload import Codec, Obj

FORGES = ("DataPC_skins_0001_00000002_dlc.forge", "DataPC_skins_0002_00000004_dlc.forge")
MENU_FORGE = FORGES[0]
CFG = json.load(open(os.path.join(HERE, "maps.json")))


def map_dirs(key):
    m = CFG["maps"][key]
    d = os.path.join(HERE, "out", "maps", key)
    return os.path.join(d, f"DataPC_{m['slot'][:19]}.forge.awd"), os.path.join(d, "menu")


def add_world_data(files, acb, meta, holder_ids, tag):
    world, donor, modes = meta["world"], meta["donor_world"], {int(k): v for k, v in meta["modes"].items()}
    done = False
    for df in files.values():
        for sub in df.subs:
            if ACB_T.name_of(sub[0]) != "ContentPackage":
                continue
            root = acb.decode(sub[2])
            for o in walk(root.obj):
                if ACB_T.name_of(o.type_hash) != "AdditionalWorldDataDLCElement":
                    continue
                hs = o.fields["AdditionalWorldDataHolders"]
                if any(u32(h.fields["AssociatedWorld"]) == world for h in hs):
                    sys.exit(f"{tag}: already has a holder for {world:#x}")
                h = copy.deepcopy(next(h for h in hs if u32(h.fields["AssociatedWorld"]) == donor))
                h.id = idb(holder_ids[0])
                h.fields["AssociatedWorld"] = idb(world)
                got = []
                assert len(h.fields["PerGameModeData"]) <= len(holder_ids) - 1
                for pm, pid in zip(h.fields["PerGameModeData"], holder_ids[1:]):
                    pm.id = idb(pid)
                    m = u32(pm.fields["AssociatedGameModeID"])
                    if m in modes:
                        pm.fields["AdditionalWorldData"].id = idb(modes[m])
                    got.append(f"{m}:{u32(pm.fields['AdditionalWorldData'].id):#x}")
                o.fields["AdditionalWorldDataHolders"] = hs + [h]
                print(f"  holder {holder_ids[0]:#x} for world {world:#x}: modes {', '.join(got)}")
                done = True
            sub[2] = acb.encode(root)
            df.dirty = True
    if not done:
        sys.exit(f"{tag}: no AdditionalWorldDataDLCElement")


def add_strings(files, acb, strings):
    """strings: {line: {language: text}} (language 1 = English, the fallback)."""
    H = name_hash(ACB, "LocalizedString")
    n = 0
    for df in files.values():
        for sub in df.subs:
            if ACB_T.name_of(sub[0]) != "LocalizationPackage":
                continue
            root = acb.decode(sub[2])
            if u32(root.obj.fields["Type"]) != 0:  # 1 subtitles, 2 e-manual
                continue
            lang = str(u32(root.obj.fields["Language"]))
            have = {u32(s.fields["TextID"]): s for s in root.obj.fields["LocalizedData"]}
            for line, texts in strings.items():
                t = texts.get(lang) or texts["1"]
                have[int(line)] = Obj(H, bytes(4), {"TextID": idb(int(line)), "Text": t.encode("utf-16-le")})
            root.obj.fields["LocalizedData"] = [have[i] for i in sorted(have)]  # binary-searched
            sub[2] = acb.encode(root)
            df.dirty = True
            n += 1
    print(f"  {len(strings)} lines added to {n} text localization packages")


def add_entries(work, entries, items, tag):
    known = {e.id for e in entries}
    n = len(entries)
    added = []
    for src, uid in items:
        if uid in known:
            sys.exit(f"{tag}: already has entry {uid:#x}")
        dst = os.path.join(work, f"{n}_-_{os.path.splitext(os.path.basename(src))[0].split('_-_')[-1]}.data")
        n += 1
        shutil.copy(src, dst)
        e = create_entry(dst, 0, Game.BROTHERHOOD)
        e.extension = 0  # as convert.py does for added entries
        added.append(e)
        known.add(uid)
    print(f"  {len(added)} entries added")
    return added


def patch(src, out_dir, work, tag, awds, fi, strings, images):
    acb = Codec(ACB_T)
    shutil.rmtree(work, ignore_errors=True)
    entries, files = load_forge(src, work, Game.BROTHERHOOD)
    for key, (awd, _d) in awds.items():
        add_world_data(files, acb, awd, awd["holder_ids"][fi], f"{tag} {key}")
    if strings:
        add_strings(files, acb, strings)
    for fn, df in files.items():
        if getattr(df, "dirty", False):
            open(os.path.join(work, fn), "wb").write(df.build(Game.BROTHERHOOD))
    items = [(os.path.join(d, fn), uid) for awd, d in awds.values() for fn, uid in sorted(awd["entries"].items())]
    items += images
    added = add_entries(work, entries, items, tag)
    out = os.path.join(out_dir, tag)
    repack(work, out, Game.BROTHERHOOD, original_entries=list(entries) + added, align_entries=True)
    print(f"  wrote {out} ({os.path.getsize(out) / 1e6:.1f} MB)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("maps", nargs="*", help="map keys from maps.json (default: all)")
    ap.add_argument("--out", default=os.path.join(HERE, "out", "maps", "skins"))
    ap.add_argument("--work", default=None)
    ap.add_argument("--menu-parts", default="strings,images", help="which menu assets to add (for A/B tests)")
    args = ap.parse_args()
    keys = args.maps or list(CFG["maps"])
    parts = args.menu_parts.split(",")
    work = args.work or os.path.join(args.out, "_work")
    awds, strings, images = {}, {}, []
    for k in keys:
        awd_dir, menu_dir = map_dirs(k)
        awds[k] = (json.load(open(os.path.join(awd_dir, "awd.json"))), awd_dir)
        menu = json.load(open(os.path.join(menu_dir, "menu.json")))
        if "strings" in parts:
            strings.update(menu["strings"])
        if "images" in parts:
            images += [(os.path.join(menu_dir, i["entry"]), i["id"]) for i in menu["images"]]
    os.makedirs(args.out, exist_ok=True)
    for fi, forge in enumerate(FORGES):
        src = os.path.join(CFG["acb_installed"], forge)
        if os.path.exists(src + ".pre_dyers"):  # install_maps.sh keeps the unpatched original there
            src += ".pre_dyers"
        print(forge, "<-", os.path.basename(src), f"({len(keys)} maps)")
        patch(src, args.out, os.path.join(work, forge), forge, awds, fi, strings,
              images if forge == MENU_FORGE else [])
    shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()

"""patch_skins.py <multi_dir> <out_dir> --awd <out_forge>.awd [--menu <menu_dir>]: what a non-DLC ported map needs
in the skins DLC forges. Reads the forges from <multi_dir> (use the installed copies -- skins_0002 there may be a
community edit; a <forge>.pre_dyers left by base_test.sh install is preferred) and writes the patched ones to <out_dir>; nothing is installed.

--awd (Chest Capture / Escort, convert.py --base output): ACB looks per-map world data up only in
  OnlineMenuController's table (+0x5950), filled from the first loaded AdditionalWorldDataDLCElement -- the skins DLC
  packages (skins_0001: modes 2/7, skins_0002: modes 2/7/6). Which of the two loads first isn't fixed, so both get:
  - the map's AdditionalWorldData entries, as dependency-free entries like retail keeps every map's;
  - a holder for the map's World appended to the element: a copy of the donor map's holder with fresh ids, modes 2
    (Chest Capture) and 7 (Escort) pointed at our entries, other modes (6, Assassinate) left on the donor's data.
--menu (menu_assets.py output) -- CharacterSkinsDLCElement::OnPackageLoaded makes each skins forge a LoadOnDemand
  source and adds its localization packages as a collection:
  - the map's menu image entries (PreviewImg / TopViewImg of the CXB MpWorld), skins_0001 only (found by id from any
    source);
  - its name/description lines, in the plain LocalizedData array of every text (Type 0) LocalizationPackage, which
    GetLocalizedStringRaw searches before the compressed blob -- in BOTH forges: LocalizationManager::CleanUpCollections
    keeps only the highest-priority collection (skins_0002: 14 > skins_0001: 12 > skins_0000: 11; each is a full
    copy), so lines only in skins_0001 are never read while skins_0002 is installed."""
import argparse, copy, json, os, shutil, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from convert import ACB, ACB_T, Game, create_entry, idb, load_forge, name_hash, repack, u32, walk
from anvilforge.fastload import Codec, Obj

FORGES = ("DataPC_skins_0001_00000002_dlc.forge", "DataPC_skins_0002_00000004_dlc.forge")
MENU_FORGE = FORGES[0]


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
                print(f"  holder {holder_ids[0]:#x} for world {world:#x} (copy of {donor:#x}'s): modes {', '.join(got)}")
                done = True
            sub[2] = acb.encode(root)
            df.dirty = True
    if not done:
        sys.exit(f"{tag}: no AdditionalWorldDataDLCElement")


def add_strings(files, acb, menu):
    H = name_hash(ACB, "LocalizedString")
    texts = dict(zip(menu["line_ids"], (menu["name"], menu["description"])))
    n = 0
    for df in files.values():
        for sub in df.subs:
            if ACB_T.name_of(sub[0]) != "LocalizationPackage":
                continue
            root = acb.decode(sub[2])
            if u32(root.obj.fields["Type"]) != 0:  # 1 subtitles, 2 e-manual
                continue
            have = {u32(s.fields["TextID"]): s for s in root.obj.fields["LocalizedData"]}
            for i, t in texts.items():
                have[i] = Obj(H, bytes(4), {"TextID": idb(i), "Text": t.encode("utf-16-le")})
            root.obj.fields["LocalizedData"] = [have[i] for i in sorted(have)]  # binary-searched
            sub[2] = acb.encode(root)
            df.dirty = True
            n += 1
    print(f"  {len(texts)} lines added to {n} text localization packages: {texts}")


def add_entries(work, entries, src_dir, names_ids, tag):
    known = {e.id for e in entries}
    n = len(entries)
    added = []
    for fn, uid in names_ids:
        if uid in known:
            sys.exit(f"{tag}: already has entry {uid:#x}")
        dst = os.path.join(work, f"{n}_-_{os.path.splitext(fn)[0].split('_-_')[-1]}.data")
        n += 1
        shutil.copy(os.path.join(src_dir, fn), dst)
        e = create_entry(dst, 0, Game.BROTHERHOOD)
        e.extension = 0  # as convert.py does for added entries
        added.append(e)
        print(f"  entry {uid:#x} ({fn})")
    return added


def patch(forge, out_dir, work, awd, awd_dir, holder_ids, menu, menu_dir, parts=("strings", "images"), strings_menu=None):
    acb = Codec(ACB_T)
    tag = os.path.basename(forge).replace(".pre_dyers", "")
    shutil.rmtree(work, ignore_errors=True)
    entries, files = load_forge(forge, work, Game.BROTHERHOOD)
    added = []
    if awd:
        add_world_data(files, acb, awd, holder_ids, tag)
    if strings_menu and "strings" in parts:
        add_strings(files, acb, strings_menu)
    for fn, df in files.items():
        if getattr(df, "dirty", False):
            open(os.path.join(work, fn), "wb").write(df.build(Game.BROTHERHOOD))
    if awd:
        added += add_entries(work, entries + added, awd_dir, sorted(awd["entries"].items()), tag)
    if menu and "images" in parts:
        added += add_entries(work, entries + added, menu_dir, [(v["entry"], v["id"]) for v in menu["images"].values()], tag)
    out = os.path.join(out_dir, tag)
    repack(work, out, Game.BROTHERHOOD, original_entries=list(entries) + added, align_entries=True)
    print(f"  wrote {out} ({os.path.getsize(out) / 1e6:.1f} MB)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("multi_dir")
    ap.add_argument("out_dir")
    ap.add_argument("--awd", required=True, help="<out_forge>.awd from convert.py --base")
    ap.add_argument("--menu", help="menu_assets.py output dir")
    ap.add_argument("--menu-parts", default="strings,images", help="which menu assets to add (for A/B tests)")
    ap.add_argument("--work", default=None)
    args = ap.parse_args()
    work = args.work or os.path.join(args.out_dir, "_work")
    awd = json.load(open(os.path.join(args.awd, "awd.json")))
    menu = json.load(open(os.path.join(args.menu, "menu.json"))) if args.menu else None
    os.makedirs(args.out_dir, exist_ok=True)
    for forge, hids in zip(FORGES, awd["holder_ids"]):
        src = os.path.join(args.multi_dir, forge)
        if os.path.exists(src + ".pre_dyers"):  # base_test.sh install keeps the unpatched original there
            src += ".pre_dyers"
        print(forge, "<-", os.path.basename(src))
        patch(src, args.out_dir, os.path.join(work, forge), awd, args.awd, hids,
              menu if forge == MENU_FORGE else None, args.menu, args.menu_parts.split(","), strings_menu=menu)
    shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()

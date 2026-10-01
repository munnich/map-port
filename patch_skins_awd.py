"""patch_skins_awd.py <out_forge>.awd <multi_dir> <out_dir>: give a non-DLC ported map Chest Capture / Escort data.

ACB looks per-map world data up only in OnlineMenuController's table (+0x5950), filled from the first loaded
AdditionalWorldDataDLCElement -- the skins DLC packages (skins_0001: modes 2/7, skins_0002: modes 2/7/6). Which of
the two loads first isn't fixed, so both get the same treatment:
  - the map's AdditionalWorldData entries (built by convert.py --base into <out_forge>.awd/) are added as
    dependency-free entries, like retail keeps every map's;
  - a holder for the map's World is appended to the element: a copy of the donor map's holder with fresh ids,
    modes 2 (Chest Capture) and 7 (Escort) pointed at our entries, other modes (6, Assassinate) left on the
    donor's data.
Reads the forges from <multi_dir> (use the installed copies -- skins_0002 there may be a community edit) and writes
the patched ones to <out_dir>; nothing is installed."""
import copy, json, os, shutil, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from convert import ACB_T, DataFile, Game, idb, load_forge, u32, walk, create_entry, repack

FORGES = ("DataPC_skins_0001_00000002_dlc.forge", "DataPC_skins_0002_00000004_dlc.forge")


def patch(forge, awd_dir, meta, holder_ids, out_dir, work):
    from anvilforge.fastload import Codec
    acb = Codec(ACB_T)
    shutil.rmtree(work, ignore_errors=True)
    entries, files = load_forge(forge, work, Game.BROTHERHOOD)
    world, donor, modes = meta["world"], meta["donor_world"], {int(k): v for k, v in meta["modes"].items()}
    done = False
    for fn, df in files.items():
        for sub in df.subs:
            if ACB_T.name_of(sub[0]) != "ContentPackage":
                continue
            root = acb.decode(sub[2])
            for o in walk(root.obj):
                if ACB_T.name_of(o.type_hash) != "AdditionalWorldDataDLCElement":
                    continue
                hs = o.fields["AdditionalWorldDataHolders"]
                if any(u32(h.fields["AssociatedWorld"]) == world for h in hs):
                    sys.exit(f"{os.path.basename(forge)}: already has a holder for {world:#x}")
                dh = next(h for h in hs if u32(h.fields["AssociatedWorld"]) == donor)
                h = copy.deepcopy(dh)
                h.id = idb(holder_ids[0])
                h.fields["AssociatedWorld"] = idb(world)
                got = []
                for pm, pid in zip(h.fields["PerGameModeData"], holder_ids[1:]):
                    pm.id = idb(pid)
                    m = u32(pm.fields["AssociatedGameModeID"])
                    if m in modes:
                        pm.fields["AdditionalWorldData"].id = idb(modes[m])
                    got.append(f"{m}:{u32(pm.fields['AdditionalWorldData'].id):#x}")
                assert len(h.fields["PerGameModeData"]) <= len(holder_ids) - 1
                o.fields["AdditionalWorldDataHolders"] = hs + [h]
                print(f"  holder {holder_ids[0]:#x} for world {world:#x} (copy of {donor:#x}'s): modes {', '.join(got)}")
                done = True
            sub[2] = acb.encode(root)
            open(os.path.join(work, fn), "wb").write(df.build(Game.BROTHERHOOD))
    if not done:
        sys.exit(f"{os.path.basename(forge)}: no AdditionalWorldDataDLCElement")
    known = {e.id for e in entries}
    n = len(entries)
    added = []
    for fn, uid in meta["entries"].items():
        if uid in known:
            sys.exit(f"{os.path.basename(forge)}: already has entry {uid:#x}")
        dst = os.path.join(work, f"{n}_-_{uid:016X}.data")
        n += 1
        shutil.copy(os.path.join(awd_dir, fn), dst)
        e = create_entry(dst, 0, Game.BROTHERHOOD)
        e.extension = 0  # as the converter does for added entries
        added.append(e)
        print(f"  entry {uid:#x} ({fn})")
    out = os.path.join(out_dir, os.path.basename(forge))
    repack(work, out, Game.BROTHERHOOD, original_entries=list(entries) + added, align_entries=True)
    print(f"  wrote {out} ({os.path.getsize(out) / 1e6:.1f} MB)")


def main():
    awd_dir, multi, out_dir = sys.argv[1:4]
    work = sys.argv[4] if len(sys.argv) > 4 else os.path.join(out_dir, "_work")
    meta = json.load(open(os.path.join(awd_dir, "awd.json")))
    os.makedirs(out_dir, exist_ok=True)
    for forge, hids in zip(FORGES, meta["holder_ids"]):
        print(forge)
        patch(os.path.join(multi, forge), awd_dir, meta, hids, out_dir, os.path.join(work, forge))
    shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()

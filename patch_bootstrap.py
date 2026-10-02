"""patch_bootstrap.py [--out DIR]: rename the LoadInfo worlds the ported maps took over (maps.json "slot") to their
own names (maps.json "name", e.g. ACFE_Souk), so each map ships as multi/DataPC_<name>.forge.

ACB finds a non-DLC map's forge via World::GetWorldAlternateSourcePrefixName -> GameBootstrap::GetObjectName: the
LoadInfo FileName of the World's id ("Game Bootstrap Settings" in DataPC.forge), copied into char[20] -> at most 19
chars. Only FileName changes; the id stays the slot world's. Input: the installed DataPC.forge's unpatched original
(DataPC.forge.pre_acfe, left by install_maps.sh; else the live file). Output: out/maps/DataPC.forge."""
import argparse, json, os, shutil, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from convert import ACB_T, HERE, Game, load_forge, repack, u32
from anvilforge.fastload import Codec

CFG = json.load(open(os.path.join(HERE, "maps.json")))
FORGE = "DataPC.forge"
SAVE = ".pre_acfe"


def map_name(m):
    """The name a ported map's forge goes by: DataPC_<map_name(m)>.forge."""
    return m.get("name", m["slot"])[:19]


def load_info(files, acb):
    for fn, df in files.items():
        for sub in df.subs:
            if sub[1] == "Game Bootstrap Settings" and ACB_T.name_of(sub[0]) == "GameBootstrap":
                return df, sub, acb.decode(sub[2])
    sys.exit("no Game Bootstrap Settings")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "out", "maps"))
    ap.add_argument("--work", default=None)
    args = ap.parse_args()
    renames = {m["slot"]: map_name(m) for m in CFG["maps"].values() if map_name(m) != m["slot"]}
    if len(set(renames.values())) != len(renames) or any(len(m.get("name", "")) > 19 for m in CFG["maps"].values()):
        sys.exit("map names must be unique and at most 19 chars")
    src = os.path.join(CFG["acb_installed"], FORGE)
    if os.path.exists(src + SAVE):
        src += SAVE
    work = args.work or os.path.join(args.out, "_work_datapc")
    shutil.rmtree(work, ignore_errors=True)
    acb = Codec(ACB_T)
    print(FORGE, "<-", src)
    entries, files = load_forge(src, work, Game.BROTHERHOOD)
    df, sub, root = load_info(files, acb)
    li = root.obj.fields["LoadInfo"]
    before = [(x.fields["FileName"], u32(x.fields["ObjectID"]), u32(x.fields["FileClassID"])) for x in li]
    names = {x.fields["FileName"].decode() for x in li}
    clash = set(renames.values()) & names
    if clash:
        sys.exit(f"names already in LoadInfo: {clash}")
    done = set()
    for x in li:
        n = x.fields["FileName"].decode()
        if n in renames and ACB_T.name_of(u32(x.fields["FileClassID"])) == "World":
            x.fields["FileName"] = renames[n].encode()
            done.add(n)
            print(f"  {n} ({u32(x.fields['ObjectID']):#x}) -> {renames[n]}")
    if done != set(renames):
        sys.exit(f"slots not in LoadInfo: {set(renames) - done}")
    sub[2] = acb.encode(root)
    df.dirty = True
    fn = next(k for k, v in files.items() if v is df)
    open(os.path.join(work, fn), "wb").write(df.build(Game.BROTHERHOOD))
    os.makedirs(args.out, exist_ok=True)
    out = os.path.join(args.out, FORGE)
    repack(work, out, Game.BROTHERHOOD, original_entries=list(entries), align_entries=True)
    print(f"  wrote {out} ({os.path.getsize(out) / 1e6:.1f} MB)")

    # read it back: LoadInfo identical except the renamed FileNames
    e2, f2 = load_forge(out, work + "_check", Game.BROTHERHOOD)
    after = [(x.fields["FileName"], u32(x.fields["ObjectID"]), u32(x.fields["FileClassID"]))
             for x in load_info(f2, acb)[2].obj.fields["LoadInfo"]]
    want = [((renames.get(n.decode(), n.decode())).encode(), i, c) for n, i, c in before]
    if after != want or len(e2) != len(entries):
        sys.exit("read-back check FAILED")
    print(f"  read back OK: {len(e2)} entries, {len(after)} LoadInfo rows, {len(renames)} renamed")
    shutil.rmtree(work, ignore_errors=True)
    shutil.rmtree(work + "_check", ignore_errors=True)


if __name__ == "__main__":
    main()

"""build_maps.py [map ...] [--rebuild] [--no-xml]: port ACR maps to ACB as separate non-DLC maps, end to end.

Config: maps.json (one entry per ACR map: source forge, LoadInfo slot, menu variants). Steps:
  1. convert.py --base <slot> for each requested map (skipped if out/maps/<key>/DataPC_<slot>.forge exists, unless
     --rebuild), then the per-forge checks (aligncheck, depcheck, blockcheck, validate, spawncheck);
  2. menu_assets.py: menu images + ACR name lines (all languages) per map;
  3. patch_skins.py: world data, lines and images of EVERY built map into the skins forges (out/maps/skins) --
     always all of them, since the installed skins forges must carry every installed map;
  4. cxb_maps.py: the menu entries of every built map into the server's mapmanagermulti.xml (rebuild the CXB from
     it with CXBTool afterwards);
  5. verify_maps.py.
Then ./install_maps.sh install."""
import argparse, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "maps.json")))


def run(cmd, log=None):
    print("$", " ".join(cmd[:6]) + (" ..." if len(cmd) > 6 else ""), flush=True)
    if log:
        with open(log, "w") as f:
            r = subprocess.run(cmd, cwd=HERE, stdout=f, stderr=subprocess.STDOUT)
    else:
        r = subprocess.run(cmd, cwd=HERE)
    if r.returncode:
        sys.exit(f"failed ({r.returncode}): {' '.join(cmd)}" + (f" -- see {log}" if log else ""))


def forge_path(key):
    return os.path.join(HERE, "out", "maps", key, f"DataPC_{CFG['maps'][key]['slot'][:19]}.forge")


def checks(key):
    f = forge_path(key)
    log = os.path.join(os.path.dirname(f), "checks.txt")
    out = []
    for script in ("aligncheck.py", "depcheck.py", "blockcheck.py", "validate.py", "spawncheck.py"):
        r = subprocess.run([sys.executable, script, f], cwd=HERE, capture_output=True, text=True)
        out.append(f"### {script} (exit {r.returncode})\n{r.stdout}{r.stderr}")
    open(log, "w").write("\n".join(out))
    text = "\n".join(out)
    summary = [l.strip() for l in text.splitlines() if l.startswith(("problems:", "entries ", "{'own entry'")) or "straddle [" in l and "0x8000:" in l]
    sp = {}
    for l in text.splitlines():  # spawncheck rows: (where, 'spawn type N', 'active') count
        if "'spawn type " in l and "'active'" in l and ("'grid" in l or "'layer:gamemode" in l):
            t = l.split("'spawn type ")[1][0]
            sp[t] = sp.get(t, 0) + int(l.split()[-1])
    summary.append("active spawns ffa/team/chest " + "/".join(str(sp.get(t, 0)) for t in "023"))
    blog = os.path.join(os.path.dirname(f), "build.log")
    if os.path.exists(blog):
        b = open(blog).read()
        summary.append(f"unsafe-ACR {b.count('UNSAFE')}, encode-fail {b.count('ENCODE-FAIL')}, "
                       f"dropped {b.count('dropped unreferenced') + b.count('unhooked + dropped')}")
    print(f"  {key}: " + " | ".join(summary), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("maps", nargs="*", help="map keys from maps.json (default: all)")
    ap.add_argument("--rebuild", action="store_true", help="re-convert even if the map forge exists")
    ap.add_argument("--no-xml", action="store_true", help="don't touch the server's mapmanagermulti.xml")
    args = ap.parse_args()
    keys = args.maps or sorted(CFG["maps"], key=lambda k: CFG["maps"][k]["index"])
    for k in keys:
        m = CFG["maps"][k]
        if args.rebuild or not os.path.exists(forge_path(k)):
            os.makedirs(os.path.dirname(forge_path(k)), exist_ok=True)
            cmd = [sys.executable, "convert.py", os.path.join(CFG["acr_multi"], m["acr_forge"]), CFG["acb_retail"],
                   forge_path(k), "--base", m["slot"], "--donor", m.get("donor", CFG["donor"]),
                   "--work", os.path.join(HERE, "out", "maps", k, "_work")]
            if m.get("remap_templates", True):
                cmd.append("--remap-acfe-templates")
            run(cmd, os.path.join(HERE, "out", "maps", k, "build.log"))
            subprocess.run(["rm", "-rf", os.path.join(HERE, "out", "maps", k, "_work")])
        checks(k)
    run([sys.executable, "menu_assets.py", *keys])
    built = [k for k in sorted(CFG["maps"], key=lambda k: CFG["maps"][k]["index"]) if os.path.exists(forge_path(k))
             and os.path.exists(os.path.join(HERE, "out", "maps", k, "menu", "menu.json"))]
    run([sys.executable, "patch_skins.py", *built])
    if not args.no_xml:
        run([sys.executable, "cxb_maps.py", *built])
    run([sys.executable, "verify_maps.py", *built])
    print(f"\nbuilt: {', '.join(built)}\nnext: ./install_maps.sh install; rebuild the CXB from {CFG['server_xml']}")


if __name__ == "__main__":
    main()

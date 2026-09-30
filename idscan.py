import sys, os, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze import ACR, forge_items
targets = {int(x, 16): x for x in sys.argv[2].split(",")}
pats = {struct.pack("<I", k): v for k, v in targets.items()}
for path in sys.argv[3:]:
    for e, subs, deps in forge_items(path):
        for ext, name, uid, p in subs:
            for pat, lab in pats.items():
                if pat in p:
                    print(f"{os.path.basename(path)}: {lab} in {ACR.name_of(ext) if ext!='ERR' else ext} '{name}' uid={uid:#x} entry={e.name} count={p.count(pat)}")

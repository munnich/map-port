"""idgrep.py <id-hex>[,<id-hex>...] <forge>...: list objects (decompressed) whose payload contains the 4-byte id."""
import sys, os, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze import forge_items, ACB
ids = {int(x, 16): struct.pack("<I", int(x, 16)) for x in sys.argv[1].split(",")}
for p in sys.argv[2:]:
    for e, subs, deps in forge_items(p):
        for i, d in ids.items():
            if i in deps: print(f"{os.path.basename(p)}: entry {e.name} DEPENDS on {i:#x}")
        for ext, name, uid, payload in subs:
            for i, b in ids.items():
                if b in payload[4:] or (uid != i and b in payload):
                    print(f"{os.path.basename(p)}: {e.name} / {ACB.name_of(ext) if ext != 'ERR' else 'ERR'} {name} ({uid:#x}) refs {i:#x} at {payload.find(b)}")

import sys, os
sys.path.insert(0, os.path.expanduser("~/Coding/Python/anvilforge-py-acrport/src"))
from analyze import ACB, ACR, forge_items
from anvilforge.objectxml import decode_object
import xml.etree.ElementTree as ET
path, sch, types = sys.argv[1], sys.argv[2], sys.argv[3].split(",")
S = ACR if sch == "acr" else ACB
for e, subs, deps in forge_items(path):
    for ext, name, uid, payload in subs:
        if ext != "ERR" and S.name_of(ext) in types:
            root = decode_object(payload, S, True)
            for rt in root.iter("RawTail"): rt.text = rt.text[:60] + "..."
            ET.indent(root)
            print(f"=== entry {e.name} / {name} uid={uid:#x}\n" + ET.tostring(root, encoding="unicode")[:4000])

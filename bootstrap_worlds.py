"""bootstrap_worlds.py <DataPC.forge> [out.json]: World name -> id from GameBootstrap.LoadInfo.

A non-DLC map's World is loaded from multi/DataPC_<name>.forge, <name> being its LoadInfo FileName
(World::GetWorldAlternateSourcePrefixName -> GameBootstrap::GetObjectName, truncated to 19 chars)."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze import forge_items
from convert import ACB_T, u32
from anvilforge.fastload import Codec

c = Codec(ACB_T)
for e, subs, _d in forge_items(sys.argv[1]):
    for ext, name, uid, p in subs:
        if name == "Game Bootstrap Settings" and ACB_T.name_of(ext) == "GameBootstrap":
            li = c.decode(p).obj.fields["LoadInfo"]
            out = {x.fields["FileName"].decode(): u32(x.fields["ObjectID"]) for x in li
                   if ACB_T.name_of(u32(x.fields["FileClassID"])) == "World"}
            json.dump(out, open(sys.argv[2] if len(sys.argv) > 2 else "bootstrap_worlds.json", "w"), indent=1)
            print(len(out), "worlds")
            raise SystemExit

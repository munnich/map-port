"""roundtrip.py <forge> <out_forge> [work]: control build -- push an untouched retail forge through convert.py's
writer path (unpack -> DataFile parse -> DataFile.build (recompress) -> repack(align_entries)). If this loads in-game
and a converted map doesn't, the writer is fine and the problem is content."""
import os, shutil, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from convert import load_forge, retail_order
from anvilforge.forge import repack
from anvilforge.games import Game

src, out = sys.argv[1], sys.argv[2]
work = sys.argv[3] if len(sys.argv) > 3 else tempfile.mkdtemp(prefix="roundtrip_")
entries, files = load_forge(src, os.path.join(work, "src"), Game.BROTHERHOOD)
out_dir = os.path.join(work, "out")
shutil.rmtree(out_dir, ignore_errors=True); os.makedirs(out_dir)
for fn in os.listdir(os.path.join(work, "src")):
    if fn.endswith(".MetaFile"):
        shutil.copy(os.path.join(work, "src", fn), os.path.join(out_dir, fn))
for n, (fn, df) in enumerate(sorted(files.items(), key=lambda kv: retail_order(kv[0]))):
    open(os.path.join(out_dir, f"{n + 1}_-_{fn.split('_-_', 1)[1]}"), "wb").write(df.build(Game.BROTHERHOOD))
os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
repack(out_dir, out, Game.BROTHERHOOD, original_entries=list(entries), align_entries=True)
print(f"wrote {out} ({os.path.getsize(out) / 1e6:.1f} MB) from {len(files)} data entries")

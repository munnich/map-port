"""aligncheck.py <forge>...: does any entry's FILEDATA header + dependency table straddle an aligned chunk boundary?
ACB's BigFileAsynchStream::HandleChunkPrefetches reads the dep table in-place from the streamed chunk buffer."""
import sys, os, collections
sys.path.insert(0, os.path.expanduser("~/Coding/Python/anvilforge-py-acrport/src"))
from anvilforge.forge import read_header
from anvilforge.fileset import iter_fileset_entries

def spans(path):
    out = []
    with open(path, "rb") as f:
        for s in range(read_header(f, 25)):
            for e in list(iter_fileset_entries(f, s, True)):
                f.seek(e.offset + 0x1b8); n = int.from_bytes(f.read(4), "little")
                out.append((e.offset, 0x1b8 + 4 + 8 * n, e.length_on_disk, e.name))
    return out

for path in sys.argv[1:]:
    sp = spans(path)
    print(f"## {os.path.basename(path)}: {len(sp)} entries")
    print("   offset mod 16:", collections.Counter(o % 16 for o, *_ in sp).most_common(4))
    for chunk in (0x8000, 0x10000, 0x20000, 0x40000, 0x80000):
        st = [(o, l, n) for o, l, _, n in sp if o // chunk != (o + l - 1) // chunk]
        print(f"   chunk {chunk:#8x}: {len(st)} headers straddle", [f"{n}@{o:#x}+{l:#x}" for o, l, n in st[:4]])

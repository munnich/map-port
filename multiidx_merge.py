"""multiidx_merge.py <dir-of-per-forge-pkls> <out.pkl>: id -> {forge name: (type, name, entry id)}."""
import glob, os, pickle, sys
out = {}
for p in sorted(glob.glob(os.path.join(sys.argv[1], "*.pkl"))):
    fg = os.path.basename(p)[:-4] + ".forge"
    for i, v in pickle.load(open(p, "rb")).items():
        out.setdefault(i, {})[fg] = v
pickle.dump(out, open(sys.argv[2], "wb"))
print(len(out), "ids")

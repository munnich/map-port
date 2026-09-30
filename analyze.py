"""Inventory a forge: entry/subpart types, ACB-vs-ACR schema compatibility, deps."""
import collections, io, json, os, sys
sys.path.insert(0, os.path.expanduser("~/Coding/Python/anvilforge-py-acrport/src"))
from anvilforge.games import Game
from anvilforge.schema import Schema
from anvilforge.datafile import iter_datafile_subparts, derive_uid_and_ext, _read_inline_dependencies
from anvilforge.fileset import iter_fileset_entries, read_entry_payload
from anvilforge.forge import read_header

ACB = Schema.load_default(Game.BROTHERHOOD)
ACR = Schema.load_default(Game.REVELATIONS)


def forge_items(path):
    """yield (entry, [(ext, name, uid, payload)], deps) without touching disk."""
    with open(path, "rb") as f:
        n = read_header(f, 25)
        for s in range(n):
            ents = list(iter_fileset_entries(f, s, True))
            for e in ents:
                raw = read_entry_payload(f, e, True)
                subs, deps = [], []
                try:
                    bf = io.BytesIO(raw)
                    for _i, ext, name, payload in iter_datafile_subparts(bf, Game.REVELATIONS):
                        uid, _ = derive_uid_and_ext(payload, True)
                        subs.append((ext, name, uid, payload))
                    bf.seek(0)
                    d, _ = _read_inline_dependencies(bf, Game.REVELATIONS)
                    deps = [x.id for x in d]
                except Exception as ex:  # noqa
                    subs.append(("ERR", str(ex), 0, b""))
                yield e, subs, deps


def sig(schema, h):
    t = schema.type_by_hash(h)
    if t is None:
        return None
    return [(p.name_hash, p.packed_type, p.flags) for p in schema.property_chain(h)]


if __name__ == "__main__":
    path = sys.argv[1]
    out = sys.argv[2]
    types = collections.Counter()
    top_types = collections.Counter()
    ids, deps_all = set(), collections.Counter()
    entries = []
    for e, subs, deps in forge_items(path):
        ids.add(e.id)
        top_types[ACR.name_of(e.extension)] += 1
        for ext, name, uid, _ in subs:
            if ext == "ERR":
                types["<ERR>"] += 1
                continue
            types[ext] += 1
            ids.add(uid)
        for d in deps:
            deps_all[d] += 1
        entries.append(dict(id=e.id, name=e.name, ext=ACR.name_of(e.extension),
                            subs=[(ACR.name_of(x[0]) if x[0] != "ERR" else "ERR", x[1], x[2]) for x in subs],
                            deps=deps))
    ext_deps = sorted(set(deps_all) - ids)
    compat = {}
    for h, c in types.items():
        if h == "<ERR>":
            continue
        a, r = sig(ACB, h), sig(ACR, h)
        status = "missing_in_acb" if a is None else ("same" if a == r else "differs")
        compat[ACR.name_of(h)] = dict(count=c, status=status, hash=h)
    json.dump(dict(top_types=top_types, compat=compat, errors=types.get("<ERR>", 0),
                   n_ids=len(ids), ext_deps=ext_deps, entries=entries),
              open(out, "w"), indent=1, default=str)
    print("entries", len(entries), "internal ids", len(ids), "external deps", len(ext_deps), "errors", types.get("<ERR>", 0))
    print("top-level entry types:", top_types.most_common(40))
    for st in ("missing_in_acb", "differs", "same"):
        rows = sorted(((k, v["count"]) for k, v in compat.items() if v["status"] == st), key=lambda x: -x[1])
        print(f"\n== {st} ({len(rows)} types, {sum(c for _, c in rows)} objects)")
        print(", ".join(f"{k}:{c}" for k, c in rows))

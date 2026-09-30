"""Schemas for the ACR->ACB port.

ACB_TRUE: the bundled ACB_MP.schema is incomplete -- some types carry nameless
placeholder properties (name hash 0, flags 0) where the real ACBMP binary
serializes a field. For those types ACR's definition matches what ACB's
FastLoad code actually reads (verified by decoding retail ACB data with it and
against the Mac binary's FastLoad routines), so ACB_TRUE = ACB schema with
those types' TypeDefs taken from ACR.
"""
import copy, os, sys
sys.path.insert(0, os.path.expanduser("~/Coding/Python/anvilforge-py-acrport/src"))
from anvilforge.games import Game
from anvilforge.schema import Schema

ACB = Schema.load_default(Game.BROTHERHOOD)
ACR = Schema.load_default(Game.REVELATIONS)


def has_placeholder(schema, t):
    return any(p.name_hash == 0 for p in t.properties)


def build_acb_true():
    s = copy.copy(ACB)
    s.types_by_hash = dict(ACB.types_by_hash)
    s.names = dict(ACR.names); s.names.update(ACB.names)
    fixed = []
    for h, t in ACB.types_by_hash.items():
        if has_placeholder(ACB, t) and h in ACR.types_by_hash:
            s.types_by_hash[h] = ACR.types_by_hash[h]
            fixed.append(ACR.name_of(h))
    # pull in any ACR-only types the replaced definitions reference
    for h, t in ACR.types_by_hash.items():
        s.types_by_hash.setdefault(h, t)
    return s, fixed


ACB_TRUE, PLACEHOLDER_FIXED = build_acb_true()

if __name__ == "__main__":
    print(len(PLACEHOLDER_FIXED), "ACB types with placeholder props replaced by ACR defs:")
    print(", ".join(sorted(PLACEHOLDER_FIXED)))

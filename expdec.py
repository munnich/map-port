"""Experimental schema decoder with tracing, to reverse-engineer the real
serialization rules (vs anvilforge's objectxml). Returns nested dicts.

Rules under test (see NOTES.md):
  - a property is on disk iff flags & 0x2000000
  - serialized BOOL is always 1 byte (elem_kind ignored)
  - pointer tags: 0/3 = null, 1 = link(id), 4 = inline(pad, id, hash, props)
"""
import io, os, struct, sys
sys.path.insert(0, os.path.expanduser("~/Coding/Python/anvilforge-py-acrport/src"))
from anvilforge.schema import Kind, PRIMITIVE_SIZE

SER = 0x2000000
NULL_TAGS = {3}


class Fail(Exception):
    def __init__(self, msg, pos, path):
        super().__init__(msg); self.pos = pos; self.path = path


class Dec:
    def __init__(self, schema, rules=None):
        self.S = schema
        self.rules = rules or {}
        self._chain = {}
        self._managed = {}
        self._levels = {}

    def chain(self, h):
        c = self._chain.get(h)
        if c is None:
            c = [p for p in self.S.property_chain(h) if p.flags & SER]
            self._chain[h] = c
        return c

    def managed(self, h):
        m = self._managed.get(h)
        if m is None:
            m = False; t = self.S.type_by_hash(h)
            while t is not None:
                if self.S.name_of(t.type_hash) == "ManagedObject": m = True; break
                t = self.S.type_by_hash(t.base_type_hash)
            self._managed[h] = m
        return m

    def read(self, f, n, path):
        b = f.read(n)
        if len(b) < n: raise Fail(f"eof reading {n}", f.tell(), path)
        return b

    def root(self, data):
        f = io.BytesIO(data)
        pre = 0
        if data[0] == 1:
            pre = 12 * int.from_bytes(data[4:8], "little") + 7
        f.seek(pre + 2)
        oid = self.read(f, 4, "hdr"); h = int.from_bytes(self.read(f, 4, "hdr"), "little")
        obj = self.props(f, h, self.S.name_of(h))
        return obj, f.tell(), len(data)

    # element classes whose (hand-written) array loops go through
    # FastLoadSerializer::SerializeObjectProperty, i.e. carry a status byte
    # (ac2::CrowdDutyRegion::FastLoad -> CrowdComposition)
    STATUS_ELEMS = set()

    DYN = {"FXCommand", "Material", "BuildColumn", "BuildRow", "FXProperty", "FXDefaultTable",
           "FXDefaultTableInstance", "FXConstantTable", "FXConstantTableInstance", "GenericObject",
           "PropertyControllerEntry", "DynamicPropertiesSet"}

    def levels(self, h):
        c = self._levels.get(h)
        if c is None:
            cls = []; t = self.S.type_by_hash(h)
            while t is not None: cls.append(t); t = self.S.type_by_hash(t.base_type_hash)
            c = [(self.S.name_of(t.type_hash), [p for p in t.properties if p.flags & SER]) for t in reversed(cls)]
            self._levels[h] = c
        return c

    def props(self, f, h, path):
        if self.S.type_by_hash(h) is None:
            raise Fail(f"unknown type {h:#x}", f.tell(), path)
        out = {"_type": self.S.name_of(h)}
        for cname, ps in self.levels(h):
            for p in ps:
                nm = self.S.name_of(p.name_hash)
                out[nm] = self.value(f, p.kind, p.elem_kind, p.static_count, p.object_hash, f"{path}.{nm}", p.flags)
            if cname in self.DYN:
                out["_dyn"] = self.dynprops(f, f"{path}._dyn")
        return out

    def statusobj(self, f, oh, path):
        """FastLoadSerializer::SerializeObjectProperty(BaseObject**): status 2=local link, 3=null, 0=inline."""
        t = self.read(f, 1, path)[0]
        if t == 3: return None
        if t == 2: return ("link", t, self.read(f, 4, path).hex())
        if t == 0:
            oid = self.read(f, 4, path); h = int.from_bytes(self.read(f, 4, path), "little")
            return self.props(f, h, f"{path}<{self.S.name_of(h)}>")
        raise Fail(f"status tag {t}", f.tell() - 1, path)

    def dynprops(self, f, path):
        n = int.from_bytes(self.read(f, 4, path), "little")
        if n > 10000: raise Fail(f"bad dyncount {n}", f.tell(), path)
        out = []
        for i in range(n):
            name = int.from_bytes(self.read(f, 4, path), "little")
            oh = int.from_bytes(self.read(f, 4, path), "little")
            hi = int.from_bytes(self.read(f, 4, path), "little")
            kind = (hi >> 16) & 0x3F
            elem = (hi >> 23) & 0x1F
            cnt = hi & 0xFFFF
            if kind == Kind.OBJECT_PTR:
                val = ("rawptr", self.read(f, 4, path).hex())
            else:
                val = self.value(f, kind, elem, cnt, oh, f"{path}[{i}]")
            out.append((self.S.name_of(name), val))
        return out

    def value(self, f, kind, elem, count, oh, path, pflags=0):
        if kind == Kind.BOOL: return self.read(f, 1, path)[0]
        if kind in PRIMITIVE_SIZE:
            b = self.read(f, PRIMITIVE_SIZE[kind], path)
            if kind == Kind.FLOAT: return struct.unpack("<f", b)[0]
            return b.hex() if len(b) > 8 else int.from_bytes(b, "little")
        if kind == Kind.ENUM: return int.from_bytes(self.read(f, 4, path), "little")
        if kind == Kind.OBJECT_ID: return self.read(f, 4, path).hex()
        if kind == Kind.HANDLE:
            t = self.read(f, 1, path)[0]
            return ("handle", t, self.read(f, 4, path).hex())
        if kind == Kind.REFERENCE:
            hdr = self.read(f, 2, path); rid = self.read(f, 4, path).hex()
            if hdr[0] == 0:
                h = int.from_bytes(self.read(f, 4, path), "little")
                return self.props(f, h, f"{path}<{self.S.name_of(h)}>")
            return ("ref", hdr.hex(), rid)
        if kind in (Kind.STRING, Kind.LSTRING):
            n = int.from_bytes(self.read(f, 4, path), "little")
            if n > 1_000_000: raise Fail("bad strlen", f.tell(), path)
            w = 2 if kind == Kind.LSTRING else 1
            if n == 0: return ""
            # FastLoadSerializer::SerializeProperty(SimpleStringTemplate*): len, then len+1 units (NUL incl.)
            return self.read(f, (n + 1) * w, path)[:-w].decode("utf-16-le" if w == 2 else "latin-1")
        if kind in (Kind.OBJECT, Kind.BASE_OBJECT):
            if kind == Kind.OBJECT and self.managed(oh): self.read(f, 1, path)
            oid = self.read(f, 4, path); h = int.from_bytes(self.read(f, 4, path), "little")
            return self.props(f, h, f"{path}<{self.S.name_of(h)}>")
        if kind in (Kind.OBJECT_PTR, Kind.BASE_OBJECT_PTR):
            t = self.read(f, 1, path)[0]
            if t == 3: return None
            if t in (1, 2, 5): return ("link", t, self.read(f, 4, path).hex())
            if t in (0, 4):
                if self.managed(oh): self.read(f, 1, path)
                oid = self.read(f, 4, path); h = int.from_bytes(self.read(f, 4, path), "little")
                return self.props(f, h, f"{path}<{self.S.name_of(h)}>")
            raise Fail(f"ptr tag {t}", f.tell() - 1, path)
        if kind in (Kind.STATIC_ARRAY, Kind.BIG_ARRAY, Kind.SMALL_ARRAY):
            n = count if kind == Kind.STATIC_ARRAY else int.from_bytes(self.read(f, 4, path), "little")
            if n > 1_000_000: raise Fail(f"bad count {n}", f.tell(), path)
            if elem == Kind.BASE_OBJECT and self.S.name_of(oh) in self.STATUS_ELEMS:
                return [self.statusobj(f, oh, f"{path}[{i}]") for i in range(n)]
            return [self.value(f, elem, 0, 0, oh, f"{path}[{i}]") for i in range(n)]
        raise Fail(f"kind {kind}", f.tell(), path)

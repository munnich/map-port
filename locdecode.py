"""locdecode.py: read ACB/ACR CompressedLocalizationData (LocalizationPackage.CompressedData.Data).

Port of scimitar::CompressedLocalizationData::DecodeHeader / GetLocalizedStringRaw (Mac build). All big-endian:
  u16 threshold, u16 nodeCount, nodeCount x (u16 a, u16 b)       pair table; b == 0 -> leaf, a is the char
  u16 blockCount, blockCount x (u32 firstLineId, u32 textOffset, u32 idTableOffset)   (offsets from data start)
  id table: u16 K, then u16 W[2K+1]: string j (line firstLineId + W[2j+1] for j>=1, firstLineId for j=0) spans
            text[W[2j-1] .. W[2j+1]] (W[-1] := 0) -- i.e. W[1+2j] = end of string j / start of string j+1,
            W[2+2j] = line offset of string j+1
  text: per symbol one byte b (< threshold), or 2 bytes ((b<<8|n) - threshold*0xff), or 0xff + u16; symbol+1 is a
        node index; a node (a, b != 0) expands b's subtree, then a's."""
import struct


def _expand(nodes, c, out):
    stack = []
    while True:
        a, b = nodes[c]
        if b:
            stack.append(a)
            c = b
            continue
        out.append(a)
        if not stack:
            return
        c = stack.pop()


def decode_all(data: bytes) -> dict[int, str]:
    thr, n = struct.unpack_from(">HH", data, 0)
    nodes = [struct.unpack_from(">HH", data, 4 + 4 * i) for i in range(n)]
    p = 4 + 4 * n
    (nblk,) = struct.unpack_from(">H", data, p)
    p += 2
    blocks = [struct.unpack_from(">III", data, p + 12 * i) for i in range(nblk)]
    out = {}
    for first, text_off, ids_off in blocks:
        (k,) = struct.unpack_from(">H", data, ids_off)
        w = struct.unpack_from(f">{2 * k + 1}H", data, ids_off + 2)
        spans = [(first, 0, w[0])] + [(first + w[2 * j + 1], w[2 * j], w[2 * j + 2]) for j in range(k)]
        for line, s, e in spans:
            q, end, chars = text_off + s, text_off + e, []
            while q < end:
                b = data[q]; q += 1
                if b >= thr:
                    if b == 0xFF:
                        sym = (data[q] << 8) | data[q + 1]; q += 2
                    else:
                        sym = ((b << 8) | data[q]) - thr * 0xFF; q += 1
                else:
                    sym = b
                _expand(nodes, sym + 1, chars)
            out[line] = "".join(map(chr, chars))
    return out


def package_strings(codec, payload: bytes) -> dict[int, str]:
    """All lines of one LocalizationPackage payload (plain LocalizedData entries override the compressed ones)."""
    o = codec.decode(payload).obj
    data = b"".join(o.fields["CompressedData"].fields["Data"])
    res = decode_all(data) if data else {}
    for s in o.fields["LocalizedData"]:
        res[int.from_bytes(s.fields["TextID"], "little")] = s.fields["Text"].decode("utf-16-le")
    return res

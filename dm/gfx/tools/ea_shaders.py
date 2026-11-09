"""EA BIG shader archives: EASF -> chunkzip v2 -> BIG -> GLSLC.

Found on FIFA 22 Legacy Edition 1.0.5. Keys are taken from the supplied
game's main, never distributed here. EASF authenticates the first 32 decoded
bytes with the digest in its header; every archive and block is bounds checked.
"""
import hashlib
import io
import re
import struct
import zlib

KEY_ID = b'datax   '


def keys_from_main(image):
    """The EASF key table stores an eight-byte identifier followed by AES key."""
    return tuple(image[m.end():m.end() + 16] for m in re.finditer(KEY_ID, image)
                 if m.end() + 16 <= len(image))


def big_entries(f):
    f.seek(0, 2); size = f.tell(); f.seek(0)
    head = f.read(16)
    if len(head) != 16 or head[:4] not in (b'BIG4', b'BIGF'):
        raise ValueError('invalid EA BIG header')
    count, end = struct.unpack_from('>II', head, 8)
    if not 16 <= end <= size or count > (end - 16) // 9:
        raise ValueError('EA BIG index out of bounds')
    table = head + f.read(end - 16)
    pos = 16
    for _ in range(count):
        if pos + 9 > end: raise ValueError('truncated EA BIG entry')
        off, length = struct.unpack_from('>II', table, pos); pos += 8
        stop = table.find(b'\0', pos)
        if stop < 0: raise ValueError('unterminated EA BIG name')
        name = table[pos:stop].decode('utf-8', 'replace'); pos = stop + 1
        if off < end or off > size or length > size - off:
            raise ValueError('EA BIG member out of bounds: ' + name)
        yield name, off, length


def decrypt(data, keys):
    if len(data) < 64 or data[:4] != b'EASF' or data[8:16] != KEY_ID or (len(data) - 48) % 16:
        raise ValueError('unsupported or truncated EASF header')
    from Crypto.Cipher import AES
    size = int.from_bytes(data[4:8], 'big')
    if not 32 <= size < len(data) - 48: raise ValueError('invalid EASF decoded size')
    for key in keys:
        # Reject false key-table matches before decoding the full payload.
        first = AES.new(key, AES.MODE_CBC, key).decrypt(data[48:80])
        if hashlib.sha256(first).digest() != data[16:48]: continue
        raw = AES.new(key, AES.MODE_CBC, key).decrypt(data[48:])
        pad = raw[-1]
        if not 1 <= pad <= 16 or raw[-pad:] != bytes([pad]) * pad or len(raw) - pad != size:
            raise ValueError('invalid EASF padding or decoded length')
        return raw[:size]
    raise ValueError('EASF key was not found in the supplied main')


def chunkzip(data):
    if len(data) < 48 or data[:8] != b'chunkzip' or int.from_bytes(data[8:12], 'big') != 2:
        raise ValueError('unsupported chunkzip header')
    total, block, count, align = struct.unpack_from('>4I', data, 12)
    if not total or not block or count != (total + block - 1) // block or align != 16:
        raise ValueError('invalid chunkzip sizes or alignment')
    pos, parts, done = 40, [], 0
    for _ in range(count):
        if pos + 8 > len(data): raise ValueError('truncated chunkzip block header')
        length, kind = struct.unpack_from('>II', data, pos); pos += 8
        if length > len(data) - pos: raise ValueError('truncated chunkzip block')
        payload = data[pos:pos + length]; pos += length
        expected = min(block, total - done)
        if kind == 1:
            dec = zlib.decompressobj(-15)
            raw = dec.decompress(payload, expected + 1)
            if not dec.eof or dec.unused_data or dec.unconsumed_tail:
                raise ValueError('invalid chunkzip deflate stream')
        elif kind == 0:
            raw = payload
        else:
            raise ValueError('unsupported chunkzip block codec')
        if len(raw) != expected: raise ValueError('chunkzip decoded length mismatch')
        parts.append(raw); done += len(raw)
        # Payloads, rather than their eight-byte headers, are 16-byte aligned.
        pos = (pos + 8 + align - 1) // align * align - 8
    return b''.join(parts)


def shader_members(f, keys, prefix='', depth=0):
    """Read shader packages without loading multi-gigabyte outer BIG archives.

    EA names its GPU packages shader.big/shaderboot.big. Scan all their members,
    preserving names so GLSLC program variations retain their vertex/pixel pairs.
    """
    if depth > 8: raise ValueError('EA shader archive nesting exceeds eight levels')
    for name, off, length in list(big_entries(f)):
        if not depth and 'shader' not in name.lower(): continue
        f.seek(off); data = f.read(length)
        if len(data) != length: raise ValueError('truncated EA shader member')
        label = prefix + '/' + name
        if data[:4] == b'EASF': data = decrypt(data, keys)
        if data[:8] == b'chunkzip': data = chunkzip(data)
        if data[:4] in (b'BIG4', b'BIGF'):
            yield from shader_members(io.BytesIO(data), keys, label, depth + 1)
        else:
            yield label, data

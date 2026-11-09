"""EA archive readers: synthetic data only; no game files or game keys."""
import hashlib
import io
from pathlib import Path
import struct
import sys
import unittest
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import ea_shaders as ea


def archive(name, data):
    index = 16 + 8 + len(name) + 1
    return (b'BIG4' + struct.pack('<I', index + len(data)) + struct.pack('>II', 1, index)
            + struct.pack('>II', index, len(data)) + name + b'\0' + data)


def chunks(parts):
    data = bytearray(b'chunkzip' + struct.pack('>5I', 2, sum(map(len, parts)), len(parts[0]), len(parts), 16) + bytes(12))
    for raw in parts:
        data += bytes((-(len(data) + 8)) % 16)
        enc = zlib.compressobj(wbits=-15); payload = enc.compress(raw) + enc.flush()
        data += struct.pack('>II', len(payload), 1) + payload
    return bytes(data)


class EaShaderTests(unittest.TestCase):
    def test_chunk_alignment_and_short_last_block(self):
        self.assertEqual(ea.chunkzip(chunks([b'A' * 128, b'B' * 47])), b'A' * 128 + b'B' * 47)

    def test_chunk_rejects_truncation_and_wrong_output_size(self):
        packed = chunks([b'A' * 128])
        with self.assertRaises(ValueError): ea.chunkzip(packed[:-1])
        bad = bytearray(packed); struct.pack_into('>I', bad, 12, 127)
        with self.assertRaises(ValueError): ea.chunkzip(bad)

    def test_easf_key_discovery_digest_and_padding(self):
        from Crypto.Cipher import AES
        key = bytes(range(16)); raw = b'example shader archive bytes----' * 4
        pad = 16 - len(raw) % 16
        encrypted = AES.new(key, AES.MODE_CBC, key).encrypt(raw + bytes([pad]) * pad)
        data = b'EASF' + struct.pack('>I', len(raw)) + ea.KEY_ID + hashlib.sha256(raw[:32]).digest() + encrypted
        keys = ea.keys_from_main(b'prefix' + ea.KEY_ID + key)
        self.assertEqual(ea.decrypt(data, keys), raw)
        with self.assertRaises(ValueError): ea.decrypt(data, [bytes(16)])
        with self.assertRaises(ValueError): ea.decrypt(data[:-1], keys)
        with self.assertRaises(ValueError): ea.decrypt(data[:16] + bytes(32) + data[48:], keys)

    def test_nested_shader_package_preserves_member_names(self):
        raw = b'GPU program'
        packed = archive(b'data/shaderboot.big', chunks([archive(b'program.glsl', raw)]))
        self.assertEqual(list(ea.shader_members(io.BytesIO(packed), ())), [('/data/shaderboot.big/program.glsl', raw)])

    def test_big_member_cannot_escape_archive(self):
        packed = bytearray(archive(b'shader.big', b'abc'))
        struct.pack_into('>I', packed, 20, 1000)
        with self.assertRaises(ValueError): list(ea.big_entries(io.BytesIO(packed)))

    def test_compute_uses_descriptor_past_constant_data_gap(self):
        import shader_split as split
        section, control_length, code_length = 0x120, 0xA00, 0x100
        data = bytearray(section + control_length + code_length)
        data[:4] = bytes.fromhex('91688619')
        struct.pack_into('<I', data, 0x44, len(data))
        struct.pack_into('<I', data, 0x4C, 1)
        struct.pack_into('<III', data, 0x90, control_length + code_length, section, 0)
        struct.pack_into('<IIII', data, 0xC0, 0, control_length, code_length, control_length)
        data[section:section + 4] = split.CTL_MAGIC
        struct.pack_into('<I', data, section + 0x20, 0x880)
        struct.pack_into('<I', data, section + 0x704, code_length)
        struct.pack_into('<III', data, section + 0x748, 32, 1, 1)
        code = bytes.fromhex('110720e200c41c00') * (code_length // 8)
        data[section + control_length:] = code
        result = split.glslc_shaders(bytes(data), 'synthetic')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][1], 'cs')
        self.assertEqual(result[0][3], code)


if __name__ == '__main__': unittest.main()

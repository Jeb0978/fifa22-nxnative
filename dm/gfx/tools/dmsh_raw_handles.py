"""Lower non-c2 2D handle arrays to GPU descriptor tables indexed by raw IDs.

Keep the full 20-bit texture / 12-bit sampler indices. The old 32-entry
fallback clamps these to 31 and cannot represent game-data handles.
"""
import re

def lower(src):
    if re.search(r'\b[a-z]+_c2\b', src):
        return src
    pattern = r'array<(texture2d<float>|sampler), 32>\s+(\w+_cb0_40000000)\s*\[\[id\((\d+)\)\]\];'
    bindings = list(re.finditer(pattern, src))
    if not bindings:
        return src
    if len(bindings) != 2 or {m[1] for m in bindings} != {'texture2d<float>', 'sampler'}:
        return src  # Other shapes need their own typed descriptor table.
    # Remove only the min(...,31) values that feed these exact array accesses.
    # SPIRV-Cross emits uint v = min(index,31u); and then array[int(v)].
    for m in bindings:
        name = m[2]
        uses = list(re.finditer(r'\b' + re.escape(name) + r'\[int\((\w+)\)\]', src))
        if not uses:
            raise ValueError('raw handle array has an unrecognized access: ' + name)
        for use in uses:
            var = use[1]
            pat = r'(uint\s+' + re.escape(var) + r'\s*=\s*)min\((.+?), 31u\);'
            src, n = re.subn(pat, r'\1\2;', src)
            if n != 1:
                raise ValueError('raw handle index has an unrecognized clamp: ' + var)
        axis = 'x' if m[1] == 'texture2d<float>' else 'y'
        src = re.sub(r'\b' + re.escape(name) + r'\[int\((\w+)\)\]',
                     name + r'[dm_raw_index(\1, spvDescriptorSet0.dm_raw_counts->' + axis + r')].value', src)
    def declaration(m):
        typ = 'DmRawTexture' if m[1] == 'texture2d<float>' else 'DmRawSampler'
        return f'constant {typ}* {m[2]} [[id({m[3]})]];'
    src = re.sub(pattern, declaration, src)
    # Arrays occupied 32 resource IDs each; pointers occupy one. Metal packs
    # the pointer fields densely even if their old IDs retain those gaps.
    # Renumber the root members so reflection aid*8 matches the compiled ABI.
    root = re.search(r'(struct spvDescriptorSetBuffer0\s*\{)(.*?)(\};)', src, re.S)
    if not root:
        raise ValueError('raw handle shader has no root argument buffer')
    next_id = 0
    def repack(m):
        nonlocal next_id
        typ, name = m[1].strip(), m[2]
        count = re.fullmatch(r'array<.+,\s*(\d+)>', typ)
        aid = next_id
        next_id += int(count[1]) if count else 1
        return f'    {typ} {name} [[id({aid})]];'
    members = root[2] + '    constant uint2* dm_raw_counts [[id(0)]];\n'
    body = re.sub(r'^\s*(.+?)\s+(\w+)\s*\[\[id\(\d+\)\]\];', repack, members, flags=re.M)
    src = src[:root.start(2)] + body + src[root.end(2):]
    definitions = ('\nstruct DmRawTexture { texture2d<float> value [[id(0)]]; };\n'
                   'struct DmRawSampler { sampler value [[id(0)]]; };\n'
                   'inline uint dm_raw_index(uint i, uint n) { return i < n ? i : 0u; }\n')
    return src.replace('using namespace metal;', 'using namespace metal;' + definitions, 1)

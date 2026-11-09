"""Check production table sizing/indexing against the former full-domain tables."""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

gfx = Path(__file__).resolve().parents[1]
host = (gfx / 'nvn/nvn_mtl.m').read_text(encoding='utf-8')
sys.path.insert(0, str(gfx / 'tools'))
from dmsh_raw_handles import lower

src = '''using namespace metal;
struct spvDescriptorSetBuffer0 {
array<texture2d<float>, 32> fp_t_cb0_40000000 [[id(0)]];
array<sampler, 32> fp_s_cb0_40000000 [[id(32)]];
};
uint t = min(handle & 1048575u, 31u);
uint s = min(handle >> 20, 31u);
spvDescriptorSet0.fp_t_cb0_40000000[int(t)];
spvDescriptorSet0.fp_s_cb0_40000000[int(s)];
'''
lowered = lower(src)
assert 'dm_raw_index(t, spvDescriptorSet0.dm_raw_counts->x)' in lowered
assert 'dm_raw_index(s, spvDescriptorSet0.dm_raw_counts->y)' in lowered
assert 'constant uint2* dm_raw_counts [[id(2)]]' in lowered
guard = re.search(r'inline uint dm_raw_index\(.*?\}', lowered)[0].replace('inline ', 'static ')
size = re.search(r'    size_t count = sampler \? MIN.*?count = MAX\(count, 1u\);', host, re.S)[0]
code = '''#include <stddef.h>
#include <assert.h>
typedef unsigned uint;
#define MIN(a,b) ((a)<(b)?(a):(b))
#define MAX(a,b) ((a)>(b)?(a):(b))
''' + guard + '''
static size_t capacity(int sampler, int g_ntreg, int g_nsreg, int g_tpool_n) {
''' + size + '''
return count;
}
int main(void) {
    int sizes[] = {0,1,31,32,33,434,1024,2048,4096,1048576,1048600};
    int pools[] = {0,1,32,1192,1048576};
    for (int sampler=0; sampler<2; sampler++)
    for (unsigned r=0; r<sizeof sizes/sizeof *sizes; r++)
    for (unsigned p=0; p<sizeof pools/sizeof *pools; p++) {
        unsigned n=capacity(sampler,sizes[r],sizes[r],pools[p]);
        unsigned domain=1u<<(sampler?12:20);
        assert(n>=1 && n<=domain);
        for (unsigned i=0; i<domain; i++) {
            unsigned old=i>0 && i<(unsigned)sizes[r] &&
                (sampler || !pools[p] || i<(unsigned)pools[p]) ? i : 0;
            unsigned j=dm_raw_index(i,n);
            assert(j<n);
            unsigned compact=j>0 && j<(unsigned)sizes[r] &&
                (sampler || !pools[p] || j<(unsigned)pools[p]) ? j : 0;
            assert(old==compact);
        }
    }
    assert(capacity(0,2048,512,0)*8==16384);
    return 0;
}
'''
with tempfile.TemporaryDirectory() as tmp:
    c = Path(tmp)/'bounds.c'
    exe = Path(tmp)/'bounds.exe'
    c.write_text(code)
    subprocess.run([sys.argv[1], '-O2', str(c), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
print('Production bounds preserve every 20-bit/12-bit lookup, including empty pools and boundary IDs.')

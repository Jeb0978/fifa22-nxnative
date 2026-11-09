"""Production BC source gate + decoder, with a deterministic queued GPU producer.

Usage: python test_bc_source_sync.py <C compiler>
This tests CPU ordering; it does not execute a Metal queue.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

gfx = Path(__file__).resolve().parents[1]
source = (gfx / 'nvn/nvn_mtl.m').read_text(encoding='utf-8')
start = source.index('static int bc_source_ready(')
end = source.index('\nstatic void copy_b2t(', start)
gate = source[start:end]
test = r'''
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <assert.h>
#include "nvn_bcdec.h"
#define WS_DIAG 0
#define MLOG(...) ((void)0)
static unsigned flags, waits, timeout;
static int g_sbw_over;
static uint8_t src[8], pixels[64];
static const uint8_t red[8]={0,248}, green[8]={224,7};
static int hit(uint64_t lo,uint64_t hi) { return lo<(uint64_t)(uintptr_t)(src+8) && hi>(uint64_t)(uintptr_t)src; }
static int pend_hits(uint64_t a,uint64_t n) { return (flags&1) && hit(a,a+n); }
static int sbw_hits(uint64_t a,uint64_t b) { return (flags&2) && hit(a,b); }
static int gw_live(uint64_t a,uint64_t b) { return (flags&4) && hit(a,b); }
static int gpu_read_wait(int site) { (void)site; waits++; if(timeout)return 0; memcpy(src,green,8); return 1; }
'''
test += gate
test += r'''
static int decode(void) {
    if(!bc_source_ready((uint64_t)(uintptr_t)src,sizeof src))return 0;
    nvn_bc_decompress_level(0x42,4,4,src,pixels,16); return 1;
}
static void is_green(void) { for(int i=0;i<16;i++) assert(pixels[4*i]==0 && pixels[4*i+1]==255 && pixels[4*i+2]==0 && pixels[4*i+3]==255); }
int main(void) {
    memcpy(src,red,8);
    nvn_bc_decompress_level(0x42,4,4,src,pixels,16);
    assert(pixels[0]==255 && pixels[1]==0); /* old path consumes stale red */
    memcpy(src,green,8); assert(decode() && waits==0); is_green();
    for(unsigned i=0;i<4;i++) {
        flags=i<3 ? 1u<<i : 0; g_sbw_over=i==3; waits=0;
        memcpy(src,red,8); assert(decode() && waits==1); is_green();
    }
    flags=7; g_sbw_over=0; waits=0;
    assert(bc_source_ready((uint64_t)(uintptr_t)(src+8),8) && waits==0);
    timeout=1; memset(pixels,0xA5,sizeof pixels); memcpy(src,red,8);
    assert(!decode() && waits==1 && src[1]==248);
    for(unsigned i=0;i<sizeof pixels;i++)assert(pixels[i]==0xA5);
    puts("PASS: stale-source reproduction; CPU-only, queued copy, shader write, prior submission, overflow tracking, non-overlap, timeout");
}
'''
with tempfile.TemporaryDirectory(prefix='bc-source-') as tmp:
    c = Path(tmp)/'test.c'
    exe = Path(tmp)/'test.exe'
    c.write_text(test, encoding='utf-8')
    subprocess.run([sys.argv[1], '-std=c11', '-Wall', '-Wextra', '-I'+str(gfx/'tex'), str(c), str(gfx/'tex/nvn_bcdec.c'), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)

// CPU-only regression: BC6H RGB half output must become bounded RGBA16F rows.
#include "../tex/nvn_bcdec.h"
#include "../tex/bcdec.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int check(int format, unsigned w, unsigned h, unsigned pad, unsigned seed) {
    size_t pitch = w * 8 + pad, size = pitch * h;
    unsigned nx = (w+3)/4, ny = (h+3)/4;
    // Extra space lets the old full-block writer fail a canary check safely.
    unsigned char *got = malloc(size*3+512), *want = malloc(size*3+512);
    uint64_t *src = calloc(nx*ny,16);
    if (!got || !want || !src) return 1;
    memset(got,0xa5,size*3+512); memset(want,0xa5,size*3+512);
    for (unsigned i=0; i<nx*ny*2; i++) {
        seed=seed*1664525u+1013904223u; src[i]=(uint64_t)seed<<32;
        seed=seed*1664525u+1013904223u; src[i]|=seed;
    }
    for (unsigned by=0;by<ny;by++) for (unsigned bx=0;bx<nx;bx++) {
        uint64_t *block=src+(by*nx+bx)*2;
        block[0]=(block[0]&~31ull)|3; // valid one-subset BC6H mode, varied endpoints/indices
        uint16_t rgb[48]; bcdec_bc6h_half(block,rgb,12,format==0x4f);
        for(unsigned y=0;y<4 && by*4+y<h;y++) for(unsigned x=0;x<4 && bx*4+x<w;x++) {
            uint16_t rgba[4]={rgb[(y*4+x)*3],rgb[(y*4+x)*3+1],rgb[(y*4+x)*3+2],0x3c00};
            memcpy(want+32+(by*4+y)*pitch+(bx*4+x)*8,rgba,8);
        }
    }
    nvn_bc_decompress_level(format,w,h,src,got+32,pitch);
    int bad=memcmp(got,want,size*3+512)!=0;
    if(bad) fprintf(stderr,"FAIL BC6H format=%x %ux%u pitch=%zu (pixels, padding or bounds)\n",format,w,h,pitch);
    free(src);free(want);free(got);return bad;
}
int main(void) {
    // Stop before clipped-block cases on the old code: its scratch buffer also overflows.
    if(check(0x50,4,4,0,1)) return 1;
    const unsigned dims[][2]={{1,1},{3,5},{4,4},{8,8},{7,9},{32,32}};
    int checks=1;
    for(int f=0x4f;f<=0x50;f++) for(unsigned i=0;i<6;i++)
        for(unsigned pad=0;pad<=16;pad+=16) for(unsigned seed=1;seed<=8;seed++) {
            if(check(f,dims[i][0],dims[i][1],pad,seed)) return 1;
            checks++;
        }
    printf("PASS %d BC6H layout/bounds cases (signed, unsigned, clipped and padded)\n",checks);
    return 0;
}

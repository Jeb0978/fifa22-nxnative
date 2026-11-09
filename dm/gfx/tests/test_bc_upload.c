#include "../tex/nvn_bcdec.h"
#include <stdio.h>
#include <string.h>

#ifdef TEST_LEGACY_TIGHT_ROWS
// Reproduce the old upload call, which dropped the source-row pitch.
#define nvn_bc_decompress_level_strided(f,w,h,s,sp,d,dp) nvn_bc_decompress_level(f,w,h,s,d,dp)
#endif

static int signed_cases(void) {
    // Index 6 of signed endpoints -127 <= +127 must decode to -127,
    // index 7 to +127. Unsigned decoding instead interpolates these endpoints.
    unsigned char src[32]={0}, dst[128];
    unsigned long long a=0x7f81, b=0x7f81;
    for(int i=0;i<16;i++) { a|=6ull<<(16+3*i); b|=7ull<<(16+3*i); }
    memcpy(src,&a,8);memcpy(src+8,&b,8);
    for(int f=0x4a;f<=0x4c;f+=2) for(int edge=0;edge<2;edge++) {
        unsigned w=edge?3:4,h=edge?2:4,bpp=f==0x4a?1:2,pitch=12;
        memset(dst,0xa5,sizeof dst);
        nvn_bc_decompress_level(f,w,h,src,dst,pitch);
        for(unsigned y=0;y<h;y++) for(unsigned x=0;x<w;x++) {
            if(dst[y*pitch+x*bpp]!=0x81) return 1;
            if(bpp==2 && dst[y*pitch+x*bpp+1]!=0x7f) return 2;
        }
        for(unsigned y=0;y<h;y++) for(unsigned x=w*bpp;x<pitch;x++)
            if(dst[y*pitch+x]!=0xa5) return 3;
    }
    return 0;
}
static int row_cases(void) {
    // Two 4-pixel-high BC1 rows separated by padding: solid red then green.
    unsigned char src[64],dst[256];memset(src,0xcc,sizeof src);
    unsigned long long red=0xf800, green=0x07e0;
    memcpy(src,&red,8);memcpy(src+32,&green,8);
    for(int edge=0;edge<2;edge++) {
        unsigned w=edge?3:4,h=edge?7:8,pitch=24;
        memset(dst,0xa5,sizeof dst);
        nvn_bc_decompress_level_strided(0x42,w,h,src,32,dst,pitch);
        for(unsigned y=0;y<h;y++) for(unsigned x=0;x<w;x++) {
            unsigned char expected[4]={y<4?255:0,y<4?0:255,0,255};
            if(memcmp(dst+y*pitch+x*4,expected,4)) return 4;
        }
        for(unsigned y=0;y<h;y++) for(unsigned x=w*4;x<pitch;x++)
            if(dst[y*pitch+x]!=0xa5) return 5;
    }
    return 0;
}
int main(void) {
    int a=signed_cases(),b=row_cases();
    if(a||b) { printf("FAIL signed=%d row=%d\n",a,b);return 1; }
    puts("PASS signed BC4/BC5 and padded BC1 uploads, full/clipped blocks");return 0;
}

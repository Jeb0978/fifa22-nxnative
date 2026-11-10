// Compare whole-image decoding with BCfast stripe partitioning.
// CPU equivalence only: does not exercise dispatch or Metal buffer lifetimes.
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../tex/nvn_bcdec.h"

static uint32_t rng=0x9e3779b9u;
static uint32_t rand32(void) { rng ^= rng<<13; rng ^= rng>>17; rng ^= rng<<5; return rng; }

static void split_decode(int fmt, unsigned w, unsigned h, int nz, const uint8_t *src,
                         size_t srcimg,size_t srcrow,uint8_t *dst,size_t dstimg,size_t dstrow,int lanes) {
 unsigned blocks_y=(h+3)/4;
 if(lanes>(int)blocks_y)lanes=blocks_y;
 for(int z=0;z<nz;z++)
 for(int part=0;part<lanes;part++){
   unsigned by0=(unsigned)((blocks_y*(size_t)part)/(size_t)lanes);
   unsigned by1=(unsigned)((blocks_y*(size_t)(part+1))/(size_t)lanes);
   if(by0==by1)continue;
   unsigned y0=by0*4;
   unsigned band_h=h-y0<(by1-by0)*4 ? h-y0:(by1-by0)*4;
   nvn_bc_decompress_level_strided(fmt,w,band_h,
     src+z*srcimg+by0*srcrow,srcrow,
     dst+z*dstimg+y0*dstrow,dstrow);
 }
}
int main(void){
 const unsigned dims[]={1,2,3,4,5,7,8,9,11,16,17,31,32,33,63,64,65,68,127,128,192,256,384,512};
 size_t tests=0, bytes=0;
 for(int fmt=0x41;fmt<=0x50;fmt++){
   int bpp=nvn_bc_decompressed_bpp(fmt);
   if(!bpp)continue;
   int blocksize=(fmt==0x41||fmt==0x42||fmt==0x45||fmt==0x46||fmt==0x49||fmt==0x4a)?8:16;
   for(int it=0;it<70;it++){
     unsigned w=dims[rand32()%24],h=dims[rand32()%24];
     int nz=(int)(rand32()%3+1);
     unsigned bx=(w+3)/4,by=(h+3)/4;
     size_t srcrow=bx*blocksize+(rand32()%4)*16;
     size_t srcimg=srcrow*by+(rand32()%3)*16;
     size_t dstrow=w*bpp+(rand32()%3)*16;
     size_t dstimg=dstrow*h+(rand32()%4)*16;
     size_t srcsz=srcimg*nz, dstsz=dstimg*nz+64;
     uint8_t *src=malloc(srcsz),*a=malloc(dstsz),*b=malloc(dstsz);
     if(!src||!a||!b)abort();
     for(size_t i=0;i<srcsz;i++)src[i]=(uint8_t)rand32();
     memset(a,0x5a,dstsz);memset(b,0x5a,dstsz);
     for(int z=0;z<nz;z++)
       nvn_bc_decompress_level_strided(fmt,w,h,src+z*srcimg,srcrow,a+z*dstimg,dstrow);
     int lanes=(int)(rand32()%4)+1;
     split_decode(fmt,w,h,nz,src,srcimg,srcrow,b,dstimg,dstrow,lanes);
     if(memcmp(a,b,dstsz)){
       size_t i=0;while(i<dstsz && a[i]==b[i])i++;
       fprintf(stderr,"FAIL fmt=%#x %ux%u nz=%d lanes=%d offset=%zu a=%02x b=%02x\n",fmt,w,h,nz,lanes,i,a[i],b[i]);return 1;
     }
     tests++;bytes+=dstsz;
     free(src);free(a);free(b);
   }
 }
 printf("PASS %zu decoded BC1-BC7/BC6H comparisons including padded strides, 1-4 stripes, 1-3 layers, odd edges; %zu total bytes checked\n",tests,bytes);
 return 0;
}
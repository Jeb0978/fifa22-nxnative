// nvn_bcdec.c - Implementation of BC decompression using bcdec.h
#define BCDEC_IMPLEMENTATION
#define BCDEC_BC4BC5_PRECISE
#include "bcdec.h"
#include "nvn_bcdec.h"
#include <string.h>

int nvn_is_bc_format(int f) {
    return (f >= 0x41 && f <= 0x50);
}

int nvn_bc_decompressed_bpp(int f) {
    switch (f) {
        case 0x41: case 0x42: case 0x43: case 0x44: // BC1, BC2, BC3
        case 0x45: case 0x46: case 0x47: case 0x48: // sRGB variants
        case 0x4D: case 0x4E:                       // BC7
            return 4; // RGBA8
        case 0x49: case 0x4A:                       // BC4
            return 1; // R8
        case 0x4B: case 0x4C:                       // BC5
            return 2; // RG8
        case 0x4F: case 0x50:                       // BC6H
            return 8; // RGBA16F (half float)
        default:
            return 0;
    }
}

uint32_t nvn_bc_to_uncompressed_mtl(int f) {
    // Metal pixel format numbers:
    // R8Unorm = 10, R8Snorm = 12
    // RG8Unorm = 30, RG8Snorm = 32
    // RGBA8Unorm = 70, RGBA8Unorm_sRGB = 71
    // RGBA16Float = 115
    switch (f) {
        case 0x41: case 0x42: case 0x43: case 0x44: case 0x4D:
            return 70; // RGBA8Unorm
        case 0x45: case 0x46: case 0x47: case 0x48: case 0x4E:
            return 71; // RGBA8Unorm_sRGB
        case 0x49:
            return 10; // R8Unorm
        case 0x4A:
            return 12; // R8Snorm
        case 0x4B:
            return 30; // RG8Unorm
        case 0x4C:
            return 32; // RG8Snorm
        case 0x4F: case 0x50:
            return 115; // RGBA16Float
        default:
            return 0;
    }
}

void nvn_bc_decompress_level(int f, uint32_t width, uint32_t height,
                             const void *src_bc, void *dst, size_t dst_pitch) {
    nvn_bc_decompress_level_strided(f, width, height, src_bc, 0, dst, dst_pitch);
}

void nvn_bc_decompress_level_strided(int f, uint32_t width, uint32_t height,
                             const void *src_bc, size_t src_pitch, void *dst, size_t dst_pitch) {
    if (!nvn_is_bc_format(f) || !src_bc || !dst) return;

    int bpp = nvn_bc_decompressed_bpp(f);
    int block_size = 16;
    if (f == 0x41 || f == 0x42 || f == 0x45 || f == 0x46 || f == 0x49 || f == 0x4A) {
        block_size = 8; // BC1 and BC4 use 8-byte blocks
    }

    uint32_t blocks_x = (width + 3) / 4;
    uint32_t blocks_y = (height + 3) / 4;
    if (!src_pitch) src_pitch = (size_t)blocks_x * block_size;
    const uint8_t *src_ptr = (const uint8_t *)src_bc;

    for (uint32_t by = 0; by < blocks_y; by++) {
        for (uint32_t bx = 0; bx < blocks_x; bx++) {
            const uint8_t *block = src_ptr + by * src_pitch + bx * block_size;
            uint8_t *dst_pixel = (uint8_t *)dst + by * 4 * dst_pitch + bx * 4 * bpp;

            if (f == 0x4F || f == 0x50) {
                // bcdec writes RGB half values; its pitch is in uint16_t elements,
                // not bytes. Metal needs RGBA16F. Decode a bounded RGB block,
                // then expand with opaque alpha and clip at mip/texture edges.
                uint16_t rgb[4 * 4 * 3];
                bcdec_bc6h_half(block, rgb, 4 * 3, f == 0x4F);
                uint32_t rows = height - by * 4, cols = width - bx * 4;
                if (rows > 4) rows = 4;
                if (cols > 4) cols = 4;
                for (uint32_t y = 0; y < rows; y++) {
                    for (uint32_t x = 0; x < cols; x++) {
                        const uint16_t *p = rgb + (y * 4 + x) * 3;
                        uint16_t rgba[4] = { p[0], p[1], p[2], 0x3c00 }; // half 1.0
                        memcpy(dst_pixel + y * dst_pitch + x * 8, rgba, sizeof rgba);
                    }
                }
                continue;
            }

            // Handle edge clipping for textures whose width or height is not a multiple of 4
            int clip = (bx * 4 + 4 > width) || (by * 4 + 4 > height);

            if (!clip) {
                switch (f) {
                    case 0x41: case 0x42: case 0x45: case 0x46:
                        bcdec_bc1(block, dst_pixel, (int)dst_pitch);
                        break;
                    case 0x43: case 0x47:
                        bcdec_bc2(block, dst_pixel, (int)dst_pitch);
                        break;
                    case 0x44: case 0x48:
                        bcdec_bc3(block, dst_pixel, (int)dst_pitch);
                        break;
                    case 0x49: case 0x4A:
                        bcdec_bc4(block, dst_pixel, (int)dst_pitch, f == 0x4A);
                        break;
                    case 0x4B: case 0x4C:
                        bcdec_bc5(block, dst_pixel, (int)dst_pitch, f == 0x4C);
                        break;
                    case 0x4D: case 0x4E:
                        bcdec_bc7(block, dst_pixel, (int)dst_pitch);
                        break;
                }
            } else {
                // Temporary 4x4 buffer for boundary blocks
                uint8_t temp[4 * 4 * 8]; // max 8 bytes per pixel (RGBA16F)
                int temp_pitch = 4 * bpp;
                switch (f) {
                    case 0x41: case 0x42: case 0x45: case 0x46:
                        bcdec_bc1(block, temp, temp_pitch);
                        break;
                    case 0x43: case 0x47:
                        bcdec_bc2(block, temp, temp_pitch);
                        break;
                    case 0x44: case 0x48:
                        bcdec_bc3(block, temp, temp_pitch);
                        break;
                    case 0x49: case 0x4A:
                        bcdec_bc4(block, temp, temp_pitch, f == 0x4A);
                        break;
                    case 0x4B: case 0x4C:
                        bcdec_bc5(block, temp, temp_pitch, f == 0x4C);
                        break;
                    case 0x4D: case 0x4E:
                        bcdec_bc7(block, temp, temp_pitch);
                        break;
                }
                uint32_t copy_w = (width > bx * 4) ? (width - bx * 4) : 0;
                if (copy_w > 4) copy_w = 4;
                uint32_t copy_h = (height > by * 4) ? (height - by * 4) : 0;
                if (copy_h > 4) copy_h = 4;

                for (uint32_t row = 0; row < copy_h; row++) {
                    memcpy(dst_pixel + row * dst_pitch, temp + row * temp_pitch, copy_w * bpp);
                }
            }
        }
    }
}

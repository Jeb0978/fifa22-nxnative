// nvn_bcdec.h - Decompression of BC1-BC7 block-compressed textures for devices without hardware BC support (e.g. Apple A16 Bionic)
#pragma once
#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

// Returns 1 if format is BC1-BC7 (0x41..0x50), 0 otherwise
int nvn_is_bc_format(int nvn_format);

// Returns bytes per pixel of the decompressed image (e.g. 4 for RGBA8, 1 for R8, 2 for RG8, 8 for RGBA16F)
int nvn_bc_decompressed_bpp(int nvn_format);

// Returns the target Metal pixel format for the decompressed data
uint32_t nvn_bc_to_uncompressed_mtl(int nvn_format);

// Decompresses a 2D image of BC blocks to uncompressed pixels
// src_bc: linear deswizzled BC blocks
// dst: uncompressed pixels
// dst_pitch: bytes per row of dst
void nvn_bc_decompress_level(int nvn_format, uint32_t width, uint32_t height,
                             const void *src_bc, void *dst, size_t dst_pitch);

// src_pitch: bytes between compressed block rows; 0 selects tightly packed rows.
void nvn_bc_decompress_level_strided(int nvn_format, uint32_t width, uint32_t height,
                             const void *src_bc, size_t src_pitch, void *dst, size_t dst_pitch);

#ifdef __cplusplus
}
#endif

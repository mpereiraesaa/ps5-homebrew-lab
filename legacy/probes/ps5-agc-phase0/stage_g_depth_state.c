#include "stage_g_depth_state.h"

int stage_g_build_d32_no_htile(
    AgcRegister1202 out[STAGE_G_DEPTH_REGISTER_COUNT], uintptr_t address,
    uint32_t width, uint32_t height)
{
    if (!out || !address || (address & 0xffffu) || !width || !height ||
        width > 16384 || height > 16384)
        return -1;

    const uint32_t lo = (uint32_t)(address >> 8);
    const uint32_t hi = (uint32_t)(address >> 40) & 0xffu;
    const AgcRegister1202 plan[STAGE_G_DEPTH_REGISTER_COUNT] = {
        {0x000, 0x00000060}, /* DB_RENDER_CONTROL: no compression */
        {0x01f, 0x00000000}, /* DB_RMI_L2_CACHE_CONTROL */
        {0x002, 0x00000000}, /* DB_DEPTH_VIEW */
        {0x004, 0x00000000}, /* DB_RENDER_OVERRIDE2 */
        {0x005, 0x00000000}, /* DB_HTILE_DATA_BASE */
        {0x007, ((height - 1) << 16) | (width - 1)},
        {0x011, 0x20000180}, /* stencil disabled; SW_64KB_Z_X */
        {0x012, lo},         /* DB_Z_READ_BASE */
        {0x013, 0x00000000}, /* no stencil read plane */
        {0x014, lo},         /* DB_Z_WRITE_BASE */
        {0x015, 0x00000000}, /* no stencil write plane */
        {0x2af, 0x00000000}, /* no HTILE surface */
        {0x2de, 0x000001e9}, /* float depth; -23 polygon-offset bits */
        {0x092, 0x00000000}, /* no stencil coher destination */
        {0x01a, hi},         /* DB_Z_READ_BASE_HI */
        {0x01c, hi},         /* DB_Z_WRITE_BASE_HI */
        {0x01b, 0x00000000}, /* no stencil read high */
        {0x01d, 0x00000000}, /* no stencil write high */
        {0x01e, 0x00000000}, /* no HTILE high */
        {0x003, 0x0000002a}, /* force HiZ and both HiS paths disabled */
        {0x010, 0x00000183}, /* D32_FLOAT, 1x, SW_64KB_Z_X */
        {0x200, 0x000000b6}, /* depth read/write, LESS_EQUAL */
    };
    for (size_t i = 0; i < STAGE_G_DEPTH_REGISTER_COUNT; ++i) out[i] = plan[i];
    return 0;
}

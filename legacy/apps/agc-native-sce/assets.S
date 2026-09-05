/* Local-only research inputs.  The build gate pins their hashes and the
 * resulting binary is never intended for publication. */
.section .rodata.agc_assets,"a",@progbits

.balign 16
.global agc_geometry_header_start
.global agc_geometry_header_end
agc_geometry_header_start:
.incbin "third_party/ProsperoTV/assets/private/geometry.header.bin"
agc_geometry_header_end:

.balign 256
.global agc_geometry_code_start
.global agc_geometry_code_end
agc_geometry_code_start:
.incbin "third_party/ProsperoTV/assets/private/geometry.text.bin"
agc_geometry_code_end:

.balign 16
.global agc_pixel_header_start
.global agc_pixel_header_end
agc_pixel_header_start:
.incbin "third_party/ProsperoTV/assets/private/pixel.header.bin"
agc_pixel_header_end:

.balign 256
.global agc_pixel_code_start
.global agc_pixel_code_end
agc_pixel_code_start:
.incbin "third_party/ProsperoTV/assets/private/pixel.text.linear-buffer.bin"
agc_pixel_code_end:

.section .note.GNU-stack,"",@progbits

.section .rodata.stage_h_assets,"a",@progbits
.balign 256
.global stage_e_gs_start
stage_e_gs_start:
.incbin "research/gpu/build/stage-h-gears/gears.bin"
.global stage_e_gs_end
stage_e_gs_end:
.global stage_e_ps_start
.balign 256
stage_e_ps_start:
.incbin "research/gpu/build/stage-h-gears/gears_lit.bin"
.global stage_e_ps_end
stage_e_ps_end:
.section .note.GNU-stack,"",@progbits

PS5_PAYLOAD_SDK ?= $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/../../../../ps5debug-NG/ps5-payload-sdk/install)
include $(PS5_PAYLOAD_SDK)/toolchain/prospero.mk

ELF := ps5-agc-phase0.elf
CFLAGS := -Wall -Wextra -Werror -O2 -g
LDLIBS := -lSceSysmodule

all: $(ELF) ps5-agc-phase0b-hold.elf ps5-agc-phase0c-driver-dmem.elf \
	ps5-agc-phase0d-dma-buildonly.elf ps5-agc-phase0e-driver-queue-state.elf \
	ps5-agc-phase0f-driver-queue-hold.elf

$(ELF): main.c
	$(CC) $(CFLAGS) -o $@ $< $(LDLIBS)

ps5-agc-phase0b-hold.elf: main.c
	$(CC) $(CFLAGS) -DPROBE_HOLD_SECONDS=20 -o $@ $< $(LDLIBS)

ps5-agc-phase0c-driver-dmem.elf: driver_dmem.c
	$(CC) $(CFLAGS) -o $@ $< -ldl $(LDLIBS)

ps5-agc-phase0d-dma-buildonly.elf: dma_buildonly.c
	$(CC) $(CFLAGS) -o $@ $<

ps5-agc-phase0e-driver-queue-state.elf: driver_queue_state.c
	$(CC) $(CFLAGS) -o $@ $< -ldl $(LDLIBS)

ps5-agc-phase0f-driver-queue-hold.elf: driver_queue_hold.c
	$(CC) $(CFLAGS) -o $@ $< $(LDLIBS)

ps5-agc-phase0g-driver-queue-sigbase.elf: driver_queue_sigbase.c
	$(CC) $(CFLAGS) -o $@ $< -ldl $(LDLIBS)

ps5-agc-phase0h-regshadow-info.elf: driver_regshadow_info.c
	$(CC) $(CFLAGS) -o $@ $< -ldl $(LDLIBS)

ps5-agc-phase0i-module-queue-state.elf: driver_module_queue_state.c
	$(CC) $(CFLAGS) -o $@ $< $(LDLIBS)

ps5-agc-phase0j-module-segments.elf: driver_module_segments.c
	$(CC) $(CFLAGS) -o $@ $< $(LDLIBS)

ps5-agc-phase0k-queue-metadata.elf: driver_queue_metadata.c
	$(CC) $(CFLAGS) -o $@ $< $(LDLIBS)

ps5-agc-phase0l-presubmit-layout.elf: driver_presubmit_layout.c
	$(CC) $(CFLAGS) -o $@ $< $(LDLIBS)

ps5-agc-phase0m-first-submit.elf: driver_first_submit.c
	$(CC) $(CFLAGS) -o $@ $< -ldl $(LDLIBS)

ps5-agc-phase0n-memory-policy.elf: memory_mapping_policy.c
	$(CC) $(CFLAGS) -o $@ $<

ps5-agc-phase0o-fixed-mapping.elf: memory_fixed_mapping.c
	$(CC) $(CFLAGS) -o $@ $<

ps5-agc-phase0p-backend-state.elf: driver_backend_state.c
	$(CC) $(CFLAGS) -o $@ $< $(LDLIBS)

# Reusable stage-B stream compositor only. This target deliberately does not
# link an executable and is excluded from `all`.
stage-b-compose.o: stage_b_compose.c stage_b_compose.h
	$(CC) $(CFLAGS) -c -o $@ stage_b_compose.c

# Pure surface-layout planner for stage B. Like the compositor, this is an
# object-only target and cannot launch or submit anything.
stage-b-surface.o: stage_b_surface.c stage_b_surface.h
	$(CC) $(CFLAGS) -c -o $@ stage_b_surface.c

# Sequencing/retention state machine only; unresolved compositor and submit
# callbacks keep this as a non-runnable relocatable object.
stage-b-transaction.o: stage_b_transaction.c stage_b_transaction.h stage_b_compose.h
	$(CC) $(CFLAGS) -c -o $@ stage_b_transaction.c

# Completion classifier only; it consumes observations supplied by a future
# backend and has no polling, cleanup, or launch capability by itself.
stage-b-completion.o: stage_b_completion.c stage_b_completion.h
	$(CC) $(CFLAGS) -c -o $@ stage_b_completion.c

# Real API adapter, still object-only. Its unresolved VideoOut/kernel symbols
# make the absence of a runnable Stage-B payload explicit.
stage-b-event-adapter.o: stage_b_event_adapter.c stage_b_event_adapter.h stage_b_completion.h
	$(CC) $(CFLAGS) -c -o $@ stage_b_event_adapter.c

# Mapping-lifecycle state machine only. It uses injected callbacks, has no
# entry point and cannot load AGC or submit commands.
stage-a-batch-mapping.o: stage_a_batch_mapping.c stage_a_batch_mapping.h
	$(CC) $(CFLAGS) -c -o $@ stage_a_batch_mapping.c

# Mapping-only Phase 0Q draft. Explicit target, excluded from `all`, and no
# supervisor action; it never loads AGC or emits/submits a command buffer.
ps5-agc-phase0q-batch-mapping.elf: batch_mapping_probe.c stage_a_batch_mapping.c stage_a_batch_mapping.h
	$(CC) $(CFLAGS) -o $@ batch_mapping_probe.c stage_a_batch_mapping.c

# First GPU execution candidate over the runtime-proven BatchMap lifecycle.
# Explicit target only; deployment requires its independent binary verifier.
ps5-agc-phase0r-batch-first-submit.elf: driver_batch_first_submit.c stage_a_batch_mapping.c stage_a_batch_mapping.h
	$(CC) $(CFLAGS) -o $@ driver_batch_first_submit.c stage_a_batch_mapping.c -ldl $(LDLIBS)

# Fence-only diagnostic successor to 0R. Explicit target and never part of all.
ps5-agc-phase0s-batch-fence-submit.elf: driver_batch_fence_submit.c driver_batch_first_submit.c stage_a_batch_mapping.c stage_a_batch_mapping.h
	$(CC) $(CFLAGS) -o $@ driver_batch_fence_submit.c stage_a_batch_mapping.c -ldl $(LDLIBS)

# Load-only libSceAgc constructor/queue comparison. No mapping or submit.
ps5-agc-phase0t-libagc-load-queue.elf: libagc_load_queue_probe.c
	$(CC) $(CFLAGS) -o $@ $< -ldl $(LDLIBS)

# Native version-8 context bootstrap observed in San Andreas. Explicit only;
# no mapping, command buffer, submit or VideoOut.
ps5-agc-phase0u-context-bootstrap.elf: libagc_context_bootstrap_probe.c
	$(CC) $(CFLAGS) -o $@ $< -ldl $(LDLIBS)

# Exact fixed-VA availability only; no AGC, physical allocation or GPU work.
ps5-agc-phase0v-fs-table-va.elf: fs_table_va_probe.c
	$(CC) $(CFLAGS) -o $@ $<

# One private page at the fixed FS-table ABI VA, copied from the relocated
# table, followed by bootstrap v8. No submit, command buffer or VideoOut.
ps5-agc-phase0w-fixed-fs-bootstrap.elf: libagc_fixed_fs_bootstrap_probe.c
	$(CC) $(CFLAGS) -o $@ $< -ldl $(LDLIBS)

# Fixed-VA BatchMap lifecycle only. No AGC, queue, DCB or submit.
ps5-agc-phase0x-fixed-batch-map.elf: fixed_batch_mapping_probe.c
	$(CC) $(CFLAGS) -o $@ $<

clean:
	rm -f $(ELF) ps5-agc-phase0b-hold.elf ps5-agc-phase0c-driver-dmem.elf \
	ps5-agc-phase0d-dma-buildonly.elf ps5-agc-phase0e-driver-queue-state.elf \
		ps5-agc-phase0f-driver-queue-hold.elf \
		ps5-agc-phase0g-driver-queue-sigbase.elf
	rm -f ps5-agc-phase0h-regshadow-info.elf
	rm -f ps5-agc-phase0i-module-queue-state.elf
	rm -f ps5-agc-phase0j-module-segments.elf
	rm -f ps5-agc-phase0k-queue-metadata.elf
	rm -f ps5-agc-phase0l-presubmit-layout.elf
	rm -f ps5-agc-phase0m-first-submit.elf
	rm -f ps5-agc-phase0n-memory-policy.elf
	rm -f ps5-agc-phase0o-fixed-mapping.elf
	rm -f ps5-agc-phase0p-backend-state.elf
	rm -f stage-b-compose.o
	rm -f stage-b-surface.o
	rm -f stage-b-transaction.o
	rm -f stage-b-completion.o
	rm -f stage-b-event-adapter.o
	rm -f stage-a-batch-mapping.o
	rm -f ps5-agc-phase0q-batch-mapping.elf
	rm -f ps5-agc-phase0r-batch-first-submit.elf
	rm -f ps5-agc-phase0s-batch-fence-submit.elf
	rm -f ps5-agc-phase0t-libagc-load-queue.elf
	rm -f ps5-agc-phase0u-context-bootstrap.elf
	rm -f ps5-agc-phase0v-fs-table-va.elf
	rm -f ps5-agc-phase0w-fixed-fs-bootstrap.elf
	rm -f ps5-agc-phase0x-fixed-batch-map.elf

.PHONY: all clean

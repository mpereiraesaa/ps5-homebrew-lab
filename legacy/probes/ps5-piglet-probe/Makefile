PS5_PAYLOAD_SDK ?= $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/../../../../ps5debug-NG/ps5-payload-sdk/install)
include $(PS5_PAYLOAD_SDK)/toolchain/prospero.mk

CFLAGS := -Wall -Wextra -Werror -O2 -g -I$(PS5_PAYLOAD_SDK)/target/include
LDLIBS := -ldl -lSceSysmodule
ELFS := piglet-phase1-resolve.elf piglet-phase1b-sysmodule.elf piglet-phase2-getconfig.elf \
	piglet-phase3-egl-init.elf piglet-phase4-clear-swap.elf

all: $(ELFS)

piglet-phase1-resolve.elf: main.c
	$(CC) $(CFLAGS) -DPROBE_PHASE=1 -o $@ $< $(LDLIBS)

piglet-phase1b-sysmodule.elf: main.c
	$(CC) $(CFLAGS) -DPROBE_PHASE=1 -DPROBE_SYSMODULE=1 -o $@ $< $(LDLIBS)

piglet-phase2-getconfig.elf: main.c
	$(CC) $(CFLAGS) -DPROBE_PHASE=2 -o $@ $< $(LDLIBS)

piglet-phase3-egl-init.elf: main.c
	$(CC) $(CFLAGS) -DPROBE_PHASE=3 -o $@ $< $(LDLIBS)

piglet-phase4-clear-swap.elf: main.c
	$(CC) $(CFLAGS) -DPROBE_PHASE=4 -o $@ $< $(LDLIBS)

clean:
	rm -f $(ELFS)

.PHONY: all clean

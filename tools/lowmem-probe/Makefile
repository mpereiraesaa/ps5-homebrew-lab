PS5_PAYLOAD_SDK ?= $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/../../../ps5debug-NG/ps5-payload-sdk/install)
include $(PS5_PAYLOAD_SDK)/toolchain/prospero.mk

CFLAGS := -Wall -Wextra -Werror -O2 -g -I$(PS5_PAYLOAD_SDK)/target/include

all: lowmem-probe.elf

lowmem-probe.elf: main.c
	$(CC) $(CFLAGS) -o $@ $<

clean:
	rm -f lowmem-probe.elf

.PHONY: all clean

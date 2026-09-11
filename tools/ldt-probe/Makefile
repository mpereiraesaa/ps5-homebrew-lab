PS5_PAYLOAD_SDK ?= $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/../../../ps5debug-NG/ps5-payload-sdk/install)
include $(PS5_PAYLOAD_SDK)/toolchain/prospero.mk

CFLAGS := -Wall -Wextra -Werror -O2 -g -I$(PS5_PAYLOAD_SDK)/target/include

all: ldt-probe.elf

ldt-probe.elf: main.c
	$(CC) $(CFLAGS) -o $@ $<

clean:
	rm -f ldt-probe.elf

.PHONY: all clean

PS5_PAYLOAD_SDK ?= $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/../../../../ps5debug-NG/ps5-payload-sdk/install)
include $(PS5_PAYLOAD_SDK)/toolchain/prospero.mk

ELF := ps5-native-jit-probe.elf
CFLAGS := -Wall -Wextra -Werror -O2 -g
LDLIBS := -lSceSystemService

all: $(ELF)

$(ELF): main.c
	$(CC) $(CFLAGS) -o $@ $^ $(LDLIBS)

clean:
	rm -f $(ELF)

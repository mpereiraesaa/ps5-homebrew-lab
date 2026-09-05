PS5_PAYLOAD_SDK ?= $(abspath ../../../../../ps5debug-NG/ps5-payload-sdk/install)
include $(PS5_PAYLOAD_SDK)/toolchain/prospero.mk

SHSRV_DIR := ../../../../third_party/ps5-shsrv
HBLDR_SRC := $(SHSRV_DIR)/bundles/hbldr/hbldr.c
ELF := hbldr-modern-early-dmem.elf

CFLAGS := -O0 -Wall -Werror -DHBLDR_BREAKPOINT_OFFSET=0x2d \
	-DHBLDR_DEFAULT_PROGRAM='"/data/homebrew/bin/ps5-agc-phase0c-driver-dmem"'
LDLIBS := -lkernel_sys -lSceSystemService -lSceUserService

all: $(ELF)

hbldr.o: $(HBLDR_SRC)
	$(CC) $(CFLAGS) -I$(SHSRV_DIR) -c -o $@ $<

pt.o: $(SHSRV_DIR)/pt.c
	$(CC) $(CFLAGS) -I$(SHSRV_DIR) -c -o $@ $<

elfldr.o: $(SHSRV_DIR)/elfldr.c
	$(CC) $(CFLAGS) -I$(SHSRV_DIR) -c -o $@ $<

$(ELF): hbldr.o pt.o elfldr.o
	$(CC) -o $@ $^ $(LDLIBS)

clean:
	rm -f *.o $(ELF)

.PHONY: all clean

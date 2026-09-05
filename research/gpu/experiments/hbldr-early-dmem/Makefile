PS5_PAYLOAD_SDK ?= $(abspath ../../../../../ps5debug-NG/ps5-payload-sdk/install)
include $(PS5_PAYLOAD_SDK)/toolchain/prospero.mk

HBLDR_DIR := ../../../../third_party/ps5-payload-hbldr
PROBE := ../../../../legacy/probes/ps5-agc-phase0/ps5-agc-phase0c-driver-dmem.elf
ELF := hbldr-early-dmem.elf

CFLAGS := -O0 -Wall -Werror -DHBLDR_BREAKPOINT_OFFSET=0x2d \
	-DHBLDR_HOST_TITLE_ID='"FAKE00000"'
LDLIBS := -lkernel -lSceLibcInternal -lSceSystemService -lSceUserService

all: $(ELF)

payload.inc: $(PROBE)
	xxd -i -n embedded_payload $< > $@

main.o: main.c payload.inc
	$(CC) $(CFLAGS) -c -o $@ $<

hbldr.o: $(HBLDR_DIR)/hbldr.c
	$(CC) $(CFLAGS) -I$(HBLDR_DIR) -c -o $@ $<

pt.o: $(HBLDR_DIR)/pt.c
	$(CC) $(CFLAGS) -I$(HBLDR_DIR) -c -o $@ $<

mdbg.o: $(HBLDR_DIR)/mdbg.c
	$(CC) $(CFLAGS) -I$(HBLDR_DIR) -c -o $@ $<

$(ELF): pt.o hbldr.o mdbg.o main.o
	$(CC) -Wl,--allow-multiple-definition -o $@ $^ $(LDLIBS)

clean:
	rm -f *.o $(ELF) payload.inc

.PHONY: all clean

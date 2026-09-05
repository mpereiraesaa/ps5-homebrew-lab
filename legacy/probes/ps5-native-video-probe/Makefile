PS5_HOST ?= 192.168.0.69
PS5_PORT ?= 9021
PS5_PAYLOAD_SDK ?= $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/../../../../ps5debug-NG/ps5-payload-sdk/install)
include $(PS5_PAYLOAD_SDK)/toolchain/prospero.mk

ELF := ps5-native-video-probe.elf
CFLAGS := -Wall -Wextra -Werror -O2 -g
LDLIBS := -lSceVideoOut -lSceSystemService -lSceUserService -lScePad -lSceAudioOut

all: $(ELF)

$(ELF): main.c
	$(CC) $(CFLAGS) -o $@ $^ $(LDLIBS)

clean:
	rm -f $(ELF)

test: $(ELF)
	$(PS5_DEPLOY) -h $(PS5_HOST) -p $(PS5_PORT) $^

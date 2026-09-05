# PS5 payload build for the hello_log example (invoked by `make ps5-example`).
PS5_PAYLOAD_SDK ?= $(abspath $(CURDIR)/../../../ps5debug-NG/ps5-payload-sdk/install)
include $(PS5_PAYLOAD_SDK)/toolchain/prospero.mk

BUILD ?= build
ELF := $(BUILD)/hello_log.elf
ELF_CAPTURE := $(BUILD)/hello_log_capture.elf
CFLAGS := -Wall -Wextra -Werror -O2 -g -Iclient

all: $(ELF) $(ELF_CAPTURE)

$(ELF): client/examples/hello_log.c client/ps5log.h
	$(CC) $(CFLAGS) -o $@ client/examples/hello_log.c

# Same program with zero-change printf capture forced on (elfldr passes no
# environment, so HELLO_LOG_CAPTURE=1 cannot be used on the console).
$(ELF_CAPTURE): client/examples/hello_log.c client/ps5log.h
	$(CC) $(CFLAGS) -DHELLO_LOG_FORCE_CAPTURE -o $@ client/examples/hello_log.c

.PHONY: all

PS5_PAYLOAD_SDK ?= $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/../../../ps5debug-NG/ps5-payload-sdk/install)
include $(PS5_PAYLOAD_SDK)/toolchain/prospero.mk

CFLAGS := -Wall -Wextra -Werror -O2 -g -I$(PS5_PAYLOAD_SDK)/target/include
LDLIBS := -lSceSystemService -lSceUserService

all: status.elf close-fake.elf launch-san-andreas.elf close-san-andreas.elf \
	close-agc-phase0.elf launch-agc-phase0-v2.elf close-agc-phase0-v2.elf \
	launch-agc-native-sce.elf close-agc-native-sce.elf \
	launch-agc-gears.elf close-agc-gears.elf \
	close-native-hello-world.elf

status.elf: main.c
	$(CC) $(CFLAGS) -DACTION_STATUS=1 -DTARGET_TITLE='"none"' -o $@ $< $(LDLIBS)

close-fake.elf: main.c
	$(CC) $(CFLAGS) -DTARGET_TITLE='"FAKE00000"' -o $@ $< $(LDLIBS)

launch-san-andreas.elf: main.c
	$(CC) $(CFLAGS) -DACTION_LAUNCH=1 -DTARGET_TITLE='"PPSA03524"' -o $@ $< $(LDLIBS)

close-san-andreas.elf: main.c
	$(CC) $(CFLAGS) -DTARGET_TITLE='"PPSA03524"' -o $@ $< $(LDLIBS)

close-agc-phase0.elf: main.c
	$(CC) $(CFLAGS) -DTARGET_TITLE='"AGCP12002"' -o $@ $< $(LDLIBS)

launch-agc-phase0-v2.elf: main.c
	$(CC) $(CFLAGS) -DACTION_LAUNCH=1 -DTARGET_TITLE='"AGCP12003"' -o $@ $< $(LDLIBS)

close-agc-phase0-v2.elf: main.c
	$(CC) $(CFLAGS) -DTARGET_TITLE='"AGCP12003"' -o $@ $< $(LDLIBS)

close-agc-native-sce.elf: main.c
	$(CC) $(CFLAGS) -DTARGET_TITLE='"PPSA99998"' -o $@ $< $(LDLIBS)

launch-agc-native-sce.elf: main.c
	$(CC) $(CFLAGS) -DACTION_LAUNCH=1 -DTARGET_TITLE='"PPSA99998"' -o $@ $< $(LDLIBS)

launch-agc-gears.elf: main.c
	$(CC) $(CFLAGS) -DACTION_LAUNCH=1 -DTARGET_TITLE='"PPSA99997"' -o $@ $< $(LDLIBS)

close-agc-gears.elf: main.c
	$(CC) $(CFLAGS) -DTARGET_TITLE='"PPSA99997"' -o $@ $< $(LDLIBS)

close-native-hello-world.elf: main.c
	$(CC) $(CFLAGS) -DTARGET_TITLE='"PPSA99999"' -o $@ $< $(LDLIBS)

clean:
	rm -f status.elf close-fake.elf launch-san-andreas.elf close-san-andreas.elf \
		launch-agc-phase0.elf close-agc-phase0.elf launch-agc-phase0-v2.elf \
		close-agc-phase0-v2.elf launch-agc-native-sce.elf close-agc-native-sce.elf \
		launch-agc-gears.elf close-agc-gears.elf \
		close-native-hello-world.elf

.PHONY: all clean

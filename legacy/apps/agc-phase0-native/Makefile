PS5_PAYLOAD_SDK ?= $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/../../../ps5debug-NG/ps5-payload-sdk/install)
include $(PS5_PAYLOAD_SDK)/toolchain/prospero.mk

TITLE_ID ?= AGCP12002
FSELF := ../../../ps5debug-NG/ps5-payload-sdk/samples/install_app/make_fself.py
CFLAGS := -Wall -Wextra -Werror -O2 -g -ffreestanding -fno-stack-protector
INSTALLER_CFLAGS := -Wall -Wextra -Werror -O2 -g -DTITLE_ID=\"$(TITLE_ID)\"
INSTALLER_LDLIBS := -lSceIpmi -lSceAppInstUtil -lSceUserService -lSceSystemService
PS4_SDK_VERSION ?= 0x07590001
AUTHID := 0x3800000000000022
AUTHINFO := 00 00 00 00 00 00 00 00 00 00 00 00 00 1C 00 40 00 FF 00 00 00 00 \
            00 80 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 80 \
            00 40 00 40 00 00 00 00 00 00 00 80 00 00 00 00 00 00 00 08 00 40 \
            FF FF 00 00 00 F0 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 \
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 \
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 \
            00 00 00 00

all: $(TITLE_ID)/eboot.bin $(TITLE_ID)/sce_sys/icon0.png installer.elf

eboot.o: eboot.c
	$(CC) -c $(CFLAGS) -o $@ $<

eboot.elf: eboot.o eboot.x
	$(LD) --static -T eboot.x -o $@ eboot.o

$(TITLE_ID)/eboot.bin: eboot.elf $(TITLE_ID)/sce_sys/param.json $(TITLE_ID)/sce_sys/param.json.system
	python3 $(FSELF) --ptype fake --paid $(AUTHID) --auth-info "$(AUTHINFO)" \
		--app-version $(PS4_SDK_VERSION) --fw-version $(PS4_SDK_VERSION) $< $@

installer.elf: installer.c
	$(CC) $(INSTALLER_CFLAGS) -o $@ $< $(INSTALLER_LDLIBS)

# Keep the second title's registration helper distinct so an incremental build
# cannot silently reuse a helper compiled for AGCP12002.
installer-agcp12003.elf: installer.c
	$(CC) -Wall -Wextra -Werror -O2 -g -DTITLE_ID=\"AGCP12003\" \
		-o $@ $< $(INSTALLER_LDLIBS)

$(TITLE_ID)/sce_sys/icon0.png:
	convert -size 512x512 xc:'#172033' -fill '#54d6ff' -gravity center \
		-pointsize 58 -font DejaVu-Sans-Bold -annotate 0 'AGC PHASE 0' \
		-depth 8 $@

clean:
	rm -f eboot.o eboot.elf installer.elf installer-agcp12003.elf \
		$(TITLE_ID)/eboot.bin \
		$(TITLE_ID)/sce_sys/icon0.png

.PHONY: all clean

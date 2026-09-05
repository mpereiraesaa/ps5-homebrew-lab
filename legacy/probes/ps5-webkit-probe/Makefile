PS5_HOST ?= 192.168.0.69
PS5_PORT ?= 9021
PS5_PAYLOAD_SDK ?= $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/../../../../ps5debug-NG/ps5-payload-sdk/install)
include $(PS5_PAYLOAD_SDK)/toolchain/prospero.mk

ELF := ps5-webkit-probe.elf
CXXFLAGS := -Wall -Wextra -Werror -O2 -g
LDLIBS := -lSceSystemService -lSceUserService

all: $(ELF)

$(ELF): main.o
	$(CC) $(CXXFLAGS) -o $@ $^ $(LDLIBS)

main.o: main.c probe.html
	$(CXX) $(CXXFLAGS) -x c++ -c -o $@ main.c

clean:
	rm -f $(ELF) main.o

test: $(ELF)
	$(PS5_DEPLOY) -h $(PS5_HOST) -p $(PS5_PORT) $^

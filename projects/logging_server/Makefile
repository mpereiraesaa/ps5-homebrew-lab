PYTHON ?= python3
CC ?= cc
CFLAGS ?= -std=c11 -O2 -Wall -Wextra -Werror -pedantic
BUILD := build
PORT ?= 9300
RUNS ?= runs

# Optional PS5 payload build (elfldr-loadable ELF). Points at the same SDK the
# laboratory probes use; override PS5_PAYLOAD_SDK to use another install.
PS5_PAYLOAD_SDK ?= $(abspath $(CURDIR)/../../../ps5debug-NG/ps5-payload-sdk/install)

CLIENT_SRC := client/ps5log.c
CLIENT_HDR := client/ps5log.h

.PHONY: check test-server test-client roundtrip host-example ps5-example serve clean

check: test-server test-client roundtrip
	@echo "logging_server: all checks passed"

test-server:
	$(PYTHON) -m unittest discover -s server/tests -p 'test_*.py'

$(BUILD):
	mkdir -p $(BUILD)

$(BUILD)/test_ps5log_host: client/tests/test_ps5log_host.c $(CLIENT_SRC) $(CLIENT_HDR) | $(BUILD)
	$(CC) $(CFLAGS) -Iclient -o $@ client/tests/test_ps5log_host.c $(CLIENT_SRC)

test-client: $(BUILD)/test_ps5log_host
	./$(BUILD)/test_ps5log_host

# The example uses single-header mode (PS5LOG_IMPLEMENTATION), so it is built
# without ps5log.c on purpose; the host unit test covers the two-file mode.
$(BUILD)/hello_log: client/examples/hello_log.c $(CLIENT_HDR) | $(BUILD)
	$(CC) $(CFLAGS) -Iclient -o $@ client/examples/hello_log.c

host-example: $(BUILD)/hello_log

roundtrip: $(BUILD)/hello_log
	HELLO_LOG_BIN=$(CURDIR)/$(BUILD)/hello_log $(PYTHON) -m unittest client/tests/test_roundtrip.py

# Requires the PS5 payload SDK; produces an elfldr payload that logs to the
# server named in /data/homebrew/dev.conf (or ./dev.conf next to the ELF).
ps5-example: | $(BUILD)
	@test -f "$(PS5_PAYLOAD_SDK)/toolchain/prospero.mk" || \
		{ echo "PS5_PAYLOAD_SDK not found at $(PS5_PAYLOAD_SDK)"; exit 2; }
	$(MAKE) -f client/examples/ps5.mk PS5_PAYLOAD_SDK="$(PS5_PAYLOAD_SDK)" BUILD="$(BUILD)"

serve:
	$(PYTHON) server/ps5logd.py --port $(PORT) --runs-dir $(RUNS)

clean:
	rm -rf $(BUILD)
	find . -name __pycache__ -type d -prune -exec rm -rf {} +

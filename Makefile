PROJECT := projects/ps5-agc-gears
LOGGER := projects/logging_server
LEGACY_PROBES := $(wildcard legacy/probes/*)

.PHONY: all check gears-check telemetry-check sdk-check native native-release clean \
	legacy-probes legacy-clean

all: check

# Canonical laboratory gate. Renderer contracts come from the publishable repo;
# telemetry retains its own independent test suite.
check: gears-check telemetry-check

gears-check:
	$(MAKE) -C $(PROJECT) all

telemetry-check:
	$(MAKE) -C $(LOGGER) check

sdk-check:
	python3 sdk/agc/tests/verify_api.py

native:
	$(MAKE) -C $(PROJECT) native

native-release:
	$(MAKE) -C $(PROJECT) native-release

clean:
	$(MAKE) -C $(PROJECT) clean
	$(MAKE) -C $(LOGGER) clean

# Historical probes are opt-in evidence, never part of the active build.
legacy-probes:
	@set -e; for probe in $(LEGACY_PROBES); do \
		if test -f "$$probe/Makefile"; then $(MAKE) -C "$$probe"; fi; \
	done

legacy-clean:
	@set -e; for probe in $(LEGACY_PROBES); do \
		if test -f "$$probe/Makefile"; then $(MAKE) -C "$$probe" clean; fi; \
	done

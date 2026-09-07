PROJECT := projects/ps5-xash3d
GEARS := projects/ps5-agc-gears
LOGGER := projects/logging_server
LEGACY_PROBES := $(wildcard legacy/probes/*)

.PHONY: all check xash3d-check gears-check telemetry-check remoteplay-check sdk-check native native-release clean \
	legacy-probes legacy-clean

all: check

# Canonical laboratory gate. Renderer contracts come from the Xash3D port repo;
# the frozen Gears demo keeps its own gate; telemetry retains its own suite.
check: xash3d-check gears-check telemetry-check remoteplay-check

xash3d-check:
	$(MAKE) -C $(PROJECT) all

gears-check:
	$(MAKE) -C $(GEARS) all

telemetry-check:
	$(MAKE) -C $(LOGGER) check

remoteplay-check:
	python3 tests/test_ps5_remoteplay.py
	python3 tests/test_ps5_ftp.py

sdk-check:
	python3 sdk/agc/tests/verify_api.py

native:
	$(MAKE) -C $(PROJECT) native

native-release:
	$(MAKE) -C $(PROJECT) native-release

clean:
	$(MAKE) -C $(PROJECT) clean
	$(MAKE) -C $(GEARS) clean
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

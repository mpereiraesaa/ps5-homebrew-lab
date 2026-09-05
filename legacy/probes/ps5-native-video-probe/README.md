# PS5 native VideoOut probe

Native framebuffer/input/audio smoke test. It uses the PS5 `VideoOut` v2
buffer registration path, presents an animated RGB gradient and generates a
stereo tone through `AudioOut`. Move the square with the left stick, hold X to
change its color and tone, and press OPTIONS to close the BigApp safely. It logs each stage to
`/data/ps5-native-video-probe.log`, and returns control to the shell.

If the payload host has no Main direct-memory pool, the probe falls back to
the general direct-memory allocator over the standard PS5 physical aperture.

The display sequence derives from John Törnblom's GPL-3.0
`ps5-payload-hbldr/test.c`.

```sh
make -C legacy/probes/ps5-native-video-probe
curl -T legacy/probes/ps5-native-video-probe/ps5-native-video-probe.elf \
  ftp://$PS5_HOST:2121/data/homebrew/bin/ps5-native-video-probe
# In shsrv on port 2323:
hbldr /data/homebrew/bin/ps5-native-video-probe
```

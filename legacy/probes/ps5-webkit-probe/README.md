# PS5 WebKit Capability Probe

A standalone PS5 payload that serves a local capability-test page on port 6969
and opens it with `sceSystemServiceLaunchWebBrowser`. The page tests WebAssembly,
WebGL, audio, controller exposure, browser APIs, and a small rendering benchmark.

```sh
make -C legacy/probes/ps5-webkit-probe
python3 ../send_elf.py legacy/probes/ps5-webkit-probe/ps5-webkit-probe.elf
```

On the PS5, select **Run all tests**, exercise the controller, select **Test
audio**, then **Save report**. The JSON is written to:

```text
/data/ps5-webkit-probe-report.json
```

Launch the already-installed Elf Arsenal home-screen tile to open the probe. It
deeplinks to localhost port 6969. The report is also available while the payload
runs at `http://PS5-IP:6969/report`.

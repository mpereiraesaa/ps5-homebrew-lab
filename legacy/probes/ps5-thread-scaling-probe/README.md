# PS5 thread scaling probe

Measures effective CPU availability and throughput with 1, 2, 4, 6, 8, 12 and 16
worker threads inside the `hbldr` BigApp. It also records the union of each
thread's affinity mask. Results go to `/data/ps5-thread-scaling-probe.log`.

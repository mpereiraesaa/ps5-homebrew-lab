# PS5 memory budget probe

Reports process resource limits and total direct-memory aperture, then tests
heap allocations around its observed boundary and direct allocations through
2048 MiB independently. Every 16 KiB page
is written and verified before the mapping is released. Heap and Main direct
memory are tested separately, never cumulatively, to keep the probe bounded.

Results go to `/data/ps5-memory-budget-probe.log`.

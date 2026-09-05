# ps5log wire protocol, version `ps5log/1`

Plain UTF-8 text, one message per line, `\n` terminated (`\r\n` tolerated).
Carried over a TCP stream or over UDP datagrams to the same port. The server
stores every received line verbatim; parsing only adds structure on top.

## Messages

### HELLO (optional, first line)

```
HELLO ps5log/1 title=<title-id> app=<app-name> boot=0x<hex> [tag=<tag>] [resume=1 next_seq=<n>]
```

- `title`: PS5 title ID (`PPSA99998`) or any identifier for payloads.
- `app`: program name. Together with `title` it names the run file.
- `boot`: a token unique per process start (the client uses the monotonic
  clock at init). Two runs with the same token are the same process.
- `tag`: free-form text from `dev.conf`.
- `resume=1 next_seq=<n>`: sent after a reconnect. The server opens a new run
  file; the sequence numbers continue from the previous connection so gaps
  are visible in the manifest.

A stream without HELLO is accepted and stored as `title=unknown app=unknown`,
so `printf ... | nc <pc> 9300` works for shell payloads.

### Record

```
<seq>\t<mono_ns>\t<level>\t<text>
```

- `seq`: decimal, starts at 1 per process, increments on every record even
  when the network is down (the mirror file keeps the same numbers).
- `mono_ns`: `CLOCK_MONOTONIC` nanoseconds on the console. The server prints
  the time relative to the first record of the run.
- `level`: short token without spaces or tabs. Conventional values: `INFO`,
  `WARN`, `ERR`, `MARK` (checkpoint/milestone). Empty means `INFO`.
- `text`: everything after the third tab; tabs are allowed, `\n`/`\r` are
  replaced by spaces by the client. Maximum record length is 1024 bytes on the
  client; the server tolerates up to 64 KiB before force-splitting.

Lines that do not match this shape are stored and printed as level `RAW`.
This is how captured `printf` output (client `ps5log_capture_stdio`) and
`nc`-style shell clients appear. RAW lines are counted in `raw_lines` and
never produce sequence gaps.

### BYE (optional, last line)

```
BYE seq=<last-seq> reason=<text>
```

Marks a clean shutdown. A run whose connection closes without BYE has
`clean=false` in its manifest. For UDP, BYE finalizes the run immediately;
otherwise a UDP run is finalized after `--udp-idle` seconds of silence.

## Server-side artifacts

For every connection (TCP) or source address (UDP) the server writes to the
runs directory:

- `<UTC>_<title>_<app>_<boot>.log`: verbatim bytes as received, one line each.
- `<same>.json`: manifest written atomically when the run ends, with
  `records`, `raw_lines`, `first_seq`, `last_seq`, `gaps`, `bytes`, `sha256`,
  `clean`, `close_reason`, `duration_s`, `device_span_s`, the HELLO identity
  and the peer address.
- `latest_<title>.log`: symlink to the most recent run for that title.

`close_reason` values: `eof` (peer closed), `error:<errno>`, `bye` (UDP),
`udp_idle`, `server_shutdown`.

## Sequence gaps

`gaps` lists every place where `seq` was not `last_seq + 1`. With TCP a gap
means the client dropped records (network down, send timeout) or reconnected.
With UDP it also covers lost or reordered datagrams. An empty `gaps` list plus
`clean=true` is the evidence that the run's log is complete.

## Durability model

Bytes accepted by `send()` live in the console kernel's socket buffer and are
delivered even if the process dies immediately afterwards. What cannot survive
is a full console freeze or power loss before the kernel transmits. The AGC
laboratory deliberately accepts that boundary instead of reintroducing console
filesystem sinks; an incomplete run remains fail-closed.

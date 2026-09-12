# File-based agent coordination

This protocol coordinates agents that share the lab filesystem but cannot use
the same messaging transport. It supplements Git branches and PRs; it does not
replace them.

## Canonical mailbox

The single append-only mailbox is:

```text
$HOME/.codex/agent-coordination/ps5-vulkan.jsonl
```

Use the checked-in writer instead of editing that file:

```sh
python3 tools/agent_coordination.py status
python3 tools/agent_coordination.py tail --lines 20
```

Each line is one `ps5-agent-coordination/1` JSON event. The writer takes an
exclusive advisory lock, appends one complete line, flushes and calls `fsync`.
Readers take a shared lock. Never truncate, rewrite, reorder or hand-edit the
mailbox.

## Required agent lifecycle

Every handoff must assign a stable agent name and task id. The agent must:

1. Read `status` and `tail` before changing files.
2. Claim all source paths and exclusive resources it will use.
3. Work in its own worktree, topic branch and PR.
4. Post `progress` after a material result, `blocker` immediately when work
   cannot continue safely, and `message --target ...` for a decision request.
5. Read the mailbox again before deploying, launching, closing or debugging the
   console.
6. Post `complete` with commit, PR and evidence paths, or `release` if the work
   is abandoned. Both release that agent/task claim.

Example:

```sh
COORD="$PWD/tools/agent_coordination.py"  # run from the lab root
python3 "$COORD" post --agent agent_ds_flash --kind claim \
  --task cts-shared-memory \
  --scope path:projects/ps5vk/cts/upstream \
  --scope path:projects/ps5vk/tests/test_upstream_runner.py \
  --message "Claiming focused upstream CTS expansion"

python3 "$COORD" post --agent agent_ds_flash --kind claim \
  --task cts-console-run --scope console:PPSA99994 \
  --message "Acquiring the reserved title for two native runs"

python3 "$COORD" post --agent agent_ds_flash --kind progress \
  --task cts-shared-memory --target orchestrator \
  --message "Host selection gate passes; native execution pending"

python3 "$COORD" post --agent agent_ds_flash --kind complete \
  --task cts-console-run --target orchestrator \
  --artifact private-captures/cts-shared/run1.json \
  --message "Two runs complete; title closed and console lease released"
```

`path:` claims conflict on identical, parent or child paths. Other resources,
including `console:PPSA99994`, conflict by exact name. A rejected claim means
the agent must not proceed; it posts a targeted blocker or waits for the owner
to release the scope.

## Important implications

- This is a **pull channel**. Appending an event does not wake or notify another
  process. Agents must poll at the lifecycle points above. Silence is not an
  acknowledgement.
- The mailbox records coordination, not authority. It does not expand the
  owner's authorization or permit work outside the handoff.
- A claim is cooperative, not an operating-system sandbox. Agents still need
  separate worktrees and must inspect Git status before edits.
- Console access is serialized independently of source ownership. Holding a
  source claim never grants a console lease.
- Do not post credentials, IP addresses, pairing data, proprietary dumps,
  shaders, raw telemetry or personal information. Post audited paths, hashes,
  summaries, commits and PR URLs only.
- Do not put large output in the mailbox. Store private evidence in an ignored
  project path and reference it with `--artifact`.
- `blocker` does not release ownership. Use `release` when another agent should
  take over.
- The orchestrator reviews and merges. Worker agents must not merge their PRs.

## Reusable handoff clause

Include this paragraph in every task handed to a file-coordinated agent:

> Coordination is file-based and pull-driven. Before work, before touching the
> console and before finishing, read the canonical mailbox with
> `tools/agent_coordination.py status` and `tail`. Claim every source path and
> `console:PPSA99994` separately before use. Report material progress, blockers,
> decision requests and completion as structured events. A written event does
> not notify anyone and silence is not approval. Never hand-edit the JSONL,
> include secrets or raw private evidence, broaden authority, work in another
> agent's claimed scope, or merge your PR.

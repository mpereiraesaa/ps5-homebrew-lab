# Project charter: accelerated graphics for PS5 homebrew

## Objective

Document, understand, and make reproducible a hardware-accelerated graphics
path for homebrew running on the owner's jailbroken PS5. The intended endpoint
is a small, documented API/layer that can initialize graphics, own its memory,
submit bounded work, synchronize completion, and present through VideoOut.

## Authorized research boundary

- Build and run purpose-made homebrew probes on the owner's console.
- Analyze owner-authorized module, executable, and memory captures.
- Reproduce ABI, memory, queue, shader, synchronization, and presentation
  contracts needed by original homebrew software.
- Automate exact-title launch and clean close when independently verified.
- Extract and study authorized shader artifacts for interoperability research.

This authorization does not imply attaching to or modifying a commercial game
process, bypassing platform security, defeating access controls, redistributing
proprietary material, or using an uncertain/forced shutdown as routine cleanup.

## Engineering principles

1. Separate static evidence, CPU-only runtime evidence, GPU execution, and
   visible presentation; never report one as proof of another.
2. Every hardware probe is bounded, minimal, reproducible, and journaled.
3. Memory and process lifetime extend beyond asynchronous GPU work until an
   explicit ownership fence proves completion.
4. Unknown or contradictory state stops automation and retains resources.
5. Promote discoveries into small public-facing abstractions only after their
   ABI and lifetime rules are verified.

## Minimal path

```text
VideoOut buffers
  -> GPU-visible owned memory
  -> AGC context/queue
  -> bounded command stream
  -> ownership fence
  -> cache/presentation transition
  -> flip completion
```

The first visible milestone is a solid hardware-generated frame. A shader
pipeline and triangle follow only after that simpler path is understood.

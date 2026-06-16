# OIDviz web toolchain guardrails

Reference for agents setting up or extending the oidviz web app.
Stack: **Vue 3 + TypeScript + Bun + Vite**. (Stack changed from Svelte 5 to Vue 3 — company-wide Vue adoption.)

---

## Package manager and runtime: Bun

Use `bun` everywhere. No `npm`, no `node`.

```sh
bun install          # add dependencies
bun run dev          # start Vite dev server
bun test             # run tests (boots in <100ms)
bunx <tool>          # run a binary without installing globally
```

Bun executes TypeScript natively — no separate transpile step.

---

## Linting: Oxlint

Oxlint (Rust) replaces ESLint. Runs in under 50ms on the full codebase.

```sh
bunx oxlint          # lint everything
bunx oxlint --deny jsx-a11y/alt-text src/
```

Add to `package.json`:
```json
{
  "scripts": {
    "lint": "oxlint src/"
  }
}
```

Do **not** install ESLint.

---

## Formatting + supplementary lint: Biome

Biome (Rust) handles formatting and catches things Oxlint misses, including a dedicated `a11y` rule group.

```sh
bunx biome check src/                       # lint + format check
bunx biome check --formatter-enabled=false  # lint only (agent feedback loop)
bunx biome format --write src/              # auto-format
```

Notable a11y rules Biome enforces:
- `useHtmlLang` — `<html lang="en">` required
- `noNoninteractiveElementInteractions` — no `onClick` on `<div>`, use `<button>`
- `useAltText` — images must have alt attributes

---

## Type checking: TypeScript

Run `tsc` without emitting; skip lib-checking to keep it fast.

```sh
bunx tsc --noEmit --skipLibCheck
```

This is the slowest step (~1–2s) but catches hallucinated imports and wrong types. Run it last in the feedback loop.

---

## Accessibility: axe-core CLI (dynamic check)

Static linting misses rendered accessibility issues (contrast, ARIA states, semantic DOM). Run axe against the live dev server.

```sh
bunx @axe-core/cli --stdout http://localhost:5173 > a11y-report.json
```

Output is structured JSON — `target` is the failing DOM node, `failureSummary` is the fix description. Parse and feed directly back to the agent.

---

## Agent feedback loop (lint and types first)

Lint and types run first — they are the fastest checks and catch the most issues. Run in order on every file save. Stop
at the first failure and feed the output back as a prompt.

```
1. bunx oxlint src/                            (<50ms)   syntax + basic a11y
2. bunx tsc --noEmit --skipLibCheck           (~1-2s)   types
3. bunx biome check src/                      (<200ms)  a11y + style + format check
4. bun test                                   (<100ms)  logic
5. just a11y                                  (~10s)    rendered a11y (builds + serves via vite preview)
```

Steps 1–4 run without a browser. Step 5 builds the app and serves it via `vite preview` — no separate dev server needed.
Use `just ci` to run all five steps in sequence.

---

## What not to do

| Don't | Do instead |
|---|---|
| `npm install` | `bun install` |
| `npx tsc` | `bunx tsc` |
| Install ESLint | Use Oxlint |
| Run `tsc --build` for feedback | `tsc --noEmit --skipLibCheck` |
| Skip step 5 for UI changes | Always axe-check pages agents touch — `just a11y` is self-contained |

---

## Type generation from JSON Schema

The trace format schema lives at `../docs/trace-format.schema.json`.
Generate TypeScript types once at setup and after schema changes:

```sh
bunx json-schema-to-typescript ../docs/trace-format.schema.json \
  -o src/types.gen.ts
```

Do not hand-write types for trace records — use the generated file.

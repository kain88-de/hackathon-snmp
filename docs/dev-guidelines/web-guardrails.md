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

## Linting: Oxlint — all rules on

Oxlint (Rust) replaces ESLint. Runs under 50ms. **All rules are enabled via `-D all`** with a project config file that disables false positives.

```sh
bunx oxlint -D all -c .oxlintrc.json --ignore-pattern "src/lib/types.gen.ts" src/
```

The `.oxlintrc.json` file in the project root disables noise rules and configures:
- `no-magic-numbers` with `ignoreEnums: true` and `ignoreArrayIndexes: true`
- `max-lines` capped at 500
- false positives off: `no-optional-chaining`, `no-ternary`, `no-continue`, `unicorn/no-null`, `unicorn/filename-case`, `explicit-function-return-type`, `sort-*`

Do **not** install ESLint. Do **not** run `bunx oxlint src/` without `-D all` — that skips most rules.

---

## Formatting + linting: Biome — all rule groups on

Biome (Rust) handles formatting **and** linting. **All rule groups are enabled**: `a11y`, `complexity`, `correctness`, `performance`, `security`, `style`, `suspicious`.

```sh
bunx biome check --formatter-enabled=false src/   # lint only (fastest feedback)
bunx biome check --linter-enabled=false src/       # format check only
bunx biome format --write src/                     # auto-format
```

`biome.json` enables all rule groups with targeted overrides:
- `useImportExtensions: off` — Vite handles extensions
- `noDefaultExport: off` in `*.vue` — Vue SFCs require default export
- `useNamingConvention: off` in `src/lib/types.gen.ts` — generated file, do not edit

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

This is the slowest step (~1–2s) but catches hallucinated imports and wrong types.

`tsconfig.json` must include `strict: true`, `noUncheckedIndexedAccess: true`, and `exactOptionalPropertyTypes: true`.

---

## Accessibility: axe-core CLI (rendered check)

Static linting misses rendered accessibility issues (contrast, ARIA states, semantic DOM). Run axe against the built app via `vite preview` — **not** the dev server, so `just a11y` is self-contained.

```sh
just a11y    # builds, serves on :4173, runs axe, kills server
```

Zero WCAG 2.1 AA violations in DOM content is a hard gate before merge. Canvas views are validated manually.

---

## Agent feedback loop

Run in this order. Stop at the first failure and fix before continuing.

```
1. bunx oxlint -D all -c .oxlintrc.json --ignore-pattern "src/lib/types.gen.ts" src/   (<50ms)   syntax + all rules
2. bunx biome check --formatter-enabled=false --error-on-warnings src/                 (<50ms)   all biome lint rules; warnings are errors
3. bunx vue-tsc --noEmit --skipLibCheck                                                (~2-4s)   types + template type checking
4. bunx biome check --linter-enabled=false src/                                        (<50ms)   format check
5. bun test                                                                            (<100ms)  logic
6. just a11y                                                                           (~10s)    rendered a11y (build + vite preview)
```

Steps 1–5 run without a browser. Use `just ci` to run steps 1–5 in sequence (`lint → types → fmt-check → test`). Run `just a11y` separately before merging.

**Warnings are errors.** `biome check --error-on-warnings` is required in step 2. CI must exit 0 with zero warnings and zero errors.

---

## Justfile targets

| Target      | Command                                                                                             |
|-------------|-----------------------------------------------------------------------------------------------------|
| `lint`      | oxlint (`-D all -c .oxlintrc.json --ignore-pattern`) + biome check (`--formatter-enabled=false`)   |
| `types`     | `bunx vue-tsc --noEmit --skipLibCheck`                                                              |
| `fmt-check` | `bunx biome check --linter-enabled=false src/`                                                      |
| `test`      | `bun test`                                                                                          |
| `ci`        | `lint → types → fmt-check → test`                                                                   |
| `a11y`      | build + `bunx vite preview --port 4173` + `bunx @axe-core/cli` + kill                              |
| `fmt`       | `bunx biome format --write src/`                                                                    |
| `dev`       | `bun run dev`                                                                                       |
| `gen-types` | `bunx json-schema-to-typescript ../docs/trace-format.schema.json -o src/lib/types.gen.ts`          |

---

## Vue component structure

Keep `.vue` files short: `<script setup>` should contain only props/emits declarations and one composable call. Heavy logic lives in `src/composables/` as plain `.ts` files.

```vue
<!-- Good: .vue file is 30-80 lines -->
<script setup lang="ts">
import type { DomainExchange } from '../lib/model.ts';
import { useMyFeature } from '../composables/useMyFeature.ts';

const props = defineProps<{ exchanges: DomainExchange[] }>();
const emit = defineEmits<{ 'focus-exchange': [seq: number] }>();
const { ref1, ref2, onEvent } = useMyFeature(() => props, emit);
</script>
```

Benefits: composable `.ts` files are fully linted (no template-scope false positives), fully type-checked by vue-tsc, and independently testable. The `.vue` file stays readable.

**For component imports in App.vue**: Biome cannot cross-reference `<script setup>` bindings with `<template>`, so component imports show as unused. Use `// biome-ignore lint/correctness/noUnusedImports: used in <template>` on each such import — this is the minimal, surgical suppression that keeps the rule active for real unused imports.

---

## What not to do

| Don't | Do instead |
|---|---|
| `npm install` | `bun install` |
| `npx tsc` | `bunx tsc` |
| Install ESLint | Use Oxlint with `-D all` |
| `bunx oxlint src/` without `-D all` | Always pass `-D all -c .oxlintrc.json` |
| Run `tsc --build` for feedback | `vue-tsc --noEmit --skipLibCheck` |
| `bunx biome check src/` for lint only | `bunx biome check --formatter-enabled=false --error-on-warnings src/` |
| Use `tsc` instead of `vue-tsc` | `vue-tsc` checks template types; `tsc` misses them |
| Put 200+ lines of TS in a `.vue` file | Extract to a composable in `src/composables/` |
| Skip `just a11y` for UI changes | Always axe-check pages agents touch |
| Hard-code hex colours in canvas | Read `--dim-*` tokens via `getComputedStyle` at draw time |

---

## Type generation from JSON Schema

The trace format schema lives at `../docs/trace-format.schema.json`.
Generate TypeScript types once at setup and after schema changes:

```sh
just gen-types
# expands to:
bunx json-schema-to-typescript ../docs/trace-format.schema.json -o src/lib/types.gen.ts
```

Do not hand-write types for trace records — use the generated file. The generated file is excluded from linting via `--ignore-pattern` in Oxlint and a `biome.json` override.

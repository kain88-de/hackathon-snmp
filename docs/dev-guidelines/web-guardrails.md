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

## Linting: three complementary tools

Three linters run in sequence — each catches what the others miss:

| Tool | Speed | Catches |
|---|---|---|
| Oxlint | ~80ms | JS/TS correctness — all rules via `-D all` |
| Biome | ~95ms | JS/TS style + formatting — all rule groups |
| ESLint + eslint-plugin-vue | ~930ms | Vue template conventions (attribute order, hyphenation, void elements) |

### Oxlint — JS/TS correctness

**All rules enabled via `-D all`**. Config in `.oxlintrc.json` suppresses false positives.

```sh
bunx oxlint -D all -c .oxlintrc.json --ignore-pattern "src/lib/types.gen.ts" src/
```

Do **not** run `bunx oxlint src/` without `-D all` — that skips most rules.

### ESLint + eslint-plugin-vue — Vue template rules

ESLint runs **only on `.vue` files** (`.ts` files are excluded — covered by Oxlint + Biome). Config in `eslint.config.mjs`. Zero warnings allowed (`--max-warnings 0`).

```sh
bunx eslint --max-warnings 0 src/
```

This is the only tool that understands Vue template syntax: it catches `vue/attribute-hyphenation` (`:app-state` not `:appState`), `vue/html-self-closing` (void elements), `vue/attributes-order`, and other template-specific conventions. Oxlint and Biome are blind to template content.

**Why ESLint despite being ~12× slower than Oxlint:** it corrects Vue template mistakes that no other tool in the stack catches. The ~930ms cost is accepted.

Do **not** run `eslint src/` without `--max-warnings 0` — warnings must be zero.

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
1. bunx oxlint -D all -c .oxlintrc.json --ignore-pattern "src/lib/types.gen.ts" src/   (~80ms)    JS/TS correctness — all rules
2. bunx biome check --formatter-enabled=false --error-on-warnings src/                 (~95ms)    JS/TS style; warnings are errors
3. bunx eslint --max-warnings 0 src/                                                   (~930ms)   Vue template conventions
4. bunx vue-tsc --noEmit --skipLibCheck                                                (~2-4s)    types + template type checking
5. bunx biome check --linter-enabled=false src/                                        (<50ms)    format check
6. bun test                                                                            (<100ms)   logic
7. just a11y                                                                           (~10s)     rendered a11y (build + vite preview)
```

Steps 1–6 run without a browser. Use `just ci` to run steps 1–6 in sequence (`lint → types → fmt-check → test`). Run `just a11y` separately before merging.

**Warnings are errors** in both Biome (`--error-on-warnings`) and ESLint (`--max-warnings 0`). CI must exit 0 with zero warnings and zero errors.

---

## Justfile targets

| Target      | Command                                                                                             |
|-------------|-----------------------------------------------------------------------------------------------------|
| `lint`      | oxlint (`-D all`) + biome check (`--error-on-warnings`) + eslint (`--max-warnings 0`)              |
| `types`     | `bunx vue-tsc --noEmit --skipLibCheck`                                                              |
| `fmt-check` | `bunx biome check --linter-enabled=false src/`                                                      |
| `test`      | `bun test`                                                                                          |
| `ci`        | `lint → types → fmt-check → test`                                                                   |
| `a11y`      | build + `bunx vite preview --port 4173` + `bunx @axe-core/cli` + kill                              |
| `fmt`       | `bunx biome format --write src/`                                                                    |
| `dev`       | `bun run dev`                                                                                       |
| `gen-types` | `bunx json-schema-to-typescript ../docs/trace-format.schema.json -o src/lib/types.gen.ts`          |

---

## Vue component structure — keep logic in `.ts` files

**Rule: if the TypeScript compiler can validate it, it must live in a `.ts` file.**

`.vue` files are opaque to linters and partially opaque to `vue-tsc`. Code inside `<script setup>` escapes `no-unused-vars`, `no-unused-imports`, and other correctness rules because Biome cannot cross-reference the script with the template. The compiler is your primary safety net — don't put logic where it can't see it clearly.

**What belongs in `.vue` files:**
- `defineProps` / `defineEmits` declarations
- Imports of composables / lib modules
- Destructuring of composable return values
- The template itself

**What belongs in `.ts` files:**
- All business logic (pure functions → `src/lib/`)
- All stateful component logic (refs, watchers, lifecycle hooks, event handlers → `src/composables/`)
- Any code you want the linter and compiler to fully validate

```vue
<!-- Good: .vue file is ~20-40 lines, all logic in .ts -->
<script setup lang="ts">
import type { DomainExchange } from '../lib/model.ts';
import { useMyFeature } from '../composables/useMyFeature.ts';

const props = defineProps<{ exchanges: DomainExchange[] }>();
const emit = defineEmits<{ 'focus-exchange': [seq: number] }>();
const { ref1, ref2, onEvent } = useMyFeature(() => props, emit);
</script>
```

**For component imports in App.vue**: Biome cannot see `<template>` usage from `<script setup>`, so component imports flag as unused. Use `// biome-ignore lint/correctness/noUnusedImports: used in <template>` on each — surgical suppression that keeps the rule active for real unused imports.

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
| `bunx eslint src/` without `--max-warnings 0` | Always pass `--max-warnings 0` |
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

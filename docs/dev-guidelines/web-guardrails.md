# OIDviz web toolchain guardrails

Stack: **Vue 3 + TypeScript + Bun + Vite**

---

## CI pipeline (`just ci`)

Stop at the first failing target. The exact commands live in `Justfile` — not
restated here so the two can't silently disagree. Current order: `lint`
(oxlint + biome + eslint) → `types` (vue-tsc) → `fmt-check` (biome, linter
disabled) → `test` (Vitest) → `e2e` (Playwright) → `a11y` (Playwright against
the dev server, axe-core, zero WCAG 2.1 AA violations required).

---

## Justfile targets

| Target      | What it runs |
|-------------|---|
| `lint`      | oxlint + biome (warn=error) + eslint (warn=error) |
| `types`     | `vue-tsc --noEmit --skipLibCheck` |
| `fmt-check` | `biome check --linter-enabled=false` |
| `test`      | `vitest run` |
| `e2e`       | `playwright test` |
| `a11y`      | `playwright test tests/e2e/a11y.spec.ts` (axe-core, zero WCAG 2.1 AA violations) |
| `ci`        | lint → types → fmt-check → test → e2e → a11y |
| `fmt`       | `biome format --write src/` |
| `gen-types` | `json-schema-to-typescript ../traceformat/trace-format.schema.json -o src/lib/types.gen.ts` |

---

## What not to do

| Don't | Do instead |
|---|---|
| `npm` / `npx` | `bun` / `bunx` |
| `tsc` | `vue-tsc` — plain tsc misses template type errors |
| `eslint src/` | `eslint --max-warnings 0 src/` |
| `biome check src/` | `biome check --formatter-enabled=false --error-on-warnings src/` |
| `oxlint src/` | `oxlint -D all -c .oxlintrc.json src/` — without `-D all` most rules are off |
| Logic in `.vue` | Extract to `src/composables/*.ts` — linters and compiler are blind to `<script setup>` |
| Hard-coded hex in canvas | `getComputedStyle(canvas).getPropertyValue('--dim-*')` at draw time |

---

## Plan review cadence

For any plan longer than 6 tasks: after every 6 tasks, pause and dispatch an Opus agent to review the plan document for wrong, missing, or contradictory guidance. Implementation reveals plan errors that aren't visible upfront — a wrong instruction replicates across every subsequent task.

The reviewer asks two questions:
1. *"Does any guidance here actively prevent correct implementation?"*
2. *"Does the plan leave correctness to runtime that the type system could catch at compile time?"* — look for bare `string`/`number` crossing boundaries that should be branded, unions consumed without exhaustiveness, external data cast without validation, or logic described in prose that should be expressed as a type constraint.

Fix the plan before continuing.

This is a process control, not a CI check: nothing in the pipeline verifies
that a review happened. It depends on whoever is running the plan actually
doing it.

---

## Type-driven development

**Principle: encode correctness in the type system. If a constraint can be a compile error, it must be.**

This means: discriminated unions with exhaustiveness checks, branded types for domain quantities where confusion is possible, and runtime validation before external data enters the typed domain. The compiler should catch the class of bug before tests run.

Logic that the compiler can validate lives in `.ts` files. `.vue` files contain only `defineProps`, `defineEmits`, a composable call, and the template.

None of this is lint-gated today — treat it as review discipline, not a guarantee:

| Practice | Enforced by |
|---|---|
| Runtime validation before external data enters the typed domain | in place for trace parsing (`src/lib/traceValidator.gen.js`); no rule requires it elsewhere |
| Branded types for ambiguous domain quantities | convention (e.g. `OidString` in `model.ts`); no lint rule |
| Discriminated union exhaustiveness | no lint rule configured; relies on code review |
| Logic confined to `.ts`, `.vue` limited to props/emits/composable/template | no lint rule; relies on code review |

---

## Type generation from JSON Schema

```sh
just gen-types
# bunx json-schema-to-typescript ../traceformat/trace-format.schema.json -o src/lib/types.gen.ts
```

Do not hand-write trace record types. The generated file is excluded from all linters.

# OIDviz web toolchain guardrails

Stack: **Vue 3 + TypeScript + Bun + Vite**

---

## CI pipeline (`just ci`)

Run in this order. Stop at the first failure.

```
bunx oxlint -D all -c .oxlintrc.json --ignore-pattern "src/lib/types.gen.ts" src/   (~80ms)
bunx biome check --formatter-enabled=false --error-on-warnings src/                 (~95ms)
bunx eslint --max-warnings 0 src/                                                   (~930ms, .vue only)
bunx vue-tsc --noEmit --skipLibCheck                                                (~2-4s)
bunx biome check --linter-enabled=false src/                                        (<50ms)
bun test                                                                            (<100ms)
```

`just a11y` (build + axe-core check) runs separately before merge — zero WCAG 2.1 AA violations required.

---

## Justfile targets

| Target      | What it runs |
|-------------|---|
| `lint`      | oxlint + biome (warn=error) + eslint (warn=error) |
| `types`     | `vue-tsc --noEmit --skipLibCheck` |
| `fmt-check` | `biome check --linter-enabled=false` |
| `test`      | `bun test` |
| `ci`        | lint → types → fmt-check → test |
| `a11y`      | build → vite preview :4173 → axe-core → kill |
| `fmt`       | `biome format --write src/` |
| `gen-types` | `json-schema-to-typescript ../docs/trace-format.schema.json -o src/lib/types.gen.ts` |

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

For any plan longer than 6 tasks: after every 6 tasks, pause and dispatch an Opus agent to review the plan document for wrong, missing, or contradictory guidance. Implementation reveals plan errors that aren't visible upfront — a wrong instruction replicates across every subsequent task. The reviewer asks: *"Does any guidance here actively prevent correct implementation?"* Fix the plan before continuing.

---

## Type-driven development

**Principle: encode correctness in the type system. If a constraint can be a compile error, it must be.**

This means: discriminated unions with exhaustiveness checks, branded types for domain quantities where confusion is possible, and runtime validation before external data enters the typed domain. The compiler should catch the class of bug before tests run.

Logic that the compiler can validate lives in `.ts` files. `.vue` files contain only `defineProps`, `defineEmits`, a composable call, and the template.

---

## Type generation from JSON Schema

```sh
just gen-types
# bunx json-schema-to-typescript ../docs/trace-format.schema.json -o src/lib/types.gen.ts
```

Do not hand-write trace record types. The generated file is excluded from all linters.

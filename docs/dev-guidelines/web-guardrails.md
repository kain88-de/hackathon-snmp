# OIDviz web toolchain guardrails

Stack: **Vue 3 + TypeScript + Bun + Vite**

Toolchain commands and invocation rules — this is what `just ci` /
`oidviz-ci.yml` actually run. For architecture and process conventions that
aren't wired to any check, see
[`web-conventions.md`](web-conventions.md).

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
| Hard-coded hex in canvas | `getComputedStyle(canvas).getPropertyValue('--dim-*')` at draw time |

(Logic confined to `.ts` vs `.vue` is a convention, not a lint rule — see
`web-conventions.md`.)

---

## Type generation from JSON Schema

```sh
just gen-types
# bunx json-schema-to-typescript ../traceformat/trace-format.schema.json -o src/lib/types.gen.ts
```

Do not hand-write trace record types. The generated file is excluded from all linters.

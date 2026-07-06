# Conventions for oidviz/tests/component

Every Vitest `test()` must have a comment directly above it stating:

1. **The synthetic prop fact it relies on** — which factory (from `helpers.ts`)
   and which override values matter for this case. Don't make the reader
   scan the mount call to check whether a value like "rtt: 2000" or "2
   violations" is really what's being tested.
2. **The behavior contract being verified** — not what the code does (that's
   already readable from the locators/assertions below it), but *why* this
   prop value proves the component behaves correctly.

If a test doesn't depend on specific synthetic prop values (e.g. a purely
structural check like "the sidebar has three view buttons"), state the
behavior contract alone.

Bad — describes the code, not the prop or the behavior:

```ts
// Build an exchange with a violation and check its badge
test("violation badge", () => { ... });
```

Good — states the synthetic prop fact and the contract, and the title
describes the behavior instead of the implementation mechanism:

```ts
// makeExchange({ rtt: 1500, violations: ["oid-not-increasing"] }) — a row
// with violations must render a violation-count badge regardless of its RTT.
test("exchange with a violation shows a violation-count badge", () => { ... });
```

Test titles should describe the behavior under test, not the implementation
detail used to check it.

## Enforcement

The `local/require-test-comment` ESLint rule (`eslint.config.mjs`, scoped to
`tests/e2e/**/*.spec.ts` and `tests/component/**/*.test.ts`) fails
`just lint` / `just ci` if a `test()` call has no comment directly above it.
The rule can only check that *a* comment exists — it cannot verify the
comment states the right synthetic prop fact or contract. Getting that right
is a code-review responsibility.

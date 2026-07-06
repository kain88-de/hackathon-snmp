# Conventions for oidviz/tests/e2e

Every Playwright `test()` must have a comment directly above it stating:

1. **The fixture fact it relies on** — which fixture, which seq/row, what it
   actually contains. Fixture layouts are defined in `test-data/generate.mjs`;
   don't make the reader open that file to check whether a value like "seq 4"
   or "1 viol" is really correct test data.
2. **The behavior contract being verified** — not what the code does (that's
   already readable from the locators/assertions below it), but *why* this
   row/count proves the app behaves correctly.

If a test doesn't depend on specific fixture data (e.g. a purely structural
check like "the sidebar has three view buttons"), state the behavior contract
alone.

Bad — describes the code, not the fixture or the behavior:

```ts
// Find the row with seq 4 and check its violation badge
test("violation badge", async ({ page }) => { ... });
```

Good — states the fixture fact and the contract, and the title describes the
behavior instead of the implementation mechanism:

```ts
// canonical seq 4: 20ms, 1 violation ("oid-not-increasing"), 1 attempt. An
// exchange with violations must render a violation-count badge.
test("exchange with a violation shows a violation-count badge", async ({ page }) => { ... });
```

Test titles should describe the behavior under test, not the implementation
detail used to check it.

## Enforcement

The `local/require-test-comment` ESLint rule (`eslint.config.mjs`, scoped to
`tests/e2e/**/*.spec.ts`) fails `just lint` / `just ci` if a `test()` call has
no comment directly above it. The rule can only check that *a* comment
exists — it cannot verify the comment states the right fixture fact or
contract. Getting that right is a code-review responsibility.

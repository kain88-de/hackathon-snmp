import pluginVue from "eslint-plugin-vue";
import vueParser from "vue-eslint-parser";
import tsParser from "@typescript-eslint/parser";

// Requires a comment directly above every Playwright test() call. The rule
// only checks a comment exists — it cannot verify the comment states the
// right fixture fact and behavior contract; see tests/e2e/CLAUDE.md.
const localRules = {
  rules: {
    "require-test-comment": {
      meta: {
        type: "problem",
        docs: {
          description:
            "Playwright test() calls must have a preceding explanatory comment",
        },
        schema: [],
      },
      create(context) {
        return {
          CallExpression(node) {
            if (node.callee.type !== "Identifier" || node.callee.name !== "test") {
              return;
            }
            const sourceCode = context.sourceCode ?? context.getSourceCode();
            const comments = sourceCode.getCommentsBefore(node);
            if (comments.length === 0) {
              context.report({
                node,
                message:
                  "test() needs a comment above it stating the fixture fact (e.g. which seq/row) and the behavior being verified — see tests/e2e/CLAUDE.md.",
              });
            }
          },
        };
      },
    },
  },
};

export default [
  {
    files: ["**/*.vue"],
    plugins: {
      vue: pluginVue,
    },
    languageOptions: {
      parser: vueParser,
      parserOptions: {
        parser: tsParser,
        extraFileExtensions: [".vue"],
        sourceType: "module",
      },
    },
    rules: {
      ...pluginVue.configs["vue3-recommended"].rules,
    },
  },
  {
    files: ["tests/e2e/**/*.spec.ts"],
    plugins: {
      local: localRules,
    },
    languageOptions: {
      parser: tsParser,
      parserOptions: {
        sourceType: "module",
      },
    },
    rules: {
      "local/require-test-comment": "error",
    },
  },
];

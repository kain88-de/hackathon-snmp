#!/usr/bin/env bun
/**
 * Headless performance test for OIDviz prototypes.
 * Usage:  bun run oidviz/tools/perf_test.ts [--url http://localhost:8090]
 *
 * Loads each fixture trace via the perf-test.html page, reads the metrics
 * from the DOM, simulates scrolling to measure FPS, and prints a report.
 * Exits non-zero if any gate fails.
 */
import { chromium } from "playwright";

const BASE = (() => {
  const i = process.argv.indexOf("--url");
  return i !== -1 ? process.argv[i + 1] : "http://localhost:8090";
})();

const PAGE_URL = `${BASE}/oidviz/prototypes/perf-test.html`;

const FIXTURES = [
  {
    label: "5k",
    path: "/oidviz/tools/fixtures/trace-5k.oidtrace.jsonl.gz",
    gates: { parseMs: 500, renderMs: 50, fpsMin: 60, heightLimit: false },
  },
  {
    label: "50k",
    path: "/oidviz/tools/fixtures/trace-50k.oidtrace.jsonl.gz",
    gates: { parseMs: 2000, renderMs: 200, fpsMin: 60, heightLimit: false },
  },
  {
    label: "100k",
    path: "/oidviz/tools/fixtures/trace-100k.oidtrace.jsonl.gz",
    gates: { parseMs: 5000, renderMs: 500, fpsMin: 30, heightLimit: true },
  },
];

const SCROLL_STEPS = 20;
const SCROLL_STEP_PX = 300;

interface Metrics {
  exchanges: number;
  parseMs: number;
  renderMs: number;
  canvasHeightPx: number;
  canvasWidthPx: number;
  heightClipped: boolean;
  visibleRows: number;
  violations: number;
  endReason: string;
  scrollFps: number;
}

async function readMetrics(page: import("playwright").Page): Promise<Metrics> {
  // Use string-based evaluate to avoid tsx __name() transpilation artifacts
  return page.evaluate(`(() => {
    const txt = id => document.getElementById(id)?.textContent?.trim() ?? '';
    const num = id => parseFloat(txt(id).replace(/[^0-9.]/g, '')) || 0;
    const cheight = txt('m-cheight');
    return {
      exchanges: num('m-exchanges'),
      parseMs: num('m-parse'),
      renderMs: num('m-render'),
      canvasHeightPx: num('m-cheight'),
      canvasWidthPx: num('m-cwidth'),
      heightClipped: cheight.includes('clipped'),
      visibleRows: num('m-visible'),
      violations: num('m-violations'),
      endReason: txt('m-end'),
      scrollFps: num('fps-value'),
    };
  })()`);
}

async function measureScrollFps(page: import("playwright").Page): Promise<number> {
  await page.evaluate(`(() => {
    window.fpsSamples = [];
    const wrap = document.getElementById('chart-wrap');
    if (wrap) wrap.scrollTop = 0;
  })()`);

  const wrap = page.locator("#chart-wrap");
  for (let i = 0; i < SCROLL_STEPS; i++) {
    await wrap.evaluate((el: HTMLElement, px: number) => { el.scrollTop += px; }, SCROLL_STEP_PX);
    await page.waitForTimeout(16); // one frame gap
  }
  for (let i = 0; i < SCROLL_STEPS; i++) {
    await wrap.evaluate((el: HTMLElement, px: number) => { el.scrollTop -= px; }, SCROLL_STEP_PX);
    await page.waitForTimeout(16);
  }

  // Read the fps metric updated by scroll events
  const fps = await page.evaluate(`(() => {
    const el = document.getElementById('fps-value');
    return parseFloat(el?.textContent?.replace(/[^0-9.]/g, '') ?? '0') || 0;
  })()`) as number;
  return fps;
}

function colorize(pass: boolean, s: string): string {
  return pass ? `\x1b[32m${s}\x1b[0m` : `\x1b[31m${s}\x1b[0m`;
}

function check(label: string, value: number | boolean, pass: boolean): string {
  const v = typeof value === "boolean" ? String(value) : String(value);
  return `  ${colorize(pass, pass ? "✓" : "✗")} ${label.padEnd(20)} ${v}`;
}

async function runFixture(
  page: import("playwright").Page,
  fixture: (typeof FIXTURES)[0]
): Promise<boolean> {
  console.log(`\n── ${fixture.label} ──────────────────────────────`);

  await page.evaluate(`loadPath(${JSON.stringify(fixture.path)})`);

  // Wait for metrics to populate (exchange count appears)
  await page.waitForFunction(
    () => {
      const el = document.getElementById("m-exchanges");
      return el && el.textContent && el.textContent !== "—";
    },
    { timeout: 15000 }
  );

  const metrics = await readMetrics(page);
  const fps = await measureScrollFps(page);

  const g = fixture.gates;
  const parseOk = metrics.parseMs <= g.parseMs;
  const renderOk = metrics.renderMs <= g.renderMs;
  const fpsOk = fps >= g.fpsMin;
  const heightOk = metrics.heightClipped === g.heightLimit;

  console.log(check("parse", metrics.parseMs, parseOk) + `ms  (gate ≤${g.parseMs}ms)`);
  console.log(check("first render", metrics.renderMs, renderOk) + `ms  (gate ≤${g.renderMs}ms)`);
  console.log(check("scroll fps", fps, fpsOk) + `fps  (gate ≥${g.fpsMin}fps)`);
  console.log(check("canvas clipped", metrics.heightClipped, heightOk) + `  (expected ${g.heightLimit})`);
  console.log(`  ${"exchanges".padEnd(21)} ${metrics.exchanges.toLocaleString()}`);
  console.log(`  ${"visible rows".padEnd(21)} ${metrics.visibleRows.toLocaleString()}`);
  console.log(`  ${"canvas height".padEnd(21)} ${metrics.canvasHeightPx.toLocaleString()}px`);
  console.log(`  ${"canvas width".padEnd(21)} ${metrics.canvasWidthPx.toLocaleString()}px`);
  console.log(`  ${"violations".padEnd(21)} ${metrics.violations}`);
  console.log(`  ${"end reason".padEnd(21)} ${metrics.endReason}`);

  return parseOk && renderOk && fpsOk && heightOk;
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.setViewportSize({ width: 1280, height: 800 });

  console.log(`\nOIDviz performance test  →  ${PAGE_URL}`);
  await page.goto(PAGE_URL);

  let allPassed = true;
  for (const fixture of FIXTURES) {
    const passed = await runFixture(page, fixture);
    if (!passed) allPassed = false;

    await page.evaluate(`if (typeof reset === 'function') reset()`);
    await page.waitForFunction(
      `!document.getElementById('drop-zone')?.classList.contains('hidden')`,
      { timeout: 2000 }
    ).catch(() => {});
  }

  await browser.close();

  console.log(
    allPassed
      ? "\n\x1b[32m✓ All gates passed\x1b[0m\n"
      : "\n\x1b[31m✗ Some gates failed\x1b[0m\n"
  );
  process.exit(allPassed ? 0 : 1);
}

main();

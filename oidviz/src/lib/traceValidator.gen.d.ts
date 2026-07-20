// Hand-written; paired with the generated traceValidator.gen.js. This shape
// is stable across schema changes — only the .js needs regenerating
// (`just gen-validator`) when trace-format.schema.json changes.
import type { Exchange, Header, Summary, SystemInfo } from "./types.gen.ts";

export declare const validateHeader: (data: unknown) => data is Header;
export declare const validateSystemInfo: (data: unknown) => data is SystemInfo;
export declare const validateExchange: (data: unknown) => data is Exchange;
export declare const validateSummary: (data: unknown) => data is Summary;

<script setup lang="ts">
import { computed, ref } from "vue";
import type {
	ActiveView,
	AppState,
	FacetState,
	ParseResult,
} from "../lib/model.ts";

const props = defineProps<{
	appState: AppState;
	result: ParseResult | null;
	facetState: FacetState;
	activeView: ActiveView;
}>();

const emit = defineEmits<{
	"file-selected": [buffer: ArrayBuffer];
	"file-error": [message: string];
	"view-change": [view: ActiveView];
	"facet-change": [patch: Partial<FacetState>];
}>();

const fileInputRef = ref<HTMLInputElement | null>(null);

const MS_PER_SECOND = 1000;

const viewLabels: Record<ActiveView, string> = {
	findings: "Findings",
	minimap: "Minimap + Detail",
	oidtree: "OID Tree",
};

const views: ActiveView[] = ["findings", "minimap", "oidtree"];

function openFilePicker(): void {
	fileInputRef.value?.click();
}

function onFileChange(event: Event): void {
	const input = event.target as HTMLInputElement;
	const file = input.files?.[0];
	if (!file) {
		return;
	}
	file
		.arrayBuffer()
		.then((buffer): void => {
			emit("file-selected", buffer);
		})
		.catch((error: unknown): void => {
			const message =
				error instanceof Error ? error.message : "Failed to read file";
			emit("file-error", message);
		});
	// Reset so the same file can be re-selected
	input.value = "";
}

const slowThresholdSeconds = computed(
	(): number => props.facetState.slowMs / MS_PER_SECOND,
);

function onSlowThresholdChange(event: Event): void {
	const seconds = Number((event.target as HTMLInputElement).value);
	if (!Number.isNaN(seconds) && seconds > 0) {
		emit("facet-change", { slowMs: seconds * MS_PER_SECOND });
	}
}

const SYSDESCR_OID = "1.3.6.1.2.1.1.1.0";
const SYSOID_OID = "1.3.6.1.2.1.1.2.0";
const SYSUPTIME_OID = "1.3.6.1.2.1.1.3.0";
const SECONDS_PER_MINUTE = 60;

interface DeviceInfo {
	sysDescr: string;
	sysObjectId: string;
	sysUpTime: string;
}

interface WalkInfo {
	duration: string;
	endReason: string;
	exchangeCount: number;
	label: string;
	oidsSeen: number | string;
	parseMs: number;
	snmpVersion: string;
	startOid: string;
	violations: number;
}

interface WalkConfig {
	bulkSize: number;
	resumeFrom: string | null;
	retries: number;
	timeBudgetS: number | null;
	timeoutS: number;
}

const deviceInfo = computed((): DeviceInfo | null => {
	const si = props.result?.systemInfo;
	if (!si || si.point !== "start") {
		return null;
	}
	const get = (oid: string): string => {
		const val = si.values[oid];
		if (val === undefined || val === null) {
			return "—";
		}
		return String(val).split("\n")[0] || "—";
	};
	return {
		sysDescr: get(SYSDESCR_OID),
		sysObjectId: get(SYSOID_OID),
		sysUpTime: get(SYSUPTIME_OID),
	};
});

const walkInfo = computed((): WalkInfo | null => {
	const r = props.result;
	if (!r) {
		return null;
	}
	const violations = r.summary
		? Object.values(r.summary.violation_counts).reduce(
				(a: number, b: number): number => a + b,
				0,
			)
		: 0;
	const durationSec = r.summary?.at ?? null;
	let duration = "—";
	if (durationSec !== null) {
		duration =
			durationSec < SECONDS_PER_MINUTE
				? `${durationSec.toFixed(1)}s`
				: `${Math.floor(durationSec / SECONDS_PER_MINUTE)}m ${(durationSec % SECONDS_PER_MINUTE).toFixed(0)}s`;
	}
	return {
		duration,
		endReason: r.summary?.end_reason ?? "—",
		exchangeCount: r.exchanges.length,
		label: r.header.label ?? "—",
		oidsSeen: r.summary?.oids_seen ?? "—",
		parseMs: r.parseMs,
		snmpVersion: r.header.snmp.version,
		startOid: r.header.settings.start_oid,
		violations,
	};
});

const walkConfig = computed((): WalkConfig | null => {
	const r = props.result;
	if (!r) {
		return null;
	}
	const s = r.header.settings;
	return {
		bulkSize: s.bulk_size,
		resumeFrom: (s.resume_from as string | undefined) ?? null,
		retries: s.retries,
		timeBudgetS: s.time_budget_s ?? null,
		timeoutS: s.timeout_s,
	};
});
</script>

<template>
	<aside class="sidebar" aria-label="Controls">
		<!-- Brand -->
		<div class="sidebar-brand">
			<span class="sidebar-brand-name">OIDviz</span>
			<span class="sidebar-brand-sub">.oidtrace viewer</span>
		</div>

		<!-- File section (viewer phase only) -->
		<section v-if="appState.phase === 'viewer'" class="sidebar-section">
			<button class="sidebar-btn" type="button" @click="openFilePicker">
				Open file
			</button>
			<input
				ref="fileInputRef"
				type="file"
				accept=".gz"
				class="visually-hidden"
				aria-hidden="true"
				tabindex="-1"
				@change="onFileChange"
			/>
		</section>

		<!-- Device section -->
		<section v-if="deviceInfo" class="sidebar-section">
			<div class="sidebar-section-title">Device</div>
			<div class="info-row">
				<span class="info-key">sysDescr</span>
				<span class="info-val" :title="deviceInfo.sysDescr">{{ deviceInfo.sysDescr }}</span>
			</div>
			<div class="info-row">
				<span class="info-key">sysObjectID</span>
				<span class="info-val" :title="deviceInfo.sysObjectId">{{ deviceInfo.sysObjectId }}</span>
			</div>
			<div class="info-row">
				<span class="info-key">sysUpTime</span>
				<span class="info-val">{{ deviceInfo.sysUpTime }}</span>
			</div>
		</section>

		<!-- Walk info section -->
		<section v-if="walkInfo" class="sidebar-section">
			<div class="sidebar-section-title">Walk info</div>
			<div class="info-row">
				<span class="info-key">Label</span>
				<span class="info-val" :title="walkInfo.label">{{ walkInfo.label }}</span>
			</div>
			<div class="info-row">
				<span class="info-key">SNMP</span>
				<span class="info-val">v{{ walkInfo.snmpVersion }}</span>
			</div>
			<div class="info-row">
				<span class="info-key">Start OID</span>
				<span class="info-val" :title="walkInfo.startOid">{{ walkInfo.startOid }}</span>
			</div>
			<div class="info-row">
				<span class="info-key">Exchanges</span>
				<span class="info-val">{{ walkInfo.exchangeCount }}</span>
			</div>
			<div class="info-row">
				<span class="info-key">OIDs seen</span>
				<span class="info-val">{{ walkInfo.oidsSeen }}</span>
			</div>
			<div class="info-row">
				<span class="info-key">Duration</span>
				<span class="info-val">{{ walkInfo.duration }}</span>
			</div>
			<div class="info-row">
				<span class="info-key">Violations</span>
				<span class="info-val" :class="walkInfo.violations > 0 ? 'info-val--err' : 'info-val--ok'">{{ walkInfo.violations }}</span>
			</div>
			<div class="info-row">
				<span class="info-key">End reason</span>
				<span class="info-val" :title="walkInfo.endReason">{{ walkInfo.endReason }}</span>
			</div>
			<div class="info-row">
				<span class="info-key">Parse time</span>
				<span class="info-val">{{ walkInfo.parseMs }}ms</span>
			</div>
		</section>

		<!-- Walk config section -->
		<section v-if="walkConfig" class="sidebar-section">
			<div class="sidebar-section-title">Walk config</div>
			<div class="info-row">
				<span class="info-key">Bulk size</span>
				<span class="info-val">{{ walkConfig.bulkSize }}</span>
			</div>
			<div class="info-row">
				<span class="info-key">Timeout</span>
				<span class="info-val">{{ walkConfig.timeoutS }}s</span>
			</div>
			<div class="info-row">
				<span class="info-key">Retries</span>
				<span class="info-val">{{ walkConfig.retries }}</span>
			</div>
			<div v-if="walkConfig.timeBudgetS !== null" class="info-row">
				<span class="info-key">Budget</span>
				<span class="info-val">{{ walkConfig.timeBudgetS }}s</span>
			</div>
			<div v-if="walkConfig.resumeFrom !== null" class="info-row">
				<span class="info-key">Resume</span>
				<span class="info-val" :title="walkConfig.resumeFrom">{{ walkConfig.resumeFrom }}</span>
			</div>
		</section>

		<!-- View navigation -->
		<nav class="sidebar-section" aria-label="Views">
			<button
				v-for="view in views"
				:key="view"
				type="button"
				class="sidebar-nav-btn"
				:class="{ 'sidebar-nav-btn--active': activeView === view }"
				:aria-current="activeView === view ? 'page' : undefined"
				@click="emit('view-change', view)"
			>
				{{ viewLabels[view] }}
			</button>
		</nav>

		<!-- Facet controls -->
		<section class="sidebar-section sidebar-facets">
			<!-- Performance facet -->
			<fieldset class="sidebar-fieldset">
				<legend class="sidebar-legend">Performance</legend>
				<label v-for="opt in [
					{ value: 'any', label: 'Any' },
					{ value: 'fast', label: 'Fast' },
					{ value: 'slow', label: 'Slow' },
					{ value: 'timeout', label: 'Timed out' },
				]" :key="opt.value" class="sidebar-radio-label">
					<input
						type="radio"
						name="perf"
						:value="opt.value"
						:checked="facetState.perf === opt.value"
						@change="emit('facet-change', { perf: opt.value as FacetState['perf'] })"
					/>
					{{ opt.label }}
				</label>
			</fieldset>

			<!-- Correctness facet -->
			<fieldset class="sidebar-fieldset">
				<legend class="sidebar-legend">Correctness</legend>
				<label class="sidebar-radio-label">
					<input
						type="radio"
						name="corr"
						value="any"
						:checked="facetState.corr === 'any'"
						@change="emit('facet-change', { corr: 'any' })"
					/>
					Any
				</label>
				<label class="sidebar-radio-label">
					<input
						type="radio"
						name="corr"
						value="violations"
						:checked="facetState.corr === 'violations'"
						@change="emit('facet-change', { corr: 'violations' })"
					/>
					Violations only
				</label>
			</fieldset>

			<!-- Retry filter -->
			<label class="sidebar-checkbox-label">
				<input
					type="checkbox"
					:checked="facetState.retryOnly"
					@change="emit('facet-change', { retryOnly: ($event.target as HTMLInputElement).checked })"
				/>
				Retries only
			</label>

			<!-- Slow threshold -->
			<label class="sidebar-input-label">
				<span>Slow threshold (s)</span>
				<input
					type="number"
					class="sidebar-number-input"
					min="0.1"
					step="0.1"
					:value="slowThresholdSeconds"
					@change="onSlowThresholdChange"
				/>
			</label>
		</section>

		<!-- Truncation warning -->
		<div
			role="status"
			aria-live="polite"
			class="sidebar-truncation"
			:class="{ 'sidebar-truncation--visible': result?.truncated === true }"
		>
			<span v-if="result?.truncated === true">
				Warning: trace was truncated
			</span>
		</div>
	</aside>
</template>

<style scoped>
.sidebar-brand {
	padding: 16px 12px 14px;
	border-bottom: 1px solid var(--sidebar-border);
	display: flex;
	flex-direction: column;
	gap: 2px;
}

.sidebar-brand-name {
	font-size: 18px;
	font-weight: 700;
	color: var(--sidebar-text);
	letter-spacing: -0.02em;
	line-height: 1;
}

.sidebar-brand-sub {
	font-size: 11px;
	color: var(--sidebar-muted);
	font-family: var(--font-mono);
	letter-spacing: 0.01em;
}

.sidebar {
	width: 220px;
	flex-shrink: 0;
	display: flex;
	flex-direction: column;
	background: var(--sidebar-bg);
	color: var(--sidebar-text);
	border-right: 1px solid var(--sidebar-border);
	height: 100%;
	overflow-y: auto;
}

.sidebar-section {
	display: flex;
	flex-direction: column;
	gap: 4px;
	padding: 12px;
	border-bottom: 1px solid var(--sidebar-border);
}

.sidebar-btn {
	background: var(--sidebar-border);
	color: var(--sidebar-text);
	border: 1px solid var(--sidebar-border);
	border-radius: 4px;
	padding: 6px 10px;
	cursor: pointer;
	font-size: 13px;
	text-align: left;
}

.sidebar-btn:hover {
	background: var(--sidebar-muted);
}

.visually-hidden {
	position: absolute;
	width: 1px;
	height: 1px;
	padding: 0;
	margin: -1px;
	overflow: hidden;
	clip: rect(0, 0, 0, 0);
	white-space: nowrap;
	border: 0;
}

.sidebar-nav-btn {
	background: transparent;
	color: var(--sidebar-text);
	border: none;
	border-radius: 4px;
	padding: 6px 10px;
	cursor: pointer;
	font-size: 13px;
	text-align: left;
}

.sidebar-nav-btn:hover {
	background: var(--sidebar-border);
}

.sidebar-nav-btn--active {
	background: var(--color-primary);
	color: var(--sidebar-text-active);
}

.sidebar-facets {
	gap: 12px;
}

.sidebar-fieldset {
	border: 1px solid var(--sidebar-border);
	border-radius: 4px;
	padding: 8px;
}

.sidebar-legend {
	color: var(--sidebar-muted);
	font-size: 11px;
	text-transform: uppercase;
	letter-spacing: 0.05em;
	padding: 0 4px;
}

.sidebar-radio-label {
	display: flex;
	align-items: center;
	gap: 6px;
	font-size: 13px;
	cursor: pointer;
	padding: 2px 0;
}

.sidebar-checkbox-label {
	display: flex;
	align-items: center;
	gap: 6px;
	font-size: 13px;
	cursor: pointer;
}

.sidebar-input-label {
	display: flex;
	flex-direction: column;
	gap: 4px;
	font-size: 13px;
}

.sidebar-number-input {
	background: var(--sidebar-border);
	color: var(--sidebar-text);
	border: 1px solid var(--sidebar-border);
	border-radius: 4px;
	padding: 4px 8px;
	font-size: 13px;
	width: 80px;
}

.sidebar-truncation {
	padding: 8px 12px;
	font-size: 12px;
	color: var(--dim-timeout);
	display: none;
}

.sidebar-truncation--visible {
	display: block;
}

.sidebar-section-title {
	font-size: 10px;
	font-weight: 700;
	text-transform: uppercase;
	letter-spacing: 0.06em;
	color: var(--sidebar-muted);
	margin-bottom: 6px;
}

.info-row {
	display: flex;
	justify-content: space-between;
	align-items: baseline;
	gap: 8px;
	padding: 2px 0;
}

.info-key {
	color: var(--sidebar-muted);
	font-size: 11px;
	flex-shrink: 0;
}

.info-val {
	font-family: var(--font-mono);
	font-size: 11px;
	font-weight: 600;
	text-align: right;
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
	max-width: 130px;
	color: var(--sidebar-text);
}

.info-val--ok {
	color: #4ade80;
}

.info-val--err {
	color: #f87171;
}
</style>

<script setup lang="ts">
import { ref } from "vue";
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
	file.arrayBuffer().then((buffer): void => {
		emit("file-selected", buffer);
	});
	// Reset so the same file can be re-selected
	input.value = "";
}

function slowThresholdSeconds(): number {
	return props.facetState.slowMs / MS_PER_SECOND;
}

function onSlowThresholdChange(event: Event): void {
	const seconds = Number((event.target as HTMLInputElement).value);
	if (!Number.isNaN(seconds) && seconds > 0) {
		emit("facet-change", { slowMs: seconds * MS_PER_SECOND });
	}
}
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
					:value="slowThresholdSeconds()"
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
</style>

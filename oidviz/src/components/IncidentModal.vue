<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import type { DomainExchange, Incident } from "../lib/model.ts";

const props = defineProps<{
	incident: Incident;
	exchanges: DomainExchange[];
	index: number;
	total: number;
}>();

const emit = defineEmits<{ close: []; navigate: [delta: number] }>();

const titleEl = ref<HTMLElement | null>(null);
const panelEl = ref<HTMLElement | null>(null);

// The exchanges visible in the table: incident members that exist in the
// filtered exchanges array (undefined indices are absent from filteredExchanges).
const memberExchanges = computed((): DomainExchange[] => {
	const result: DomainExchange[] = [];
	for (const idx of props.incident.members) {
		const ex = props.exchanges[idx];
		if (ex !== undefined) {
			result.push(ex);
		}
	}
	return result;
});

function onKeydown(e: KeyboardEvent): void {
	if (e.key === "Escape") {
		emit("close");
	}
}

onMounted((): void => {
	document.addEventListener("keydown", onKeydown);
	// Move focus to the dialog heading
	titleEl.value?.focus();
});

onBeforeUnmount((): void => {
	document.removeEventListener("keydown", onKeydown);
});
</script>

<template>
	<div class="modal-overlay" @click.self="emit('close')">
		<div
			ref="panelEl"
			class="modal-panel"
			role="dialog"
			aria-modal="true"
			:aria-labelledby="`incident-title-${index}`"
		>
			<div class="modal-header">
				<h2
					:id="`incident-title-${index}`"
					ref="titleEl"
					class="modal-title"
					tabindex="-1"
				>
					Incident {{ index + 1 }} of {{ total }} — {{ incident.region }}
				</h2>
				<button class="close-btn" aria-label="Close" @click="emit('close')">
					✕
				</button>
			</div>

			<div class="modal-meta">
				<span class="meta-item">Score: <strong>{{ incident.score }}</strong></span>
				<span class="meta-item">Peak RTT: <strong>{{ incident.peakRtt }}ms</strong></span>
				<span v-if="incident.timeoutCount > 0" class="meta-item chip chip-timeout">
					{{ incident.timeoutCount }} timeout{{ incident.timeoutCount > 1 ? 's' : '' }}
				</span>
				<span v-if="incident.retryCount > 0" class="meta-item chip chip-retry">
					{{ incident.retryCount }} retries
				</span>
				<span v-if="incident.violationTypes.size > 0" class="meta-item chip chip-violation">
					{{ incident.violationTypes.size }} violation type{{ incident.violationTypes.size > 1 ? 's' : '' }}
				</span>
			</div>

			<div class="modal-nav">
				<button
					:disabled="index <= 0"
					@click="emit('navigate', -1)"
				>
					← Prev
				</button>
				<span class="nav-label">{{ index + 1 }} / {{ total }}</span>
				<button
					:disabled="index >= total - 1"
					@click="emit('navigate', 1)"
				>
					Next →
				</button>
			</div>

			<div class="exchange-table-wrap">
				<p v-if="memberExchanges.length === 0" class="no-members">
					No matching exchanges.
				</p>
				<table v-else class="exchange-table">
					<thead>
						<tr>
							<th>OID</th>
							<th>RTT</th>
							<th>Attempts</th>
							<th>Violations</th>
						</tr>
					</thead>
					<tbody>
						<tr
							v-for="ex in memberExchanges"
							:key="ex.seq"
						>
							<td class="td-oid" :title="ex.requestOid">{{ ex.requestOid }}</td>
							<td :class="ex.isTimeout ? 'td-timeout' : ex.rtt > 1000 ? 'td-slow' : ''">
								{{ ex.isTimeout ? 'timeout' : ex.rtt + 'ms' }}
							</td>
							<td>{{ ex.attemptCount }}</td>
							<td>{{ ex.violations.join(', ') }}</td>
						</tr>
					</tbody>
				</table>
			</div>
		</div>
	</div>
</template>

<style scoped>
.modal-overlay {
	position: fixed;
	inset: 0;
	background: rgba(0, 0, 0, 0.45);
	display: flex;
	align-items: center;
	justify-content: center;
	z-index: 100;
}

.modal-panel {
	background: var(--color-surface);
	border: 1px solid var(--color-border);
	border-radius: 8px;
	width: min(720px, 95vw);
	max-height: 80vh;
	display: flex;
	flex-direction: column;
	overflow: hidden;
	box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
}

.modal-header {
	display: flex;
	align-items: center;
	justify-content: space-between;
	padding: 16px 20px 12px;
	border-bottom: 1px solid var(--color-border);
	flex-shrink: 0;
}

.modal-title {
	font-size: 16px;
	font-weight: 600;
	margin: 0;
	color: var(--color-text);
}

.modal-title:focus {
	outline: none;
}

.close-btn {
	background: none;
	border: none;
	cursor: pointer;
	font-size: 16px;
	color: var(--color-text-muted);
	padding: 4px 8px;
	border-radius: 4px;
}

.close-btn:hover {
	background: var(--color-primary-bg);
}

.modal-meta {
	display: flex;
	flex-wrap: wrap;
	gap: 8px;
	padding: 12px 20px;
	border-bottom: 1px solid var(--color-border);
	flex-shrink: 0;
}

.meta-item {
	font-size: 13px;
	color: var(--color-text);
}

.modal-nav {
	display: flex;
	align-items: center;
	gap: 12px;
	padding: 8px 20px;
	border-bottom: 1px solid var(--color-border);
	flex-shrink: 0;
}

.modal-nav button {
	padding: 4px 10px;
	border: 1px solid var(--color-border);
	background: var(--color-surface);
	border-radius: 4px;
	cursor: pointer;
	font-size: 13px;
	color: var(--color-text);
}

.modal-nav button:disabled {
	opacity: 0.4;
	cursor: not-allowed;
}

.nav-label {
	font-size: 13px;
	color: var(--color-text-muted);
}

.exchange-table-wrap {
	overflow-y: auto;
	flex: 1;
}

.no-members {
	padding: 20px;
	color: var(--color-text-muted);
	text-align: center;
}

.exchange-table {
	width: 100%;
	border-collapse: collapse;
	font-size: 12px;
	font-family: var(--font-mono);
}

.exchange-table th {
	text-align: left;
	padding: 6px 12px;
	background: var(--color-bg);
	border-bottom: 1px solid var(--color-border);
	font-size: 11px;
	font-weight: 600;
	color: var(--color-text-muted);
	position: sticky;
	top: 0;
}

.exchange-table td {
	padding: 5px 12px;
	border-bottom: 1px solid var(--color-border);
	color: var(--color-text);
}

.td-oid {
	max-width: 260px;
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
}

.td-timeout {
	color: var(--dim-timeout);
}

.td-slow {
	color: var(--dim-slow);
}

.chip {
	font-size: 11px;
	padding: 2px 6px;
	border-radius: 3px;
	white-space: nowrap;
}

.chip-timeout {
	color: var(--dim-timeout);
	background: var(--dim-timeout-bg);
}

.chip-retry {
	color: var(--dim-retry);
	background: var(--dim-retry-bg);
}

.chip-violation {
	color: var(--dim-violation);
	background: var(--dim-violation-bg);
}
</style>

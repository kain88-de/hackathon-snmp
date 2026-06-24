<script setup lang="ts">
import { ref } from "vue";

type AppState =
	| { phase: "landing" }
	| { phase: "loading" }
	| { phase: "viewer"; result: { [k: string]: never } }
	| { phase: "error"; message: string };

defineProps<{ appState: AppState }>();

const emit = defineEmits<{ "file-selected": [buffer: ArrayBuffer] }>();

const isDragOver = ref(false);
const fileInputRef = ref<HTMLInputElement | undefined>(undefined);

function openPicker(): void {
	if (fileInputRef.value !== undefined) {
		fileInputRef.value.click();
	}
}

function onKeyDown(event: KeyboardEvent): void {
	if (event.key === "Enter" || event.key === " ") {
		event.preventDefault();
		openPicker();
	}
}

function onDragOver(event: DragEvent): void {
	event.preventDefault();
	isDragOver.value = true;
}

function onDragLeave(): void {
	isDragOver.value = false;
}

function onDrop(event: DragEvent): void {
	event.preventDefault();
	isDragOver.value = false;
	if (event.dataTransfer !== null && event.dataTransfer !== undefined) {
		const file = event.dataTransfer.files.item(0);
		if (file !== null) {
			readFile(file);
		}
	}
}

function onFileChange(event: Event): void {
	const input = event.target as HTMLInputElement;
	if (input.files !== null) {
		const file = input.files.item(0);
		if (file !== null) {
			readFile(file);
		}
	}
}

function readFile(file: File): void {
	file
		.arrayBuffer()
		.then((buffer): void => {
			emit("file-selected", buffer);
		})
		.catch((): void => {
			// error handling is task 2
		});
}
</script>

<template>
	<div class="landing-root">
		<div
			v-if="appState.phase === 'loading'"
			class="loading-overlay"
			role="status"
			aria-label="Loading trace file"
		>
			<div class="spinner" aria-hidden="true" />
			<p class="loading-text">Loading trace…</p>
		</div>

		<div
			v-else
			class="drop-zone"
			role="region"
			aria-label="Drop zone for OID trace files"
			tabindex="0"
			:class="{ 'drag-over': isDragOver }"
			@dragover="onDragOver"
			@dragleave="onDragLeave"
			@drop="onDrop"
			@keydown="onKeyDown"
			@click="openPicker"
		>
			<p class="drop-title">Drop an OID trace file</p>
			<p class="drop-sub">
				or press <kbd>Enter</kbd> / <kbd>Space</kbd> to browse
			</p>
			<p class="drop-format">
				Accepts <code>.oidtrace.jsonl.gz</code>
			</p>
		</div>

		<input
			ref="fileInputRef"
			type="file"
			accept=".gz,.jsonl.gz"
			class="file-input-hidden"
			aria-hidden="true"
			tabindex="-1"
			@change="onFileChange"
		/>

		<div
			v-if="appState.phase === 'error'"
			role="alert"
			class="error-banner"
		>
			{{ appState.message }}
		</div>
	</div>
</template>

<style scoped>
.landing-root {
	flex: 1;
	display: flex;
	flex-direction: column;
	align-items: center;
	justify-content: center;
	gap: 12px;
	padding: 40px;
}

.drop-zone {
	border: 2px dashed var(--color-border);
	border-radius: 12px;
	padding: 48px 64px;
	text-align: center;
	background: var(--color-surface);
	cursor: pointer;
	transition:
		border-color 0.15s,
		background 0.15s;
	min-width: 300px;
	outline: none;
}

.drop-zone:hover,
.drop-zone:focus-visible,
.drop-zone.drag-over {
	border-color: var(--color-primary);
	background: var(--color-primary-bg);
}

.drop-title {
	font-size: 18px;
	font-weight: 600;
	margin-bottom: 6px;
	color: var(--color-text);
}

.drop-sub {
	font-size: 13px;
	color: var(--color-text-muted);
	margin-bottom: 4px;
}

.drop-format {
	font-size: 12px;
	color: var(--color-text-muted);
}

.drop-format code {
	font-family: var(--font-mono);
	color: var(--color-text);
}

kbd {
	font-family: var(--font-mono);
	font-size: 11px;
	background: var(--color-bg);
	border: 1px solid var(--color-border);
	border-radius: 3px;
	padding: 1px 5px;
}

.file-input-hidden {
	display: none;
}

.loading-overlay {
	display: flex;
	flex-direction: column;
	align-items: center;
	gap: 16px;
}

.spinner {
	width: 40px;
	height: 40px;
	border: 3px solid var(--color-border);
	border-top-color: var(--color-primary);
	border-radius: 50%;
	animation: spin 0.7s linear infinite;
}

@keyframes spin {
	to {
		transform: rotate(360deg);
	}
}

.loading-text {
	color: var(--color-text-muted);
	font-size: 14px;
}

.error-banner {
	background: var(--dim-timeout-bg);
	color: var(--dim-timeout);
	border: 1px solid var(--dim-timeout);
	border-radius: 6px;
	padding: 10px 16px;
	max-width: 480px;
	font-size: 13px;
}
</style>

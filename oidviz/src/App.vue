<script setup lang="ts">
import { ref } from "vue";
import LandingScreen from "./components/LandingScreen.vue";

type AppState =
	| { phase: "landing" }
	| { phase: "loading" }
	| { phase: "viewer"; result: ParseResult }
	| { phase: "error"; message: string };

// ParseResult is a placeholder for task 2 (worker + parsing)
interface ParseResult {
	[k: string]: never;
}

const state = ref<AppState>({ phase: "landing" });

function onFileSelected(_buffer: ArrayBuffer): void {
	state.value = { phase: "loading" };
}
</script>

<template>
	<LandingScreen
		v-if="state.phase === 'landing' || state.phase === 'loading'"
		:app-state="state"
		@file-selected="onFileSelected"
	/>
</template>

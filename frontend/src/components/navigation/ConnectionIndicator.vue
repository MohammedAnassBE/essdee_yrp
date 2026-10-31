<template>
	<span
		v-if="indicator"
		class="app-connection"
		:class="`app-connection--${indicator.tone}`"
		role="status"
		:aria-label="indicator.title"
		:title="indicator.title"
	>
		<span class="app-connection__dot" aria-hidden="true" />
		<span v-if="indicator.label" class="app-connection__label">{{ indicator.label }}</span>
		<span v-if="indicator.shortLabel" class="app-connection__label app-connection__label--short">{{ indicator.shortLabel }}</span>
	</span>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue"

import { hasLiveRooms, realtimeStatus } from "../../api/realtime.js"
import { getConnectionIndicator } from "./connectionIndicator.js"

const isBrowserOnline = ref(globalThis.navigator?.onLine ?? true)
const indicator = computed(() => getConnectionIndicator({ status: realtimeStatus.value, hasLiveUse: hasLiveRooms.value, isBrowserOnline: isBrowserOnline.value }))

function updateOnline() { isBrowserOnline.value = globalThis.navigator?.onLine ?? true }
onMounted(() => {
	window.addEventListener("online", updateOnline)
	window.addEventListener("offline", updateOnline)
})
onBeforeUnmount(() => {
	window.removeEventListener("online", updateOnline)
	window.removeEventListener("offline", updateOnline)
})
</script>

<style scoped>
.app-connection { display: inline-flex; flex: 0 1 auto; align-items: center; gap: 6px; min-width: 0; min-height: 24px; padding: 2px 8px; overflow: hidden; color: var(--erp-text-secondary); font-size: var(--erp-font-size-caption); font-weight: var(--erp-font-weight-semibold); white-space: nowrap; border-radius: 999px; cursor: default; }
.app-connection__dot { flex: 0 0 auto; width: 8px; height: 8px; border-radius: 50%; background: currentColor; }
.app-connection__label { min-width: 0; overflow: hidden; text-overflow: ellipsis; }
.app-connection__label--short { display: none; }
.app-connection--connected { padding-inline: 4px; color: var(--erp-success); }
.app-connection--connected .app-connection__dot { width: 7px; height: 7px; opacity: .7; }
.app-connection--connecting { color: var(--erp-warning); background: var(--erp-warning-soft); }
.app-connection--offline { color: var(--erp-danger); background: var(--erp-danger-soft); }
@media (prefers-reduced-motion: no-preference) {
	.app-connection--connecting .app-connection__dot { animation: app-connection-pulse 1.2s ease-in-out infinite; }
}
@keyframes app-connection-pulse { 50% { opacity: .35; } }
@media (max-width: 900px) {
	.app-connection__label { display: none; }
	.app-connection__label--short { display: inline; }
}
/* Phones: a badge on the top bar's corner, so the nav buttons keep their room. */
@media (max-width: 540px) {
	.app-connection { position: absolute; top: 5px; left: 5px; min-height: 0; padding: 2px; background: var(--erp-surface); }
	.app-connection__label--short { display: none; }
}
</style>

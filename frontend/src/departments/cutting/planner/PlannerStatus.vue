<template>
	<section class="planner-status" :class="`planner-status--${slug(status)}`" aria-label="Optimization status">
		<div class="planner-status__icon"><i :class="icon"></i></div>
		<div class="planner-status__copy"><span>Optimization</span><strong>{{ status }}</strong><small>{{ message }}</small></div>
		<div v-if="started || completed" class="planner-status__times"><span v-if="started">Started <strong>{{ formatDisplayDatetime(started, { fallback: "" }) }}</strong></span><span v-if="completed">Completed <strong>{{ formatDisplayDatetime(completed, { fallback: "" }) }}</strong></span></div>
	</section>
</template>

<script setup>
import { computed } from "vue"
import { formatDisplayDatetime } from "../../../utils/dateFormat.js"

const props = defineProps({ status: { type: String, default: "Not Started" }, error: { type: String, default: "" }, started: { type: String, default: "" }, completed: { type: String, default: "" } })
const icon = computed(() => props.status === "Completed" ? "pi pi-check-circle" : props.status === "Failed" ? "pi pi-exclamation-triangle" : ["Queued", "Running"].includes(props.status) ? "pi pi-spin pi-spinner" : "pi pi-sliders-h")
const message = computed(() => props.status === "Failed" ? props.error || "No feasible lay plan was found." : props.status === "Completed" ? "The strategy portfolio is ready for comparison." : props.status === "Running" ? "Strategies are running on the long worker." : props.status === "Queued" ? "Waiting for the long worker to start." : "Save the inputs, then run Optimize.")
function slug(value) { return String(value).toLowerCase().replaceAll(" ", "-") }
</script>

<style scoped>
.planner-status { display: flex; min-height: 66px; padding: 10px 13px; align-items: center; gap: 10px; color: var(--erp-text); background: var(--erp-surface-soft); border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); }.planner-status__icon { display: grid; width: 34px; height: 34px; flex: 0 0 auto; place-items: center; color: var(--erp-accent); background: var(--erp-accent-soft); border-radius: 50%; }.planner-status__copy { display: grid; min-width: 0; gap: 1px; }.planner-status__copy > span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 720; letter-spacing: .04em; text-transform: uppercase; }.planner-status__copy > strong { font-size: var(--erp-font-size-caption); }.planner-status__copy > small { overflow: hidden; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); text-overflow: ellipsis; white-space: nowrap; }.planner-status__times { display: flex; margin-left: auto; align-items: center; gap: 16px; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }.planner-status__times span { display: grid; gap: 1px; }.planner-status__times strong { color: var(--erp-text); font-weight: 650; }.planner-status--completed .planner-status__icon { color: var(--erp-success-text); background: var(--erp-success-soft); }.planner-status--failed { border-color: color-mix(in srgb, var(--erp-danger) 32%, var(--erp-border)); }.planner-status--failed .planner-status__icon { color: var(--erp-danger); background: var(--erp-danger-soft); }
@media (max-width: 760px) { .planner-status { align-items: flex-start; flex-wrap: wrap; }.planner-status__times { width: 100%; margin-left: 44px; }.planner-status__copy small { white-space: normal; } }
</style>

<template>
	<section class="ppo-overview erp-card" aria-label="Production Order overview">
		<div v-for="field in visibleFields" :key="field.fieldname" :class="{ 'ppo-overview__wide': /comments/i.test(field.fieldname) }">
			<span>{{ field.label }}</span><strong>{{ display(field) }}</strong>
		</div>
	</section>
</template>

<script setup>
import { computed } from "vue"
import { plainTextFromHtml } from "../../utils/documentValues.js"

const props = defineProps({ fields: { type: Array, default: () => [] } })
const hidden = new Set(["status", "item"])
const visibleFields = computed(() => props.fields.filter((field) => !hidden.has(field.fieldname)))

function display(field) {
	const value = field.value
	if (value === null || value === undefined || value === "") return "—"
	if ((field.fieldtype === "Date" || /date$/i.test(field.fieldname)) && /^\d{4}-\d{2}-\d{2}/.test(String(value))) {
		const [year, month, day] = String(value).slice(0, 10).split("-")
		return `${day}-${month}-${year}`
	}
	if (field.fieldname === "skip_box_sticker_print") return Number(value) ? "Yes" : "No"
	return plainTextFromHtml(value)
}
</script>

<style scoped>
.ppo-overview { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); min-width: 0; overflow: hidden; border-color: var(--erp-border); box-shadow: var(--erp-shadow-xs); }
.ppo-overview > div { display: grid; min-width: 0; min-height: 62px; align-content: center; gap: 4px; padding: 10px 13px; border-right: 1px solid var(--erp-border); border-bottom: 1px solid var(--erp-border); }
.ppo-overview > div:nth-child(3n) { border-right: 0; }
.ppo-overview__wide { grid-column: 1 / -1; border-right: 0 !important; }
.ppo-overview span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 740; letter-spacing: .035em; text-transform: uppercase; }
.ppo-overview strong { min-width: 0; overflow: hidden; color: var(--erp-text); font-size: var(--erp-font-size-caption); line-height: 1.4; overflow-wrap: anywhere; text-overflow: ellipsis; white-space: nowrap; }
.ppo-overview__wide strong { white-space: normal; }
@media (max-width: 760px) { .ppo-overview { grid-template-columns: repeat(2, minmax(0, 1fr)); } .ppo-overview > div:nth-child(3n) { border-right: 1px solid var(--erp-border); } .ppo-overview > div:nth-child(2n) { border-right: 0; } }
@media (max-width: 480px) { .ppo-overview { grid-template-columns: 1fr; } .ppo-overview > div { border-right: 0; } }
</style>

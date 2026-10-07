<template>
	<aside class="bulk-workflow-rail erp-card" aria-label="Split lot workflow">
		<header class="bulk-workflow-rail__header"><div><span>Split lots</span><h2>Lot workflow</h2></div><Tag :value="`${rows.length} ${rows.length === 1 ? 'lot' : 'lots'}`" severity="secondary" rounded /></header>
		<div v-if="rows.length" class="bulk-workflow-rail__scroll">
			<article
				v-for="row in rows" :key="row.name"
				class="bulk-workflow-card" :class="{ 'bulk-workflow-card--active': row.cutting_laysheet === activeLaySheet }"
				:tabindex="row.actions?.can_activate ? 0 : -1" :role="row.actions?.can_activate ? 'button' : undefined"
				@click="select(row)" @keydown.enter.prevent="select(row)" @keydown.space.prevent="select(row)"
			>
				<header><div class="bulk-workflow-card__title"><span>{{ String(row.idx || 0).padStart(2, '0') }}</span><div><strong>{{ row.lot }}</strong><small>{{ row.cutting_laysheet || "LaySheet not created" }}</small></div></div><Tag :value="row.status" :severity="statusSeverity(row.status)" rounded /></header>
				<dl><div><dt>Plan</dt><dd>{{ row.cutting_plan || "—" }}</dd></div><div><dt>Marker</dt><dd>{{ row.cutting_marker || "—" }}</dd></div><div><dt>Work Order</dt><dd>{{ row.work_order || "—" }}</dd></div></dl>
				<div v-if="row.lot_transfer || row.delivery_challan" class="bulk-workflow-card__links"><span v-if="row.lot_transfer"><i class="pi pi-arrow-right-arrow-left"></i>{{ row.lot_transfer }}</span><span v-if="row.delivery_challan"><i class="pi pi-truck"></i>{{ row.delivery_challan }}</span></div>
				<div v-if="actionButtons(row).length" class="bulk-workflow-card__actions" @click.stop>
					<Button v-for="action in actionButtons(row)" :key="action.key" :label="action.label" :icon="action.icon" size="small" :severity="action.severity" :outlined="action.outlined" :loading="busy === `${action.key}:${row.name}`" @click="emit('action', { action: action.key, row })" />
				</div>
			</article>
		</div>
		<div v-else class="bulk-workflow-empty"><i class="pi pi-clone"></i><strong>No split lots</strong><span>Add the split-lot setup first.</span></div>
	</aside>
</template>

<script setup>
import Button from "primevue/button"
import Tag from "primevue/tag"

const props = defineProps({ rows: { type: Array, default: () => [] }, activeLaySheet: { type: String, default: "" }, busy: { type: String, default: "" } })
const emit = defineEmits(["select", "action"])

function select(row) { if (row.actions?.can_activate) emit("select", row) }
function actionButtons(row) {
	const actions = row.actions || {}
	return [
		["generate", "Generate", "pi pi-box", "secondary", true, actions.can_generate_bundles],
		["create-transfer", "Create Transfer", "pi pi-arrow-right-arrow-left", "secondary", true, actions.can_create_lot_transfer],
		["submit-transfer", "Submit Transfer", "pi pi-check", "success", false, actions.can_submit_lot_transfer],
		["create-dc", "Create DC", "pi pi-truck", "secondary", true, actions.can_create_delivery_challan],
		["submit-dc", "Submit DC", "pi pi-check", "success", false, actions.can_submit_delivery_challan],
		["approve", "Approve", "pi pi-verified", "warn", false, actions.can_approve_grammage],
		["print", "Print Labels", "pi pi-print", "success", false, actions.can_print_labels],
	].filter((entry) => entry[5]).map(([key, label, icon, severity, outlined]) => ({ key, label, icon, severity, outlined }))
}
function statusSeverity(status) { if (status === "Completed") return "success"; if (status === "Ready to Print") return "info"; if (String(status).includes("Submit") || String(status).includes("Approval")) return "warn"; if (String(status).includes("Cancelled") || String(status).includes("Missing")) return "danger"; return "secondary" }
</script>

<style scoped>
.bulk-workflow-rail { display: flex; min-width: 0; min-height: 0; overflow: hidden; flex-direction: column; }
.bulk-workflow-rail__header { display: flex; min-height: 66px; padding: 13px 14px; align-items: center; justify-content: space-between; gap: 10px; border-bottom: 1px solid var(--erp-border); }
.bulk-workflow-rail__header span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 720; letter-spacing: .04em; text-transform: uppercase; }.bulk-workflow-rail__header h2 { margin: 2px 0 0; color: var(--erp-text); font-size: var(--erp-font-size-section); }
.bulk-workflow-rail__scroll { display: grid; min-height: 0; padding: 10px; overflow-y: auto; align-content: start; gap: 9px; }
.bulk-workflow-card { display: grid; min-height: 178px; padding: 11px; gap: 9px; background: var(--erp-surface); border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); cursor: pointer; transition: border-color .15s ease, background .15s ease, box-shadow .15s ease; }.bulk-workflow-card:hover { border-color: var(--erp-border-strong); box-shadow: var(--erp-shadow-xs); }.bulk-workflow-card--active { background: var(--erp-accent-soft); border-color: var(--erp-accent); box-shadow: 0 0 0 1px color-mix(in srgb, var(--erp-accent) 18%, transparent); }
.bulk-workflow-card > header { display: flex; align-items: flex-start; justify-content: space-between; gap: 7px; }.bulk-workflow-card__title { display: flex; min-width: 0; align-items: center; gap: 8px; }.bulk-workflow-card__title > span { display: grid; width: 26px; height: 26px; flex: 0 0 auto; place-items: center; color: var(--erp-accent); font-size: var(--erp-font-size-min); font-weight: 780; background: #fff; border: 1px solid var(--erp-border); border-radius: 50%; }.bulk-workflow-card__title div { display: grid; min-width: 0; gap: 1px; }.bulk-workflow-card__title strong, .bulk-workflow-card__title small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.bulk-workflow-card__title strong { color: var(--erp-text); font-size: var(--erp-font-size-caption); }.bulk-workflow-card__title small { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.bulk-workflow-card dl { display: grid; margin: 0; gap: 4px; }.bulk-workflow-card dl div { display: grid; grid-template-columns: 60px minmax(0, 1fr); gap: 6px; }.bulk-workflow-card dt { color: var(--erp-text-subtle); font-size: var(--erp-font-size-min); }.bulk-workflow-card dd { min-width: 0; margin: 0; overflow: hidden; color: var(--erp-text); font-size: var(--erp-font-size-min); font-weight: 650; text-overflow: ellipsis; white-space: nowrap; }
.bulk-workflow-card__links { display: flex; flex-wrap: wrap; gap: 5px; }.bulk-workflow-card__links span { display: inline-flex; align-items: center; gap: 4px; padding: 3px 6px; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); background: var(--erp-surface-muted); border-radius: 999px; }.bulk-workflow-card__links i { color: var(--erp-accent); font-size: var(--erp-font-size-min); }
.bulk-workflow-card__actions { display: flex; margin-top: auto; flex-wrap: wrap; gap: 5px; }.bulk-workflow-card__actions :deep(.p-button) { padding: 5px 7px; font-size: var(--erp-font-size-min); white-space: nowrap; }
.bulk-workflow-empty { display: grid; min-height: 220px; place-content: center; justify-items: center; gap: 6px; color: var(--erp-text-muted); text-align: center; }.bulk-workflow-empty i { color: var(--erp-accent); font-size: 1.5rem; }.bulk-workflow-empty strong { color: var(--erp-text); }
</style>

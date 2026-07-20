<!--
  DcEntryChips — quick-pick chip strips for the Delivery Challan entry
  variants (dcEntry knob, spec §6.4; demo-7 "size-matrix" / demo-5
  "inline-grid" behaviour, custom ui/demos/_template.html §11).

  Rendered ONLY by the dcEntry hosts (DocOverlayHost's size-matrix bottom
  sheet / DynamicListPage's inline-grid panel) — never by the default
  full-page form, so a layout without the knob renders today's UI exactly
  (parity law).

  Chips are ARRANGEMENT, not capability (spec §15): each strip loads through
  the existing canRead-gated list API — no read permission on the source
  doctype ⇒ that strip renders nothing — and a click only relays the value to
  the host, which sets the SAME form field the user could type (embedded
  DocDetail setFormField → onFieldChanged → runDocAutofill), so the DC
  autofill (get_work_order_defaults → size-pivot grid) fires exactly as if
  the value had been picked in the Link field. No config key feeds a query:
  both fetches below are fixed, code-owned filters.

    WO chips       — the ~8 most recent SUBMITTED, not-closed Work Orders
                     (same filter semantics as the work_order Link search in
                     config/fields/delivery-challan.js: docstatus 1,
                     open_status != Close), labelled "WO-number · item".
    Job-worker chips — the distinct suppliers of the ~10 most recent
                     Delivery Challans (Q18 vendor-party term: "Job-worker").
-->
<template>
	<div v-if="(showWoChips && woAllowed) || (showSupplierChips && supAllowed)" class="dc-entry-chips">
		<div v-if="showWoChips && woAllowed" class="dc-chips-group">
			<span class="dc-chips-label">Work Order</span>
			<div class="dc-chips-row dc-chips-row--scroll">
				<button
					v-for="wo in workOrders"
					:key="wo.name"
					type="button"
					class="dc-chip"
					:class="{ active: wo.name === activeWorkOrder }"
					@click="$emit('pick-wo', wo.name)"
				>
					<span class="dc-chip-id">{{ wo.name }}</span>
					<span v-if="wo.item" class="dc-chip-sub">· {{ wo.item }}</span>
				</button>
				<span v-if="woLoaded && !workOrders.length" class="dc-chips-empty">No open Work Orders</span>
			</div>
		</div>
		<div v-if="showSupplierChips && supAllowed" class="dc-chips-group">
			<span class="dc-chips-label">Job-worker</span>
			<div class="dc-chips-row" :class="{ 'dc-chips-row--buttons': supplierStyle === 'buttons' }">
				<button
					v-for="s in suppliers"
					:key="s"
					type="button"
					class="dc-chip"
					:class="{ active: s === activeSupplier, 'dc-btn': supplierStyle === 'buttons' }"
					@click="$emit('pick-supplier', s)"
				>{{ s }}</button>
				<span v-if="supLoaded && !suppliers.length" class="dc-chips-empty">No recent Job-workers</span>
			</div>
		</div>
	</div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue"
import { getList } from "@/api/client"
import { usePermissions } from "@/composables/usePermissions"

const props = defineProps({
	showWoChips: { type: Boolean, default: false },
	showSupplierChips: { type: Boolean, default: false },
	activeWorkOrder: { type: String, default: "" },
	activeSupplier: { type: String, default: "" },
	// dcEntry.supplierPicker presentation for the Job-worker strip: "chips"
	// (default — the pill chips) or "buttons" (a segmented button group, item 5).
	// Same buttons, same pick-supplier relay — presentation only.
	supplierStyle: { type: String, default: "chips" },
})
defineEmits(["pick-wo", "pick-supplier"])

const { canRead } = usePermissions()
const woAllowed = computed(() => canRead("Work Order"))
const supAllowed = computed(() => canRead("Delivery Challan"))

const workOrders = ref([]) // [{name, item}]
const suppliers = ref([]) // distinct supplier names, most recent DC first
const woLoaded = ref(false)
const supLoaded = ref(false)

// Best-effort strips: a fetch failure just renders an empty strip — the
// form's own Link fields remain the full entry path either way.
onMounted(() => {
	if (props.showWoChips && woAllowed.value) loadWorkOrders()
	if (props.showSupplierChips && supAllowed.value) loadSuppliers()
})

async function loadWorkOrders() {
	try {
		const { data } = await getList("Work Order", {
			fields: ["name", "item"],
			filters: { docstatus: 1, open_status: ["!=", "Close"] },
			order_by: "modified desc",
			limit_page_length: 8,
		})
		workOrders.value = Array.isArray(data) ? data : []
	} catch (_) {
		workOrders.value = []
	} finally {
		woLoaded.value = true
	}
}

async function loadSuppliers() {
	try {
		const { data } = await getList("Delivery Challan", {
			fields: ["supplier"],
			order_by: "modified desc",
			limit_page_length: 10,
		})
		const seen = new Set()
		const out = []
		for (const row of data || []) {
			const s = row.supplier
			if (!s || seen.has(s)) continue
			seen.add(s)
			out.push(s)
		}
		suppliers.value = out
	} catch (_) {
		suppliers.value = []
	} finally {
		supLoaded.value = true
	}
}
</script>

<style scoped>
.dc-entry-chips {
	display: flex;
	flex-direction: column;
	gap: 10px;
	margin-bottom: 14px;
	padding: 12px 14px;
	background: var(--esd-card);
	border: 1px solid var(--esd-line);
	border-radius: 10px;
}
.dc-chips-group {
	display: flex;
	flex-direction: column;
	gap: 6px;
}
.dc-chips-label {
	font-size: 0.72rem;
	font-weight: 600;
	text-transform: uppercase;
	letter-spacing: 0.04em;
	color: var(--esd-muted);
}
.dc-chips-row {
	display: flex;
	flex-wrap: wrap;
	gap: 8px;
	align-items: center;
}
/* WO chips keep the full number visible and scroll sideways (demo-7's
   dc-wochips strip) instead of wrapping into a tall block. */
.dc-chips-row--scroll {
	flex-wrap: nowrap;
	overflow-x: auto;
	padding-bottom: 4px;
}
.dc-chip {
	display: inline-flex;
	align-items: center;
	gap: 4px;
	padding: 6px 12px;
	border: 1px solid var(--esd-line);
	border-radius: 999px;
	background: var(--esd-card);
	color: var(--esd-ink-2);
	font-size: 0.82rem;
	line-height: 1.2;
	cursor: pointer;
	white-space: nowrap;
	transition: border-color 0.15s, background 0.15s, color 0.15s;
}
.dc-chip:hover {
	border-color: var(--esd-accent2);
	color: var(--esd-ink);
}
.dc-chip.active {
	background: var(--esd-accent2-50);
	border-color: var(--esd-accent2);
	color: var(--esd-ink);
	font-weight: 600;
}
.dc-chip-id {
	font-weight: 600;
}
.dc-chip-sub {
	color: var(--esd-muted);
}
.dc-chips-empty {
	font-size: 0.8rem;
	color: var(--esd-muted-2);
	padding: 2px 0;
}
/* supplierPicker "buttons" (item 5): a segmented button group — rectangular,
   larger finger targets — instead of the pill chips. Same buttons/relay. */
.dc-chips-row--buttons {
	gap: 8px;
}
.dc-chip.dc-btn {
	border-radius: 8px;
	padding: 10px 16px;
	font-size: 0.88rem;
	font-weight: 600;
}
.dc-chip.dc-btn.active {
	background: var(--esd-accent2);
	border-color: var(--esd-accent2);
	color: var(--esd-on-accent, #fff);
}
</style>

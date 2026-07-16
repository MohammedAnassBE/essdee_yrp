<!-- home-quick-create block — OPTIONAL standalone quick-create card.

     Registered for layouts to place (spec §6.3); the Default layout does NOT
     place it (today's DOM folds quick-create into the greeting hero), so with
     Default active this block never renders. A layout placing it gets a card
     of "New <DocType>" shortcuts.

     Knobs:
       doctypes : Array<String> — which doctypes to offer. Default: the
                  layout's resolved quickCreate list from the store (§8.3).
     Every entry stays gated by canCreate() at render — arrangement never
     grants capability (spec §15). -->
<template>
	<div v-if="creates.length" class="esd-card qc-card">
		<div class="qc-title">Quick create</div>
		<div class="qc-grid">
			<button
				v-for="qc in creates"
				:key="qc.doctype"
				class="qc-item"
				@click="goCreate(qc)"
			>
				<i :class="[qc.icon, 'qc-item__icon']" />
				<span>New {{ qc.label }}</span>
			</button>
		</div>
	</div>
</template>

<script setup>
import { computed } from "vue"
import { useRouter } from "vue-router"
import { useUiConfigStore } from "@yrp/web-engine"
import { usePermissions } from "@/composables/usePermissions"
import { getRegistryByDoctype } from "@/config/doctypes"

defineOptions({ inheritAttrs: false })

const props = defineProps({
	// null → the layout's quickCreate list (store) decides.
	doctypes: { type: Array, default: null },
})

const router = useRouter()
const { canCreate } = usePermissions()
const ui = useUiConfigStore()

const creates = computed(() =>
	(props.doctypes || ui.quickCreate)
		.filter((dt) => typeof dt === "string" && canCreate(dt))
		.map((dt) => {
			const reg = getRegistryByDoctype(dt)
			return { doctype: dt, label: dt, icon: reg?.icon || "pi pi-plus", route: reg?.route || "" }
		})
		.filter((qc) => qc.route)
)

function goCreate(qc) {
	router.push(`/${qc.route}/new`)
}
</script>

<style scoped>
.qc-card {
	padding: 14px 16px 16px;
}
.qc-title {
	font-size: 11px;
	font-weight: 700;
	text-transform: uppercase;
	letter-spacing: 0.04em;
	color: var(--esd-muted);
	margin-bottom: 10px;
}
.qc-grid {
	display: flex;
	flex-wrap: wrap;
	gap: 10px;
}
.qc-item {
	display: inline-flex;
	align-items: center;
	gap: 8px;
	background: var(--esd-card);
	border: 1px solid var(--esd-line);
	border-radius: var(--radius-sm);
	padding: 9px 13px;
	font-size: 13px;
	font-weight: 600;
	color: var(--esd-ink-2);
	cursor: pointer;
	font-family: inherit;
	transition: background 0.12s, box-shadow 0.14s;
}
.qc-item:hover {
	background: var(--esd-slate-50);
	box-shadow: var(--esd-shadow-card);
}
.qc-item__icon {
	color: var(--esd-accent);
	font-size: 13px;
}
</style>

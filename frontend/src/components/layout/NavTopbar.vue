<!-- NavTopbar — horizontal pill navigation (layout `nav.position: "topbar"`,
     spec extension 2026-07-15). Rendered by AppLayout under the chrome strip
     when the active layout asks for topbar nav; the sidebar is not mounted at
     all in that shell. Layouts without the knob keep today's sidebar exactly
     (parity law).

     Locked decisions (conventions.md 2026-07-15):
       - pills carry WORDING ONLY — no icons;
       - Home is first, filled/active state tracks the route.
     Every item passes the live canRead() gate — arrangement never grants
     capability (spec §15). Items flatten from store.navGroups in layout order;
     unknown doctypes drop with a console.warn (same rule as AppSidebar).
     Narrow widths: the row scrolls horizontally (demo .topnav overflow-x). -->
<template>
	<nav class="esd-topnav" aria-label="Primary">
		<router-link
			to="/home"
			class="topnav-pill"
			:class="{ active: isHomeActive }"
		>Home</router-link>
		<router-link
			v-for="item in pillItems"
			:key="item.route"
			:to="`/${item.route}`"
			class="topnav-pill"
			:class="{ active: isItemActive(item) }"
		>{{ item.label }}</router-link>
	</nav>
</template>

<script setup>
import { computed } from "vue"
import { useRoute } from "vue-router"
import { useUiConfigStore } from "@yrp/web-engine"
import { usePermissions } from "@/composables/usePermissions"
import { getRegistryByDoctype } from "@/config/doctypes"

const route = useRoute()
const ui = useUiConfigStore()
const { canRead } = usePermissions()

// Flatten the layout's nav groups (hidden items already filtered by the store)
// into one ordered pill list. Registry supplies route/label; canRead gates.
const pillItems = computed(() => {
	const items = []
	for (const grp of ui.navGroups) {
		for (const item of grp.items || []) {
			const reg = getRegistryByDoctype(item.doctype)
			if (!reg) {
				console.warn(`[essdee topnav] unknown doctype in layout nav: "${item.doctype}" — dropped`)
				continue
			}
			if (!canRead(reg.doctype)) continue
			items.push({ doctype: reg.doctype, route: reg.route, label: reg.label })
		}
	}
	return items
})

const isHomeActive = computed(() => route.path === "/home" || route.path === "/")

// A pill stays active on its detail routes too (/work-order/WO-00001).
function isItemActive(item) {
	const base = `/${item.route}`
	return route.path === base || route.path.startsWith(`${base}/`)
}
</script>

<style scoped>
/* demo .topnav / .topnav .nav-item, on the app's theme tokens */
.esd-topnav {
	display: flex;
	gap: 8px;
	padding: 12px 18px 2px;
	overflow-x: auto;
	flex: none;
	background: var(--esd-bg);
	scrollbar-width: thin;
	scrollbar-color: var(--esd-line) transparent;
}

.topnav-pill {
	flex: none;
	border-radius: 999px;
	padding: 7px 15px;
	background: var(--esd-card);
	border: 1px solid var(--esd-line);
	color: var(--esd-muted);
	font-size: 13.5px;
	font-weight: 600;
	white-space: nowrap;
	text-decoration: none;
	cursor: pointer;
	transition: background 0.12s ease, color 0.12s ease, border-color 0.12s ease;
}
.topnav-pill:hover {
	background: var(--esd-slate-50);
	color: var(--esd-ink);
}
.topnav-pill.active {
	background: var(--esd-accent);
	border-color: var(--esd-accent);
	color: #fff;
}
</style>

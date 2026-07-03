<template>
	<header class="esd-topbar">
		<div class="topbar-left">
			<button
				class="topbar-hamburger"
				type="button"
				aria-label="Open navigation menu"
				:aria-expanded="drawerOpen"
				@click="$emit('toggle-drawer')"
			>
				<i class="pi pi-bars" />
			</button>
			<span class="topbar-title">{{ pageTitle }}</span>
		</div>

		<div class="topbar-right">
			<!-- Global search / command palette trigger (also ⌘K / Ctrl+K). -->
			<button
				class="cmdk-trigger"
				type="button"
				aria-label="Open search (Ctrl or Cmd + K)"
				title="Search — Ctrl/Cmd + K"
				@click="openPalette"
			>
				<i class="pi pi-search" />
				<span class="cmdk-trigger__label">Search…</span>
				<span class="cmdk-trigger__kbd">⌘K</span>
			</button>
			<!-- Real role(s), read-only — NO switcher (plan: the user's real
			     role drives the UI). -->
			<div class="role-chip" :title="roleTitle">
				<div class="avatar">{{ initials }}</div>
				<div class="role-meta">
					<span class="role-name">{{ fullName }}</span>
					<span class="role-sub">{{ primaryRole }}</span>
				</div>
			</div>
			<Button
				:icon="isDark ? 'pi pi-sun' : 'pi pi-moon'"
				severity="secondary"
				text
				rounded
				:aria-label="isDark ? 'Switch to light theme' : 'Switch to dark theme'"
				:title="isDark ? 'Light mode' : 'Dark mode'"
				@click="toggleTheme"
			/>
			<Button
				icon="pi pi-sign-out"
				severity="secondary"
				text
				rounded
				aria-label="Log out"
				title="Log out"
				@click="onLogout"
			/>
		</div>
	</header>
</template>

<script setup>
import { computed } from "vue"
import { useRoute } from "vue-router"
import Button from "primevue/button"
import { useAuth } from "@/composables/useAuth"
import { useTheme } from "@/composables/useTheme"
import { useCommandPalette } from "@/composables/useCommandPalette"
import { getRegistryByRoute } from "@/config/doctypes"

defineProps({ drawerOpen: Boolean })
defineEmits(["toggle-drawer"])

const route = useRoute()
const { fullName, logout } = useAuth()
const { isDark, toggleTheme } = useTheme()
const { openPalette } = useCommandPalette()

const bootUser = window.frappe?.boot?.user || {}
const roles = Array.isArray(bootUser.roles) ? bootUser.roles : []

// Show the most relevant business role first; fall back to first role.
const ROLE_PRIORITY = [
	"System Manager",
	"Production Manager",
	"Purchase Manager",
	"Stock Manager",
]
const primaryRole = computed(() => {
	for (const r of ROLE_PRIORITY) {
		if (roles.includes(r)) return r
	}
	return roles[0] || "User"
})
const roleTitle = computed(() => `Roles: ${roles.join(", ") || "—"}`)

// Q3: readable titles for the specialized rich-flow routes (their route.name is
// camelCase like "ProcessMatrix", which leaked into the topbar). Generic
// list/detail routes resolve to the DocType label via the registry.
const ROUTE_TITLES = {
	Home: "Home",
	IPDCreate: "New Item Production Detail",
	IPDEditFields: "Edit Item Production Detail",
	IPDConfig: "Item Production Detail",
	ProcessMatrix: "Process Matrix",
	BOMMapping: "Item BOM Mapping",
}

const pageTitle = computed(() => {
	const reg = getRegistryByRoute(route.params.docRoute)
	if (reg) return reg.label
	return ROUTE_TITLES[route.name] || route.name || ""
})

const initials = computed(() => {
	const n = (fullName.value || "U").trim()
	const parts = n.split(/\s+/)
	return parts.length >= 2
		? (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
		: n.slice(0, 2).toUpperCase()
})

async function onLogout() {
	await logout()
}
</script>

<style scoped>
.esd-topbar {
	grid-area: topbar;
	background: var(--esd-card);
	border-bottom: 1px solid var(--esd-line);
	display: flex;
	align-items: center;
	justify-content: space-between;
	padding: 0 20px;
}

.topbar-left {
	display: flex;
	align-items: center;
	gap: 10px;
	min-width: 0;
}

/* Mobile-only menu button (opens the drawer). */
.topbar-hamburger {
	display: none;
	background: transparent;
	border: 0;
	color: var(--esd-ink-2);
	font-size: 18px;
	padding: 6px 8px;
	border-radius: var(--radius-sm);
	cursor: pointer;
}
.topbar-hamburger:hover {
	background: var(--esd-slate-50);
}
@media (max-width: 768px) {
	.topbar-hamburger {
		display: inline-flex;
		align-items: center;
	}
}

.topbar-title {
	font-size: 13px;
	font-weight: 600;
	color: var(--esd-ink-2);
}

.topbar-right {
	display: flex;
	align-items: center;
	gap: 10px;
}

/* Global search trigger — looks like a search field, opens the ⌘K palette. */
.cmdk-trigger {
	display: flex;
	align-items: center;
	gap: var(--space-2);
	height: 32px;
	min-width: 200px;
	padding: 0 8px 0 10px;
	background: var(--esd-bg);
	border: 1px solid var(--esd-line);
	border-radius: var(--radius-sm);
	color: var(--esd-muted);
	font-family: inherit;
	font-size: var(--fs-sm);
	cursor: pointer;
	transition: border-color 0.12s ease, color 0.12s ease;
}
.cmdk-trigger:hover {
	border-color: var(--esd-accent);
	color: var(--esd-ink-2);
}
.cmdk-trigger .pi {
	font-size: var(--fs-sm);
	color: var(--esd-muted-2);
}
.cmdk-trigger__label {
	flex: 1;
	text-align: left;
}
.cmdk-trigger__kbd {
	font-size: var(--fs-2xs);
	font-weight: 700;
	color: var(--esd-muted-2);
	background: var(--esd-card);
	border: 1px solid var(--esd-line);
	border-radius: 4px;
	padding: 1px 5px;
}

.role-chip {
	display: flex;
	align-items: center;
	gap: 8px;
	padding: 4px 10px 4px 4px;
	background: var(--esd-slate-50);
	border-radius: 999px;
	user-select: none;
}

.role-chip .avatar {
	width: 28px;
	height: 28px;
	border-radius: 50%;
	/* Teal (brand) so initials stay legible in both light and dark — the old
	   --esd-ink bg inverted to near-white in dark, hiding white initials. */
	background: var(--esd-accent);
	color: #fff;
	font-weight: 600;
	font-size: 12px;
	display: grid;
	place-items: center;
}

.role-meta {
	display: flex;
	flex-direction: column;
	line-height: 1.2;
}

.role-name {
	font-weight: 600;
	font-size: 13px;
}

.role-sub {
	font-size: 11.5px;
	color: var(--esd-muted);
}
</style>

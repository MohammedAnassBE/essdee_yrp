<template>
	<div class="app-shell" data-ui="essdee-erp">
		<div class="app-route-progress" :class="{ 'is-active': isNavigating }" aria-hidden="true"></div>
		<a class="app-skip-link" href="#app-main">Skip to main content</a>

		<header class="app-topbar">
			<RouterLink class="app-brand" :to="getHomePath()" aria-label="Essdee YRP administrator home">
				<img v-if="appLogo && !isLogoBroken" class="app-brand__logo" :src="appLogo" alt="" @error="isLogoBroken = true" />
				<span v-else class="app-brand__mark" aria-hidden="true">EY</span>
				<span class="app-brand__copy">
					<span class="app-brand__name">Essdee YRP</span>
					<span class="app-brand__suite">Operations suite</span>
				</span>
			</RouterLink>

			<nav class="app-topbar__nav" aria-label="Application navigation">
				<span v-if="activeDepartment" class="app-topbar__context" aria-current="page">
					{{ activeDepartment.label }}
				</span>
				<ConnectionIndicator />
				<button
					type="button"
					class="app-theme-toggle"
					:aria-label="themeToggleLabel"
					:title="themeToggleLabel"
					:aria-pressed="isDarkTheme"
					@click="switchTheme"
				>
					<i :class="isDarkTheme ? 'pi pi-sun' : 'pi pi-moon'" aria-hidden="true" />
					<span>{{ isDarkTheme ? "Light" : "Dark" }}</span>
				</button>
				<AccountMenu />
				<RouterLink v-if="!lockedDepartment" class="app-topbar__home" to="/" aria-label="Workspaces">
					<i class="pi pi-th-large" aria-hidden="true" />
					<span>Workspaces</span>
				</RouterLink>
			</nav>
		</header>

		<div id="app-main" class="app-main" tabindex="-1">
			<RouterView v-slot="{ Component }">
				<Transition name="app-route">
					<component :is="Component" />
				</Transition>
			</RouterView>
		</div>

		<Toast position="bottom-center" />
		<ConfirmDialog />
		<ServerMessageDialog />
	</div>
</template>

<script setup>
import ConfirmDialog from "primevue/confirmdialog"
import Toast from "primevue/toast"
import { computed, nextTick, onBeforeUnmount, ref, watch, watchEffect } from "vue"
import { RouterLink, RouterView, useRoute, useRouter } from "vue-router"

import ServerMessageDialog from "./components/common/ServerMessageDialog.vue"
import AccountMenu from "./components/navigation/AccountMenu.vue"
import ConnectionIndicator from "./components/navigation/ConnectionIndicator.vue"
import { reportedPageTitle } from "./composables/usePageTitle.js"
import { departments } from "./departments/registry.js"
import { getHomePath, isOutsideLayout, lockedDepartment } from "./router/departmentLock.js"
import { getAppLogo } from "./utils/appLogo.js"
import { resolvePageTitle } from "./utils/pageTitle.js"
import { currentTheme, toggleTheme } from "./utils/themePreference.js"

const route = useRoute()
const appLogo = getAppLogo()
const isLogoBroken = ref(false)
const router = useRouter()
const isNavigating = ref(false)
const isDarkTheme = ref(currentTheme() === "dark")
const themeToggleLabel = computed(() => isDarkTheme.value ? "Switch to light theme" : "Switch to dark theme")

function switchTheme() {
	isDarkTheme.value = toggleTheme() === "dark"
}

let pendingNavigation = null
const removeBeforeEach = router.beforeEach((to) => {
	pendingNavigation = to
	isNavigating.value = true
})
const removeAfterEach = router.afterEach((to) => {
	if (to === pendingNavigation) {
		isNavigating.value = false
	}
})
const removeOnError = router.onError((error, to) => {
	if (!to || to === pendingNavigation) {
		isNavigating.value = false
	}
})

onBeforeUnmount(() => {
	removeBeforeEach()
	removeAfterEach()
	removeOnError()
})

const activeDepartment = computed(() => {
	const owner = departments.find(
		(department) =>
			route.path === department.path || route.path.startsWith(`${department.path}/`),
	)
	return lockedDepartment?.combines?.includes(owner?.key) && !isOutsideLayout(route.path) ? lockedDepartment : owner
})

watchEffect(() => {
	document.title = resolvePageTitle(route, departments, reportedPageTitle.value)
})

watch(
	() => route.path,
	async () => {
		await nextTick()
		window.requestAnimationFrame(() => document.getElementById("app-main")?.focus({ preventScroll: true }))
	},
	{ immediate: true },
)
</script>

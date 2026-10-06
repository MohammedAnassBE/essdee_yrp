<template>
	<div class="app-shell" data-ui="essdee-erp">
		<a class="app-skip-link" href="#app-main">Skip to main content</a>

		<header class="app-topbar">
			<RouterLink class="app-brand" to="/" aria-label="Essdee YRP administrator home">
				<span class="app-brand__mark" aria-hidden="true">EY</span>
				<span class="app-brand__copy">
					<span class="app-brand__name">Essdee YRP</span>
					<span class="app-brand__suite">Operations suite</span>
				</span>
			</RouterLink>

			<nav class="app-topbar__nav" aria-label="Application navigation">
				<span v-if="activeDepartment" class="app-topbar__context" aria-current="page">
					{{ activeDepartment.label }}
				</span>
				<RouterLink class="app-topbar__home" to="/">
					<i class="pi pi-th-large" aria-hidden="true" />
					<span>Workspaces</span>
				</RouterLink>
			</nav>
		</header>

		<div id="app-main" class="app-main" tabindex="-1">
			<RouterView v-slot="{ Component }">
				<Transition name="app-route" mode="out-in">
					<component :is="Component" />
				</Transition>
			</RouterView>
		</div>

		<Toast position="bottom-center" />
		<ConfirmDialog />
	</div>
</template>

<script setup>
import ConfirmDialog from "primevue/confirmdialog"
import Toast from "primevue/toast"
import { computed } from "vue"
import { RouterLink, RouterView, useRoute } from "vue-router"

import { departments } from "./departments/registry.js"

const route = useRoute()
const activeDepartment = computed(() =>
	departments.find(
		(department) =>
			route.path === department.path || route.path.startsWith(`${department.path}/`),
	),
)
</script>

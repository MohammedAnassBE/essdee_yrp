<template>
	<DepartmentPage title="PD" accent="#a3378f" :show-title="false" flat full-width>
		<WorkspacePlaceholder title="PD" icon="pi pi-palette" description="Product Development. No tools are available in this workspace yet. Department tools will appear here when they are enabled." />
	</DepartmentPage>
</template>

<script setup>
import DepartmentPage from "../components/DepartmentPage.vue"
import WorkspacePlaceholder from "../components/common/WorkspacePlaceholder.vue"
</script>

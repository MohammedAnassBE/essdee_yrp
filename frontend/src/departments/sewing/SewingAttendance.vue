<template>
	<SewingWorkspaceShell title="Attendance Report" section="attendance">
		<section data-sewing-destination="attendance" aria-label="Attendance Report workspace">
			<AttendanceStrengthReport />
		</section>
	</SewingWorkspaceShell>
</template>

<script setup>
import SewingWorkspaceShell from "./SewingWorkspaceShell.vue"
import AttendanceStrengthReport from "../../components/reports/AttendanceStrengthReport.vue"
</script>

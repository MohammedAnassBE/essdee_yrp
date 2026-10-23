/** Copy a new planned end date into expected delivery unless the user overrode it. */
export function applyPlannedEndDate(form, value) {
	const previous = form.planned_end_date || ""
	const expected = form.expected_delivery_date || ""
	form.planned_end_date = value || ""
	if (!expected || expected === previous) form.expected_delivery_date = form.planned_end_date
}

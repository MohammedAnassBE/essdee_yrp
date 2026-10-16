export function clothSelection(cloth, defaults = {}) {
	const profile = cloth.profile || {}
	return {
		...cloth,
		profile,
		dyed_yarn_colours: [...(cloth.dyed_yarn_colours || [])],
		same_finished_colours: [...(cloth.same_finished_colours || [])],
		cloth_per_kg_yarn: getProfileValue(profile, defaults, "cloth_per_kg_yarn", 1),
		knitting_process: getProfileValue(profile, defaults, "knitting_process", ""),
		dyeing_process: getProfileValue(profile, defaults, "dyeing_process", ""),
		compacting_process: getProfileValue(profile, defaults, "compacting_process", null),
		non_dyed_colour: defaults.knitting_output_colour || "",
	}
}

function getProfileValue(profile, defaults, field, fallback) {
	return profile[field] || defaults[field] || fallback
}

export function fabricRoutes(selection) {
	return (selection.required_colours || []).flatMap((colour) =>
		(selection.required_routes || [])
			.filter((route) => route.colour === colour)
			.sort((first, second) => diaNumber(first.dia) - diaNumber(second.dia))
			.map((route) => {
				const stored = (selection.profile.fabric_routes || []).find(
					(row) => row.finished_colour === colour && row.finished_dia === route.dia,
				)
				const dyed = selection.dyed_yarn_colours.includes(colour)
				return {
					finished_colour: colour,
					finished_dia: route.dia,
					knitting_output_dia: stored?.knitting_output_dia || route.dia || null,
					knitting_output_colour:
						dyed || selection.same_finished_colours.includes(colour)
							? colour
							: selection.non_dyed_colour,
					use_dyed_yarn: dyed ? 1 : 0,
				}
			}),
	)
}
function diaNumber(value) {
	return Number(String(value || "").match(/-?\d+(?:\.\d+)?/)?.[0] ?? Number.MAX_SAFE_INTEGER)
}

export function buildSelection(selection) {
	return {
		cloth_item: selection.cloth_item,
		production_detail: selection.production_detail || null,
		dyed_yarn_colours: selection.dyed_yarn_colours,
		same_finished_colours: selection.same_finished_colours,
		fabric_routes: fabricRoutes(selection),
		non_dyed_colour: selection.non_dyed_colour,
		yarns: selection.item_yarns || [],
		yarn_item: selection.item_yarns?.[0]?.yarn_item,
		cloth_per_kg_yarn: selection.cloth_per_kg_yarn,
		knitting_process: selection.knitting_process,
		dyeing_process: selection.dyeing_process || null,
		compacting_process: selection.compacting_process,
		required_colours: selection.required_colours || [],
	}
}

export function clothErrors(selection) {
	const errors = {}
	const recipe = selection.item_yarns || []
	if (
		!recipe.length ||
		recipe.some((row) => !row.yarn_item || !(Number(row.ratio) > 0)) ||
		new Set(recipe.map((row) => row.yarn_item)).size !== recipe.length ||
		Math.abs(recipe.reduce((sum, row) => sum + Number(row.ratio), 0) - 100) > 0.001
	) {
		errors.item_yarns =
			"Configure unique Yarn Items with positive ratios totalling 100% on the Cloth Item."
	}
	if (!(selection.cloth_per_kg_yarn > 0))
		errors.cloth_per_kg_yarn = "Cloth Kgs / 1 Kg Yarn must be greater than zero."
	if (!selection.knitting_process) errors.knitting_process = "Knitting Process is required."
	return { ...errors, ...routeErrors(selection) }
}

function routeErrors(selection) {
	const errors = {}
	const routes = fabricRoutes(selection)
	if (routes.some((route) => !route.knitting_output_colour))
		errors.routes = "Set Default Knitting Yarn Colour in SD YRP IPD Settings."
	if (routes.some((route) => !route.knitting_output_dia))
		errors.routes = "Configure the missing Knitting Output Dia in the cloth IPD."
	if (
		routes.some((route) => route.knitting_output_colour !== route.finished_colour) &&
		!selection.dyeing_process
	)
		errors.dyeing_process = "Dyeing Process is required for routes that change Colour."
	if (
		routes.some((route) => route.knitting_output_dia !== route.finished_dia) &&
		!selection.compacting_process
	)
		errors.routes = "Set Default Dia-change Process in SD YRP IPD Settings."
	return errors
}

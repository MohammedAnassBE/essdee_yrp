<template>
	<div class="item-conversion">
		<div class="summary mb-3">
			<div><span>From Value</span><strong>{{ money(from_total) }}</strong></div>
			<div><span>To Value</span><strong>{{ money(to_total) }}</strong></div>
			<div :class="has_difference ? 'text-danger' : 'text-success'">
				<span>Difference</span><strong>{{ money(difference) }}</strong>
			</div>
		</div>

		<conversion-side
			title="From Item"
			:groups="from_items"
			:editable="docstatus === 0"
			:rate-read-only="true"
			@add="open_editor('from')"
			@edit="(group, item) => open_editor('from', group, item)"
			@remove="(group, item) => remove_item('from', group, item)"
			@changed="from_changed"
		/>
		<conversion-side
			class="mt-4"
			title="To Item"
			:groups="to_items"
			:editable="docstatus === 0"
			:rate-read-only="true"
			@add="open_editor('to')"
			@edit="(group, item) => open_editor('to', group, item)"
			@remove="(group, item) => remove_item('to', group, item)"
			@changed="to_changed"
		/>
	</div>
</template>

<script>
import { computed, defineComponent, h, nextTick, ref } from "vue";

const METHOD = "essdee_yrp.essdee_yrp.doctype.item_conversion.item_conversion.";
const ITEM_METHOD = "yrp.yrp.doctype.item.item.";

const ConversionSide = defineComponent({
	props: ["title", "groups", "editable", "rateReadOnly"],
	emits: ["add", "edit", "remove", "changed"],
	setup(props, { emit }) {
		function value_rows(item) { return Object.entries(item.values || {}); }
		return () => h("section", [
			h("div", { class: "d-flex justify-content-between align-items-center mb-2" }, [
				h("h5", { class: "m-0" }, props.title),
				props.editable ? h("button", { class: "btn btn-default btn-xs", onClick: () => emit("add") }, __("Add Item")) : null,
			]),
			...(props.groups || []).flatMap((group, group_index) => (group.items || []).map((item, item_index) =>
				h("div", { class: "conversion-row border rounded p-2 mb-2" }, [
					h("div", { class: "d-flex justify-content-between" }, [
						h("div", [h("strong", item.name), h("span", { class: "text-muted ml-2" }, item.lot || "")]),
						props.editable ? h("div", [
							h("button", { class: "btn btn-default btn-xs mr-1", onClick: () => emit("edit", group_index, item_index) }, __("Edit")),
							h("button", { class: "btn btn-default btn-xs text-danger", onClick: () => emit("remove", group_index, item_index) }, __("Remove")),
						]) : null,
					]),
					h("div", { class: "small text-muted mb-2" }, [
						Object.entries(item.attributes || {}).map(([key, value]) => `${key}: ${value}`).join(" · "),
						item.received_type ? ` · ${item.received_type}` : "",
					]),
					h("div", { class: "d-flex flex-wrap gap-2" }, value_rows(item).map(([label, value]) =>
						h("div", { class: "value-cell" }, [
							h("label", { class: "small" }, label === "default" ? __("Quantity") : label),
							h("div", `${value.qty || 0} ${item.default_uom || ""}`),
							h("small", { class: "text-muted" }, `${__("Rate")}: ${frappe.format(value.rate || 0, { fieldtype: "Currency" })}`),
					])
				)),
			])
			)),
		]);
	},
});

export default {
	components: { ConversionSide },
	setup() {
		const docstatus = ref(cur_frm.doc.docstatus);
		const from_items = ref([]);
		const to_items = ref([]);
		const from_total = computed(() => total(from_items.value));
		const to_total = computed(() => total(to_items.value));
		const difference = computed(() => round(from_total.value - to_total.value));
		const has_difference = computed(() => Math.abs(difference.value) > 0.001);

		function call(method, args) {
			return new Promise((resolve, reject) => frappe.call({
				method, args, no_spinner: true,
				callback: (response) => resolve(response.message), error: reject,
			}));
		}

		async function open_editor(side, group_index = null, item_index = null) {
			const template = cur_frm.doc[side === "from" ? "from_item" : "to_item"];
			if (!template) frappe.throw(__(`Select ${side === "from" ? "From" : "To"} Item first.`));
			const groups = side === "from" ? from_items.value : to_items.value;
			const existing = group_index === null ? null : groups[group_index].items[item_index];
			const details = await call(ITEM_METHOD + "get_attribute_details", { item_name: template });
			const fields = [
				{ fieldname: "lot", fieldtype: "Link", options: "Lot", label: "Lot", reqd: 1, default: existing?.lot },
				{ fieldname: "received_type", fieldtype: "Link", options: "Received Type", label: "Received Type", reqd: 1, default: existing?.received_type },
				{ fieldname: "remarks", fieldtype: "Data", label: "Remarks", default: existing?.remarks },
				{ fieldtype: "Section Break", label: "Attributes" },
			];
			(details.attributes || []).forEach((attribute, index) => fields.push({
				fieldname: `attribute_${index}`,
				fieldtype: "Link",
				options: "Item Attribute Value",
				label: attribute,
				reqd: 1,
				default: existing?.attributes?.[attribute],
				get_query: () => ({ query: ITEM_METHOD + "get_item_attribute_values", filters: { item: template, attribute } }),
			}));
			if (details.primary_attribute) {
				fields.push({
					fieldname: "primary_value", fieldtype: "Select", label: details.primary_attribute,
					options: details.primary_attribute_values || [], reqd: 1,
					default: existing ? Object.keys(existing.values || {})[0] : null,
				});
			}
			const existing_value = existing ? Object.values(existing.values || {})[0] || {} : {};
			fields.push(
				{ fieldtype: "Section Break", label: "Quantity" },
				{ fieldname: "qty", fieldtype: "Float", label: `Quantity (${details.default_uom || ""})`, reqd: 1, default: existing_value.qty || 0 },
				{ fieldname: "secondary_qty", fieldtype: "Float", label: details.secondary_uom ? `Secondary Quantity (${details.secondary_uom})` : "Secondary Quantity", hidden: !details.secondary_uom, default: existing_value.secondary_qty || 0 },
			);
			const dialog = new frappe.ui.Dialog({
				title: existing ? __("Edit Conversion Item") : __("Add Conversion Item"),
				fields,
				primary_action_label: existing ? __("Update") : __("Add"),
				async primary_action(values) {
					if (positive_values(groups) && !existing) frappe.throw(__("Only one quantity row is allowed on each side."));
					const attributes = {};
					(details.attributes || []).forEach((attribute, index) => { attributes[attribute] = values[`attribute_${index}`]; });
					const key = details.primary_attribute ? values.primary_value : "default";
					const item = {
						name: template, lot: values.lot, attributes,
						primary_attribute: details.primary_attribute,
						values: { [key]: { qty: values.qty, rate: existing_value.rate || 0, secondary_qty: values.secondary_qty || 0 } },
						default_uom: details.default_uom, secondary_uom: details.secondary_uom,
						received_type: values.received_type, remarks: values.remarks,
					};
					const group = {
						attributes: details.attributes || [], primary_attribute: details.primary_attribute,
						primary_attribute_values: details.primary_attribute_values || [], items: [item],
					};
					if (existing) groups.splice(group_index, 1, group); else groups.splice(0, groups.length, group);
					dialog.hide();
					if (side === "from") await from_changed(); else to_changed();
				},
			});
			dialog.show();
		}

		async function refresh_from_rates() {
			const jobs = [];
			for (const group of from_items.value) for (const item of group.items || []) {
				for (const [key, value] of Object.entries(item.values || {})) {
					if (!(Number(value.qty) > 0)) continue;
					const attributes = { ...(item.attributes || {}) };
					if (group.primary_attribute && key !== "default") attributes[group.primary_attribute] = key;
					jobs.push(call(METHOD + "get_item_conversion_valuation_rate", {
						item: item.name, attributes: JSON.stringify(attributes), lot: item.lot,
						received_type: item.received_type, uom: item.default_uom,
						warehouse: cur_frm.doc.warehouse, posting_date: cur_frm.doc.posting_date,
						posting_time: cur_frm.doc.posting_time,
					}).then((result) => { value.rate = Number(result?.rate || 0); }));
				}
			}
			await Promise.all(jobs);
			auto_balance(); sync();
		}

		function auto_balance() {
			const values = all_values(to_items.value).filter((value) => Number(value.qty) > 0);
			if (values.length === 1 && from_total.value > 0) values[0].rate = Number((from_total.value / Number(values[0].qty)).toFixed(9));
		}
		async function from_changed() { await refresh_from_rates(); dirty(); }
		function to_changed() { auto_balance(); sync(); dirty(); }
		function remove_item(side, group_index) {
			(side === "from" ? from_items.value : to_items.value).splice(group_index, 1);
			if (side === "from") from_changed(); else to_changed();
		}
		function dirty() { if (cur_frm.doc.docstatus === 0) cur_frm.dirty(); }
		function sync() {
			if (cur_frm.doc.docstatus !== 0) return;
			cur_frm.doc.from_total_amount = from_total.value;
			cur_frm.doc.to_total_amount = to_total.value;
			cur_frm.doc.difference_amount = difference.value;
			cur_frm.refresh_fields(["from_total_amount", "to_total_amount", "difference_amount"]);
		}
		function load_data(data) {
			from_items.value = JSON.parse(JSON.stringify(data.from_items || []));
			to_items.value = JSON.parse(JSON.stringify(data.to_items || []));
			if (cur_frm.doc.docstatus === 0) nextTick(refresh_from_rates);
		}
		function get_items() {
			return { from_items: from_items.value, to_items: to_items.value, from_total_amount: from_total.value, to_total_amount: to_total.value, difference_amount: difference.value, has_difference: has_difference.value };
		}
		function update_status() { docstatus.value = cur_frm.doc.docstatus; }
		return { docstatus, from_items, to_items, from_total, to_total, difference, has_difference, open_editor, remove_item, from_changed, to_changed, refresh_from_rates, load_data, get_items, update_status, money };
	},
};

function all_values(groups) { return (groups || []).flatMap((group) => (group.items || []).flatMap((item) => Object.values(item.values || {}))); }
function positive_values(groups) { return all_values(groups).filter((value) => Number(value.qty) > 0).length; }
function total(groups) { return round(all_values(groups).reduce((sum, value) => sum + Number(value.qty || 0) * Number(value.rate || 0), 0)); }
function round(value) { return Math.round(Number(value || 0) * 1000) / 1000; }
function money(value) { return frappe.format(value || 0, { fieldtype: "Currency" }); }
</script>

<style scoped>
.summary { display: flex; justify-content: flex-end; gap: 1.25rem; padding: .6rem; border: 1px solid var(--border-color); border-radius: 6px; }
.summary > div { display: flex; gap: .4rem; align-items: center; }
.summary span { color: var(--text-muted); }
.gap-2 { gap: .5rem; }
.value-cell { min-width: 120px; padding: .35rem .6rem; background: var(--control-bg); border-radius: 4px; }
</style>

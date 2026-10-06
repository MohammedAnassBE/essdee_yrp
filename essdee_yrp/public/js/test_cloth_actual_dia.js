const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const vm = require("node:vm");

function detail(qty, pending, allowed, reference) {
	return {
		qty,
		pending_quantity: pending,
		max_receivable_quantity: allowed,
		ref_docname: reference,
	};
}

function entry({ dia = "30", receivedType = "Accepted", qty = 0, pending = 0, allowed = 0, reference }) {
	return {
		name: "KNIT-CLOTH",
		attributes: { Colour: "Navy", Dia: dia },
		dimensions: { received_type: receivedType },
		set_combination: {},
		values: { default: detail(qty, pending, allowed, reference) },
	};
}

function loadGrnFormHelpers() {
	const context = {
		console,
		__: (value) => value,
		flt: (value) => Number(value || 0),
		format_number: String,
		essdee_yrp: {},
		frappe: { ui: { form: { on() {} } } },
	};
	const sourcePath = path.join(__dirname, "goods_received_note.js");
	vm.runInNewContext(fs.readFileSync(sourcePath, "utf8"), context, { filename: sourcePath });
	return context.essdee_yrp;
}

(async () => {
	const helperUrl = pathToFileURL(path.join(
		__dirname,
		"../../../../yrp/yrp/public/js/WorkOrder/grnReceiptRows.mjs",
	));
	const {
		buildLogicalReceiptRows,
		buildReceiptRowKey,
		removeSplitSources,
		setSplitQuantity,
	} = await import(helperUrl.href);
	const grnHelpers = loadGrnFormHelpers();

	{
		const referenced = entry({ qty: 2, reference: "WOR-1" });
		const unreferenced = entry({ qty: 3 });
		for (const candidate of [referenced, unreferenced]) {
			const group = { primary_attribute_values: [], items: [candidate] };
			const rows = buildLogicalReceiptRows([group]);
			assert.equal(
				buildReceiptRowKey(group, candidate),
				rows[0].key,
				"Received Type cloning uses the same reference-aware key as logical rows",
			);
		}
	}

	{
		const planned = entry({ dia: "30", qty: 4, pending: 10, allowed: 12, reference: "WOR-1" });
		planned.row_index = "0";
		planned.table_index = "0";
		const group = { primary_attribute_values: [], items: [planned] };
		const source = { group, entry: planned, valueKey: "default", reference: "WOR-1" };
		const actual = grnHelpers.append_actual_dia_row(source, "32", 6);
		assert.equal(group.items.length, 2, "Actual Dia creates a physical split row");
		assert.equal(actual.attributes.Dia, "32");
		assert.equal(actual.values.default.qty, 6);
		assert.equal(actual.values.default.ref_docname, "WOR-1", "exact receivable lineage is retained");
		assert.equal(actual.row_index, undefined);
		assert.equal(actual.table_index, undefined);
		assert.equal(grnHelpers.actual_dia_exists([group], "WOR-1", "32"), true);
	}

	{
		const first = entry({ qty: 2, pending: 5, allowed: 6, reference: "WOR-1" });
		const second = entry({ qty: 3, pending: 7, allowed: 8, reference: "WOR-2" });
		const groups = [{ primary_attribute_values: [], items: [first, second] }];
		const rows = buildLogicalReceiptRows(groups, { aggregatePhysicalRows: true });
		assert.equal(rows.length, 2, "different receivable references remain independently editable");
		assert.equal(rows[0].splits[0].entry.values.default.qty, 2);
		assert.equal(rows[0].splits[0].sourceEntries.length, 1);
		assert.equal(rows[1].splits[0].entry.values.default.qty, 3);
		assert.equal(rows[1].splits[0].sourceEntries.length, 1);
	}

	{
		const first = entry({ qty: 2, pending: 5, allowed: 6, reference: "WOR-1" });
		const second = entry({ qty: 3, pending: 7, allowed: 8, reference: "WOR-1" });
		const groups = [{ primary_attribute_values: [], items: [first, second] }];
		const rows = buildLogicalReceiptRows(groups, { aggregatePhysicalRows: true });
		assert.equal(rows.length, 1, "duplicate rows for the same physical source render once");
		assert.equal(rows[0].splits[0].entry.values.default.qty, 5);
		assert.equal(rows[0].splits[0].entry.values.default.pending_quantity, 12);
		assert.equal(rows[0].splits[0].entry.values.default.max_receivable_quantity, 14);
		assert.equal(rows[0].splits[0].sourceEntries.length, 2);
	}

	{
		const accepted = entry({ qty: 2, receivedType: "Accepted", reference: "WOR-1" });
		const acceptedRoute = entry({ qty: 3, receivedType: "Accepted", reference: "WOR-1" });
		const rejected = entry({ qty: 1, receivedType: "Rejected", reference: "WOR-1" });
		const groups = [{ primary_attribute_values: [], items: [accepted, acceptedRoute, rejected] }];
		const rows = buildLogicalReceiptRows(groups, { aggregatePhysicalRows: true });
		assert.deepEqual(
			rows[0].splits.map((split) => [split.receivedType, split.entry.values.default.qty]),
			[["Accepted", 5], ["Rejected", 1]],
			"Received Types aggregate independently",
		);
		removeSplitSources(groups, rows[0].splits[1]);
		assert.deepEqual(groups[0].items, [accepted, acceptedRoute], "removing a split removes its source rows");
	}

	{
		const first = entry({ qty: 0, reference: "WOR-1" });
		const second = entry({ qty: 0, reference: "WOR-2" });
		const compacted = grnHelpers.compact_physical_grn_groups([
			{ primary_attribute_values: [], items: [first, second] },
		]);
		assert.equal(compacted[0].items.length, 2, "physical compaction retains each receivable reference");
	}

	{
		const physical = entry({ qty: 0, pending: 5, allowed: 5, reference: "WOR-1" });
		const groups = [{ primary_attribute_values: [], items: [physical] }];
		const rows = buildLogicalReceiptRows(groups, { aggregatePhysicalRows: true });
		const split = rows[0].splits[0];
		assert.equal(setSplitQuantity(split, "default", 8, { allowExcess: true, maxValue: 5 }), 8);
		assert.equal(physical.values.default.qty, 8, "excess quantity persists to the physical source row");
	}

	{
		const original = entry({ qty: 0, pending: 5, allowed: 5, reference: "WOR-1" });
		const groups = [{ primary_attribute_values: [], items: [original] }];
		const rows = buildLogicalReceiptRows(groups);
		const split = rows[0].splits[0];
		assert.equal(split.entry, original, "default mode preserves the original row object");
		assert.equal(setSplitQuantity(split, "default", 8, { maxValue: 5 }), 5);
		assert.equal(original.values.default.qty, 5, "default mode keeps the existing quantity cap");
	}

	{
		const lotComponent = fs.readFileSync(
			path.join(__dirname, "Lot/ActualDiaConversions.vue"),
			"utf8",
		);
		assert.match(lotComponent, /row\.planned_item/);
		assert.match(lotComponent, /row\.actual_item/);
		assert.match(lotComponent, /row\.actual_quantity/);
		assert.match(lotComponent, /openDoc\('Item', row\.planned_item\)/);
		assert.doesNotMatch(lotComponent, /Item Variant/);
		const lotForm = fs.readFileSync(
			path.join(__dirname, "../../essdee_yrp/doctype/sd_yrp_lot/sd_yrp_lot.js"),
			"utf8",
		);
		assert.match(lotForm, /mount_actual_dia_conversions\(frm\)/);
	}

	console.log("Cloth Actual Dia Desk helper tests passed");
})().catch((error) => {
	console.error(error);
	process.exitCode = 1;
});

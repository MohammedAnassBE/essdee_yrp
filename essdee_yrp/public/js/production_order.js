frappe.ui.form.on("YRP Production Order", {
	refresh(frm) {
		render_lot_ordered_details(frm);
		render_price_requests(frm);
	},
});

function render_lot_ordered_details(frm) {
	const field = frm.fields_dict["lot_ordered_html"];
	if (!field) return;

	field.$wrapper.html("");
	frm.lot_ordered_view = null;

	if (frm.is_new()) return;

	const view = new frappe.production.ui.LotOrderedDetail(field.wrapper);
	const requested_name = frm.doc.name;
	frm.lot_ordered_view = view;
	frappe.call({
		method: "essdee_yrp.production_order.get_lot_ordered_details",
		args: { production_order: requested_name },
		callback(response) {
			// Ignore stale responses after switching to another record.
			if (frm.lot_ordered_view !== view || frm.doc.name !== requested_name) return;
			view.load_data(response.message || {});
		},
	});
}

const PRICE_REQUEST_STATUS_COLORS = { Approved: "green", Rejected: "red" };

function render_price_requests(frm) {
	const field = frm.fields_dict["ppo_price_request_html"];
	if (!field) return;

	const requests = (frm.doc.__onload || {}).price_requests || [];
	const heading = `<div class="control-label">${__("Price Changes")}</div>`;
	if (!requests.length) {
		field.$wrapper.html(
			`${heading}<div class="text-muted" style="padding:15px;">${__("No price change requests")}</div>`
		);
		return;
	}

	const headers = [
		"Request",
		"Status",
		"Requested By",
		"Requested At",
		"Approved/Rejected By",
		"Approved/Rejected At",
	].map((label) => `<th>${__(label)}</th>`);
	field.$wrapper.html(`${heading}<div style="padding:10px 0;">
		<table class="table table-bordered table-sm">
			<thead><tr>${headers.join("")}</tr></thead>
			<tbody>${requests.map(price_request_row).join("")}</tbody>
		</table>
	</div>`);
}

function price_request_row(request) {
	const escape = (value) => frappe.utils.escape_html(String(value ?? ""));
	const user = (value) => (value ? frappe.user.full_name(value) : "");
	const datetime = (value) => (value ? frappe.datetime.str_to_user(value) : "");
	const url = `/app/sd-yrp-ppo-price-request/${encodeURIComponent(String(request.name ?? ""))}`;
	const color = PRICE_REQUEST_STATUS_COLORS[request.status] || "orange";
	return `<tr>
		<td><a href="${url}">${escape(request.name)}</a></td>
		<td><span class="indicator-pill ${color}">${escape(request.status)}</span></td>
		<td>${escape(user(request.requested_by))}</td>
		<td>${escape(datetime(request.requested_at))}</td>
		<td>${escape(user(request.approved_by))}</td>
		<td>${escape(datetime(request.approved_at))}</td>
	</tr>`;
}

#!/usr/bin/env python3
"""Render current independent audit results, without hardcoded outcome claims."""

import argparse
import html
import json
from collections import defaultdict
from pathlib import Path

from audit_production_api_source_values import _connect


# Reviewed code-change inventory only. Outcome counts always come from the
# supplied independent audit, never from historical hand-written totals.
CORRECTED_FIELDS = {
	"Bin": {"reserved_qty"},
	"Cut Panel Movement": {"process_name"},
	"Cutting Marker": {"cutting_marker_parts"},
	"FG Stock Entry": {"lot"},
	"Lot": {"version"},
	"Lotwise Item Profit Qty Rate": {"ratio"},
	"Item BOM Attribute Mapping": {"lot_template"},
	"Item Production Detail": {"additional_cloth", "stiching_attribute_quantity"},
	"Stock Settings": {"location_mapping", "sms_old_database_host", "sms_old_database_name",
		"sms_old_database_port", "sms_old_database_user", "sms_old_database_password"},
	"Supplier": {"deparments"},
	"Delivery Challan": {"ste_transferred", "total_delivered_qty"},
	"Delivery Challan Item": {"delivered_quantity", "pending_quantity", "ste_delivered_quantity"},
	"Goods Received Note Item": {"quantity", "stock_qty"},
	"Lot BOM": {"required_qty"},
	"Purchase Invoice Item": {"amount"},
}


def render(audit, live):
	summary = audit["summary"]
	fields = audit["field_results"]
	doctypes = defaultdict(lambda: {"targets": set(), "rows": 0, "missing": 0, "projected": 0})
	for route in audit["document_routes"]:
		row = doctypes[route["source_doctype"]]
		row["targets"].add(route["target_doctype"])
		row["rows"] += route["source_rows"]
		row["missing"] += route["missing_direct_rows"]
		row["projected"] += route["special_projection_rows"]
	doctype_rows = [{"doctype": dt, **row, "targets": sorted(row["targets"])} for dt, row in sorted(doctypes.items())]
	checks = {
		"Incomplete application audit scope": 0 if audit.get("complete_application_scope") is True else 1,
		"Schema gap field routes": summary.get("schema_gap_routes"),
		"Ignored fields containing material data": summary.get("ignored_field_routes_with_material_data"),
		"Missing credential rows": summary.get("missing_auth_rows"),
		"Ignored credential rows containing data": summary.get("ignored_auth_rows_with_data"),
		"Credential record identity mismatches": summary.get("credential_record_identity_mismatches"),
		"Physical invoice rows versus original GRNs": summary.get("purchase_invoice_physical_grn_mismatches"),
		"Historical Bin and active reservation mismatches": summary.get("bin_reservation_mismatches"),
		"Missing direct row values": summary.get("missing_target_row_field_values"),
		"Different stored values": summary.get("mismatched_field_values"),
		"Rounded numeric values": summary.get("normalized_matches"),
		"Source blank fills without independent evidence": summary.get("unverified_default_fills", summary.get("target_fills_from_source_blank")),
		"Default fill count reconciliation": (
			abs(summary.get("target_fills_from_source_blank", 0) - summary.get("verified_default_fills", 0) - summary.get("unverified_default_fills", 0))
		),
		"Credential value mismatches": summary.get("credential_value_mismatches"),
		"Original IPD row archive mismatches": summary.get("raw_source_archive_mismatches"),
		"Retired table archive mismatches": summary.get("retired_source_archive_mismatches"),
		"Supporting / framework value mismatches": summary.get("framework_value_mismatches"),
		"Original File column / byte mismatches": summary.get("attachment_value_mismatches"),
		"PI grouped projection mismatches": summary.get("purchase_invoice_group_mismatches"),
		"Unsupported Debit discriminators": summary.get("unsupported_debit_discriminators"),
	}
	verified = all(value == 0 for value in checks.values())
	file_report = live.get("report", {}).get("files", {})
	retired = audit.get("retired_source_archives", {})
	archives = dict(audit.get("raw_source_archives", {}) or {})
	archives["tables"] = [
		row
		for row in archives.get("tables", [])
		if row.get("source_parent") != "Purchase Invoice"
	]
	archives["mismatch_count"] = sum(
		int(row.get("mismatch_count") or 0) for row in archives["tables"]
	)
	unavailable_files = int(audit.get('attachments', {}).get('missing_source_blob_count') or 0) + len(retired.get("missing_source_blobs", []))
	unavailable_files += int(audit.get("framework_history", {}).get("missing_blob_count") or 0)
	keys_unavailable = audit.get("auth", {}).get("source_key_unavailable_rows", 0)
	unindexed_references = int(audit.get('attachments', {}).get('missing_metadata_reference_count') or 0)
	readiness = audit.get('valuation_lineage_readiness') or {}
	unmapped = int(readiness.get('wholly_unmapped_grn_deliverables') or 0)
	valuation_notice = (
		f'Historical stock-valuation adjustments are not certified: {unmapped:,} GRN deliverable rows have no proven allocation links. See Archives & projections.'
		if unmapped else 'Historical stock-valuation readiness is a separate check; see Archives & projections.'
		if readiness else 'Historical stock-valuation readiness was not included in this audit.'
	)
	link_report = live.get('report', {}).get('links') or {}
	link_notice = (
		f"Pre-existing unresolved source links retained: {int(link_report.get('audited_broken_link_values') or 0):,}; unexpected broken target links: {int(link_report.get('unexpected_broken_link_values') or 0):,}. See Method & limits."
		if link_report else 'Built-in link verification details are not available yet.'
	)
	metrics = [("Source DocTypes", summary["source_doctypes"]), ("Source rows inspected", summary["source_rows_read"]),
		("Field values inspected", summary["source_field_values_seen"]), ("Field routes", summary["field_routes"])]
	cards = "".join(f'<div class="card"><strong>{value:,}</strong><span>{html.escape(label)}</span></div>' for label, value in metrics)
	check_rows = "".join(f'<tr><td>{html.escape(label)}</td><td class="number">{value if value is not None else "Not run"}</td></tr>' for label, value in checks.items())
	payload = {
		"fields": fields, "doctypes": doctype_rows,
		"corrections": [row for row in fields if row["source_field"] in CORRECTED_FIELDS.get(row["source_doctype"], set())],
		"archives": archives, "retired": retired,
		"framework": audit.get("framework_history", {}),
		"credentials": audit.get("auth", {}), "files": file_report,
		"attachments": audit.get("attachments", {}),
		"physical_pi": audit.get("purchase_invoice_physical_grns", {}),
		"reservations": audit.get("bin_reservations", {}),
		"default_fills": {"total": summary.get("target_fills_from_source_blank"),
			"verified": summary.get("verified_default_fills"),
			"unverified": summary.get("unverified_default_fills"),
			"fields": [{key: row.get(key) for key in ("source_doctype", "target_doctype", "context", "source_field", "target_fields", "target_filled_from_source_blank", "verified_default_fills", "default_fill_rule", "samples")}
				for row in fields if row.get("target_filled_from_source_blank")]},
		"debit": audit.get("debit_discriminator", {}), "live": live,
		"valuation_readiness": audit.get("valuation_lineage_readiness", {}),
		"audit_provenance": audit.get("framework_audit_refresh", {"method": audit.get("method"), "generated_on": audit.get("generated_on")}),
	}
	data = json.dumps(payload, ensure_ascii=False, default=str).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
	rendered = TEMPLATE.replace("__CARDS__", cards).replace("__CHECKS__", check_rows).replace(
		"__GENERATED__", html.escape(audit["generated_on"])).replace("__SOURCE__", html.escape(audit["source"]["site"])).replace(
		"__TARGET__", html.escape(audit["target"]["site"])).replace("__RESULT__", "Database comparison checks passed" if verified else "Database comparison needs review").replace(
		"__GAPS__", f"{unavailable_files:,} attachment blobs unavailable/corrupt in the source snapshot; {keys_unavailable} credentials cannot be decrypted with its current key. App file references without corresponding source File records: {unindexed_references}; see attachment evidence.").replace(
		"__LIVE_STATUS__", html.escape(str(live.get("status", "Not checked"))))
	return rendered.replace("__VALUATION_NOTICE__", html.escape(valuation_notice)).replace("__LINK_NOTICE__", html.escape(link_notice)).replace("__DATA__", data)


TEMPLATE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Production API migration reconciliation</title>
<style>
:root{font:14px/1.5 system-ui,sans-serif;color:#1e293b;background:#f3f6fa}*{box-sizing:border-box}body{margin:0}header{padding:28px max(20px,4vw);background:#10243a;color:white}h1{font-size:26px;margin:0 0 8px}h2{font-size:21px}header p{color:#d1e0ee;margin:0}nav{display:flex;overflow:auto;gap:8px;background:white;padding:12px max(20px,4vw);position:sticky;top:0;z-index:3;border-bottom:1px solid #d9e1e9}button{border:1px solid #c7d1dc;border-radius:7px;padding:8px 12px;background:white;color:#233d56;cursor:pointer;white-space:nowrap}button.active{background:#174e75;color:white;border-color:#174e75}main{max-width:1550px;margin:auto;padding:24px max(16px,3vw)}section{display:none}section.active{display:block}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin:20px 0}.card{padding:18px;border:1px solid #d9e1e9;background:white;border-radius:10px}.card strong{display:block;font-size:26px}.card span,.muted{color:#657487}.notice{padding:16px;border-left:4px solid #bb7806;background:#fff7df;border-radius:7px;margin:14px 0}.table{overflow:auto;background:white;border:1px solid #d9e1e9;border-radius:9px;max-height:70vh}table{width:100%;border-collapse:collapse}th,td{padding:9px 12px;text-align:left;vertical-align:top;border-bottom:1px solid #e8edf3}th{position:sticky;top:0;background:#eaf0f5;z-index:1;font-size:12px}td.number{text-align:right;font-variant-numeric:tabular-nums}.bad{color:#ae2828}.good{color:#14664d}code{font-family:ui-monospace,monospace;overflow-wrap:anywhere}.tools{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0}input,select{padding:10px;border:1px solid #9eafbd;border-radius:7px;background:white;min-width:230px}.pager{display:flex;align-items:center;gap:12px;margin:12px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:white;padding:18px;border-radius:9px;border:1px solid #d9e1e9;font-size:12px}.subtle{font-size:12px;color:#657487}a{color:#145a84}@media(max-width:650px){h1{font-size:21px}main{padding:14px}.card strong{font-size:22px}th,td{padding:8px}}
</style></head><body>
<header><h1>Production API → ERP Now: data reconciliation</h1><p>__SOURCE__ → __TARGET__ · __GENERATED__</p></header>
<nav><button class="active" data-tab="summary">Result</button><button data-tab="corrections">Corrected omissions</button><button data-tab="doctypes">DocType mapping</button><button data-tab="fields">Every field</button><button data-tab="framework">Supporting data & history</button><button data-tab="archives">Archives & projections</button><button data-tab="credentials">Credentials & files</button><button data-tab="method">Method & limits</button></nav>
<main><section id="summary" class="active"><h2>__RESULT__</h2><div class="notice"><strong>Not an unconditional production-ready certificate.</strong><br>__GAPS__<br>__VALUATION_NOTICE__<br>__LINK_NOTICE__<br>Migration screen status: <strong>__LIVE_STATUS__</strong>.</div><div class="cards">__CARDS__</div><div class="table"><table><thead><tr><th>Independent comparison</th><th>Unresolved count</th></tr></thead><tbody>__CHECKS__</tbody></table></div><p>Renamed fields and DocTypes are compared through their documented routes. Grouped rows and retired history are checked separately. Empty/retired field definitions remain visible in the field inventory.</p><p><a href="production-api-field-definitions-20260905.html">Open the separate missing-field definition inventory</a></p></section>
<section id="corrections"><h2>Fields restored or protected in this reload</h2><p>This is the reviewed change list, with counts from the current independent audit. Child-table fields are reconciled through their child rows; Password fields use the separate credential proof. Purchase Invoice data is represented only by direct GRN rows in <code>items</code> and grouped commercial rows in <code>essdee_items</code>.</p><div id="correction-table"></div><p>Additional cross-cutting fixes preserve original child positions, orphan child rows, source tags/comments/assignments, selected attachment URLs, and retired-table history. <code>Bin.reserved_qty → YRP Bin.reserved_qty</code> preserves the field name, label and stored balance. Stock Reservation Entry remains authoritative and keeps the visible Bin balance synchronized.</p></section>
<section id="doctypes"><h2>Every source DocType and target</h2><div class="tools"><input id="dt-search" placeholder="Search source or target"></div><div id="dt-table"></div><div id="dt-pager" class="pager"></div></section>
<section id="fields"><h2>Every source field route</h2><p>Missing values, precision changes, ignored fields, child tables, passwords, and preserved source metadata are all included. Counts refer to this audit, not an earlier migration.</p><div class="tools"><input id="field-search" placeholder="Search DocType, field, context"><select id="field-filter"><option value="all">All fields</option><option value="issues">Differences / missing / fills</option><option value="ignored">Ignored / no direct target</option><option value="schema">Schema gaps</option></select></div><div id="field-table"></div><div id="field-pager" class="pager"></div></section>
<section id="framework"><h2>Supporting masters, timeline and inactive history</h2><p>Address, Contact and their child links retain their original identities, with DocType controllers renamed. Ordinary comments and versions are restored to the native timeline. Every original SQL value is also stored in an encrypted private archive. Sharing keys, permission rows, workflow actions, mail, reports, import and integration configuration remain inactive archive data: migration does not activate old permissions, send messages or replace ERPNext configuration.</p><div id="framework-table"></div><h3>Every archived SQL field</h3><div id="framework-fields"></div><h3>Independent comparison and source attachment gaps</h3><pre id="framework-detail"></pre></section>
<section id="archives"><h2>Original values retained separately</h2><p>Purchase Invoice <code>items</code> contains direct GRN valuation variants and <code>essdee_items</code> contains grouped commercial rows; there is no third JSON item copy. IPD original process history is retained in <code>original_process_rows</code>. Retired tables are read-only audit data; their old workflows and permissions are not activated.</p><h3>Physical invoice rows versus original GRNs</h3><pre id="physical-pi-detail"></pre><h3>IPD raw process-row comparison</h3><pre id="archive-detail"></pre><h3>Retired SQL tables and attachments</h3><pre id="retired-detail"></pre><h3>Debit discriminator mapping</h3><pre id="debit-detail"></pre></section>
<section id="credentials"><h2>Credentials and attachment evidence</h2><p>Secret values are never rendered. Re-encrypted credentials are compared after decryption independently of the migration writer. Undecryptable source credentials require exact ciphertext preservation and remain explicitly unavailable.</p><div id="credential-table"></div><h3>Independent original File columns, folder links and byte checks</h3><pre id="attachment-detail"></pre><h3>Original migration attachment checks</h3><pre id="file-detail"></pre><p>Retired-dashboard attachment evidence appears in the archive tab. Missing source blobs need the original file archive; preserving a URL or File row does not recreate its contents.</p></section>
<section id="method"><h2>How this report was verified</h2><p>The independent audit reads source and target SQL by original row identity. It uses the reviewed routing contract only to locate fields, not the migration transformer to manufacture expected documents. It separately compares the two PI operational projections, the original IPD process-row archive, retired-table archives, and encrypted credential values.</p><p>Schema coverage includes the 262 active Production API DocTypes plus SMS Settings and SMS Parameter. Physical columns absent from live metadata, child parent contexts, user tags/comments/assignments, and removed-table history are considered separately. The supporting-data audit independently reconstructs direct/reverse Address and Contact links plus framework DocType references, children and attachments. It checks source identity digests, every archived SQL column, and native master/timeline values. Unrelated framework records and login sessions are not included; naming-series counters are preserved by their own check.</p><p>A database comparison does not supply missing source file bytes or a missing historical encryption key. It also does not certify every future business workflow. Existing broken source links are retained as source history rather than fabricated or silently removed.</p><h3>Live migration summary</h3><pre id="live-detail"></pre></section></main>
<script>
const data=__DATA__;
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=v=>Number(v||0).toLocaleString();
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>{document.querySelectorAll('nav button,main section').forEach(x=>x.classList.remove('active'));b.classList.add('active');document.getElementById(b.dataset.tab).classList.add('active')});
function table(id,heads,rows){document.getElementById(id).innerHTML='<div class="table"><table><thead><tr>'+heads.map(h=>'<th>'+esc(h)+'</th>').join('')+'</tr></thead><tbody>'+rows.join('')+'</tbody></table></div>'}
table('correction-table',['Source field','Target field','Context','Material source values','Exact matches','Mismatch / missing / rounding','Disposition'],data.corrections.map(r=>`<tr><td>${esc(r.source_doctype)}<br><code>${esc(r.source_field)}</code></td><td>${esc(r.target_doctype)}<br><code>${esc((r.target_fields||[]).join(', ')||'Raw source archive')}</code></td><td>${esc(r.context)}</td><td class="number">${num(r.source_material_values)}</td><td class="number">${num(r.exact_matches)}</td><td class="number">${num(r.mismatches+r.missing_target_rows+r.normalized_matches)}</td><td>${esc(r.disposition)}<br><span class="subtle">${esc(r.reason)}</span></td></tr>`));
function paged(kind,rows,filter,draw){let page=0;const size=150;function refresh(){const selected=rows.filter(filter),pages=Math.max(1,Math.ceil(selected.length/size));page=Math.min(page,pages-1);draw(selected.slice(page*size,(page+1)*size));const el=document.getElementById(kind+'-pager');el.innerHTML='<button data-dir="-1">Previous</button><span>Page '+(page+1)+' / '+pages+' · '+num(selected.length)+' rows</span><button data-dir="1">Next</button>';el.querySelectorAll('button').forEach(b=>b.onclick=()=>{page=Math.min(pages-1,Math.max(0,page+Number(b.dataset.dir)));refresh()})}refresh();return ()=>{page=0;refresh()}}
let dtQuery='';const dtRefresh=paged('dt',data.doctypes,r=>!dtQuery||(r.doctype+' '+r.targets.join(' ')).toLowerCase().includes(dtQuery),rows=>table('dt-table',['Source','Target','Source rows','Missing direct rows','Separately projected'],rows.map(r=>`<tr><td>${esc(r.doctype)}</td><td>${r.targets.map(esc).join('<br>')}</td><td class="number">${num(r.rows)}</td><td class="number ${r.missing?'bad':''}">${num(r.missing)}</td><td class="number">${num(r.projected)}</td></tr>`)));document.getElementById('dt-search').oninput=e=>{dtQuery=e.target.value.toLowerCase();dtRefresh()};
let query='',filter='all';const fieldRefresh=paged('field',data.fields,r=>(!query||[r.source_doctype,r.target_doctype,r.source_field,r.context,...(r.target_fields||[])].join(' ').toLowerCase().includes(query))&&(filter==='all'||filter==='issues'&&(r.mismatches||r.missing_target_rows||r.normalized_matches||r.target_filled_from_source_blank)||filter==='ignored'&&(r.disposition==='ignored'||!(r.target_fields||[]).length)||filter==='schema'&&r.status==='Schema Gap'),rows=>table('field-table',['Source → target','Context / field','Target field','Disposition','Seen','Exact','Rounded','Mismatch','Missing','Filled / verified blanks','Status'],rows.map(r=>`<tr><td>${esc(r.source_doctype)}<br><span class="muted">→ ${esc(r.target_doctype)}</span></td><td><span class="subtle">${esc(r.context)}</span><br><code>${esc(r.source_field)}</code></td><td><code>${esc((r.target_fields||[]).join(', ')||'—')}</code></td><td>${esc(r.disposition)}<br><span class="subtle">${esc(r.reason)}</span></td><td class="number">${num(r.source_values_seen)}</td><td class="number">${num(r.exact_matches)}</td><td class="number ${r.normalized_matches?'bad':''}">${num(r.normalized_matches)}</td><td class="number ${r.mismatches?'bad':''}">${num(r.mismatches)}</td><td class="number ${r.missing_target_rows?'bad':''}">${num(r.missing_target_rows)}</td><td class="number ${r.target_filled_from_source_blank!==(r.verified_default_fills||0)?'bad':''}" title="${esc(r.default_fill_rule)}">${num(r.target_filled_from_source_blank)} / ${num(r.verified_default_fills)}</td><td>${esc(r.status)}</td></tr>`)));document.getElementById('field-search').oninput=e=>{query=e.target.value.toLowerCase();fieldRefresh()};document.getElementById('field-filter').onchange=e=>{filter=e.target.value;fieldRefresh()};
table('credential-table',['Source','Target','Present','Value proof','Record identity'],(data.credentials.rows||[]).map(r=>`<tr><td>${esc(r.source_doctype)}<br><code>${esc(r.source_field)}</code></td><td>${esc(r.target_doctype)}<br><code>${esc(r.target_field)}</code></td><td>${r.target_auth_row_exists?'Yes':'No'}</td><td class="${r.value_matches?'good':'bad'}">${esc(r.value_status||r.status)}</td><td class="${r.record_identity_matches?'good':'bad'}">${r.record_identity_matches?(r.source_record_exists?'Existing record':'Source orphan preserved; no record recreated'):'Unverified or mismatched'}</td></tr>`));
table('framework-table',['Source table','Archived source rows','Native master / timeline rows','Archive-only rows'],Object.entries(data.framework.tables||{}).map(([dt,count])=>`<tr><td>${esc(dt)}</td><td class="number">${num(count)}</td><td class="number">${num(data.framework.native_tables?.[dt])}</td><td class="number">${num(count-(data.framework.native_tables?.[dt]||0))}</td></tr>`));
table('framework-fields',['Source table','SQL field','Values checked'],Object.entries(data.framework.field_inventory||{}).flatMap(([dt,fields])=>Object.entries(fields).map(([field,count])=>`<tr><td>${esc(dt)}</td><td><code>${esc(field)}</code></td><td class="number">${num(count)}</td></tr>`)));
const {field_inventory: _fieldInventory,...frameworkSummary}=data.framework;
document.getElementById('physical-pi-detail').textContent=JSON.stringify(data.physical_pi,null,2);
const reservationHeading=document.createElement('h3');reservationHeading.textContent='Historical Bin cache and active reservations';
const reservationDetail=document.createElement('pre');reservationDetail.id='reservation-detail';reservationDetail.textContent=JSON.stringify(data.reservations,null,2);
document.getElementById('corrections').append(reservationHeading,reservationDetail);
const fillHeading=document.createElement('h3');fillHeading.textContent='Disclosed source blanks filled on target';
const fillNote=document.createElement('p');fillNote.textContent='These values were blank in the original source. Verified fills match independently checked source relationships or explicit reviewed defaults; they are not counted as exact copies. Unknown or incorrect fills remain unresolved.';
const fillDetail=document.createElement('pre');fillDetail.id='default-fill-detail';fillDetail.textContent=JSON.stringify(data.default_fills,null,2);
document.getElementById('fields').append(fillHeading,fillNote,fillDetail);
const lineageHeading=document.createElement('h3');lineageHeading.textContent='Historical stock-valuation link readiness (separate from copied source values)';
const lineageNote=document.createElement('p');lineageNote.textContent='These are new target allocation links, not omitted source fields. Ambiguous historical input-to-output allocations are not guessed. Nonzero unresolved or invalid counts require review before using historical valuation adjustments, even if original source values compare successfully.';
const lineageDetail=document.createElement('pre');lineageDetail.id='valuation-readiness-detail';lineageDetail.textContent=JSON.stringify(data.valuation_readiness,null,2);
document.getElementById('archives').append(lineageHeading,lineageNote,lineageDetail);
const provenanceHeading=document.createElement('h3');provenanceHeading.textContent='Audit provenance';
const provenanceDetail=document.createElement('pre');provenanceDetail.id='audit-provenance';provenanceDetail.textContent=JSON.stringify(data.audit_provenance,null,2);
document.getElementById('method').append(provenanceHeading,provenanceDetail);
const numericNote=document.createElement('p');numericNote.id='builtin-numeric-note';numericNote.textContent='The built-in verifier compares transformed/generated values at target SQL precision and reports its numeric storage normalizations separately below. That counter is not the independent original-source rounding counter above. Original PI values are checked through the direct GRN and grouped operational tables; derived PI amounts also have a disclosed arithmetic/storage tolerance.';
document.getElementById('live-detail').before(numericNote);
for(const [id,value] of [['archive-detail',data.archives],['retired-detail',data.retired],['framework-detail',frameworkSummary],['debit-detail',data.debit],['attachment-detail',data.attachments],['file-detail',data.files],['live-detail',data.live]])document.getElementById(id).textContent=JSON.stringify(value,null,2);
</script></body></html>'''


def main():
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--audit", type=Path, required=True)
	parser.add_argument("--output", type=Path, required=True)
	args = parser.parse_args()
	audit = json.loads(args.audit.read_text())
	target = audit["target"]
	connection = _connect(Path(target["bench"]), target["site"])
	try:
		with connection.cursor() as cursor:
			cursor.execute("SELECT name,status,last_action,report_json FROM `tabSD YRP MRP Data Migration` WHERE name=%s", (audit["migration_name"],))
			row = cursor.fetchone()
		if not row:
			raise RuntimeError("Migration audit record not found")
		report = json.loads(row.pop("report_json") or "{}")
		live = {**row, "report": {key: report.get(key) for key in ("mode", "failed", "complete_source_preservation", "identities", "values", "orphan_values", "auth", "files", "stock", "links", "retired_tables", "framework_history", "series", "purchase_invoice_physical_projection", "purchase_order_dual_projection")}}
	finally:
		connection.close()
	args.output.write_text(render(audit, live), encoding="utf-8")
	print(json.dumps({"html": str(args.output), "audit_generated_on": audit["generated_on"], "migration_status": live["status"]}))


if __name__ == "__main__":
	main()

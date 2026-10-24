# Copyright (c) 2026, Essdee and contributors
# For license information, please see license.txt
import json
from datetime import timedelta

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime, time_diff_in_seconds
from frappe.utils.background_jobs import get_job
from rq.job import JobStatus
from rq.utils import now as rq_now
from yrp.attribute_links import value as _attribute_value

DOCTYPE = "SD YRP Cutting Laysheet Planner"
ACTIVE_OPTIMIZATION_STATUSES = {"Queued", "Running"}
OPTIMIZATION_METHOD = f"{__name__}.run_optimization"
OPTIMIZATION_QUEUE = "long"
OPTIMIZATION_TIMEOUT = 900
STALE_OPTIMIZATION_SECONDS = OPTIMIZATION_TIMEOUT + 300
ENQUEUE_GRACE_SECONDS = 60
LIVE_JOB_STATUSES = {JobStatus.QUEUED, JobStatus.STARTED, JobStatus.DEFERRED, JobStatus.SCHEDULED}


class SDYRPCuttingLaysheetPlanner(Document):
	def validate(self):
		values = _get_optimizer_inputs(self)
		_validate_optimizer_inputs(values)

		previous = self.get_doc_before_save()
		if not previous:
			if not self.optimization_status:
				self.optimization_status = "Not Started"
			return

		inputs_changed = _input_fingerprint(values) != _input_fingerprint(_get_optimizer_inputs(previous))
		if not inputs_changed:
			return

		if previous.optimization_status in ACTIVE_OPTIMIZATION_STATUSES:
			frappe.throw("Inputs cannot be changed while lay optimization is queued or running.")

		_clear_results(self)
		self.optimization_status = "Not Started"
		self.optimization_started_on = None
		self.optimization_completed_on = None
		self.optimization_error = None
		self.optimization_input_json = None


@frappe.whitelist()
def optimize(doc_name):
	"""Validate saved inputs and queue the complete strategy portfolio."""
	doc = frappe.get_doc(DOCTYPE, doc_name)
	doc.check_permission("write")

	if doc.optimization_status in ACTIVE_OPTIMIZATION_STATUSES:
		frappe.throw(f"Optimization is already {doc.optimization_status.lower()}.")

	values = _get_optimizer_inputs(doc)
	_validate_optimizer_inputs(values)
	input_json = json.dumps(values, separators=(",", ":"), ensure_ascii=False)

	discard_stale_optimization_job(doc.name)
	_clear_results(doc)
	doc.optimization_status = "Queued"
	doc.optimization_started_on = None
	doc.optimization_completed_on = None
	doc.optimization_error = None
	doc.optimization_input_json = input_json
	doc.save()

	frappe.enqueue(
		OPTIMIZATION_METHOD,
		queue=OPTIMIZATION_QUEUE,
		timeout=OPTIMIZATION_TIMEOUT,
		enqueue_after_commit=True,
		job_id=get_optimization_job_id(doc.name),
		deduplicate=True,
		doc_name=doc.name,
		input_json=input_json,
	)

	return {"doc_name": doc.name, "status": "Queued"}


def run_optimization(doc_name, input_json):
	"""Run v4.1 in a long-queue worker and persist validated portfolio results."""
	doc = frappe.get_doc(DOCTYPE, doc_name)
	if doc.optimization_status != "Queued" or doc.optimization_input_json != input_json:
		return

	doc.db_set(
		{
			"optimization_status": "Running",
			"optimization_started_on": now_datetime(),
			"optimization_completed_on": None,
			"optimization_error": None,
		},
		notify=True,
		commit=True,
	)

	try:
		from essdee_yrp.cutting.lay_optimizer import (
			optimize_all_strategies,
		)

		values = json.loads(input_json)
		results, outcomes = optimize_all_strategies(**values)
		payload = {
			"results": results,
			"failed": outcomes,
			"input": values,
			"optimizer_version": "4.1.0",
		}

		if not results:
			_mark_optimization_failed(
				doc_name,
				input_json,
				"No feasible lay plan was found. Review the strategy outcomes and constraints.",
				payload,
			)
			return

		doc = frappe.get_doc(DOCTYPE, doc_name)
		if doc.optimization_input_json != input_json:
			return

		_apply_results(doc, results, outcomes, values)
		doc.optimization_status = "Completed"
		doc.optimization_completed_on = now_datetime()
		doc.optimization_error = None
		doc.flags.ignore_permissions = True
		doc.save()
		doc.notify_update()
	except Exception:
		frappe.db.rollback()
		frappe.log_error(
			title=f"Lay optimization failed: {doc_name}",
			message=frappe.get_traceback(with_context=True),
		)
		_mark_optimization_failed(
			doc_name,
			input_json,
			"Lay optimization failed unexpectedly. Please review the Error Log or contact an administrator.",
		)
		raise


def get_optimization_job_id(doc_name):
	return f"cutting-laysheet-optimizer-{doc_name}"


def discard_stale_optimization_job(doc_name):
	"""Drop a leftover RQ job so a retry is not swallowed by enqueue deduplication."""
	job = get_job(get_optimization_job_id(doc_name))
	if not job:
		return
	if job.get_status() == JobStatus.STARTED and job.started_at:
		if (rq_now() - job.started_at) < timedelta(seconds=STALE_OPTIMIZATION_SECONDS):
			frappe.throw("The previous lay optimization job is still running. Try again when it finishes.")
	job.delete()


def get_stuck_optimization_message(doc):
	"""Return why an active optimization can no longer finish, or None while it still can."""
	job = get_job(get_optimization_job_id(doc.name))
	status = job.get_status() if job else None
	age = time_diff_in_seconds(now_datetime(), doc.modified)
	if status == JobStatus.FAILED:
		lines = str(job.exc_info or "").strip().splitlines() or ["unknown error"]
		return f"Lay optimization job failed: {lines[-1]}"
	if status in LIVE_JOB_STATUSES:
		if age <= STALE_OPTIMIZATION_SECONDS:
			return None
		return (
			f"Lay optimization did not finish within {STALE_OPTIMIZATION_SECONDS // 60} minutes. "
			f"Check that a background worker is running the '{OPTIMIZATION_QUEUE}' queue, then retry."
		)
	if age <= ENQUEUE_GRACE_SECONDS:
		return None
	return "Lay optimization job ended without saving a result. Retry the optimization."


def recover_stuck_optimization(doc):
	"""Mark a Queued/Running planner Failed when its background job cannot finish it."""
	if doc.optimization_status not in ACTIVE_OPTIMIZATION_STATUSES:
		return False
	message = get_stuck_optimization_message(doc)
	if not message:
		return False
	_mark_optimization_failed(doc.name, doc.optimization_input_json, message)
	doc.reload()
	return True


@frappe.whitelist()
def get_optimization_status(doc_name):
	"""Return only lightweight state; the form reloads once work is complete."""
	doc = frappe.get_doc(DOCTYPE, doc_name)
	doc.check_permission("read")
	recover_stuck_optimization(doc)
	return {
		"status": doc.optimization_status or "Not Started",
		"error_message": doc.optimization_error,
		"started_on": doc.optimization_started_on,
		"completed_on": doc.optimization_completed_on,
		"modified": doc.modified,
	}


@frappe.whitelist()
def select_strategy(doc_name, strategy):
	doc = frappe.get_doc(DOCTYPE, doc_name)
	doc.check_permission("write")

	if not doc.result_json:
		frappe.throw("No optimization results found. Please run Optimize first.")

	stored = json.loads(doc.result_json)
	results = stored.get("results", [])
	outcomes = stored.get("failed", [])

	selected = next(
		(result for result in results if result.get("strategy") == strategy),
		None,
	)
	if not selected:
		outcome = next(
			(item for item in outcomes if item.get("strategy") == strategy and item.get("success")),
			None,
		)
		if outcome and outcome.get("deduplicated"):
			selected = next(
				(result for result in results if result.get("strategy") == outcome.get("same_as")),
				None,
			)
		elif outcome:
			selected = outcome

	if not selected:
		frappe.throw(f"Strategy '{strategy}' is not available for selection.")

	doc.selected_strategy = strategy
	_apply_summary(doc, selected["summary"])
	doc.save()
	return {"doc_name": doc.name, "selected_strategy": strategy}


def _get_optimizer_inputs(doc):
	order = {}
	seen_sizes = set()

	if not doc.order_details:
		frappe.throw("Please add at least one size and quantity before optimizing.")

	for row in doc.order_details:
		size = (_attribute_value(row.size) or "").strip()
		if not size:
			frappe.throw(f"Size is required in order row {row.idx}.")
		if size in seen_sizes:
			frappe.throw(f"Duplicate size '{size}' is not allowed.")
		seen_sizes.add(size)
		order[size] = row.qty

	return {
		"order": order,
		"max_plies": doc.max_plies,
		"max_pieces": doc.max_pieces,
		"tolerance_pct": (doc.tolerance_pct if doc.tolerance_pct is not None else 3.0),
		"max_lays": doc.max_lays if doc.max_lays is not None else 8,
		"tubular": bool(doc.tubular),
	}


def _validate_optimizer_inputs(values):
	from essdee_yrp.cutting.lay_optimizer.common import (
		validate_inputs,
	)

	try:
		validate_inputs(
			values["order"],
			values["max_plies"],
			values["max_pieces"],
			values["tolerance_pct"],
			values["max_lays"],
		)
	except (TypeError, ValueError) as exc:
		frappe.throw(str(exc))


def _input_fingerprint(values):
	return json.dumps(values, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _clear_results(doc):
	doc.set("lay_details", [])
	doc.total_lays = 0
	doc.total_order = 0
	doc.total_cut = 0
	doc.overcut = 0
	doc.overcut_pct = 0
	doc.undercut = 0
	doc.undercut_pct = 0
	doc.selected_strategy = None
	doc.result_json = None


def _apply_results(doc, results, outcomes, values):
	doc.set("lay_details", [])
	for result in results:
		for lay in result["lays"]:
			doc.append(
				"lay_details",
				{
					"strategy": result["strategy"],
					"lay_no": lay["lay_no"],
					"plies": lay["plies"],
					"ratio": json.dumps(lay["ratio"], ensure_ascii=False),
					"pieces_per_ply": lay["pieces_per_ply"],
					"total_pieces": lay["total_pieces"],
					"cut_per_size": json.dumps(lay["cut_per_size"], ensure_ascii=False),
				},
			)

	best = results[0]
	doc.selected_strategy = best["strategy"]
	_apply_summary(doc, best["summary"])
	doc.result_json = json.dumps(
		{
			"results": results,
			"failed": outcomes,
			"input": values,
			"optimizer_version": "4.1.0",
		},
		ensure_ascii=False,
	)


def _apply_summary(doc, summary):
	doc.total_lays = summary["total_lays"]
	doc.total_cut = summary["total_cut"]
	doc.total_order = summary["total_order"]
	doc.overcut = summary["overcut"]
	doc.overcut_pct = summary["overcut_pct"]
	doc.undercut = summary["undercut"]
	doc.undercut_pct = summary["undercut_pct"]


def _mark_optimization_failed(doc_name, input_json, message, payload=None):
	values = {
		"optimization_status": "Failed",
		"optimization_completed_on": now_datetime(),
		"optimization_error": message,
	}
	if payload is not None:
		values["result_json"] = json.dumps(payload, ensure_ascii=False)

	current_snapshot = frappe.db.get_value(DOCTYPE, doc_name, "optimization_input_json")
	if current_snapshot != input_json:
		return

	frappe.db.set_value(DOCTYPE, doc_name, values, update_modified=True)
	frappe.db.commit()
	frappe.get_doc(DOCTYPE, doc_name).notify_update()


CuttingLaysheetPlanner = SDYRPCuttingLaysheetPlanner

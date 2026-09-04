# Payroll Specialist Responsibilities

## Role summary

The Payroll Specialist reviews every department's submission each cycle,
resolves or queries flagged issues, approves clean submissions, and
exports the approved data for payment. The Specialist is the final human
decision-maker -- nothing is approved automatically.

## Reviewing issues

For each flagged issue, decide whether to accept it as correct, reject the
row, or add it to a query back to the department. Factual errors (unknown
Staff ID, missing values, duplicates, out-of-range values) rarely need
judgement -- they should be corrected by the department. Judgement-based
issues, particularly unusual overtime, need a decision about whether the
explanation given is plausible.

## Querying a department

When something needs the department's confirmation before approval, send a
correction query listing the specific items. Be specific about which row
and what is being asked, so the submitter can respond efficiently.

## Reading a submitter's response

When a submitter answers a query, their response falls into one of three
categories: the value is confirmed correct (with an explanation), the
value is wrong and will be corrected via resubmission, or the submitter is
not sure and needs guidance. Only the first case is normally sufficient to
resolve the item without a resubmission.

## Approval

A submission can only be approved once every issue on the current version
has been accepted, rejected, or answered. A submission that was blocked
before validation ever ran (for example because of a column mapping
conflict, or because the file did not look like payroll data) cannot be
approved either, since it has not actually been checked -- it must be
fixed and resubmitted by the department first.

## Export

Once a submission is approved, its rows become part of the clean dataset
ready for export. Only approved submissions are included in an export --
unresolved departments are simply left out of that export and picked up
once they are ready.

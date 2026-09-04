# Employee Master Data Rules

## What the employee master record is

The employee master record is the authoritative list of who is employed in
each department, maintained separately from any single payroll submission.
Every payroll row is checked against it. A payroll file cannot introduce a
new employee on its own -- the employee master record must already contain
the Staff ID before that employee can be paid.

## Fields on the employee master record

Each employee record holds: Staff ID, full name, department, employment
status (active or exited), grade, basic pay, allowances, and an average
overtime figure calculated from recent periods.

## Adding a new employee

If a payroll file includes someone who genuinely is a new employee but does
not yet exist in the employee master record, the row will be flagged as an
unknown employee. The department must arrange for the employee master
record to be updated before that person can be paid -- this is not
something a submitter can fix by editing the spreadsheet alone, since the
underlying record has to exist first.

## Exited employees

When someone leaves the organisation, their employee master record is
marked as exited, with the date they left. A payroll file that still
includes an exited employee will be flagged, because paying someone after
their exit date is treated as an error unless proven otherwise.

## Keeping records current

Departments are responsible for promptly reporting starters, leavers, and
grade or department changes so the employee master record stays accurate.
An out-of-date master record is one of the most common causes of payroll
validation issues.

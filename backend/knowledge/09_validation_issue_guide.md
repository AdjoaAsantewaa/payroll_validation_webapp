# Validation Issue Guide

## Unknown employee

The Staff ID on this row does not match anyone in the employee master
data. Check the ID against your department's records. If this is a
genuinely new employee, they must be added to the employee master data
before they can be paid -- editing the spreadsheet alone does not create
an employee record. If the ID was entered incorrectly, correct it and
resubmit.

## Exited employee

The Staff ID belongs to an employee whose record shows they have exited
the organisation. Remove the row if they should not be paid this period,
or provide a specific explanation if a payment is genuinely still due
(see Exited Employee Guidance).

## Duplicate entry

The same Staff ID appears more than once in the file. Keep only the
correct entry and remove the other, then resubmit.

## Missing information

A required field -- Staff ID, employee name, or overtime hours -- is
empty for this row. Fill in the value in the source file and resubmit.

## Invalid value

A submitted value falls outside the permitted range -- for example,
negative overtime hours, or overtime above the permitted ceiling for a
single period. Correct the value in the source file; this is always a
data error, never something to explain around.

## Unusual overtime

The submitted overtime hours are technically within range but
substantially above this employee's own recent average. This may be a
genuine mistake or a legitimate unusual period. If correct, explain it for
the Payroll Specialist; if not, correct the value and resubmit (see
Overtime Guidance).

## Employee details mismatch / unusual allowance

A value such as an allowance does not match what has previously been paid
at this employee's grade. Confirm whether the new value is intentional and
provide an explanation, or correct the file if it was entered in error.

## Column mapping issue

Two columns in the source file were matched to the same expected field,
which the system cannot resolve on its own. Adjust the mapping so each
field is matched to exactly one column, then continue.

## File structure issue

The uploaded file does not contain anything resembling the fields payroll
validation needs (for example, no column that looks like overtime hours at
all). This usually means the wrong file was uploaded, or the mapping needs
to be reviewed before the file can be checked row by row.

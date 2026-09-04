# Staff ID / Data Quality Standards

## Staff ID is the anchor field

Every payroll row is matched to an employee by Staff ID. If the Staff ID is
missing, misspelled, or does not match any record in the employee master
data, the system cannot safely process that row at all -- no other field
is used as a substitute for matching an employee.

## Common causes of a Staff ID mismatch

The most frequent causes are: the ID was typed incorrectly, a column other
than the real Staff ID column was mapped to Staff ID by mistake, the
employee is genuinely new and not yet in the employee master data, or the
row belongs to a different department's ID range entirely.

## Required fields

At minimum, every row needs a Staff ID, an employee name, and an overtime
hours figure (which may legitimately be zero, but must be present). Rows
missing any of these are flagged and cannot be validated further until the
value is supplied.

## Duplicate entries

The same Staff ID must not appear more than once in a single submission.
A duplicate usually means a row was copied by mistake, or the same person
was entered twice under slightly different details. Keep only the correct
entry and remove the other.

## Column mapping quality

Source spreadsheets do not need to use the exact same column names every
time -- the system matches common variations (for example "Emp No.",
"Staff No.", or "Personnel No." are all recognised as the Staff ID column).
However, two different source columns must never be mapped to the same
field, and a file that does not contain anything resembling the required
fields at all will be rejected before row-by-row checking even starts, so
that submitters are not shown a wall of unrelated errors from an
unsuitable file.

const FIELDS = [
  {
    name: "Staff ID",
    required: true,
    description:
      "Uniquely identifies the employee and is matched against this department's employee records. " +
      "Every row needs one, and the same Staff ID can't appear twice in a submission.",
  },
  {
    name: "Full Name",
    required: true,
    description: "The employee's name, used alongside the Staff ID to confirm the match.",
  },
  {
    name: "Overtime Hours",
    required: true,
    description: "Hours worked beyond normal hours for the period. Enter 0 if none — the field still needs a value.",
  },
  {
    name: "Basic Pay",
    required: false,
    description: "The employee's basic salary for the period.",
  },
  {
    name: "Allowances",
    required: false,
    description: "Any additional allowances paid for the period.",
  },
];

export function PayrollFormatModal({ onClose }: { onClose: () => void }) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
      onClick={onClose}
    >
      <div
        className="max-h-[85vh] w-full max-w-[560px] overflow-y-auto rounded-xl bg-white p-4 shadow-2xl sm:p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-[16px] font-bold">Payroll format</h2>
            <p className="mt-0.5 text-[12px] text-[#8a8a8a]">
              What a department's payroll file needs to include
            </p>
          </div>
          <button onClick={onClose} className="shrink-0 text-[#8a8a8a] hover:text-[#111]">
            ✕
          </button>
        </div>

        <p className="mb-4 text-[13px] leading-relaxed text-[#333]">
          One spreadsheet (CSV or Excel), one row per employee being paid this cycle. Column
          headers don't need to match exactly — common variations (e.g. "Emp No.", "Staff No.")
          are recognised automatically during upload.
        </p>

        <div className="flex flex-col gap-2.5">
          {FIELDS.map((f) => (
            <div key={f.name} className="rounded-md border border-[#eee] px-3 py-2.5">
              <div className="mb-0.5 flex items-center gap-1.5">
                <span className="text-[13px] font-semibold text-[#111]">{f.name}</span>
                {f.required && (
                  <span className="badge badge-grey">Required</span>
                )}
              </div>
              <p className="text-[12px] leading-relaxed text-[#666]">{f.description}</p>
            </div>
          ))}
        </div>

        <p className="mt-4 text-[11px] text-[#999]">
          Rows missing a required field, or with a Staff ID that doesn't match this department's
          records, are flagged for correction after upload.
        </p>
      </div>
    </div>
  );
}

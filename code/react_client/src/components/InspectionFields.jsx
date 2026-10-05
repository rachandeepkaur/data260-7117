import { useSelector } from "react-redux";

// Form fields shared by the create and update screens. `values` uses the API
// field names; `onChange(field, value)` updates one of them.
export default function InspectionFields({ values, onChange, disabled = false, autoFocus = false }) {
  const inspectors = useSelector((state) => state.inspectors.items);
  const field = (name) => ({
    value: values[name],
    onChange: (e) => onChange(name, e.target.value),
    disabled,
  });

  return (
    <>
      <label>
        Inspection Code
        <input {...field("inspection_code")} placeholder="e.g., INS-005001" pattern="INS-\d{6}"
               title="INS- followed by 6 digits" required autoFocus={autoFocus} />
      </label>
      <label>
        Facility Name / ID
        <input {...field("facility_name")} placeholder="e.g., FA0206933 - YUMMY KITCHEN" required />
      </label>
      <label>
        Program Site Address
        <input {...field("site_address")} placeholder="e.g., 1711 BRANHAM LN A9, SAN JOSE, CA 95118" required />
      </label>
      <label>
        Score (0-100)
        <input {...field("score")} type="number" min="0" max="100" required />
      </label>
      <label>
        Inspector
        <select {...field("inspector_id")} required>
          <option value="">Select an inspector…</option>
          {inspectors.map((i) => (
            <option key={i.id} value={i.id}>{i.id} - {i.full_name} ({i.district})</option>
          ))}
        </select>
      </label>
    </>
  );
}

export const toPayload = (values) => ({
  ...values,
  score: Number(values.score),
  inspector_id: Number(values.inspector_id),
});

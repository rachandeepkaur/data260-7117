import { useEffect, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import { updateInspection } from "../store/inspectionsSlice.js";
import InspectionFields, { toPayload } from "./InspectionFields.jsx";

const pick = (r) => ({
  inspection_code: r.inspection_code,
  facility_name: r.facility_name,
  site_address: r.site_address,
  score: String(r.score),
  inspector_id: String(r.inspector_id),
});

// Rendered at /update?id=<record id>; without an id it asks for one.
export default function UpdateRecord() {
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const recordId = searchParams.get("id");
  const cached = useSelector((state) => state.inspections.items.find((r) => String(r.id) === recordId));
  const [idInput, setIdInput] = useState("");
  const [values, setValues] = useState(null);
  const [error, setError] = useState("");

  // Prefill from the Redux list when the record is on the current page,
  // otherwise GET /api/records/{id}. `ignore` drops a stale response (e.g.
  // StrictMode's second run) so it can't overwrite what the user typed.
  useEffect(() => {
    if (!recordId) return undefined;
    let ignore = false;
    setValues(null);
    setError("");
    if (cached) {
      setValues(pick(cached));
      return undefined;
    }
    api
      .getRecord(recordId)
      .then(({ data }) => { if (!ignore) setValues(pick(data)); })
      .catch((err) => { if (!ignore) setError(err.message); });
    return () => { ignore = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only refetch when the id changes
  }, [recordId]);

  const handleSubmit = async (event) => {
    event.preventDefault();
    try {
      await dispatch(updateInspection({ id: Number(recordId), changes: toPayload(values) })).unwrap();
      navigate("/");
    } catch (err) {
      setError(err.message);
    }
  };

  if (!recordId) {
    return (
      <form className="card form" onSubmit={(e) => { e.preventDefault(); setSearchParams({ id: idInput }); }}>
        <h2>Update Inspection Record</h2>
        <label>
          Record ID
          <input type="number" min="1" value={idInput} onChange={(e) => setIdInput(e.target.value)} required />
        </label>
        <button type="submit" className="btn">Load Record</button>
      </form>
    );
  }

  return (
    <form className="card form" onSubmit={handleSubmit}>
      <h2>Update Inspection Record #{recordId}</h2>
      {error && <div className="alert">{error}</div>}
      {values && (
        <>
          <InspectionFields values={values} onChange={(k, v) => setValues({ ...values, [k]: v })} />
          <button type="submit" className="btn btn-primary">Update Inspection Record</button>
        </>
      )}
    </form>
  );
}

import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

// Rendered at /delete?id=<record id>; without an id it asks for one.
export default function DeleteRecord({ onDeleteRecord, fetchRecord }) {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const recordId = searchParams.get("id");
  const [idInput, setIdInput] = useState("");
  const [record, setRecord] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!recordId) return undefined;
    let ignore = false;
    setRecord(null);
    fetchRecord(recordId)
      .then((data) => { if (!ignore) { setRecord(data); setError(""); } })
      .catch((err) => { if (!ignore) setError(err.message); });
    return () => { ignore = true; };
  }, [recordId, fetchRecord]);

  const handleDelete = async () => {
    try {
      await onDeleteRecord(recordId);
      navigate("/");
    } catch (err) {
      setError(err.message);
    }
  };

  if (!recordId) {
    return (
      <form className="card form" onSubmit={(e) => { e.preventDefault(); setSearchParams({ id: idInput }); }}>
        <h2>Delete Inspection Record</h2>
        <label>
          Record ID
          <input type="number" min="1" value={idInput} onChange={(e) => setIdInput(e.target.value)} required />
        </label>
        <button type="submit" className="btn">Load Record</button>
      </form>
    );
  }

  return (
    <div className="card form">
      <h2>Delete Inspection Record #{recordId}</h2>
      {error && <div className="alert">{error}</div>}
      {record && (
        <dl>
          <dt>Facility Name / ID</dt>
          <dd>{record.facility_name}</dd>
          <dt>Program Site Address</dt>
          <dd>{record.site_address}</dd>
        </dl>
      )}
      <div className="actions">
        <button className="btn btn-danger" onClick={handleDelete} disabled={!record}>Delete Inspection Record</button>
        <button className="btn" onClick={() => navigate("/")}>Cancel</button>
      </div>
    </div>
  );
}

import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

// Rendered at /update?id=<record id>; without an id it asks for one.
export default function UpdateRecord({ onUpdateRecord, fetchRecord }) {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const recordId = searchParams.get("id");
  const [idInput, setIdInput] = useState("");
  const [facilityName, setFacilityName] = useState("");
  const [siteAddress, setSiteAddress] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");

  // Prefill the form with the record's current values from MySQL. `ignore`
  // drops a stale response (e.g. StrictMode's second run) so it can't
  // overwrite what the user has already typed.
  useEffect(() => {
    if (!recordId) return undefined;
    let ignore = false;
    setLoaded(false);
    fetchRecord(recordId)
      .then((record) => {
        if (ignore) return;
        setFacilityName(record.facility_name);
        setSiteAddress(record.site_address);
        setLoaded(true);
        setError("");
      })
      .catch((err) => { if (!ignore) setError(err.message); });
    return () => { ignore = true; };
  }, [recordId, fetchRecord]);

  const handleSubmit = async (event) => {
    event.preventDefault();
    try {
      await onUpdateRecord(recordId, { facility_name: facilityName, site_address: siteAddress });
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
      <label>
        Facility Name / ID
        <input value={facilityName} onChange={(e) => setFacilityName(e.target.value)} required disabled={!loaded} />
      </label>
      <label>
        Program Site Address
        <input value={siteAddress} onChange={(e) => setSiteAddress(e.target.value)} required disabled={!loaded} />
      </label>
      <button type="submit" className="btn btn-primary" disabled={!loaded}>Update Inspection Record</button>
    </form>
  );
}

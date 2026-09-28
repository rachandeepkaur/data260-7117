import { useState } from "react";
import { useNavigate } from "react-router-dom";

export default function CreateRecord({ onAddRecord }) {
  const navigate = useNavigate();
  const [facilityName, setFacilityName] = useState("");
  const [siteAddress, setSiteAddress] = useState("");
  const [error, setError] = useState("");

  const handleSubmit = async (event) => {
    event.preventDefault();
    try {
      // The id is assigned by MySQL AUTO_INCREMENT on the backend.
      await onAddRecord({ facility_name: facilityName, site_address: siteAddress });
      navigate("/");
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <form className="card form" onSubmit={handleSubmit}>
      <h2>Add Inspection Record</h2>
      {error && <div className="alert">{error}</div>}
      <label>
        Facility Name / ID
        <input
          value={facilityName}
          onChange={(e) => setFacilityName(e.target.value)}
          placeholder="e.g., FA0206933 - YUMMY KITCHEN"
          required
          autoFocus
        />
      </label>
      <label>
        Program Site Address
        <input
          value={siteAddress}
          onChange={(e) => setSiteAddress(e.target.value)}
          placeholder="e.g., 1711 BRANHAM LN A9, SAN JOSE, CA 95118"
          required
        />
      </label>
      <button type="submit" className="btn btn-primary">Add Inspection Record</button>
    </form>
  );
}

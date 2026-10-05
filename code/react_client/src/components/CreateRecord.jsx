import { useState } from "react";
import { useDispatch } from "react-redux";
import { useNavigate } from "react-router-dom";
import { createInspection } from "../store/inspectionsSlice.js";
import InspectionFields, { toPayload } from "./InspectionFields.jsx";

const EMPTY = { inspection_code: "", facility_name: "", site_address: "", score: "100", inspector_id: "" };

export default function CreateRecord() {
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const [values, setValues] = useState(EMPTY);
  const [error, setError] = useState("");

  const handleSubmit = async (event) => {
    event.preventDefault();
    try {
      // The id is assigned by MySQL AUTO_INCREMENT; the fulfilled action adds
      // the returned record to the top of state.inspections.items.
      await dispatch(createInspection(toPayload(values))).unwrap();
      navigate("/");
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <form className="card form" onSubmit={handleSubmit}>
      <h2>Add Inspection Record</h2>
      {error && <div className="alert">{error}</div>}
      <InspectionFields values={values} onChange={(k, v) => setValues({ ...values, [k]: v })} autoFocus />
      <button type="submit" className="btn btn-primary">Add Inspection Record</button>
    </form>
  );
}

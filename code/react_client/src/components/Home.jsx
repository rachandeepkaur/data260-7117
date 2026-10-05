import { useDispatch, useSelector } from "react-redux";
import { Link } from "react-router-dom";
import { deleteInspection, setPage } from "../store/inspectionsSlice.js";

// Reads the record list straight from Redux; create/update/delete thunks
// change state.inspections.items, so this table re-renders on its own.
export default function Home() {
  const dispatch = useDispatch();
  const { items, total, page, pageSize, status, error } = useSelector((state) => state.inspections);
  const inspectors = useSelector((state) => state.inspectors.items);
  const inspectorName = (id) => inspectors.find((i) => i.id === id)?.full_name ?? `#${id}`;
  const lastPage = Math.max(0, Math.ceil(total / pageSize) - 1);

  return (
    <div className="card">
      <div className="card-header">
        <h2>Inspection Records</h2>
        <span className="muted">
          {status === "loading" ? "Loading…" : `${total.toLocaleString()} records in MySQL`}
        </span>
      </div>
      {error && <div className="alert">{error.message}</div>}
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Code</th>
            <th>Facility Name / ID</th>
            <th>Program Site Address</th>
            <th>Score</th>
            <th>Inspector</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {items.map((record) => (
            <tr key={record.id}>
              <td>{record.id}</td>
              <td className="nowrap">{record.inspection_code}</td>
              <td>{record.facility_name}</td>
              <td>{record.site_address}</td>
              <td className={record.score < 70 ? "fail" : undefined}>{record.score}</td>
              <td>{inspectorName(record.inspector_id)}</td>
              <td className="actions">
                <Link to={`/update?id=${record.id}`} className="btn">Edit</Link>
                <button className="btn btn-danger" onClick={() => dispatch(deleteInspection(record.id))}>
                  Delete
                </button>
              </td>
            </tr>
          ))}
          {items.length === 0 && status !== "loading" && (
            <tr>
              <td colSpan={7} className="muted">No inspection records yet.</td>
            </tr>
          )}
        </tbody>
      </table>
      <div className="pager">
        <button className="btn" disabled={page === 0} onClick={() => dispatch(setPage(page - 1))}>Previous</button>
        <span>Page {page + 1} of {lastPage + 1}</span>
        <button className="btn" disabled={page >= lastPage} onClick={() => dispatch(setPage(page + 1))}>Next</button>
      </div>
    </div>
  );
}

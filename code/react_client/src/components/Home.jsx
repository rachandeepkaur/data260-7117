import { Link } from "react-router-dom";

export default function Home({ records, total, page, pageSize, onPageChange }) {
  const lastPage = Math.max(0, Math.ceil(total / pageSize) - 1);

  return (
    <div className="card">
      <div className="card-header">
        <h2>Inspection Records</h2>
        <span className="muted">{total.toLocaleString()} records in MySQL</span>
      </div>
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Facility Name / ID</th>
            <th>Program Site Address</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {records.map((record) => (
            <tr key={record.id}>
              <td>{record.id}</td>
              <td>{record.facility_name}</td>
              <td>{record.site_address}</td>
              <td className="actions">
                <Link to={`/update?id=${record.id}`} className="btn">Edit</Link>
                <Link to={`/delete?id=${record.id}`} className="btn btn-danger">Delete</Link>
              </td>
            </tr>
          ))}
          {records.length === 0 && (
            <tr>
              <td colSpan={4} className="muted">No inspection records yet.</td>
            </tr>
          )}
        </tbody>
      </table>
      <div className="pager">
        <button className="btn" disabled={page === 0} onClick={() => onPageChange(page - 1)}>Previous</button>
        <span>Page {page + 1} of {lastPage + 1}</span>
        <button className="btn" disabled={page >= lastPage} onClick={() => onPageChange(page + 1)}>Next</button>
      </div>
    </div>
  );
}

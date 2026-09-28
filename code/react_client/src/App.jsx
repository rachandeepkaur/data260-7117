import { useCallback, useEffect, useState } from "react";
import { Link, Route, Routes, useNavigate } from "react-router-dom";
import { api, ApiError } from "./api.js";
import Home from "./components/Home.jsx";
import Login from "./components/Login.jsx";
import CreateRecord from "./components/CreateRecord.jsx";
import UpdateRecord from "./components/UpdateRecord.jsx";
import DeleteRecord from "./components/DeleteRecord.jsx";
import LoginRequired from "./components/LoginRequired.jsx";

const PAGE_SIZE = 25;

// App owns the auth state and the record list, and passes the CRUD
// operations down to the route components as props.
export default function App() {
  const navigate = useNavigate();
  const [user, setUser] = useState(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [records, setRecords] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [error, setError] = useState("");

  // On load, ask the backend whether the session cookie is still valid.
  useEffect(() => {
    api
      .me()
      .then(({ data }) => setUser(data))
      .catch(() => setUser(null))
      .finally(() => setAuthChecked(true));
  }, []);

  const handleApiError = useCallback((err) => {
    if (err instanceof ApiError && err.status === 401) {
      setUser(null); // session expired or revoked server-side
      navigate("/login");
    }
    setError(err.message);
  }, [navigate]);

  const loadRecords = useCallback(async () => {
    try {
      const { data, headers } = await api.listRecords(PAGE_SIZE, page * PAGE_SIZE);
      setRecords(data);
      setTotal(Number(headers.get("X-Total-Count") ?? data.length));
      setError("");
    } catch (err) {
      handleApiError(err);
    }
  }, [page, handleApiError]);

  useEffect(() => {
    if (user) loadRecords();
    else setRecords([]);
  }, [user, loadRecords]);

  const login = async (email, password) => {
    const { data } = await api.login(email, password);
    setUser(data);
    setPage(0);
    navigate("/");
  };

  const logout = async () => {
    await api.logout().catch(() => {});
    setUser(null);
    navigate("/login");
  };

  const addRecord = async (record) => {
    await api.createRecord(record);
    setPage(0); // newest first, so the new record is on page 1
    await loadRecords();
  };

  const updateRecord = async (id, record) => {
    await api.updateRecord(id, record);
    await loadRecords();
  };

  const deleteRecord = async (id) => {
    await api.deleteRecord(id);
    await loadRecords();
  };

  const fetchRecord = useCallback(async (id) => (await api.getRecord(id)).data, []);

  if (!authChecked) return <p className="container">Loading…</p>;

  const guard = (element) => (user ? element : <LoginRequired />);

  return (
    <>
      <nav className="navbar">
        <Link to="/" className="brand">Restaurant Inspections</Link>
        <div className="nav-links">
          <Link to="/">Home</Link>
          {user ? (
            <>
              <Link to="/create" className="btn btn-primary">Add Inspection Record</Link>
              <span className="muted">Signed in as {user.name}</span>
              <button className="btn" onClick={logout}>Logout</button>
            </>
          ) : (
            <>
              <button className="btn btn-primary" disabled title="Login required">Add Inspection Record</button>
              <Link to="/login" className="btn">Login</Link>
            </>
          )}
        </div>
      </nav>
      <main className="container">
        {error && user && <div className="alert">{error}</div>}
        <Routes>
          <Route
            path="/"
            element={guard(
              <Home records={records} total={total} page={page} pageSize={PAGE_SIZE} onPageChange={setPage} />
            )}
          />
          <Route path="/login" element={<Login onLogin={login} user={user} />} />
          <Route path="/create" element={guard(<CreateRecord onAddRecord={addRecord} />)} />
          <Route
            path="/update"
            element={guard(<UpdateRecord onUpdateRecord={updateRecord} fetchRecord={fetchRecord} />)}
          />
          <Route
            path="/delete"
            element={guard(<DeleteRecord onDeleteRecord={deleteRecord} fetchRecord={fetchRecord} />)}
          />
        </Routes>
      </main>
    </>
  );
}

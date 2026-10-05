import { useEffect, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { Link, Route, Routes, useNavigate } from "react-router-dom";
import { api } from "./api.js";
import Home from "./components/Home.jsx";
import Login from "./components/Login.jsx";
import CreateRecord from "./components/CreateRecord.jsx";
import UpdateRecord from "./components/UpdateRecord.jsx";
import LoginRequired from "./components/LoginRequired.jsx";
import { fetchInspections, reset } from "./store/inspectionsSlice.js";
import { fetchInspectors } from "./store/inspectorsSlice.js";

// App owns only the auth state. Inspection records live in the Redux store
// (store/inspectionsSlice.js); the screens read them with useSelector and
// change them by dispatching thunks.
export default function App() {
  const navigate = useNavigate();
  const dispatch = useDispatch();
  const [user, setUser] = useState(null);
  const [authChecked, setAuthChecked] = useState(false);
  const { page, pageSize, error } = useSelector((state) => state.inspections);

  // On load, ask the backend whether the session cookie is still valid.
  useEffect(() => {
    api
      .me()
      .then(({ data }) => setUser(data))
      .catch(() => setUser(null))
      .finally(() => setAuthChecked(true));
  }, []);

  useEffect(() => {
    if (user) {
      dispatch(fetchInspections({ page, pageSize }));
      dispatch(fetchInspectors());
    } else {
      dispatch(reset());
    }
  }, [user, page, pageSize, dispatch]);

  // Session expired or revoked server-side.
  useEffect(() => {
    if (error?.status === 401) {
      setUser(null);
      navigate("/login");
    }
  }, [error, navigate]);

  const login = async (email, password) => {
    const { data } = await api.login(email, password);
    setUser(data);
    navigate("/");
  };

  const logout = async () => {
    await api.logout().catch(() => {});
    setUser(null);
    navigate("/login");
  };

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
              <Link to="/update" className="btn">Update by ID</Link>
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
        <Routes>
          <Route path="/" element={guard(<Home />)} />
          <Route path="/login" element={<Login onLogin={login} user={user} />} />
          <Route path="/create" element={guard(<CreateRecord />)} />
          <Route path="/update" element={guard(<UpdateRecord />)} />
        </Routes>
      </main>
    </>
  );
}

import { useState } from "react";
import { Navigate } from "react-router-dom";

export default function Login({ onLogin, user }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  if (user) return <Navigate to="/" replace />;

  const handleSubmit = async (event) => {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      await onLogin(username, password);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form className="card form" onSubmit={handleSubmit}>
      <h2>Inspector Login</h2>
      {error && <div className="alert">{error}</div>}
      <label>
        Username
        <input type="text" value={username} onChange={(e) => setUsername(e.target.value)} required autoFocus />
      </label>
      <label>
        Password
        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
      </label>
      <button type="submit" className="btn btn-primary" disabled={submitting}>
        {submitting ? "Logging in…" : "Login"}
      </button>
    </form>
  );
}

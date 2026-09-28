import { Link } from "react-router-dom";

export default function LoginRequired() {
  return (
    <div className="card">
      <h2>Login required</h2>
      <p>You must be logged in to view and manage inspection records.</p>
      <Link to="/login" className="btn btn-primary">Go to Login</Link>
    </div>
  );
}

// Thin fetch wrapper for the FastAPI backend. `credentials: "include"` makes
// the browser send the HttpOnly session cookie; JS never reads the cookie.
export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

async function request(path, { method = "GET", body } = {}) {
  const response = await fetch(path, {
    method,
    credentials: "include",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    let detail = `${method} ${path} failed (${response.status})`;
    try {
      const data = await response.json();
      if (typeof data.detail === "string") detail = data.detail;
      else if (Array.isArray(data.detail)) detail = data.detail.map((d) => d.msg).join("; ");
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) return { data: null, headers: response.headers };
  return { data: await response.json(), headers: response.headers };
}

export const api = {
  me: () => request("/api/auth/me"),
  login: (email, password) => request("/api/auth/login", { method: "POST", body: { email, password } }),
  logout: () => request("/api/auth/logout", { method: "POST" }),
  listRecords: (limit, offset) => request(`/api/records?limit=${limit}&offset=${offset}`),
  getRecord: (id) => request(`/api/records/${id}`),
  createRecord: (record) => request("/api/records", { method: "POST", body: record }),
  updateRecord: (id, record) => request(`/api/records/${id}`, { method: "PUT", body: record }),
  deleteRecord: (id) => request(`/api/records/${id}`, { method: "DELETE" }),
};

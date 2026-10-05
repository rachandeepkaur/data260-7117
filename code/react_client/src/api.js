import axios from "axios";

// Axios instance for the FastAPI backend. Vite proxies /api to PORT_BASE
// (8817), and `withCredentials` makes the browser send the HttpOnly session
// cookie; JS never reads the cookie.
export const http = axios.create({ withCredentials: true });

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

// Turn FastAPI error bodies ({detail: "..."} or a 422 list) into one readable message.
http.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status ?? 0;
    const detail = error.response?.data?.detail;
    let message = error.message;
    if (typeof detail === "string") message = detail;
    else if (Array.isArray(detail)) message = detail.map((d) => `${d.loc?.slice(-1)[0]}: ${d.msg}`).join("; ");
    return Promise.reject(new ApiError(status, message));
  }
);

export const api = {
  me: () => http.get("/api/auth/me"),
  login: (email, password) => http.post("/api/auth/login", { email, password }),
  logout: () => http.post("/api/auth/logout"),
  getRecord: (id) => http.get(`/api/records/${id}`),
};

import axios from "axios";

// Axios instance for the FastAPI backend. Vite proxies /api and /auth to
// PORT_BASE (8817). HW7: the JWT from POST /auth/login is kept in
// sessionStorage (cleared when the tab closes) and sent as a bearer token.
const TOKEN_KEY = "s7117_access_token";
export const tokenStore = {
  get: () => sessionStorage.getItem(TOKEN_KEY),
  set: (token) => sessionStorage.setItem(TOKEN_KEY, token),
  clear: () => sessionStorage.removeItem(TOKEN_KEY),
};

export const http = axios.create();
http.interceptors.request.use((config) => {
  const token = tokenStore.get();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

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
  me: () => http.get("/auth/me"),
  login: async (username, password) => {
    const { data } = await http.post("/auth/login", { username, password });
    tokenStore.set(data.access_token);
    return http.get("/auth/me");
  },
  // JWTs are stateless: logging out just discards the token client-side.
  logout: async () => tokenStore.clear(),
  getRecord: (id) => http.get(`/api/records/${id}`),
};

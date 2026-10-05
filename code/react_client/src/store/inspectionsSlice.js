import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import { http } from "../api.js";

// Redux state for the primary domain entity (inspection records, /api/records).
// Each thunk calls one FastAPI endpoint; errors come back through
// rejectWithValue as {status, message} so the UI can show them (and App can
// log out on 401).

const toError = (err) => ({ status: err.status ?? 0, message: err.message });

export const fetchInspections = createAsyncThunk(
  "inspections/fetch",
  async ({ page = 0, pageSize = 25 } = {}, { rejectWithValue }) => {
    try {
      const res = await http.get("/api/records", { params: { limit: pageSize, offset: page * pageSize } });
      return { items: res.data, total: Number(res.headers["x-total-count"] ?? res.data.length), page };
    } catch (err) {
      return rejectWithValue(toError(err));
    }
  }
);

export const createInspection = createAsyncThunk("inspections/create", async (record, { rejectWithValue }) => {
  try {
    return (await http.post("/api/records", record)).data;
  } catch (err) {
    return rejectWithValue(toError(err));
  }
});

export const updateInspection = createAsyncThunk(
  "inspections/update",
  async ({ id, changes }, { rejectWithValue }) => {
    try {
      return (await http.put(`/api/records/${id}`, changes)).data;
    } catch (err) {
      return rejectWithValue(toError(err));
    }
  }
);

export const deleteInspection = createAsyncThunk("inspections/delete", async (id, { rejectWithValue }) => {
  try {
    await http.delete(`/api/records/${id}`);
    return id;
  } catch (err) {
    return rejectWithValue(toError(err));
  }
});

const inspectionsSlice = createSlice({
  name: "inspections",
  initialState: { items: [], total: 0, page: 0, pageSize: 25, status: "idle", error: null },
  reducers: {
    setPage(state, action) {
      state.page = action.payload;
    },
    clearError(state) {
      state.error = null;
    },
    reset() {
      return inspectionsSlice.getInitialState();
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchInspections.pending, (state) => {
        state.status = "loading";
      })
      .addCase(fetchInspections.fulfilled, (state, { payload }) => {
        state.status = "succeeded";
        state.items = payload.items;
        state.total = payload.total;
        state.page = payload.page;
        state.error = null;
      })
      // Newest first: a created record goes to the top of the list.
      .addCase(createInspection.fulfilled, (state, { payload }) => {
        state.items.unshift(payload);
        if (state.items.length > state.pageSize) state.items.pop();
        state.total += 1;
        state.error = null;
      })
      .addCase(updateInspection.fulfilled, (state, { payload }) => {
        const i = state.items.findIndex((r) => r.id === payload.id);
        if (i !== -1) state.items[i] = payload;
        state.error = null;
      })
      .addCase(deleteInspection.fulfilled, (state, { payload: id }) => {
        state.items = state.items.filter((r) => r.id !== id);
        state.total -= 1;
        state.error = null;
      })
      .addMatcher(
        (action) => action.type.startsWith("inspections/") && action.type.endsWith("/rejected"),
        (state, action) => {
          state.status = "failed";
          state.error = action.payload ?? { status: 0, message: action.error.message };
        }
      );
  },
});

export const { setPage, clearError, reset } = inspectionsSlice.actions;
export default inspectionsSlice.reducer;

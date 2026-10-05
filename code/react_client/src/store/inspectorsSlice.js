import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import { http } from "../api.js";

// Inspectors (the related entity) - loaded once to fill the inspector dropdown
// on the create/update forms and to show names in the Home table.
export const fetchInspectors = createAsyncThunk("inspectors/fetch", async (_, { rejectWithValue }) => {
  try {
    return (await http.get("/api/inspectors", { params: { page: 1, page_size: 100 } })).data;
  } catch (err) {
    return rejectWithValue({ status: err.status ?? 0, message: err.message });
  }
});

const inspectorsSlice = createSlice({
  name: "inspectors",
  initialState: { items: [], status: "idle", error: null },
  reducers: {},
  extraReducers: (builder) => {
    builder
      .addCase(fetchInspectors.pending, (state) => {
        state.status = "loading";
      })
      .addCase(fetchInspectors.fulfilled, (state, { payload }) => {
        state.status = "succeeded";
        state.items = payload;
      })
      .addCase(fetchInspectors.rejected, (state, action) => {
        state.status = "failed";
        state.error = action.payload;
      });
  },
});

export default inspectorsSlice.reducer;

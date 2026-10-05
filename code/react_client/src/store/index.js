import { configureStore } from "@reduxjs/toolkit";
import inspectionsReducer from "./inspectionsSlice.js";
import inspectorsReducer from "./inspectorsSlice.js";

export const store = configureStore({
  reducer: {
    inspections: inspectionsReducer,
    inspectors: inspectorsReducer,
  },
});

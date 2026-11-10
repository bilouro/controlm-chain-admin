import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import { App } from "@/app/App";
import { applyTheme, storedTheme } from "@/features/theme/theme";
import { captureToken } from "@/lib/api/session";

captureToken();
applyTheme(storedTheme()); // before the first paint, so the page does not flash

const root = document.getElementById("root");
if (!root) {
  throw new Error("missing #root element");
}
createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

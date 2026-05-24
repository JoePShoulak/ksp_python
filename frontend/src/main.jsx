import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App.jsx";

createRoot(document.getElementById("root")).render(
  // Keep StrictMode disabled while p5 canvases render twice under development remounts.
  <App />,
);

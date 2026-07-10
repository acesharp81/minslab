import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "@tanstack/react-router";
import { getRouter } from "./router";
import "./styles.css";

const container = document.getElementById("root");

if (!container) {
  throw new Error("현장점검 플랫폼의 root 요소를 찾지 못했습니다.");
}

const router = getRouter();

createRoot(container).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
);

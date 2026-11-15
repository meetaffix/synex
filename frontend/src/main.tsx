import { lazy, StrictMode, Suspense } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
// Plus Jakarta Sans, bundled with the app: no request to a font CDN.
import "@fontsource/plus-jakarta-sans/latin-400.css";
import "@fontsource/plus-jakarta-sans/latin-500.css";
import "@fontsource/plus-jakarta-sans/latin-600.css";
import "@fontsource/plus-jakarta-sans/latin-700.css";
import "./index.css";
import { App } from "./app/App";
import { clerkEnabled } from "./lib/clerk";

// Clerk wraps the app only in Clerk mode, and is loaded on demand.
const ClerkRoot = lazy(() => import("./features/auth/ClerkRoot"));

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      {clerkEnabled ? (
        <Suspense fallback={null}>
          <ClerkRoot>
            <App />
          </ClerkRoot>
        </Suspense>
      ) : (
        <App />
      )}
    </BrowserRouter>
  </StrictMode>
);

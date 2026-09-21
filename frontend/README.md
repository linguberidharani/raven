# RAVEN frontend

React 18, Vite 6, React Router 7 (declarative mode: BrowserRouter, Routes, NavLink), plain CSS with design tokens (`src/styles/tokens.css`). JavaScript, no CSS framework.

Run everything from this folder (`D:\Projects\RAVEN\frontend`) in PowerShell:

    npm ci                 # install exactly the versions of package-lock.json (first time, or after a change)
    npm run dev            # http://localhost:5173 ; /api is forwarded to the backend on 127.0.0.1:8000
    npm run build          # production build into dist\
    npm run lint           # ESLint
    npm test               # Vitest (API client, hooks, helpers, pages)

The backend must be running (`scripts\run_backend.ps1`). The browser only talks to one origin, so the session cookie
(HttpOnly, SameSite=Lax) works without CORS.

## Data source

`VITE_DATA_SOURCE=api` (default) uses the real backend. `VITE_DATA_SOURCE=demo` (for design work and screenshots) serves
clearly invented demo data and shows the permanent banner "Demo data, not real telemetry." Copy `.env.example` to
`.env.local` to change it. The frontend shows what the API returns; it never computes findings.

## Layout

    src\api\        one fetch wrapper (client.js), ApiError, one small module per resource
    src\auth\       AuthProvider: the session lives in an HttpOnly cookie, the code only knows who is signed in
    src\hooks\      useApi (data, loading, error, reload), useReducedMotion
    src\components\ shared building blocks (badges, cards, states, form fields, shell, sidebar)
    src\pages\      one file per screen; pages of an investigation are registered in InvestigationStep.jsx
    src\styles\     tokens, base, components, layout, auth, intro
    src\demo\       demo data, used only when VITE_DATA_SOURCE=demo
    src\utils\      format, mapping, navigation, validation, storage (with unit tests)

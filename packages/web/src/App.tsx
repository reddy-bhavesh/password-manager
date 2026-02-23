import { Outlet } from "@tanstack/react-router";

export function App() {
  return (
    <main className="app-page">
      <div className="app-backdrop" aria-hidden="true" />
      <div className="app-shell">
        <Outlet />
      </div>
    </main>
  );
}

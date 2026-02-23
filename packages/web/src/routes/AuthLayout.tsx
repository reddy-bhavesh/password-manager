import { Link, Outlet, useLocation } from "@tanstack/react-router";

const routeMeta: Record<string, { title: string; subtitle: string }> = {
  "/login": {
    title: "Sign in to VaultGuard",
    subtitle: "Zero-knowledge access for your organization vault."
  },
  "/mfa": {
    title: "Verify your identity",
    subtitle: "Enter the code from your authenticator app to continue."
  }
};

export function AuthLayout() {
  const location = useLocation();
  const meta = routeMeta[location.pathname] ?? routeMeta["/login"];

  return (
    <section className="auth-shell" aria-labelledby="auth-title">
      <aside className="auth-aside">
        <p className="auth-kicker">VaultGuard</p>
        <h1 id="auth-title">{meta.title}</h1>
        <p className="auth-subtitle">{meta.subtitle}</p>
        <div className="auth-aside-panel">
          <p className="auth-aside-label">Security defaults</p>
          <ul className="auth-feature-list">
            <li>RS256 short-lived access tokens</li>
            <li>Argon2id credential verification</li>
            <li>MFA challenge completion flow</li>
          </ul>
        </div>
      </aside>

      <div className="auth-card">
        <nav className="auth-tabs" aria-label="Authentication">
          <Link to="/login" className="auth-tab" activeProps={{ "data-active": "true" }}>
            Login
          </Link>
          <Link to="/mfa" className="auth-tab" activeProps={{ "data-active": "true" }}>
            MFA
          </Link>
        </nav>
        <Outlet />
      </div>
    </section>
  );
}

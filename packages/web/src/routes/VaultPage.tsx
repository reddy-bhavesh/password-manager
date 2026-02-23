import { Link } from "@tanstack/react-router";
import { useAuthStore } from "../features/auth/store";

export function VaultPage() {
  const user = useAuthStore((state) => state.user);
  const accessToken = useAuthStore((state) => state.accessToken);
  const clearSession = useAuthStore((state) => state.clearSession);

  return (
    <section className="vault-shell" aria-labelledby="vault-title">
      <header className="vault-header">
        <div>
          <p className="auth-kicker">Vault</p>
          <h1 id="vault-title">Authenticated session established</h1>
          <p className="vault-subtitle">
            FE-002 redirect target. Access token is stored in Zustand and the refresh token is expected in an
            HttpOnly cookie.
          </p>
        </div>
        <button type="button" className="btn btn-secondary" onClick={() => clearSession()}>
          Clear Session
        </button>
      </header>

      <div className="vault-grid">
        <article className="vault-panel">
          <h2>User</h2>
          {user ? (
            <dl className="kv-list">
              <div>
                <dt>Name</dt>
                <dd>{user.name}</dd>
              </div>
              <div>
                <dt>Email</dt>
                <dd>{user.email}</dd>
              </div>
              <div>
                <dt>Role</dt>
                <dd>{user.role}</dd>
              </div>
              <div>
                <dt>MFA Enabled</dt>
                <dd>{user.mfa_enabled ? "Yes" : "No"}</dd>
              </div>
            </dl>
          ) : (
            <p>No authenticated user in store. <Link to="/login">Go to login</Link>.</p>
          )}
        </article>

        <article className="vault-panel">
          <h2>Access Token (preview)</h2>
          <p className="vault-subtitle">Stored in Zustand state for authenticated API calls.</p>
          <code className="token-preview">{accessToken ? `${accessToken.slice(0, 32)}...` : "Not set"}</code>
        </article>
      </div>
    </section>
  );
}

export function App() {
  return (
    <main className="ds-page">
      <div className="ds-shell">
        <header className="ds-hero">
          <p className="eyebrow">VaultGuard Design System</p>
          <h1>Dark-first tokens and global styles</h1>
          <p className="lede">
            Baseline visual tokens for the web app. The theme defaults to dark mode and adapts to light mode based on
            the user&apos;s system preference.
          </p>
        </header>

        <section className="ds-panel" aria-labelledby="color-tokens">
          <div className="section-head">
            <h2 id="color-tokens">Core Color Tokens</h2>
            <p>Required brand and status colors are exposed as CSS custom properties.</p>
          </div>

          <div className="swatch-grid">
            <article className="swatch-card">
              <div className="swatch-chip token-primary" aria-hidden="true" />
              <p className="swatch-label">Primary</p>
              <p className="swatch-meta">
                <code>--color-primary</code> <span>#1A1F36</span>
              </p>
            </article>
            <article className="swatch-card">
              <div className="swatch-chip token-accent" aria-hidden="true" />
              <p className="swatch-label">Accent</p>
              <p className="swatch-meta">
                <code>--color-accent</code> <span>#6C63FF</span>
              </p>
            </article>
            <article className="swatch-card">
              <div className="swatch-chip token-success" aria-hidden="true" />
              <p className="swatch-label">Success</p>
              <p className="swatch-meta">
                <code>--color-success</code> <span>#0FB76B</span>
              </p>
            </article>
            <article className="swatch-card">
              <div className="swatch-chip token-danger" aria-hidden="true" />
              <p className="swatch-label">Danger</p>
              <p className="swatch-meta">
                <code>--color-danger</code> <span>#FF4D4D</span>
              </p>
            </article>
          </div>
        </section>

        <section className="ds-panel" aria-labelledby="typography">
          <div className="section-head">
            <h2 id="typography">Typography</h2>
            <p>Inter is used for UI text and JetBrains Mono is reserved for secret values and code-like content.</p>
          </div>

          <div className="type-grid">
            <div className="type-card">
              <p className="type-label">Inter / UI text</p>
              <p className="type-sample">
                Team credential access, audit reporting, and vault workflows are readable at a glance.
              </p>
            </div>
            <div className="type-card">
              <p className="type-label">JetBrains Mono / Secret values</p>
              <p className="type-sample secret-sample">DB_PASSWORD=Vg!9yQ2k#lT8mA4x</p>
            </div>
          </div>
        </section>

        <section className="ds-panel" aria-labelledby="surfaces">
          <div className="section-head">
            <h2 id="surfaces">Surface Preview</h2>
            <p>Reusable button, input, and status badges using the token system.</p>
          </div>

          <div className="preview-grid">
            <label className="field">
              <span>Work Email</span>
              <input type="email" placeholder="alex@vaultguard.local" />
            </label>
            <label className="field">
              <span>Secret Preview</span>
              <input className="mono-input" type="text" value="••••••••••••••••" readOnly />
            </label>
            <div className="button-row">
              <button type="button" className="btn btn-primary">
                Unlock Vault
              </button>
              <button type="button" className="btn btn-secondary">
                Cancel
              </button>
            </div>
            <div className="badge-row" aria-label="Status badges">
              <span className="badge badge-success">Healthy</span>
              <span className="badge badge-danger">Action Required</span>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}

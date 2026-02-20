import type { ReactElement } from "react";

export function App(): ReactElement {
  return (
    <main className="popup-shell" aria-label="VaultGuard popup">
      <header>
        <p className="eyebrow">VaultGuard</p>
        <h1>Extension Ready</h1>
      </header>
      <p className="body-copy">Popup placeholder loaded successfully.</p>
      <button type="button" className="action-button">
        Open Vault
      </button>
    </main>
  );
}

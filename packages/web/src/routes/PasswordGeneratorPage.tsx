import { Link } from "@tanstack/react-router";
import { PasswordGenerator } from "../features/password-generator/PasswordGenerator";

export function PasswordGeneratorPage() {
  return (
    <section className="generator-page" aria-labelledby="generator-page-title">
      <header className="generator-page-header">
        <div>
          <p className="auth-kicker">Tools</p>
          <h1 id="generator-page-title">Password Generator</h1>
          <p className="vault-subtitle">
            Generate strong passwords or EFF-word-list passphrases, copy them with auto-clear, and paste into vault
            item forms.
          </p>
        </div>
        <div className="generator-page-actions">
          <Link to="/vault" className="btn btn-secondary">
            Back to Vault
          </Link>
        </div>
      </header>

      <PasswordGenerator
        title="Standalone Generator"
        description="Use this page for quick generation before creating or updating vault items."
      />
    </section>
  );
}


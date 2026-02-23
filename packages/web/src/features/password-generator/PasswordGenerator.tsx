import { useEffect, useMemo, useRef, useState } from "react";
import {
  DEFAULT_PASSWORD_OPTIONS,
  DEFAULT_PASSPHRASE_OPTIONS,
  EFF_SHORT_WORD_LIST,
  PASSPHRASE_WORD_COUNT_MAX,
  PASSPHRASE_WORD_COUNT_MIN,
  PASSWORD_LENGTH_MAX,
  PASSWORD_LENGTH_MIN,
  createBrowserRandomSource,
  estimatePassphraseStrength,
  estimatePasswordStrength,
  generatePassphrase,
  generatePassword,
  type PassphraseGeneratorOptions,
  type PasswordGeneratorOptions,
  type PasswordMode
} from "./generator";

type PasswordGeneratorProps = {
  className?: string;
  title?: string;
  description?: string;
  compact?: boolean;
  onUseValue?: (value: string) => void;
  useLabel?: string;
};

function mergeClassNames(...parts: Array<string | undefined | false>): string {
  return parts.filter(Boolean).join(" ");
}

export function PasswordGenerator({
  className,
  title = "Password Generator",
  description,
  compact = false,
  onUseValue,
  useLabel = "Use in Form"
}: PasswordGeneratorProps) {
  const randomSource = useMemo(() => createBrowserRandomSource(), []);
  const [mode, setMode] = useState<PasswordMode>("password");
  const [passwordOptions, setPasswordOptions] = useState<PasswordGeneratorOptions>(DEFAULT_PASSWORD_OPTIONS);
  const [passphraseOptions, setPassphraseOptions] = useState<PassphraseGeneratorOptions>(DEFAULT_PASSPHRASE_OPTIONS);
  const [generatedValue, setGeneratedValue] = useState("");
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [generationError, setGenerationError] = useState<string | null>(null);
  const statusTimerRef = useRef<number | null>(null);
  const clipboardClearTimerRef = useRef<number | null>(null);

  const strength = mode === "password" ? estimatePasswordStrength(passwordOptions) : estimatePassphraseStrength(passphraseOptions);

  useEffect(() => {
    return () => {
      if (statusTimerRef.current !== null) {
        window.clearTimeout(statusTimerRef.current);
      }
      if (clipboardClearTimerRef.current !== null) {
        window.clearTimeout(clipboardClearTimerRef.current);
      }
    };
  }, []);

  useEffect(() => {
    regenerate(mode);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, passwordOptions, passphraseOptions]);

  function setTransientStatus(message: string) {
    setStatusMessage(message);

    if (statusTimerRef.current !== null) {
      window.clearTimeout(statusTimerRef.current);
    }

    statusTimerRef.current = window.setTimeout(() => {
      setStatusMessage(null);
      statusTimerRef.current = null;
    }, 2600);
  }

  function regenerate(targetMode = mode) {
    try {
      const nextValue =
        targetMode === "password"
          ? generatePassword(passwordOptions, randomSource)
          : generatePassphrase(passphraseOptions, randomSource, EFF_SHORT_WORD_LIST);

      setGeneratedValue(nextValue);
      setGenerationError(null);
    } catch (error) {
      setGeneratedValue("");
      setGenerationError(error instanceof Error ? error.message : "Could not generate a value.");
    }
  }

  async function copyGeneratedValue() {
    if (!generatedValue) {
      return;
    }

    if (!navigator?.clipboard?.writeText) {
      setTransientStatus("Clipboard is not available in this browser.");
      return;
    }

    try {
      await navigator.clipboard.writeText(generatedValue);
      setTransientStatus("Copied. Clipboard clears in 30s.");

      if (clipboardClearTimerRef.current !== null) {
        window.clearTimeout(clipboardClearTimerRef.current);
      }

      clipboardClearTimerRef.current = window.setTimeout(async () => {
        try {
          await navigator.clipboard.writeText("");
        } catch {
          // Ignore browser clipboard permission failures.
        } finally {
          clipboardClearTimerRef.current = null;
        }
      }, 30_000);
    } catch {
      setTransientStatus("Copy failed.");
    }
  }

  return (
    <section className={mergeClassNames("generator-card", compact && "generator-card--compact", className)} aria-label={title}>
      <div className="generator-header">
        <div>
          <p className="auth-kicker">Generator</p>
          <h3>{title}</h3>
          {description ? <p className="generator-subtitle">{description}</p> : null}
        </div>
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => regenerate()} disabled={Boolean(generationError)}>
          Regenerate
        </button>
      </div>

      <div className="generator-mode-switch" role="tablist" aria-label="Generator mode">
        <button
          type="button"
          className="generator-mode-button"
          role="tab"
          aria-selected={mode === "password"}
          data-active={mode === "password"}
          onClick={() => setMode("password")}
        >
          Password
        </button>
        <button
          type="button"
          className="generator-mode-button"
          role="tab"
          aria-selected={mode === "passphrase"}
          data-active={mode === "passphrase"}
          onClick={() => setMode("passphrase")}
        >
          Passphrase
        </button>
      </div>

      <div className="generator-output">
        <div className="generator-output-row">
          <code className="generator-preview">{generatedValue || "No value generated yet."}</code>
          <div className="generator-output-actions">
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => void copyGeneratedValue()} disabled={!generatedValue}>
              Copy
            </button>
            {onUseValue ? (
              <button
                type="button"
                className="btn btn-primary btn-sm"
                onClick={() => onUseValue(generatedValue)}
                disabled={!generatedValue}
              >
                {useLabel}
              </button>
            ) : null}
          </div>
        </div>
        <div className="generator-strength" aria-live="polite">
          <div className="generator-strength-bar" aria-hidden="true">
            <span style={{ width: `${((strength.score + 1) / 5) * 100}%` }} data-score={strength.score} />
          </div>
          <p className="generator-strength-label">
            Strength: <strong>{strength.label}</strong> <span>({Math.round(strength.entropyBits)} bits)</span>
          </p>
        </div>
        {statusMessage ? (
          <p className="generator-status" role="status">
            {statusMessage}
          </p>
        ) : null}
        {generationError ? <p className="inline-error">{generationError}</p> : null}
      </div>

      {mode === "password" ? (
        <div className="generator-controls">
          <label className="form-field">
            <span>Password Length: {passwordOptions.length}</span>
            <input
              type="range"
              min={PASSWORD_LENGTH_MIN}
              max={PASSWORD_LENGTH_MAX}
              step={1}
              value={passwordOptions.length}
              onChange={(event) =>
                setPasswordOptions((current) => ({
                  ...current,
                  length: Number(event.target.value)
                }))
              }
            />
          </label>

          <div className="generator-toggle-grid">
            <label className="generator-toggle">
              <input
                type="checkbox"
                checked={passwordOptions.uppercase}
                onChange={(event) =>
                  setPasswordOptions((current) => ({
                    ...current,
                    uppercase: event.target.checked
                  }))
                }
              />
              <span>Uppercase</span>
            </label>
            <label className="generator-toggle">
              <input
                type="checkbox"
                checked={passwordOptions.lowercase}
                onChange={(event) =>
                  setPasswordOptions((current) => ({
                    ...current,
                    lowercase: event.target.checked
                  }))
                }
              />
              <span>Lowercase</span>
            </label>
            <label className="generator-toggle">
              <input
                type="checkbox"
                checked={passwordOptions.numbers}
                onChange={(event) =>
                  setPasswordOptions((current) => ({
                    ...current,
                    numbers: event.target.checked
                  }))
                }
              />
              <span>Numbers</span>
            </label>
            <label className="generator-toggle">
              <input
                type="checkbox"
                checked={passwordOptions.symbols}
                onChange={(event) =>
                  setPasswordOptions((current) => ({
                    ...current,
                    symbols: event.target.checked
                  }))
                }
              />
              <span>Symbols</span>
            </label>
            <label className="generator-toggle generator-toggle--wide">
              <input
                type="checkbox"
                checked={passwordOptions.excludeAmbiguous}
                onChange={(event) =>
                  setPasswordOptions((current) => ({
                    ...current,
                    excludeAmbiguous: event.target.checked
                  }))
                }
              />
              <span>Exclude ambiguous characters (I, l, 1, O, 0, |)</span>
            </label>
          </div>
        </div>
      ) : (
        <div className="generator-controls">
          <label className="form-field">
            <span>Word Count</span>
            <select
              className="vault-select"
              value={passphraseOptions.wordCount}
              onChange={(event) =>
                setPassphraseOptions((current) => ({
                  ...current,
                  wordCount: Number(event.target.value)
                }))
              }
            >
              {Array.from(
                { length: PASSPHRASE_WORD_COUNT_MAX - PASSPHRASE_WORD_COUNT_MIN + 1 },
                (_, index) => PASSPHRASE_WORD_COUNT_MIN + index
              ).map((count) => (
                <option key={count} value={count}>
                  {count} words
                </option>
              ))}
            </select>
          </label>

          <label className="form-field">
            <span>Separator</span>
            <input
              type="text"
              value={passphraseOptions.separator}
              maxLength={3}
              onChange={(event) =>
                setPassphraseOptions((current) => ({
                  ...current,
                  separator: event.target.value
                }))
              }
              placeholder="-"
            />
          </label>

          <p className="generator-note">
            Using bundled EFF short word list ({EFF_SHORT_WORD_LIST.length} words).
          </p>
        </div>
      )}
    </section>
  );
}


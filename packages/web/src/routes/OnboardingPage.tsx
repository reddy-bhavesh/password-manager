import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { startTransition, useEffect, useMemo, useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { ApiError } from "../api/http";
import {
  confirmTotpMfaRequest,
  enrollTotpMfaRequest,
  loginRequest,
  registerRequest
} from "../features/auth/api";
import { useAuthStore } from "../features/auth/store";
import {
  TOTAL_ONBOARDING_STEPS,
  buildQrImageUrl,
  canAdvanceToStep,
  clearOnboardingState,
  deriveRegistrationCryptoArtifacts,
  getStepTitle,
  loadOnboardingState,
  mfaConfirmSchema,
  parseImportFile,
  persistOnboardingState,
  registrationSchema,
  scorePassword,
  type OnboardingState,
  type OnboardingStep,
  type Step1FormState
} from "../features/onboarding/utils";

type Step1Errors = Partial<Record<keyof Step1FormState, string>>;

export function OnboardingPage() {
  const navigate = useNavigate();
  const prefersReducedMotion = useReducedMotion();
  const setAuthenticatedSession = useAuthStore((state) => state.setAuthenticatedSession);

  const initialState = useMemo(() => loadOnboardingState(), []);
  const [wizard, setWizard] = useState<OnboardingState>(initialState);
  const [step1Form, setStep1Form] = useState<Step1FormState>({
    ...initialState.step1Draft,
    masterPassword: "",
    confirmPassword: ""
  });
  const [step1Errors, setStep1Errors] = useState<Step1Errors>({});
  const [step1SubmitError, setStep1SubmitError] = useState<string | null>(null);
  const [isRegistering, setIsRegistering] = useState(false);

  const [step2Code, setStep2Code] = useState("");
  const [step2CodeError, setStep2CodeError] = useState<string | null>(null);
  const [step2SubmitError, setStep2SubmitError] = useState<string | null>(null);
  const [isEnrollingMfa, setIsEnrollingMfa] = useState(false);
  const [isConfirmingMfa, setIsConfirmingMfa] = useState(false);
  const [mfaEnrollmentError, setMfaEnrollmentError] = useState<string | null>(null);

  const [importError, setImportError] = useState<string | null>(null);
  const [isParsingImport, setIsParsingImport] = useState(false);
  const [isDragActive, setIsDragActive] = useState(false);

  const [transitionDirection, setTransitionDirection] = useState<1 | -1>(1);

  const passwordStrength = useMemo(() => scorePassword(step1Form.masterPassword), [step1Form.masterPassword]);
  const currentStep = wizard.step;

  useEffect(() => {
    persistOnboardingState({
      ...wizard,
      step1Draft: {
        email: step1Form.email,
        name: step1Form.name,
        orgId: step1Form.orgId,
        invitationToken: step1Form.invitationToken
      }
    });
  }, [wizard, step1Form.email, step1Form.invitationToken, step1Form.name, step1Form.orgId]);

  useEffect(() => {
    if (!wizard.authSession) return;
    setAuthenticatedSession({
      accessToken: wizard.authSession.accessToken,
      user: wizard.authSession.user
    });
  }, [setAuthenticatedSession, wizard.authSession]);

  useEffect(() => {
    if (wizard.step !== 2 || wizard.mfaEnrollment || wizard.mfaConfirmed || isEnrollingMfa) return;
    const accessToken = wizard.authSession?.accessToken;
    if (!accessToken) {
      setMfaEnrollmentError("Session expired. Return to Step 1 and register again.");
      return;
    }

    let active = true;
    setIsEnrollingMfa(true);
    setMfaEnrollmentError(null);
    void enrollTotpMfaRequest(accessToken)
      .then((response) => {
        if (!active) return;
        setWizard((current) => ({
          ...current,
          mfaEnrollment: { otpauthUri: response.otpauth_uri, backupCodes: response.backup_codes }
        }));
      })
      .catch((error: unknown) => {
        if (!active) return;
        if (error instanceof ApiError && error.status === 401) {
          setMfaEnrollmentError("Your session expired. Return to Step 1 and sign in again.");
          return;
        }
        setMfaEnrollmentError("Unable to start MFA enrollment right now.");
      })
      .finally(() => {
        if (active) setIsEnrollingMfa(false);
      });

    return () => {
      active = false;
    };
  }, [isEnrollingMfa, wizard.authSession, wizard.mfaConfirmed, wizard.mfaEnrollment, wizard.step]);

  function moveToStep(nextStep: OnboardingStep) {
    setWizard((current) => {
      if (!canAdvanceToStep(current, nextStep)) return current;
      setTransitionDirection(nextStep > current.step ? 1 : -1);
      return { ...current, step: nextStep };
    });
  }

  async function submitStep1(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isRegistering) return;

    setStep1SubmitError(null);
    setStep1Errors({});

    const parsed = registrationSchema.safeParse(step1Form);
    if (!parsed.success) {
      const errors: Step1Errors = {};
      for (const issue of parsed.error.issues) {
        const key = issue.path[0];
        if (typeof key === "string" && !errors[key as keyof Step1FormState]) {
          errors[key as keyof Step1FormState] = issue.message;
        }
      }
      setStep1Errors(errors);
      return;
    }

    setIsRegistering(true);
    try {
      const cryptoArtifacts = await deriveRegistrationCryptoArtifacts(parsed.data.masterPassword);
      const registration = await registerRequest({
        email: parsed.data.email,
        name: parsed.data.name,
        org_id: parsed.data.orgId,
        auth_verifier: parsed.data.masterPassword,
        public_key: cryptoArtifacts.publicKey,
        encrypted_private_key: cryptoArtifacts.encryptedPrivateKey,
        invitation_token: parsed.data.invitationToken?.trim() || null
      });

      const login = await loginRequest({
        email: parsed.data.email,
        auth_verifier: parsed.data.masterPassword
      });

      if (login.mfa_required) {
        setStep1SubmitError("This account already requires MFA. Use /login instead.");
        return;
      }
      if (!login.access_token || !login.user) {
        setStep1SubmitError("Registration completed, but sign-in did not return a usable session.");
        return;
      }
      const accessToken = login.access_token;
      const authenticatedUser = login.user;

      setWizard((current) => ({
        ...current,
        registeredUser: registration,
        authSession: { accessToken, user: authenticatedUser },
        step: 2
      }));
      setTransitionDirection(1);
      setStep1Form((current) => ({ ...current, masterPassword: "", confirmPassword: "" }));
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.status === 409) {
          setStep1SubmitError("A user with this email already exists.");
          return;
        }
        if (error.status === 410) {
          setStep1SubmitError("The invitation token is invalid, expired, or already used.");
          return;
        }
      }
      setStep1SubmitError("Unable to complete registration right now.");
    } finally {
      setIsRegistering(false);
    }
  }

  async function submitStep2(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isConfirmingMfa) return;

    setStep2CodeError(null);
    setStep2SubmitError(null);
    const parsed = mfaConfirmSchema.safeParse({ code: step2Code });
    if (!parsed.success) {
      setStep2CodeError(parsed.error.issues[0]?.message ?? "Enter a valid code.");
      return;
    }

    const accessToken = wizard.authSession?.accessToken;
    if (!accessToken) {
      setStep2SubmitError("Session expired. Return to Step 1.");
      return;
    }

    setIsConfirmingMfa(true);
    try {
      const result = await confirmTotpMfaRequest({ code: parsed.data.code }, accessToken);
      if (!result.mfa_enabled) {
        setStep2SubmitError("MFA confirmation did not complete.");
        return;
      }
      setTransitionDirection(1);
      setWizard((current) => ({ ...current, mfaConfirmed: true, step: 3 }));
      setStep2Code("");
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setStep2SubmitError("Invalid or expired MFA code.");
      } else {
        setStep2SubmitError("Unable to verify MFA right now.");
      }
    } finally {
      setIsConfirmingMfa(false);
    }
  }

  async function handleImportFile(file: File) {
    setImportError(null);
    setIsParsingImport(true);
    try {
      const preview = await parseImportFile(file);
      setWizard((current) => ({ ...current, importPreview: preview }));
    } catch (error) {
      setImportError(error instanceof Error ? error.message : "Unable to parse file.");
    } finally {
      setIsParsingImport(false);
    }
  }

  async function onImportInputChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (file) await handleImportFile(file);
    event.target.value = "";
  }

  async function onDropImport(event: React.DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setIsDragActive(false);
    const file = event.dataTransfer.files?.[0];
    if (file) await handleImportFile(file);
  }

  function finishOnboarding() {
    clearOnboardingState();
    startTransition(() => {
      void navigate({ to: "/vault" });
    });
  }

  const stepPanelMotion = {
    initial: prefersReducedMotion ? { opacity: 0 } : { opacity: 0, x: transitionDirection > 0 ? 20 : -20 },
    animate: { opacity: 1, x: 0 },
    exit: prefersReducedMotion ? { opacity: 0 } : { opacity: 0, x: transitionDirection > 0 ? -12 : 12 }
  };

  return (
    <section className="onboarding-shell" aria-labelledby="onboarding-title">
      <aside className="onboarding-sidebar">
        <p className="auth-kicker">First-Run Setup</p>
        <h1 id="onboarding-title">VaultGuard onboarding wizard</h1>
        <p className="auth-subtitle">
          Complete your account setup in four guided steps. Wizard progress is stored in this browser session.
        </p>

        <div className="onboarding-step-card">
          <p className="onboarding-step-counter">
            Step {currentStep}/{TOTAL_ONBOARDING_STEPS}
          </p>
          <ol className="onboarding-step-list">
            {([1, 2, 3, 4] as const).map((step) => {
              const done =
                (step === 1 && Boolean(wizard.registeredUser)) ||
                (step === 2 && wizard.mfaConfirmed) ||
                (step === 3 && currentStep === 4);
              return (
                <li key={step} data-active={currentStep === step ? "true" : "false"} data-done={done ? "true" : "false"}>
                  <span className="onboarding-step-index">{done ? "OK" : step}</span>
                  <div>
                    <strong>{getStepTitle(step)}</strong>
                    <p>
                      {step === 1 && "Register and derive client-side keys"}
                      {step === 2 && "Scan a TOTP QR code and verify"}
                      {step === 3 && "Install extension or skip"}
                      {step === 4 && "Drag-and-drop CSV/JSON import preview"}
                    </p>
                  </div>
                </li>
              );
            })}
          </ol>
        </div>
      </aside>

      <div className="onboarding-card">
        <AnimatePresence initial={false} mode="wait">
          <motion.div
            key={currentStep}
            className="onboarding-step-panel"
            initial={stepPanelMotion.initial}
            animate={stepPanelMotion.animate}
            exit={stepPanelMotion.exit}
            transition={{ duration: prefersReducedMotion ? 0.12 : 0.2, ease: "easeOut" }}
          >
            {currentStep === 1 && (
              <form className="onboarding-form" onSubmit={(event) => void submitStep1(event)} noValidate>
                <div className="onboarding-panel-header">
                  <h2>Step 1: Set Master Password</h2>
                  <p>Derives an Argon2id client key with libsodium and calls the registration API.</p>
                </div>

                <div className="form-section">
                  <label className="form-field">
                    <span>Work email</span>
                    <input
                      type="email"
                      autoComplete="email"
                      value={step1Form.email}
                      onChange={(event) => setStep1Form((current) => ({ ...current, email: event.target.value }))}
                      aria-invalid={step1Errors.email ? "true" : "false"}
                      placeholder="alex@company.com"
                    />
                    {step1Errors.email && <p className="field-error">{step1Errors.email}</p>}
                  </label>

                  <label className="form-field">
                    <span>Full name</span>
                    <input
                      type="text"
                      autoComplete="name"
                      value={step1Form.name}
                      onChange={(event) => setStep1Form((current) => ({ ...current, name: event.target.value }))}
                      aria-invalid={step1Errors.name ? "true" : "false"}
                      placeholder="Alex Johnson"
                    />
                    {step1Errors.name && <p className="field-error">{step1Errors.name}</p>}
                  </label>

                  <label className="form-field">
                    <span>Organization ID (UUID)</span>
                    <input
                      type="text"
                      value={step1Form.orgId}
                      onChange={(event) => setStep1Form((current) => ({ ...current, orgId: event.target.value }))}
                      aria-invalid={step1Errors.orgId ? "true" : "false"}
                      placeholder="Provided by your organization admin"
                    />
                    {step1Errors.orgId && <p className="field-error">{step1Errors.orgId}</p>}
                  </label>

                  <label className="form-field">
                    <span>Invitation token (optional)</span>
                    <input
                      type="text"
                      value={step1Form.invitationToken}
                      onChange={(event) =>
                        setStep1Form((current) => ({ ...current, invitationToken: event.target.value }))
                      }
                      placeholder="Paste invite token if required"
                    />
                  </label>

                  <label className="form-field">
                    <span>Master password</span>
                    <input
                      type="password"
                      autoComplete="new-password"
                      value={step1Form.masterPassword}
                      onChange={(event) =>
                        setStep1Form((current) => ({ ...current, masterPassword: event.target.value }))
                      }
                      aria-invalid={step1Errors.masterPassword ? "true" : "false"}
                      placeholder="Use a long passphrase"
                    />
                    {step1Errors.masterPassword && <p className="field-error">{step1Errors.masterPassword}</p>}
                  </label>

                  <div className="onboarding-strength-card" aria-live="polite">
                    <div className="generator-strength">
                      <div className="generator-strength-bar" aria-hidden="true">
                        <span style={{ width: `${passwordStrength.score}%` }} />
                      </div>
                      <p className="generator-strength-label">
                        Strength: <strong>{passwordStrength.label}</strong> <span>({passwordStrength.score}/100)</span>
                      </p>
                    </div>
                    <p className="generator-note">{passwordStrength.hint}</p>
                  </div>

                  <label className="form-field">
                    <span>Confirm master password</span>
                    <input
                      type="password"
                      autoComplete="new-password"
                      value={step1Form.confirmPassword}
                      onChange={(event) =>
                        setStep1Form((current) => ({ ...current, confirmPassword: event.target.value }))
                      }
                      aria-invalid={step1Errors.confirmPassword ? "true" : "false"}
                      placeholder="Repeat password"
                    />
                    {step1Errors.confirmPassword && <p className="field-error">{step1Errors.confirmPassword}</p>}
                  </label>
                </div>

                {step1SubmitError && (
                  <p className="inline-error" role="alert">
                    {step1SubmitError}
                  </p>
                )}

                <div className="onboarding-actions">
                  <button type="submit" className="btn btn-primary" disabled={isRegistering}>
                    {isRegistering ? "Creating account..." : "Create account & continue"}
                  </button>
                </div>
              </form>
            )}

            {currentStep === 2 && (
              <form className="onboarding-form" onSubmit={(event) => void submitStep2(event)} noValidate>
                <div className="onboarding-panel-header">
                  <h2>Step 2: Enable MFA</h2>
                  <p>Scan the QR code from the enrollment API and verify your first authenticator code.</p>
                </div>

                {isEnrollingMfa && <p className="onboarding-muted-box">Generating TOTP enrollment...</p>}
                {mfaEnrollmentError && (
                  <p className="inline-error" role="alert">
                    {mfaEnrollmentError}
                  </p>
                )}

                {wizard.mfaEnrollment && (
                  <div className="onboarding-mfa-grid">
                    <div className="onboarding-qr-card">
                      <img
                        className="onboarding-qr-image"
                        src={buildQrImageUrl(wizard.mfaEnrollment.otpauthUri)}
                        alt="TOTP QR code for VaultGuard onboarding"
                      />
                      <p className="onboarding-step-note">Fallback setup URI</p>
                      <code className="vault-code-block">{wizard.mfaEnrollment.otpauthUri}</code>
                    </div>

                    <div className="onboarding-backup-card">
                      <h3>Backup Codes</h3>
                      <p className="onboarding-step-note">Store these securely. They are one-time-use recovery codes.</p>
                      <ul className="onboarding-backup-list">
                        {wizard.mfaEnrollment.backupCodes.map((code) => (
                          <li key={code}>
                            <code>{code}</code>
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                )}

                <label className="form-field">
                  <span>Authenticator code</span>
                  <input
                    type="text"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    maxLength={6}
                    placeholder="123456"
                    value={step2Code}
                    onChange={(event) => setStep2Code(event.target.value)}
                    aria-invalid={step2CodeError ? "true" : "false"}
                  />
                  {step2CodeError && <p className="field-error">{step2CodeError}</p>}
                </label>

                {step2SubmitError && (
                  <p className="inline-error" role="alert">
                    {step2SubmitError}
                  </p>
                )}

                <div className="onboarding-actions">
                  <button type="button" className="btn btn-secondary" onClick={() => moveToStep(1)}>
                    Back
                  </button>
                  <button
                    type="submit"
                    className="btn btn-primary"
                    disabled={isConfirmingMfa || isEnrollingMfa || !wizard.mfaEnrollment}
                  >
                    {isConfirmingMfa ? "Verifying..." : "Verify & continue"}
                  </button>
                </div>
              </form>
            )}

            {currentStep === 3 && (
              <div className="onboarding-form">
                <div className="onboarding-panel-header">
                  <h2>Step 3: Install Browser Extension</h2>
                  <p>Install now for auto-fill, or skip and continue to the web vault.</p>
                </div>

                <div className="onboarding-link-grid">
                  <a
                    className="onboarding-store-card"
                    href="https://chrome.google.com/webstore/category/extensions"
                    target="_blank"
                    rel="noreferrer"
                  >
                    <strong>Chrome / Edge</strong>
                    <p>Open the Chrome Web Store. Install VaultGuard when your organization publishes it.</p>
                  </a>
                  <a
                    className="onboarding-store-card"
                    href="https://addons.mozilla.org/firefox/extensions/"
                    target="_blank"
                    rel="noreferrer"
                  >
                    <strong>Firefox</strong>
                    <p>Open Firefox Add-ons. Install VaultGuard when your organization publishes it.</p>
                  </a>
                </div>

                <div className="onboarding-actions">
                  <button type="button" className="btn btn-secondary" onClick={() => moveToStep(2)}>
                    Back
                  </button>
                  <button type="button" className="btn btn-secondary" onClick={() => moveToStep(4)}>
                    Skip
                  </button>
                  <button type="button" className="btn btn-primary" onClick={() => moveToStep(4)}>
                    Continue
                  </button>
                </div>
              </div>
            )}

            {currentStep === 4 && (
              <div className="onboarding-form">
                <div className="onboarding-panel-header">
                  <h2>Step 4: Import or Skip</h2>
                  <p>Drop a CSV or JSON file for a local preview. Upload/import processing is handled later.</p>
                </div>

                <label
                  className="onboarding-dropzone"
                  data-drag-active={isDragActive ? "true" : "false"}
                  onDragEnter={(event) => {
                    event.preventDefault();
                    setIsDragActive(true);
                  }}
                  onDragOver={(event) => {
                    event.preventDefault();
                    setIsDragActive(true);
                  }}
                  onDragLeave={(event) => {
                    event.preventDefault();
                    setIsDragActive(false);
                  }}
                  onDrop={(event) => void onDropImport(event)}
                >
                  <input type="file" accept=".csv,.json,text/csv,application/json" onChange={(e) => void onImportInputChange(e)} />
                  <strong>{isParsingImport ? "Parsing..." : "Drop CSV/JSON here"}</strong>
                  <p>or click to browse</p>
                </label>

                {importError && (
                  <p className="inline-error" role="alert">
                    {importError}
                  </p>
                )}

                {wizard.importPreview && (
                  <div className="onboarding-import-preview">
                    <div className="onboarding-import-preview-header">
                      <div>
                        <h3>{wizard.importPreview.fileName}</h3>
                        <p>
                          {wizard.importPreview.format.toUpperCase()} - {wizard.importPreview.rowCount} row
                          {wizard.importPreview.rowCount === 1 ? "" : "s"}
                        </p>
                      </div>
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => setWizard((current) => ({ ...current, importPreview: null }))}
                      >
                        Clear
                      </button>
                    </div>

                    <div className="onboarding-chip-list">
                      {(wizard.importPreview.columns.length > 0 ? wizard.importPreview.columns : ["No columns"]).map(
                        (column) => (
                          <span key={column}>{column}</span>
                        )
                      )}
                    </div>

                    <div className="onboarding-table-wrap">
                      <table className="onboarding-preview-table">
                        <thead>
                          <tr>
                            {wizard.importPreview.columns.slice(0, 6).map((column) => (
                              <th key={column}>{column}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {wizard.importPreview.sampleRows.length > 0 ? (
                            wizard.importPreview.sampleRows.map((row, index) => (
                              <tr key={`${index}-${Object.values(row).join("|")}`}>
                                {(wizard.importPreview?.columns.slice(0, 6).map((column) => (
                                  <td key={`${index}-${column}`}>{row[column] ?? ""}</td>
                                )) ?? null)}
                              </tr>
                            ))
                          ) : (
                            <tr>
                              <td colSpan={Math.max(1, wizard.importPreview?.columns.slice(0, 6).length ?? 1)}>
                                No rows found.
                              </td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                <div className="onboarding-actions">
                  <button type="button" className="btn btn-secondary" onClick={() => moveToStep(3)}>
                    Back
                  </button>
                  <button type="button" className="btn btn-secondary" onClick={finishOnboarding}>
                    Skip
                  </button>
                  <button type="button" className="btn btn-primary" onClick={finishOnboarding}>
                    Finish onboarding
                  </button>
                </div>
              </div>
            )}
          </motion.div>
        </AnimatePresence>
      </div>
    </section>
  );
}

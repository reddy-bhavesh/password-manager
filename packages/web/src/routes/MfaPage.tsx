import { startTransition, useState } from "react";
import { Link, useNavigate } from "@tanstack/react-router";
import { useForm } from "react-hook-form";
import { ApiError } from "../api/http";
import { verifyMfaRequest } from "../features/auth/api";
import { useAuthStore } from "../features/auth/store";
import { type MfaFormValues, mfaFormSchema } from "../features/auth/validation";
import { zodResolver } from "../lib/zodResolver";

export function MfaPage() {
  const navigate = useNavigate();
  const pendingMfaToken = useAuthStore((state) => state.pendingMfaToken);
  const clearPendingMfa = useAuthStore((state) => state.clearPendingMfa);
  const setAuthenticatedSession = useAuthStore((state) => state.setAuthenticatedSession);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting }
  } = useForm<MfaFormValues>({
    resolver: zodResolver(mfaFormSchema),
    defaultValues: {
      code: ""
    }
  });

  const onSubmit = handleSubmit(async (values) => {
    if (!pendingMfaToken) {
      setSubmitError("Your MFA challenge has expired. Please sign in again.");
      return;
    }

    setSubmitError(null);

    try {
      const response = await verifyMfaRequest({
        mfa_token: pendingMfaToken,
        code: values.code
      });

      if (!response.access_token || !response.user) {
        setSubmitError("MFA verification succeeded but the session response was incomplete.");
        return;
      }

      clearPendingMfa();
      setAuthenticatedSession({
        accessToken: response.access_token,
        user: response.user
      });

      startTransition(() => {
        void navigate({ to: "/vault" });
      });
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setSubmitError(error.message);
        return;
      }

      setSubmitError("Unable to verify MFA right now. Please try again.");
    }
  });

  return (
    <form className="auth-form" onSubmit={(event) => void onSubmit(event)} noValidate>
      <div className="form-section">
        <label className="form-field">
          <span>Authenticator code</span>
          <input
            type="text"
            inputMode="numeric"
            autoComplete="one-time-code"
            placeholder="123456"
            maxLength={6}
            aria-invalid={errors.code ? "true" : "false"}
            {...register("code")}
          />
          {errors.code ? <p className="field-error">{errors.code.message}</p> : null}
        </label>
      </div>

      {!pendingMfaToken ? (
        <p className="inline-error" role="alert">
          No MFA challenge is pending. <Link to="/login">Return to login</Link>.
        </p>
      ) : null}

      {submitError ? (
        <p className="inline-error" role="alert">
          {submitError}
        </p>
      ) : null}

      <button type="submit" className="btn btn-primary btn-block" disabled={isSubmitting || !pendingMfaToken}>
        {isSubmitting ? "Verifying..." : "Verify & Continue"}
      </button>
    </form>
  );
}

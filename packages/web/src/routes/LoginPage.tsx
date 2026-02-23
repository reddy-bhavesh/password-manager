import { startTransition, useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "@tanstack/react-router";
import { ApiError } from "../api/http";
import { loginRequest } from "../features/auth/api";
import { useAuthStore } from "../features/auth/store";
import { type LoginFormValues, loginFormSchema } from "../features/auth/validation";
import { zodResolver } from "../lib/zodResolver";

export function LoginPage() {
  const navigate = useNavigate();
  const setAuthenticatedSession = useAuthStore((state) => state.setAuthenticatedSession);
  const setPendingMfa = useAuthStore((state) => state.setPendingMfa);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting }
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginFormSchema),
    defaultValues: {
      email: "",
      password: ""
    }
  });

  const onSubmit = handleSubmit(async (values) => {
    setSubmitError(null);

    try {
      const response = await loginRequest({
        email: values.email,
        auth_verifier: values.password
      });

      if (response.mfa_required) {
        if (!response.mfa_token) {
          setSubmitError("Login requires MFA, but the server did not return a challenge token.");
          return;
        }

        setPendingMfa(response.mfa_token);
        startTransition(() => {
          void navigate({ to: "/mfa" });
        });
        return;
      }

      if (!response.access_token || !response.user) {
        setSubmitError("Login response was incomplete. Please try again.");
        return;
      }

      // Refresh token is expected to be written by the server via Set-Cookie (HttpOnly).
      setAuthenticatedSession({
        accessToken: response.access_token,
        user: response.user
      });

      startTransition(() => {
        void navigate({ to: "/vault" });
      });
    } catch (error) {
      if (error instanceof ApiError && (error.status === 401 || error.status === 429)) {
        setSubmitError(error.message);
        return;
      }

      setSubmitError("Unable to sign in right now. Please try again.");
    }
  });

  return (
    <form className="auth-form" onSubmit={(event) => void onSubmit(event)} noValidate>
      <div className="form-section">
        <label className="form-field">
          <span>Work email</span>
          <input
            type="email"
            autoComplete="username"
            placeholder="alex@company.com"
            aria-invalid={errors.email ? "true" : "false"}
            {...register("email")}
          />
          {errors.email ? <p className="field-error">{errors.email.message}</p> : null}
        </label>

        <label className="form-field">
          <span>Password</span>
          <input
            type="password"
            autoComplete="current-password"
            placeholder="Enter your master password verifier"
            aria-invalid={errors.password ? "true" : "false"}
            {...register("password")}
          />
          {errors.password ? <p className="field-error">{errors.password.message}</p> : null}
        </label>
      </div>

      {submitError ? (
        <p className="inline-error" role="alert">
          {submitError}
        </p>
      ) : null}

      <button type="submit" className="btn btn-primary btn-block" disabled={isSubmitting}>
        {isSubmitting ? "Signing in..." : "Sign In"}
      </button>
    </form>
  );
}

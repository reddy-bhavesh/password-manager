import { postJson } from "../../api/http";

export type AuthenticatedUser = {
  id: string;
  org_id: string;
  email: string;
  name: string;
  role: string;
  status: string;
  mfa_enabled: boolean;
};

export type LoginResponse = {
  access_token: string | null;
  refresh_token: string | null;
  user: AuthenticatedUser | null;
  mfa_required: boolean;
  mfa_token: string | null;
};

export type RegisterRequest = {
  email: string;
  name: string;
  org_id: string;
  auth_verifier: string;
  public_key: string;
  encrypted_private_key: string;
  invitation_token?: string | null;
};

export type RegisterResponse = {
  id: string;
  org_id: string;
  email: string;
  name: string;
  created_at: string;
};

export type TotpEnrollResponse = {
  otpauth_uri: string;
  backup_codes: string[];
};

export type TotpConfirmResponse = {
  mfa_enabled: boolean;
};

export async function registerRequest(input: RegisterRequest): Promise<RegisterResponse> {
  return postJson<RegisterResponse, RegisterRequest>("/api/v1/auth/register", input);
}

export async function loginRequest(input: { email: string; auth_verifier: string }): Promise<LoginResponse> {
  return postJson<LoginResponse, { email: string; auth_verifier: string }>("/api/v1/auth/login", input);
}

export async function enrollTotpMfaRequest(accessToken: string): Promise<TotpEnrollResponse> {
  return postJson<TotpEnrollResponse, Record<string, never>>("/api/v1/auth/mfa/totp/enroll", {}, { accessToken });
}

export async function confirmTotpMfaRequest(
  input: { code: string },
  accessToken: string
): Promise<TotpConfirmResponse> {
  return postJson<TotpConfirmResponse, { code: string }>("/api/v1/auth/mfa/totp/confirm", input, { accessToken });
}

export async function verifyMfaRequest(input: { mfa_token: string; code: string }): Promise<LoginResponse> {
  return postJson<LoginResponse, { mfa_token: string; code: string }>("/api/v1/auth/mfa/verify", input);
}

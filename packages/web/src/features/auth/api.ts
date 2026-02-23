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

export async function loginRequest(input: { email: string; auth_verifier: string }): Promise<LoginResponse> {
  return postJson<LoginResponse, { email: string; auth_verifier: string }>("/api/v1/auth/login", input);
}

export async function verifyMfaRequest(input: { mfa_token: string; code: string }): Promise<LoginResponse> {
  return postJson<LoginResponse, { mfa_token: string; code: string }>("/api/v1/auth/mfa/verify", input);
}

import { create } from "zustand";
import type { AuthenticatedUser } from "./api";

type AuthState = {
  accessToken: string | null;
  user: AuthenticatedUser | null;
  pendingMfaToken: string | null;
  setAuthenticatedSession: (input: { accessToken: string; user: AuthenticatedUser }) => void;
  setPendingMfa: (mfaToken: string) => void;
  clearPendingMfa: () => void;
  clearSession: () => void;
};

export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  user: null,
  pendingMfaToken: null,
  setAuthenticatedSession: ({ accessToken, user }) =>
    set({
      accessToken,
      user,
      pendingMfaToken: null
    }),
  setPendingMfa: (mfaToken) =>
    set({
      pendingMfaToken: mfaToken,
      accessToken: null,
      user: null
    }),
  clearPendingMfa: () => set({ pendingMfaToken: null }),
  clearSession: () =>
    set({
      accessToken: null,
      user: null,
      pendingMfaToken: null
    })
}));

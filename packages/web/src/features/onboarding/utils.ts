import sodium from "libsodium-wrappers-sumo";
import { z } from "zod";
import type { AuthenticatedUser, RegisterResponse } from "../auth/api";

export const ONBOARDING_STORAGE_KEY = "vaultguard.onboarding.v1";
export const TOTAL_ONBOARDING_STEPS = 4;
export type OnboardingStep = 1 | 2 | 3 | 4;

export type Step1Draft = {
  email: string;
  name: string;
  orgId: string;
  invitationToken: string;
};

export type Step1FormState = Step1Draft & {
  masterPassword: string;
  confirmPassword: string;
};

export type MfaEnrollmentState = {
  otpauthUri: string;
  backupCodes: string[];
};

export type ImportPreview = {
  fileName: string;
  format: "csv" | "json";
  rowCount: number;
  columns: string[];
  sampleRows: Array<Record<string, string>>;
};

export type OnboardingState = {
  step: OnboardingStep;
  step1Draft: Step1Draft;
  registeredUser: RegisterResponse | null;
  authSession: { accessToken: string; user: AuthenticatedUser } | null;
  mfaEnrollment: MfaEnrollmentState | null;
  mfaConfirmed: boolean;
  importPreview: ImportPreview | null;
};

export type PasswordStrength = {
  score: number;
  label: string;
  hint: string;
};

type SodiumModule = typeof sodium;

type ParsedImport = {
  rowCount: number;
  columns: string[];
  sampleRows: Array<Record<string, string>>;
};

export const defaultStep1Draft: Step1Draft = {
  email: "",
  name: "",
  orgId: "",
  invitationToken: ""
};

export const registrationSchema = z
  .object({
    email: z.string().trim().email("Enter a valid work email."),
    name: z.string().trim().min(1, "Name is required."),
    orgId: z.string().trim().uuid("Enter a valid organization UUID."),
    invitationToken: z.string().trim().optional().or(z.literal("")),
    masterPassword: z.string().min(12, "Use at least 12 characters.").max(256, "Master password is too long."),
    confirmPassword: z.string().min(1, "Confirm your master password.")
  })
  .refine((value) => value.masterPassword === value.confirmPassword, {
    path: ["confirmPassword"],
    message: "Passwords do not match."
  });

export const mfaConfirmSchema = z.object({
  code: z
    .string()
    .trim()
    .regex(/^\d{6}$/, "Enter the 6-digit code from your authenticator app.")
});

let sodiumReadyPromise: Promise<SodiumModule> | null = null;

export function getDefaultOnboardingState(): OnboardingState {
  return {
    step: 1,
    step1Draft: { ...defaultStep1Draft },
    registeredUser: null,
    authSession: null,
    mfaEnrollment: null,
    mfaConfirmed: false,
    importPreview: null
  };
}

export function normalizeStep(step: unknown): OnboardingStep {
  return step === 2 || step === 3 || step === 4 ? step : 1;
}

export function loadOnboardingState(): OnboardingState {
  if (typeof window === "undefined") {
    return getDefaultOnboardingState();
  }

  const raw = window.sessionStorage.getItem(ONBOARDING_STORAGE_KEY);
  if (!raw) {
    return getDefaultOnboardingState();
  }

  try {
    const parsed = JSON.parse(raw) as Partial<OnboardingState>;
    return {
      ...getDefaultOnboardingState(),
      step: normalizeStep(parsed.step),
      step1Draft: { ...defaultStep1Draft, ...(parsed.step1Draft ?? {}) },
      registeredUser: parsed.registeredUser ?? null,
      authSession: parsed.authSession ?? null,
      mfaEnrollment: parsed.mfaEnrollment ?? null,
      mfaConfirmed: Boolean(parsed.mfaConfirmed),
      importPreview: parsed.importPreview ?? null
    };
  } catch {
    return getDefaultOnboardingState();
  }
}

export function persistOnboardingState(state: OnboardingState): void {
  if (typeof window === "undefined") {
    return;
  }
  window.sessionStorage.setItem(ONBOARDING_STORAGE_KEY, JSON.stringify(state));
}

export function clearOnboardingState(): void {
  if (typeof window === "undefined") {
    return;
  }
  window.sessionStorage.removeItem(ONBOARDING_STORAGE_KEY);
}

async function getSodium(): Promise<SodiumModule> {
  if (!sodiumReadyPromise) {
    sodiumReadyPromise = sodium.ready.then(() => sodium);
  }
  return sodiumReadyPromise;
}

export async function deriveRegistrationCryptoArtifacts(masterPassword: string): Promise<{
  publicKey: string;
  encryptedPrivateKey: string;
}> {
  const sodiumLib = await getSodium();
  const salt = sodiumLib.randombytes_buf(sodiumLib.crypto_pwhash_SALTBYTES);
  const derivedKey = sodiumLib.crypto_pwhash(
    sodiumLib.crypto_secretbox_KEYBYTES,
    masterPassword,
    salt,
    sodiumLib.crypto_pwhash_OPSLIMIT_INTERACTIVE,
    sodiumLib.crypto_pwhash_MEMLIMIT_INTERACTIVE,
    sodiumLib.crypto_pwhash_ALG_ARGON2ID13
  );

  const keyPair = sodiumLib.crypto_box_keypair();
  const nonce = sodiumLib.randombytes_buf(sodiumLib.crypto_secretbox_NONCEBYTES);
  const encryptedPrivateKeyBytes = sodiumLib.crypto_secretbox_easy(keyPair.privateKey, nonce, derivedKey);

  const publicKey = `vgpk1:${sodiumLib.to_base64(keyPair.publicKey, sodiumLib.base64_variants.ORIGINAL)}`;
  const encryptedPrivateKey = [
    "vgsk1",
    "argon2id13",
    sodiumLib.to_base64(salt, sodiumLib.base64_variants.ORIGINAL),
    sodiumLib.to_base64(nonce, sodiumLib.base64_variants.ORIGINAL),
    sodiumLib.to_base64(encryptedPrivateKeyBytes, sodiumLib.base64_variants.ORIGINAL)
  ].join(":");

  sodiumLib.memzero(derivedKey);
  sodiumLib.memzero(keyPair.privateKey);

  return { publicKey, encryptedPrivateKey };
}

export function scorePassword(value: string): PasswordStrength {
  const length = value.length;
  const classes = [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].reduce((count, re) => count + Number(re.test(value)), 0);
  const uniqueChars = new Set(value).size;

  let score = Math.min(40, length * 2) + classes * 12 + Math.min(12, uniqueChars);
  if (length < 12) score -= 25;
  if (/password|1234|qwerty|admin/i.test(value)) score -= 20;
  score = Math.max(0, Math.min(100, score));

  if (score < 35) return { score, label: "Weak", hint: "Use a longer passphrase with mixed character types." };
  if (score < 65) return { score, label: "Fair", hint: "Add length and a symbol for stronger resistance." };
  if (score < 85) return { score, label: "Strong", hint: "Good baseline. Consider a passphrase for memorability." };
  return { score, label: "Very strong", hint: "Strong choice for a master password." };
}

function parseCsvLine(line: string): string[] {
  const result: string[] = [];
  let current = "";
  let inQuotes = false;

  for (let i = 0; i < line.length; i += 1) {
    const char = line[i];
    if (char === '"') {
      if (inQuotes && line[i + 1] === '"') {
        current += '"';
        i += 1;
      } else {
        inQuotes = !inQuotes;
      }
      continue;
    }
    if (char === "," && !inQuotes) {
      result.push(current.trim());
      current = "";
      continue;
    }
    current += char;
  }

  result.push(current.trim());
  return result;
}

function parseCsvImport(text: string): ParsedImport {
  const lines = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  if (lines.length === 0) {
    throw new Error("CSV file is empty.");
  }

  const headers = parseCsvLine(lines[0]).map((header, index) => header || `column_${index + 1}`);
  if (headers.length === 0) {
    throw new Error("CSV header row is missing.");
  }

  const rows = lines.slice(1).map((line) => {
    const values = parseCsvLine(line);
    const row: Record<string, string> = {};
    headers.forEach((header, index) => {
      row[header] = values[index] ?? "";
    });
    return row;
  });

  return { rowCount: rows.length, columns: headers, sampleRows: rows.slice(0, 5) };
}

function normalizeJsonRow(input: unknown, index: number): Record<string, string> {
  if (!input || typeof input !== "object" || Array.isArray(input)) {
    return { row: String(index + 1), value: JSON.stringify(input) };
  }

  const output: Record<string, string> = {};
  for (const [key, value] of Object.entries(input as Record<string, unknown>)) {
    output[key] =
      typeof value === "string"
        ? value
        : typeof value === "number" || typeof value === "boolean"
          ? String(value)
          : value == null
            ? ""
            : JSON.stringify(value);
  }
  return output;
}

function parseJsonImport(text: string): ParsedImport {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    throw new Error("JSON file could not be parsed.");
  }

  const source = Array.isArray(parsed)
    ? parsed
    : parsed && typeof parsed === "object" && Array.isArray((parsed as { items?: unknown[] }).items)
      ? (parsed as { items: unknown[] }).items
      : [parsed];

  const rows = source.map(normalizeJsonRow);
  const columns = [...new Set(rows.flatMap((row) => Object.keys(row)))];
  return { rowCount: rows.length, columns, sampleRows: rows.slice(0, 5) };
}

export async function parseImportFile(file: File): Promise<ImportPreview> {
  const text = await file.text();
  const lower = file.name.toLowerCase();

  if (lower.endsWith(".csv") || file.type.includes("csv")) {
    return { fileName: file.name, format: "csv", ...parseCsvImport(text) };
  }
  if (lower.endsWith(".json") || file.type.includes("json")) {
    return { fileName: file.name, format: "json", ...parseJsonImport(text) };
  }
  throw new Error("Unsupported file type. Upload a CSV or JSON file.");
}

export function buildQrImageUrl(otpauthUri: string): string {
  const params = new URLSearchParams({ cht: "qr", chs: "240x240", chl: otpauthUri });
  return `https://chart.googleapis.com/chart?${params.toString()}`;
}

export function getStepTitle(step: OnboardingStep): string {
  if (step === 1) return "Set Master Password";
  if (step === 2) return "Enable MFA";
  if (step === 3) return "Install Browser Extension";
  return "Import Data";
}

export function canAdvanceToStep(state: OnboardingState, nextStep: OnboardingStep): boolean {
  if (nextStep <= state.step) return true;
  if (nextStep === 2) return Boolean(state.registeredUser && state.authSession);
  if (nextStep === 3) return state.mfaConfirmed;
  if (nextStep === 4) return state.step >= 3;
  return false;
}

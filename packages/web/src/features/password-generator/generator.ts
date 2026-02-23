import { EFF_SHORT_WORD_LIST } from "./effWordList";
export { EFF_SHORT_WORD_LIST } from "./effWordList";

export const PASSWORD_LENGTH_MIN = 8;
export const PASSWORD_LENGTH_MAX = 128;
export const PASSPHRASE_WORD_COUNT_MIN = 3;
export const PASSPHRASE_WORD_COUNT_MAX = 8;

export const PASSWORD_CHAR_SETS = {
  uppercase: "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
  lowercase: "abcdefghijklmnopqrstuvwxyz",
  numbers: "0123456789",
  symbols: "!@#$%^&*()-_=+[]{};:,.?/<>~"
} as const;

export const AMBIGUOUS_PASSWORD_CHARS = new Set(["I", "l", "1", "O", "0", "|"]);

export type PasswordMode = "password" | "passphrase";

export type PasswordGeneratorOptions = {
  length: number;
  uppercase: boolean;
  lowercase: boolean;
  numbers: boolean;
  symbols: boolean;
  excludeAmbiguous: boolean;
};

export type PassphraseGeneratorOptions = {
  wordCount: number;
  separator: string;
};

export type GeneratorStrength = {
  score: 0 | 1 | 2 | 3 | 4;
  label: "Very Weak" | "Weak" | "Fair" | "Strong" | "Excellent";
  entropyBits: number;
};

export type RandomSource = () => number;

export const DEFAULT_PASSWORD_OPTIONS: PasswordGeneratorOptions = {
  length: 20,
  uppercase: true,
  lowercase: true,
  numbers: true,
  symbols: true,
  excludeAmbiguous: false
};

export const DEFAULT_PASSPHRASE_OPTIONS: PassphraseGeneratorOptions = {
  wordCount: 4,
  separator: "-"
};

export function clampNumber(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function sanitizePasswordOptions(options: PasswordGeneratorOptions): PasswordGeneratorOptions {
  return {
    ...options,
    length: clampNumber(Math.trunc(options.length), PASSWORD_LENGTH_MIN, PASSWORD_LENGTH_MAX)
  };
}

function sanitizePassphraseOptions(options: PassphraseGeneratorOptions): PassphraseGeneratorOptions {
  return {
    ...options,
    wordCount: clampNumber(Math.trunc(options.wordCount), PASSPHRASE_WORD_COUNT_MIN, PASSPHRASE_WORD_COUNT_MAX)
  };
}

function randomIndex(length: number, random: RandomSource): number {
  if (length <= 0) {
    throw new Error("Random index length must be positive.");
  }

  const value = random();
  if (!Number.isFinite(value) || value < 0 || value >= 1) {
    throw new Error("Random source must return a number in [0, 1).");
  }

  return Math.floor(value * length);
}

function pickRandomChar(charset: string, random: RandomSource): string {
  return charset[randomIndex(charset.length, random)] ?? "";
}

function buildPasswordCharsets(options: PasswordGeneratorOptions): string[] {
  const activeSets: string[] = [];

  if (options.uppercase) {
    activeSets.push(PASSWORD_CHAR_SETS.uppercase);
  }
  if (options.lowercase) {
    activeSets.push(PASSWORD_CHAR_SETS.lowercase);
  }
  if (options.numbers) {
    activeSets.push(PASSWORD_CHAR_SETS.numbers);
  }
  if (options.symbols) {
    activeSets.push(PASSWORD_CHAR_SETS.symbols);
  }

  if (!options.excludeAmbiguous) {
    return activeSets;
  }

  return activeSets
    .map((set) => [...set].filter((char) => !AMBIGUOUS_PASSWORD_CHARS.has(char)).join(""))
    .filter((set) => set.length > 0);
}

export function generatePassword(options: PasswordGeneratorOptions, random: RandomSource = Math.random): string {
  const normalized = sanitizePasswordOptions(options);
  const charsets = buildPasswordCharsets(normalized);

  if (charsets.length === 0) {
    throw new Error("Select at least one character set.");
  }

  const requiredChars = charsets.map((charset) => pickRandomChar(charset, random));
  const combinedCharset = charsets.join("");
  const generated: string[] = [...requiredChars];

  while (generated.length < normalized.length) {
    generated.push(pickRandomChar(combinedCharset, random));
  }

  for (let index = generated.length - 1; index > 0; index -= 1) {
    const swapIndex = randomIndex(index + 1, random);
    [generated[index], generated[swapIndex]] = [generated[swapIndex] as string, generated[index] as string];
  }

  return generated.join("");
}

export function generatePassphrase(
  options: PassphraseGeneratorOptions,
  random: RandomSource = Math.random,
  words: readonly string[] = EFF_SHORT_WORD_LIST
): string {
  const normalized = sanitizePassphraseOptions(options);

  if (words.length === 0) {
    throw new Error("Passphrase word list is empty.");
  }

  const selectedWords = Array.from({ length: normalized.wordCount }, () => words[randomIndex(words.length, random)] as string);
  return selectedWords.join(normalized.separator);
}

export function estimatePasswordEntropyBits(options: PasswordGeneratorOptions): number {
  const normalized = sanitizePasswordOptions(options);
  const charsets = buildPasswordCharsets(normalized);
  const poolSize = new Set(charsets.join("")).size;

  if (poolSize <= 0) {
    return 0;
  }

  return normalized.length * Math.log2(poolSize);
}

export function estimatePassphraseEntropyBits(
  options: PassphraseGeneratorOptions,
  wordListSize = EFF_SHORT_WORD_LIST.length
): number {
  const normalized = sanitizePassphraseOptions(options);
  if (wordListSize <= 1) {
    return 0;
  }
  return normalized.wordCount * Math.log2(wordListSize);
}

export function strengthFromEntropy(entropyBits: number): GeneratorStrength {
  const clampedEntropy = Math.max(0, entropyBits);

  if (clampedEntropy < 30) {
    return { score: 0, label: "Very Weak", entropyBits: clampedEntropy };
  }
  if (clampedEntropy < 45) {
    return { score: 1, label: "Weak", entropyBits: clampedEntropy };
  }
  if (clampedEntropy < 60) {
    return { score: 2, label: "Fair", entropyBits: clampedEntropy };
  }
  if (clampedEntropy < 80) {
    return { score: 3, label: "Strong", entropyBits: clampedEntropy };
  }
  return { score: 4, label: "Excellent", entropyBits: clampedEntropy };
}

export function estimatePasswordStrength(options: PasswordGeneratorOptions): GeneratorStrength {
  return strengthFromEntropy(estimatePasswordEntropyBits(options));
}

export function estimatePassphraseStrength(options: PassphraseGeneratorOptions): GeneratorStrength {
  return strengthFromEntropy(estimatePassphraseEntropyBits(options));
}

function cryptoRandomInt(maxExclusive: number): number {
  if (maxExclusive <= 0) {
    throw new Error("maxExclusive must be positive.");
  }

  const cryptoApi = globalThis.crypto;
  if (!cryptoApi?.getRandomValues) {
    return Math.floor(Math.random() * maxExclusive);
  }

  const maxUint32 = 0xffffffff;
  const limit = Math.floor((maxUint32 + 1) / maxExclusive) * maxExclusive;
  const buffer = new Uint32Array(1);

  while (true) {
    cryptoApi.getRandomValues(buffer);
    const value = buffer[0] as number;
    if (value < limit) {
      return value % maxExclusive;
    }
  }
}

export function createBrowserRandomSource(): RandomSource {
  return () => {
    const precision = 1_000_000;
    return cryptoRandomInt(precision) / precision;
  };
}

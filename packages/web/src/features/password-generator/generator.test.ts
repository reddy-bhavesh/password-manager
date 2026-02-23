import { describe, expect, it } from "vitest";
import {
  AMBIGUOUS_PASSWORD_CHARS,
  estimatePassphraseStrength,
  estimatePasswordStrength,
  generatePassphrase,
  generatePassword,
  PASSWORD_CHAR_SETS
} from "./generator";

function sequenceRandom(values: number[]) {
  let index = 0;
  return () => {
    const value = values[index] ?? 0.123456;
    index += 1;
    return value;
  };
}

describe("password generator logic", () => {
  it("clamps password length to the supported range", () => {
    const shortPassword = generatePassword(
      {
        length: 3,
        uppercase: false,
        lowercase: true,
        numbers: false,
        symbols: false,
        excludeAmbiguous: false
      },
      sequenceRandom([0.1])
    );

    const longPassword = generatePassword(
      {
        length: 999,
        uppercase: false,
        lowercase: true,
        numbers: false,
        symbols: false,
        excludeAmbiguous: false
      },
      sequenceRandom([0.2])
    );

    expect(shortPassword).toHaveLength(8);
    expect(longPassword).toHaveLength(128);
  });

  it("includes at least one character from each enabled set", () => {
    const generated = generatePassword(
      {
        length: 24,
        uppercase: true,
        lowercase: true,
        numbers: true,
        symbols: true,
        excludeAmbiguous: false
      },
      sequenceRandom([0.01, 0.02, 0.03, 0.04, 0.3, 0.5, 0.7, 0.9, 0.12, 0.34, 0.56, 0.78, 0.21, 0.43, 0.65, 0.87])
    );

    expect([...generated].some((char) => PASSWORD_CHAR_SETS.uppercase.includes(char))).toBe(true);
    expect([...generated].some((char) => PASSWORD_CHAR_SETS.lowercase.includes(char))).toBe(true);
    expect([...generated].some((char) => PASSWORD_CHAR_SETS.numbers.includes(char))).toBe(true);
    expect([...generated].some((char) => PASSWORD_CHAR_SETS.symbols.includes(char))).toBe(true);
  });

  it("removes ambiguous characters when requested", () => {
    const generated = generatePassword(
      {
        length: 64,
        uppercase: true,
        lowercase: true,
        numbers: true,
        symbols: true,
        excludeAmbiguous: true
      },
      sequenceRandom(Array.from({ length: 120 }, (_, index) => ((index % 97) + 0.5) / 100))
    );

    expect([...generated].some((char) => AMBIGUOUS_PASSWORD_CHARS.has(char))).toBe(false);
  });

  it("throws when no character sets are enabled", () => {
    expect(() =>
      generatePassword(
        {
          length: 16,
          uppercase: false,
          lowercase: false,
          numbers: false,
          symbols: false,
          excludeAmbiguous: false
        },
        sequenceRandom([0.1])
      )
    ).toThrow("Select at least one character set.");
  });

  it("builds passphrases from the provided word list and clamps word count", () => {
    const passphrase = generatePassphrase(
      { wordCount: 1, separator: "-" },
      sequenceRandom([0, 0.49, 0.99, 0.1]),
      ["alpha", "bravo", "charlie", "delta"]
    );

    expect(passphrase.split("-")).toHaveLength(3);
    expect(passphrase).toMatch(/^(alpha|bravo|charlie|delta)(-(alpha|bravo|charlie|delta)){2}$/);
  });

  it("returns stronger scores for stronger settings", () => {
    const weak = estimatePasswordStrength({
      length: 8,
      uppercase: false,
      lowercase: true,
      numbers: false,
      symbols: false,
      excludeAmbiguous: false
    });
    const strong = estimatePasswordStrength({
      length: 32,
      uppercase: true,
      lowercase: true,
      numbers: true,
      symbols: true,
      excludeAmbiguous: false
    });
    const passphrase = estimatePassphraseStrength({ wordCount: 8, separator: "-" });

    expect(weak.score).toBeLessThan(strong.score);
    expect(passphrase.score).toBeGreaterThanOrEqual(3);
  });
});


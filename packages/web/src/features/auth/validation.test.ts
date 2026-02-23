import { describe, expect, it } from "vitest";
import { loginFormSchema, mfaFormSchema } from "./validation";

describe("loginFormSchema", () => {
  it("accepts a valid email and non-empty password", () => {
    const parsed = loginFormSchema.safeParse({
      email: "alex@example.com",
      password: "verifier-value"
    });

    expect(parsed.success).toBe(true);
  });

  it("rejects invalid email format", () => {
    const parsed = loginFormSchema.safeParse({
      email: "not-an-email",
      password: "verifier-value"
    });

    expect(parsed.success).toBe(false);
    if (!parsed.success) {
      expect(parsed.error.issues[0]?.message).toContain("valid email");
    }
  });

  it("rejects empty password", () => {
    const parsed = loginFormSchema.safeParse({
      email: "alex@example.com",
      password: "   "
    });

    expect(parsed.success).toBe(false);
    if (!parsed.success) {
      expect(parsed.error.issues[0]?.path).toEqual(["password"]);
    }
  });
});

describe("mfaFormSchema", () => {
  it("accepts a six-digit code", () => {
    const parsed = mfaFormSchema.safeParse({ code: "123456" });
    expect(parsed.success).toBe(true);
  });

  it("rejects non-numeric or wrong-length codes", () => {
    const parsed = mfaFormSchema.safeParse({ code: "12ab" });
    expect(parsed.success).toBe(false);
  });
});

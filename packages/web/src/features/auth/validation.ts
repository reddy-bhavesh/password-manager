import { z } from "zod";

export const loginFormSchema = z.object({
  email: z.string().trim().email("Enter a valid email address."),
  password: z.string().trim().min(1, "Password is required.")
});

export const mfaFormSchema = z.object({
  code: z
    .string()
    .trim()
    .regex(/^\d{6}$/, "Enter the 6-digit code from your authenticator app.")
});

export type LoginFormValues = z.infer<typeof loginFormSchema>;
export type MfaFormValues = z.infer<typeof mfaFormSchema>;

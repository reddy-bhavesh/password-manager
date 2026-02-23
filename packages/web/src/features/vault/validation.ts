import { z } from "zod";

export const vaultItemTypeSchema = z.enum(["login", "secure_note", "credit_card"]);

const commonFields = {
  type: vaultItemTypeSchema,
  name: z.string().trim().min(1, "Item name is required.").max(255, "Item name is too long."),
  folder_id: z.string().uuid("Folder must be a valid identifier.").nullable()
};

export const loginVaultItemFormSchema = z.object({
  ...commonFields,
  type: z.literal("login"),
  username: z.string().trim().min(1, "Username is required."),
  password: z.string().min(1, "Password is required."),
  url: z.string().trim().url("Enter a valid URL (including https://).")
});

export const secureNoteVaultItemFormSchema = z.object({
  ...commonFields,
  type: z.literal("secure_note"),
  note: z.string().trim().min(1, "Note text is required.")
});

export const creditCardVaultItemFormSchema = z.object({
  ...commonFields,
  type: z.literal("credit_card"),
  card_number: z
    .string()
    .trim()
    .regex(/^[0-9 ]{12,23}$/, "Enter a valid card number."),
  expiry: z.string().trim().regex(/^(0[1-9]|1[0-2])\/\d{2}$/, "Use MM/YY format."),
  cvv: z.string().trim().regex(/^\d{3,4}$/, "CVV must be 3 or 4 digits."),
  cardholder_name: z.string().trim().optional().default("")
});

export const vaultItemFormSchema = z.discriminatedUnion("type", [
  loginVaultItemFormSchema,
  secureNoteVaultItemFormSchema,
  creditCardVaultItemFormSchema
]);

export type VaultItemFormValues = z.infer<typeof vaultItemFormSchema>;

export type VaultItemPlaintextFields =
  | {
      type: "login";
      username: string;
      password: string;
      url: string;
    }
  | {
      type: "secure_note";
      note: string;
    }
  | {
      type: "credit_card";
      card_number: string;
      expiry: string;
      cvv: string;
      cardholder_name?: string;
    };

export function getVaultItemPlaintextFields(values: VaultItemFormValues): VaultItemPlaintextFields {
  if (values.type === "login") {
    return {
      type: "login",
      username: values.username,
      password: values.password,
      url: values.url
    };
  }

  if (values.type === "secure_note") {
    return {
      type: "secure_note",
      note: values.note
    };
  }

  return {
    type: "credit_card",
    card_number: values.card_number,
    expiry: values.expiry,
    cvv: values.cvv,
    cardholder_name: values.cardholder_name
  };
}

export function getDefaultVaultItemFormValues(): VaultItemFormValues {
  return {
    type: "login",
    name: "",
    folder_id: null,
    username: "",
    password: "",
    url: "https://"
  };
}

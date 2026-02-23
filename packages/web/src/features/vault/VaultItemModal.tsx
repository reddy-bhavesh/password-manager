import * as Dialog from "@radix-ui/react-dialog";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { ApiError } from "../../api/http";
import { zodResolver } from "../../lib/zodResolver";
import {
  createVaultItem,
  type VaultFolderTreeNode,
  type VaultItemRecord,
  type VaultItemWriteRequest,
  updateVaultItem
} from "./api";
import { decryptVaultItemFields, encryptVaultItemFields } from "./crypto";
import {
  getDefaultVaultItemFormValues,
  getVaultItemPlaintextFields,
  type VaultItemFormValues,
  vaultItemFormSchema
} from "./validation";

type VaultItemModalMode = "create" | "edit";

type VaultItemModalProps = {
  accessToken: string;
  open: boolean;
  mode: VaultItemModalMode;
  item: VaultItemRecord | null;
  folders: VaultFolderTreeNode[];
  onOpenChange: (open: boolean) => void;
  onSaved: (itemId: string) => void;
};

type PrefillState = {
  loading: boolean;
  warning: string | null;
};

type FolderOption = {
  id: string;
  label: string;
};

type VaultItemFormDraft = {
  type: VaultItemFormValues["type"];
  name: string;
  folder_id: string | null;
  username: string;
  password: string;
  url: string;
  note: string;
  card_number: string;
  expiry: string;
  cvv: string;
  cardholder_name: string;
};

const SUPPORTED_ITEM_TYPES = new Set(["login", "secure_note", "credit_card"]);

function flattenFolders(folders: VaultFolderTreeNode[], depth = 0): FolderOption[] {
  return folders.flatMap((folder) => [
    {
      id: folder.id,
      label: `${"  ".repeat(depth)}${folder.name}`
    },
    ...flattenFolders(folder.children, depth + 1)
  ]);
}

function getDefaultValuesForType(
  type: VaultItemFormValues["type"],
  base?: { name?: string; folder_id?: string | null }
): VaultItemFormDraft {
  if (type === "login") {
    return {
      type,
      name: base?.name ?? "",
      folder_id: base?.folder_id ?? null,
      username: "",
      password: "",
      url: "https://",
      note: "",
      card_number: "",
      expiry: "",
      cvv: "",
      cardholder_name: ""
    };
  }

  if (type === "secure_note") {
    return {
      type,
      name: base?.name ?? "",
      folder_id: base?.folder_id ?? null,
      username: "",
      password: "",
      url: "https://",
      note: "",
      card_number: "",
      expiry: "",
      cvv: "",
      cardholder_name: ""
    };
  }

  return {
    type,
    name: base?.name ?? "",
    folder_id: base?.folder_id ?? null,
    username: "",
    password: "",
    url: "https://",
    note: "",
    card_number: "",
    expiry: "",
    cvv: "",
    cardholder_name: ""
  };
}

function toWritePayload(values: VaultItemFormValues, encrypted: { encrypted_data: string; encrypted_key: string }): VaultItemWriteRequest {
  return {
    type: values.type,
    name: values.name,
    folder_id: values.folder_id,
    encrypted_data: encrypted.encrypted_data,
    encrypted_key: encrypted.encrypted_key
  };
}

function formatMutationError(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "Unable to save vault item.";
}

export function isSupportedEditableVaultItemType(type: string): type is VaultItemFormValues["type"] {
  return SUPPORTED_ITEM_TYPES.has(type);
}

function parseVaultItemFormDraft(values: VaultItemFormDraft): VaultItemFormValues {
  return vaultItemFormSchema.parse(values);
}

export function VaultItemModal({
  accessToken,
  open,
  mode,
  item,
  folders,
  onOpenChange,
  onSaved
}: VaultItemModalProps) {
  const queryClient = useQueryClient();
  const [prefillState, setPrefillState] = useState<PrefillState>({
    loading: false,
    warning: null
  });
  const [submitError, setSubmitError] = useState<string | null>(null);

  const folderOptions = useMemo(() => flattenFolders(folders), [folders]);

  const form = useForm<VaultItemFormDraft>({
    resolver: zodResolver(vaultItemFormSchema as never) as never,
    defaultValues: {
      ...getDefaultValuesForType("login"),
      ...getDefaultVaultItemFormValues()
    }
  });

  const selectedType = form.watch("type");
  const fieldErrors = form.formState.errors as Partial<Record<keyof VaultItemFormDraft, { message?: string }>>;

  const saveMutation = useMutation({
    mutationFn: async (values: VaultItemFormDraft) => {
      const parsedValues = parseVaultItemFormDraft(values);
      const encrypted = await encryptVaultItemFields(getVaultItemPlaintextFields(parsedValues));
      const payload = toWritePayload(parsedValues, encrypted);

      if (mode === "edit" && item) {
        const updated = await updateVaultItem(accessToken, item.id, payload);
        return updated.id;
      }

      const created = await createVaultItem(accessToken, payload);
      return created.id;
    },
    onSuccess: async (savedItemId) => {
      await queryClient.invalidateQueries({ queryKey: ["vault", "items"] });
      setSubmitError(null);
      onOpenChange(false);
      onSaved(savedItemId);
    },
    onError: (error) => {
      setSubmitError(formatMutationError(error));
    }
  });

  useEffect(() => {
    if (!open) {
      setSubmitError(null);
      setPrefillState({ loading: false, warning: null });
      return;
    }

    let active = true;
    setSubmitError(null);

    if (mode === "create") {
      form.reset({ ...getDefaultValuesForType("login"), ...getDefaultVaultItemFormValues() });
      setPrefillState({ loading: false, warning: null });
      return;
    }

    if (!item || !isSupportedEditableVaultItemType(item.type)) {
      setPrefillState({
        loading: false,
        warning: "This item type is not editable in this modal yet."
      });
      return;
    }

    const editableType = item.type;
    const base = { name: item.name, folder_id: item.folder_id };
    form.reset(getDefaultValuesForType(editableType, base));
    setPrefillState({ loading: true, warning: null });

    void (async () => {
      const decrypted = await decryptVaultItemFields({
        encrypted_data: item.encrypted_data,
        encrypted_key: item.encrypted_key
      });

      if (!active) {
        return;
      }

      if (!decrypted || decrypted.type !== editableType) {
        form.reset(getDefaultValuesForType(editableType, base));
        setPrefillState({
          loading: false,
          warning:
            "Could not decrypt existing fields for prefill in this browser session. Update fields and save to re-encrypt."
        });
        return;
      }

      if (decrypted.type === "login") {
        form.reset({
          type: "login",
          name: item.name,
          folder_id: item.folder_id,
          username: decrypted.username,
          password: decrypted.password,
          url: decrypted.url
        });
      } else if (decrypted.type === "secure_note") {
        form.reset({
          type: "secure_note",
          name: item.name,
          folder_id: item.folder_id,
          note: decrypted.note
        });
      } else {
        form.reset({
          type: "credit_card",
          name: item.name,
          folder_id: item.folder_id,
          card_number: decrypted.card_number,
          expiry: decrypted.expiry,
          cvv: decrypted.cvv,
          cardholder_name: decrypted.cardholder_name ?? ""
        });
      }

      setPrefillState({ loading: false, warning: null });
    })().catch(() => {
      if (!active) {
        return;
      }

      form.reset(getDefaultValuesForType(editableType, base));
      setPrefillState({
        loading: false,
        warning:
          "Could not decrypt existing fields for prefill in this browser session. Update fields and save to re-encrypt."
      });
    });

    return () => {
      active = false;
    };
  }, [form, item, mode, open]);

  function handleTypeChange(nextType: VaultItemFormValues["type"]) {
    const current = form.getValues();
    form.reset(getDefaultValuesForType(nextType, { name: current.name, folder_id: current.folder_id }));
    setPrefillState((state) => ({
      ...state,
      warning: state.warning && mode === "edit" ? state.warning : null
    }));
  }

  return (
    <Dialog.Root open={open} onOpenChange={(nextOpen) => (saveMutation.isPending ? undefined : onOpenChange(nextOpen))}>
      <Dialog.Portal>
        <Dialog.Overlay className="vault-dialog-overlay" />
        <Dialog.Content className="vault-dialog-content">
          <Dialog.Title className="vault-dialog-title">{mode === "edit" ? "Edit Vault Item" : "New Vault Item"}</Dialog.Title>
          <Dialog.Description className="vault-dialog-description">
            Encrypts item fields locally in the browser before sending ciphertext to the API.
          </Dialog.Description>

          {prefillState.warning ? <p className="inline-error">{prefillState.warning}</p> : null}
          {submitError ? <p className="inline-error">{submitError}</p> : null}

          <form
            className="auth-form vault-item-form"
            onSubmit={form.handleSubmit((values) => {
              setSubmitError(null);
              saveMutation.mutate(values);
            })}
          >
            <div className="form-section">
              <label className="form-field">
                <span>Item Name</span>
                <input
                  type="text"
                  autoComplete="off"
                  {...form.register("name")}
                  aria-invalid={fieldErrors.name ? "true" : "false"}
                  disabled={saveMutation.isPending}
                />
                {fieldErrors.name ? <span className="field-error">{fieldErrors.name.message}</span> : null}
              </label>

              <label className="form-field">
                <span>Type</span>
                <select
                  className="vault-select"
                  value={selectedType}
                  onChange={(event) => handleTypeChange(event.target.value as VaultItemFormValues["type"])}
                  disabled={saveMutation.isPending || (mode === "edit" && !!item)}
                >
                  <option value="login">Login</option>
                  <option value="secure_note">Secure Note</option>
                  <option value="credit_card">Credit Card</option>
                </select>
              </label>

              <label className="form-field">
                <span>Folder</span>
                <select
                  className="vault-select"
                  value={form.watch("folder_id") ?? ""}
                  onChange={(event) => form.setValue("folder_id", event.target.value || null, { shouldValidate: true })}
                  disabled={saveMutation.isPending}
                >
                  <option value="">Unfiled</option>
                  {folderOptions.map((folder) => (
                    <option key={folder.id} value={folder.id}>
                      {folder.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <div className="form-section vault-item-form-fields">
              {prefillState.loading ? <p className="vault-panel-state">Decrypting item fields for edit prefill...</p> : null}

              {selectedType === "login" ? (
                <>
                  <label className="form-field">
                    <span>Username</span>
                    <input
                      type="text"
                      autoComplete="username"
                      {...form.register("username")}
                      aria-invalid={fieldErrors.username ? "true" : "false"}
                      disabled={saveMutation.isPending}
                    />
                    {fieldErrors.username ? (
                      <span className="field-error">{String(fieldErrors.username.message ?? "")}</span>
                    ) : null}
                  </label>
                  <label className="form-field">
                    <span>Password</span>
                    <input
                      type="password"
                      autoComplete="new-password"
                      {...form.register("password")}
                      aria-invalid={fieldErrors.password ? "true" : "false"}
                      disabled={saveMutation.isPending}
                    />
                    {fieldErrors.password ? (
                      <span className="field-error">{String(fieldErrors.password.message ?? "")}</span>
                    ) : null}
                  </label>
                  <label className="form-field">
                    <span>URL</span>
                    <input
                      type="url"
                      inputMode="url"
                      autoComplete="url"
                      {...form.register("url")}
                      aria-invalid={fieldErrors.url ? "true" : "false"}
                      disabled={saveMutation.isPending}
                    />
                    {fieldErrors.url ? (
                      <span className="field-error">{String(fieldErrors.url.message ?? "")}</span>
                    ) : null}
                  </label>
                </>
              ) : null}

              {selectedType === "secure_note" ? (
                <label className="form-field">
                  <span>Note Text</span>
                  <textarea
                    className="vault-textarea"
                    rows={8}
                    {...form.register("note")}
                    aria-invalid={fieldErrors.note ? "true" : "false"}
                    disabled={saveMutation.isPending}
                  />
                  {fieldErrors.note ? (
                    <span className="field-error">{String(fieldErrors.note.message ?? "")}</span>
                  ) : null}
                </label>
              ) : null}

              {selectedType === "credit_card" ? (
                <>
                  <label className="form-field">
                    <span>Card Number</span>
                    <input
                      type="text"
                      inputMode="numeric"
                      autoComplete="cc-number"
                      placeholder="4111 1111 1111 1111"
                      {...form.register("card_number")}
                      aria-invalid={fieldErrors.card_number ? "true" : "false"}
                      disabled={saveMutation.isPending}
                    />
                    {fieldErrors.card_number ? (
                      <span className="field-error">{String(fieldErrors.card_number.message ?? "")}</span>
                    ) : null}
                  </label>
                  <div className="vault-form-grid-2">
                    <label className="form-field">
                      <span>Expiry (MM/YY)</span>
                      <input
                        type="text"
                        inputMode="numeric"
                        autoComplete="cc-exp"
                        placeholder="08/29"
                        {...form.register("expiry")}
                        aria-invalid={fieldErrors.expiry ? "true" : "false"}
                        disabled={saveMutation.isPending}
                      />
                      {fieldErrors.expiry ? (
                        <span className="field-error">{String(fieldErrors.expiry.message ?? "")}</span>
                      ) : null}
                    </label>
                    <label className="form-field">
                      <span>CVV</span>
                      <input
                        type="password"
                        inputMode="numeric"
                        autoComplete="cc-csc"
                        placeholder="123"
                        {...form.register("cvv")}
                        aria-invalid={fieldErrors.cvv ? "true" : "false"}
                        disabled={saveMutation.isPending}
                      />
                      {fieldErrors.cvv ? (
                        <span className="field-error">{String(fieldErrors.cvv.message ?? "")}</span>
                      ) : null}
                    </label>
                  </div>
                  <label className="form-field">
                    <span>Cardholder Name (optional)</span>
                    <input
                      type="text"
                      autoComplete="cc-name"
                      {...form.register("cardholder_name")}
                      disabled={saveMutation.isPending}
                    />
                  </label>
                </>
              ) : null}
            </div>

            <div className="vault-dialog-actions">
              <Dialog.Close asChild>
                <button type="button" className="btn btn-secondary" disabled={saveMutation.isPending}>
                  Cancel
                </button>
              </Dialog.Close>
              <button
                type="submit"
                className="btn btn-primary"
                disabled={saveMutation.isPending || prefillState.loading || (mode === "edit" && (!item || !isSupportedEditableVaultItemType(item.type)))}
              >
                {saveMutation.isPending ? "Saving..." : mode === "edit" ? "Save Changes" : "Create Item"}
              </button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

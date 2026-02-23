import sodium from "libsodium-wrappers-sumo";
import type { VaultItemPlaintextFields } from "./validation";

const SESSION_KEY_STORAGE_KEY = "vaultguard.vault.session-key.v1";
const DATA_PREFIX = "vg1d";
const KEY_PREFIX = "vg1k";

type SodiumModule = typeof sodium;

type VaultPlaintextEnvelope = {
  version: 1;
  type: VaultItemPlaintextFields["type"];
  fields: Record<string, string>;
};

export type EncryptedVaultFields = {
  encrypted_data: string;
  encrypted_key: string;
};

let sodiumReadyPromise: Promise<SodiumModule> | null = null;

async function getSodium(): Promise<SodiumModule> {
  if (!sodiumReadyPromise) {
    sodiumReadyPromise = sodium.ready.then(() => sodium);
  }

  return sodiumReadyPromise;
}

function isBrowserSessionStorageAvailable(): boolean {
  return typeof window !== "undefined" && typeof window.sessionStorage !== "undefined";
}

function encodeBox(sodiumLib: SodiumModule, prefix: string, nonce: Uint8Array, ciphertext: Uint8Array): string {
  return [
    prefix,
    sodiumLib.to_base64(nonce, sodiumLib.base64_variants.ORIGINAL),
    sodiumLib.to_base64(ciphertext, sodiumLib.base64_variants.ORIGINAL)
  ].join(":");
}

function decodeBox(sodiumLib: SodiumModule, encoded: string, expectedPrefix: string): { nonce: Uint8Array; ciphertext: Uint8Array } | null {
  const [prefix, nonceB64, ciphertextB64] = encoded.split(":");
  if (prefix !== expectedPrefix || !nonceB64 || !ciphertextB64) {
    return null;
  }

  try {
    return {
      nonce: sodiumLib.from_base64(nonceB64, sodiumLib.base64_variants.ORIGINAL),
      ciphertext: sodiumLib.from_base64(ciphertextB64, sodiumLib.base64_variants.ORIGINAL)
    };
  } catch {
    return null;
  }
}

async function getOrCreateSessionKey(sodiumLib: SodiumModule): Promise<Uint8Array> {
  if (!isBrowserSessionStorageAvailable()) {
    throw new Error("Browser session storage is unavailable for vault encryption.");
  }

  const existing = window.sessionStorage.getItem(SESSION_KEY_STORAGE_KEY);
  if (existing) {
    return sodiumLib.from_base64(existing, sodiumLib.base64_variants.ORIGINAL);
  }

  const sessionKey = sodiumLib.randombytes_buf(sodiumLib.crypto_secretbox_KEYBYTES);
  const encoded = sodiumLib.to_base64(sessionKey, sodiumLib.base64_variants.ORIGINAL);
  window.sessionStorage.setItem(SESSION_KEY_STORAGE_KEY, encoded);
  return sessionKey;
}

function toEnvelope(fields: VaultItemPlaintextFields): VaultPlaintextEnvelope {
  const base = { version: 1 as const, type: fields.type };

  if (fields.type === "login") {
    return {
      ...base,
      fields: {
        username: fields.username,
        password: fields.password,
        url: fields.url
      }
    };
  }

  if (fields.type === "secure_note") {
    return {
      ...base,
      fields: {
        note: fields.note
      }
    };
  }

  return {
    ...base,
    fields: {
      card_number: fields.card_number,
      expiry: fields.expiry,
      cvv: fields.cvv,
      cardholder_name: fields.cardholder_name ?? ""
    }
  };
}

function envelopeToFields(envelope: VaultPlaintextEnvelope): VaultItemPlaintextFields | null {
  if (envelope.version !== 1) {
    return null;
  }

  if (envelope.type === "login") {
    const { username, password, url } = envelope.fields;
    if (typeof username !== "string" || typeof password !== "string" || typeof url !== "string") {
      return null;
    }

    return { type: "login", username, password, url };
  }

  if (envelope.type === "secure_note") {
    const { note } = envelope.fields;
    if (typeof note !== "string") {
      return null;
    }

    return { type: "secure_note", note };
  }

  if (envelope.type === "credit_card") {
    const { card_number, expiry, cvv, cardholder_name } = envelope.fields;
    if (
      typeof card_number !== "string" ||
      typeof expiry !== "string" ||
      typeof cvv !== "string" ||
      (cardholder_name !== undefined && typeof cardholder_name !== "string")
    ) {
      return null;
    }

    return {
      type: "credit_card",
      card_number,
      expiry,
      cvv,
      cardholder_name
    };
  }

  return null;
}

export async function encryptVaultItemFields(
  fields: VaultItemPlaintextFields,
  options?: { sessionKey?: Uint8Array }
): Promise<EncryptedVaultFields> {
  const sodiumLib = await getSodium();
  const sessionKey = options?.sessionKey ?? (await getOrCreateSessionKey(sodiumLib));
  const itemKey = sodiumLib.randombytes_buf(sodiumLib.crypto_secretbox_KEYBYTES);

  const plaintext = sodiumLib.from_string(JSON.stringify(toEnvelope(fields)));
  const dataNonce = sodiumLib.randombytes_buf(sodiumLib.crypto_secretbox_NONCEBYTES);
  const dataCiphertext = sodiumLib.crypto_secretbox_easy(plaintext, dataNonce, itemKey);

  const keyNonce = sodiumLib.randombytes_buf(sodiumLib.crypto_secretbox_NONCEBYTES);
  const keyCiphertext = sodiumLib.crypto_secretbox_easy(itemKey, keyNonce, sessionKey);

  return {
    encrypted_data: encodeBox(sodiumLib, DATA_PREFIX, dataNonce, dataCiphertext),
    encrypted_key: encodeBox(sodiumLib, KEY_PREFIX, keyNonce, keyCiphertext)
  };
}

export async function decryptVaultItemFields(
  encrypted: EncryptedVaultFields,
  options?: { sessionKey?: Uint8Array }
): Promise<VaultItemPlaintextFields | null> {
  const sodiumLib = await getSodium();
  const sessionKey = options?.sessionKey ?? (await getOrCreateSessionKey(sodiumLib));

  const keyBox = decodeBox(sodiumLib, encrypted.encrypted_key, KEY_PREFIX);
  const dataBox = decodeBox(sodiumLib, encrypted.encrypted_data, DATA_PREFIX);
  if (!keyBox || !dataBox) {
    return null;
  }

  let itemKey: Uint8Array;
  let plaintextBytes: Uint8Array;
  try {
    itemKey = sodiumLib.crypto_secretbox_open_easy(keyBox.ciphertext, keyBox.nonce, sessionKey);
    plaintextBytes = sodiumLib.crypto_secretbox_open_easy(dataBox.ciphertext, dataBox.nonce, itemKey);
  } catch {
    return null;
  }

  try {
    const parsed = JSON.parse(sodiumLib.to_string(plaintextBytes)) as VaultPlaintextEnvelope;
    return envelopeToFields(parsed);
  } catch {
    return null;
  }
}

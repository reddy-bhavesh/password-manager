import sodium from "libsodium-wrappers-sumo";
import { describe, expect, it } from "vitest";
import { decryptVaultItemFields, encryptVaultItemFields } from "./crypto";

describe("vault item crypto", () => {
  it("round-trips login fields with libsodium secretbox encryption", async () => {
    await sodium.ready;
    const sessionKey = sodium.randombytes_buf(sodium.crypto_secretbox_KEYBYTES);

    const encrypted = await encryptVaultItemFields(
      {
        type: "login",
        username: "alex@example.com",
        password: "Sup3rS3cret!",
        url: "https://portal.example.com/login"
      },
      { sessionKey }
    );

    expect(encrypted.encrypted_data).toContain("vg1d:");
    expect(encrypted.encrypted_key).toContain("vg1k:");
    expect(encrypted.encrypted_data).not.toContain("Sup3rS3cret!");

    const decrypted = await decryptVaultItemFields(encrypted, { sessionKey });
    expect(decrypted).toEqual({
      type: "login",
      username: "alex@example.com",
      password: "Sup3rS3cret!",
      url: "https://portal.example.com/login"
    });
  });

  it("returns null when decrypting with the wrong session key", async () => {
    await sodium.ready;
    const goodKey = sodium.randombytes_buf(sodium.crypto_secretbox_KEYBYTES);
    const wrongKey = sodium.randombytes_buf(sodium.crypto_secretbox_KEYBYTES);

    const encrypted = await encryptVaultItemFields(
      {
        type: "secure_note",
        note: "Database root password rotated on Friday."
      },
      { sessionKey: goodKey }
    );

    await expect(decryptVaultItemFields(encrypted, { sessionKey: wrongKey })).resolves.toBeNull();
  });
});

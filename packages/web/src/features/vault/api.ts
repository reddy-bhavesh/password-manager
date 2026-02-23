import { getJson, postJson, putJson } from "../../api/http";

export type VaultFolderTreeNode = {
  id: string;
  name: string;
  parent_folder_id: string | null;
  created_at: string;
  children: VaultFolderTreeNode[];
};

export type VaultItemRecord = {
  id: string;
  owner_id: string;
  org_id: string;
  type: string;
  encrypted_data: string;
  encrypted_key: string;
  name: string;
  folder_id: string | null;
  favorite: boolean;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
};

export type VaultItemsPageResponse = {
  items: VaultItemRecord[];
  total: number;
  limit: number;
  offset: number;
};

export type VaultItemWriteRequest = {
  type: "login" | "secure_note" | "credit_card";
  encrypted_data: string;
  encrypted_key: string;
  name: string;
  folder_id: string | null;
};

export type VaultItemCreatedResponse = {
  id: string;
  type: string;
  name: string;
  created_at: string;
};

export async function fetchVaultFolders(accessToken: string, signal?: AbortSignal): Promise<VaultFolderTreeNode[]> {
  return getJson<VaultFolderTreeNode[]>("/api/v1/vault/folders", {
    accessToken,
    signal
  });
}

export async function fetchVaultItems(
  accessToken: string,
  signal?: AbortSignal,
  params?: { limit?: number; offset?: number }
): Promise<VaultItemsPageResponse> {
  const search = new URLSearchParams();

  if (params?.limit !== undefined) {
    search.set("limit", String(params.limit));
  }

  if (params?.offset !== undefined) {
    search.set("offset", String(params.offset));
  }

  const suffix = search.size > 0 ? `?${search.toString()}` : "";

  return getJson<VaultItemsPageResponse>(`/api/v1/vault${suffix}`, {
    accessToken,
    signal
  });
}

export async function createVaultItem(
  accessToken: string,
  payload: VaultItemWriteRequest,
  signal?: AbortSignal
): Promise<VaultItemCreatedResponse> {
  return postJson<VaultItemCreatedResponse, VaultItemWriteRequest>("/api/v1/vault/items", payload, {
    accessToken,
    signal
  });
}

export async function updateVaultItem(
  accessToken: string,
  itemId: string,
  payload: VaultItemWriteRequest,
  signal?: AbortSignal
): Promise<VaultItemRecord> {
  return putJson<VaultItemRecord, VaultItemWriteRequest>(`/api/v1/vault/items/${itemId}`, payload, {
    accessToken,
    signal
  });
}

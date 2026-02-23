import { Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { motion, useReducedMotion } from "framer-motion";
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { ApiError } from "../api/http";
import { useAuthStore } from "../features/auth/store";
import { fetchVaultFolders, fetchVaultItems, type VaultFolderTreeNode, type VaultItemRecord } from "../features/vault/api";
import { VaultItemModal, isSupportedEditableVaultItemType } from "../features/vault/VaultItemModal";

type VaultDashboardLayoutProps = {
  userName: string | null;
  mobileSidebarOpen: boolean;
  onToggleSidebar: () => void;
  onClearSession: () => void;
  sidebar: ReactNode;
  list: ReactNode;
  detail: ReactNode;
};

type PanelBodyProps = {
  title: string;
  actions?: ReactNode;
  children: ReactNode;
};

type PanelTone = "default" | "detail";

type PanelProps = {
  className?: string;
  tone?: PanelTone;
  children: ReactNode;
};

type SecretFieldKey = "encrypted_data" | "encrypted_key";

function mergeClassNames(...parts: Array<string | undefined | false>): string {
  return parts.filter(Boolean).join(" ");
}

function formatQueryError(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }

  if (error instanceof Error) {
    return error.message;
  }

  return "An unexpected error occurred.";
}

function formatDate(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(parsed);
}

function itemTypeLabel(type: string): string {
  return type
    .split("_")
    .map((segment) => segment.slice(0, 1).toUpperCase() + segment.slice(1))
    .join(" ");
}

function EyeOpenIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path
        d="M2.2 12c2.2-4 5.7-6.1 9.8-6.1s7.6 2.1 9.8 6.1c-2.2 4-5.7 6.1-9.8 6.1S4.4 16 2.2 12Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="12" cy="12" r="3.2" fill="none" stroke="currentColor" strokeWidth="1.7" />
    </svg>
  );
}

function EyeClosedIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path
        d="M3 3l18 18"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M10.6 6.2c.5-.1 1-.2 1.4-.2 4.1 0 7.6 2.1 9.8 6.1-.8 1.4-1.7 2.6-2.9 3.5M7.8 7.8C5.5 8.8 3.6 10.2 2.2 12c1.9 3.5 4.8 5.6 8.2 6.1m1.6 0c1.1-.1 2.2-.4 3.2-.8"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function CopyIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <rect x="9" y="9" width="10" height="10" rx="2" fill="none" stroke="currentColor" strokeWidth="1.7" />
      <path
        d="M6 15H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v1"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function Panel({ className, tone = "default", children }: PanelProps) {
  return <section className={mergeClassNames("vault-panel-card", `vault-panel-card--${tone}`, className)}>{children}</section>;
}

function PanelBody({ title, actions, children }: PanelBodyProps) {
  const reducedMotion = useReducedMotion();

  return (
    <motion.div
      className="vault-panel-body"
      initial={reducedMotion ? false : { opacity: 0, y: 10 }}
      animate={reducedMotion ? undefined : { opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: "easeOut" }}
    >
      <div className="vault-panel-heading">
        <h2>{title}</h2>
        {actions ? <div className="vault-panel-heading-actions">{actions}</div> : null}
      </div>
      {children}
    </motion.div>
  );
}

function FolderTreeNodeRow({
  node,
  depth,
  onSelectFolder
}: {
  node: VaultFolderTreeNode;
  depth: number;
  onSelectFolder: (folderId: string) => void;
}) {
  return (
    <li>
      <button
        type="button"
        className="vault-folder-row"
        style={{ paddingInlineStart: `${0.75 + depth * 0.95}rem` }}
        onClick={() => onSelectFolder(node.id)}
      >
        <span className="vault-folder-icon" aria-hidden="true">
          []
        </span>
        <span>{node.name}</span>
      </button>
      {node.children.length > 0 ? (
        <ul className="vault-folder-tree" role="list">
          {node.children.map((child) => (
            <FolderTreeNodeRow key={child.id} node={child} depth={depth + 1} onSelectFolder={onSelectFolder} />
          ))}
        </ul>
      ) : null}
    </li>
  );
}

function FolderSidebarContent({
  folders,
  isLoading,
  isError,
  errorMessage
}: {
  folders: VaultFolderTreeNode[];
  isLoading: boolean;
  isError: boolean;
  errorMessage: string | null;
}) {
  if (isLoading) {
    return <p className="vault-panel-state">Loading folders...</p>;
  }

  if (isError) {
    return <p className="vault-panel-state vault-panel-state--error">{errorMessage ?? "Failed to load folders."}</p>;
  }

  if (folders.length === 0) {
    return <p className="vault-panel-state">No folders yet.</p>;
  }

  return (
    <ul className="vault-folder-tree" role="list">
      {folders.map((node) => (
        <FolderTreeNodeRow key={node.id} node={node} depth={0} onSelectFolder={() => undefined} />
      ))}
    </ul>
  );
}

function VaultItemListContent({
  items,
  total,
  selectedItemId,
  onSelectItem,
  isLoading,
  isError,
  errorMessage
}: {
  items: VaultItemRecord[];
  total: number;
  selectedItemId: string | null;
  onSelectItem: (itemId: string) => void;
  isLoading: boolean;
  isError: boolean;
  errorMessage: string | null;
}) {
  if (isLoading) {
    return <p className="vault-panel-state">Loading vault items...</p>;
  }

  if (isError) {
    return <p className="vault-panel-state vault-panel-state--error">{errorMessage ?? "Failed to load vault items."}</p>;
  }

  if (items.length === 0) {
    return <p className="vault-panel-state">No items found.</p>;
  }

  return (
    <div className="vault-list-wrap">
      <div className="vault-list-meta">{total} item{total === 1 ? "" : "s"}</div>
      <ul className="vault-item-list" role="list">
        {items.map((item) => (
          <li key={item.id}>
            <button
              type="button"
              className="vault-item-row"
              data-active={item.id === selectedItemId}
              onClick={() => onSelectItem(item.id)}
            >
              <span className="vault-item-row-top">
                <strong>{item.name}</strong>
                {item.favorite ? (
                  <span className="vault-item-badge" aria-label="Favorite item">
                    *
                  </span>
                ) : null}
              </span>
              <span className="vault-item-row-meta">
                <span>{itemTypeLabel(item.type)}</span>
                <span>{formatDate(item.updated_at)}</span>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function VaultDetailContent({ item }: { item: VaultItemRecord | null }) {
  const [revealedFields, setRevealedFields] = useState<Record<SecretFieldKey, boolean>>({
    encrypted_data: false,
    encrypted_key: false
  });
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const toastTimerRef = useRef<number | null>(null);
  const clipboardClearTimerRef = useRef<number | null>(null);

  useEffect(() => {
    setRevealedFields({
      encrypted_data: false,
      encrypted_key: false
    });
  }, [item?.id]);

  useEffect(() => {
    return () => {
      if (toastTimerRef.current !== null) {
        window.clearTimeout(toastTimerRef.current);
      }
      if (clipboardClearTimerRef.current !== null) {
        window.clearTimeout(clipboardClearTimerRef.current);
      }
    };
  }, []);

  if (!item) {
    return <p className="vault-panel-state">Select an item to view details.</p>;
  }

  const maskedValue = "\u2022".repeat(8);

  function showToast(message: string) {
    setToastMessage(message);

    if (toastTimerRef.current !== null) {
      window.clearTimeout(toastTimerRef.current);
    }

    toastTimerRef.current = window.setTimeout(() => {
      setToastMessage(null);
      toastTimerRef.current = null;
    }, 2600);
  }

  function toggleSecretField(field: SecretFieldKey) {
    setRevealedFields((current) => ({
      ...current,
      [field]: !current[field]
    }));
  }

  async function copySecretValue(label: string, value: string) {
    if (!navigator?.clipboard?.writeText) {
      showToast("Clipboard is not available in this browser.");
      return;
    }

    try {
      await navigator.clipboard.writeText(value);
      showToast(`${label} copied. Clipboard clears in 30s.`);

      if (clipboardClearTimerRef.current !== null) {
        window.clearTimeout(clipboardClearTimerRef.current);
      }

      clipboardClearTimerRef.current = window.setTimeout(async () => {
        try {
          await navigator.clipboard.writeText("");
        } catch {
          // Ignore clipboard clear failures (permissions or browser policy).
        } finally {
          clipboardClearTimerRef.current = null;
        }
      }, 30_000);
    } catch {
      showToast(`Failed to copy ${label.toLowerCase()}.`);
    }
  }

  function SecretValueRow({
    label,
    field,
    value
  }: {
    label: string;
    field: SecretFieldKey;
    value: string;
  }) {
    const revealed = revealedFields[field];

    return (
      <div className="vault-secret-row">
        <dt>{label}</dt>
        <dd>
          <div className="vault-secret-card">
            <div className="vault-secret-actions">
              <button
                type="button"
                className="vault-icon-button"
                aria-label={revealed ? `Hide ${label}` : `Reveal ${label}`}
                aria-pressed={revealed}
                onClick={() => toggleSecretField(field)}
              >
                <span className="vault-icon-button__icon">{revealed ? <EyeOpenIcon /> : <EyeClosedIcon />}</span>
                <span>{revealed ? "Hide" : "Reveal"}</span>
              </button>
              <button
                type="button"
                className="vault-icon-button"
                aria-label={`Copy ${label}`}
                onClick={() => void copySecretValue(label, value)}
              >
                <span className="vault-icon-button__icon">
                  <CopyIcon />
                </span>
                <span>Copy</span>
              </button>
            </div>
            <code className="vault-secret-value" data-masked={!revealed}>
              {revealed ? value : maskedValue}
            </code>
          </div>
        </dd>
      </div>
    );
  }

  return (
    <div className="vault-detail">
      {toastMessage ? (
        <p className="vault-toast" role="status" aria-live="polite">
          {toastMessage}
        </p>
      ) : null}

      <div className="vault-detail-header">
        <p className="auth-kicker">Item Detail</p>
        <h3>{item.name}</h3>
        <p className="vault-detail-subtitle">
          {itemTypeLabel(item.type)} | Updated {formatDate(item.updated_at)}
        </p>
      </div>

      <dl className="kv-list vault-detail-kv">
        <div>
          <dt>Item ID</dt>
          <dd>{item.id}</dd>
        </div>
        <div>
          <dt>Folder ID</dt>
          <dd>{item.folder_id ?? "Unfiled"}</dd>
        </div>
        <div>
          <dt>Created</dt>
          <dd>{formatDate(item.created_at)}</dd>
        </div>
        <SecretValueRow label="Encrypted Data" field="encrypted_data" value={item.encrypted_data} />
        <SecretValueRow label="Encrypted Key" field="encrypted_key" value={item.encrypted_key} />
      </dl>
    </div>
  );
}

export function VaultDashboardLayout({
  userName,
  mobileSidebarOpen,
  onToggleSidebar,
  onClearSession,
  sidebar,
  list,
  detail
}: VaultDashboardLayoutProps) {
  return (
    <section
      className="vault-dashboard"
      data-sidebar-open={mobileSidebarOpen}
      aria-labelledby="vault-dashboard-title"
    >
      <header className="vault-dashboard-header">
        <div className="vault-dashboard-titleblock">
          <p className="auth-kicker">Vault</p>
          <h1 id="vault-dashboard-title">Credential dashboard</h1>
          <p className="vault-subtitle">
            {userName ? `Signed in as ${userName}.` : "Signed in session required."} Browse folders, inspect items, and
            review encrypted records.
          </p>
        </div>

        <div className="vault-dashboard-actions">
          <button
            type="button"
            className="btn btn-secondary vault-mobile-sidebar-toggle"
            onClick={onToggleSidebar}
            aria-expanded={mobileSidebarOpen}
            aria-controls="vault-sidebar-panel"
          >
            {mobileSidebarOpen ? "Hide sidebar" : "Show sidebar"}
          </button>
          <button type="button" className="btn btn-secondary" onClick={onClearSession}>
            Clear Session
          </button>
        </div>
      </header>

      <div className="vault-dashboard-grid">
        <Panel className="vault-sidebar-panel" tone="default">
          <div id="vault-sidebar-panel">{sidebar}</div>
        </Panel>
        <Panel className="vault-list-panel" tone="default">
          {list}
        </Panel>
        <Panel className="vault-detail-panel" tone="detail">
          {detail}
        </Panel>
      </div>
    </section>
  );
}

export function VaultPage() {
  const user = useAuthStore((state) => state.user);
  const accessToken = useAuthStore((state) => state.accessToken);
  const clearSession = useAuthStore((state) => state.clearSession);

  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null);
  const [itemModalOpen, setItemModalOpen] = useState(false);
  const [itemModalMode, setItemModalMode] = useState<"create" | "edit">("create");

  const foldersQuery = useQuery({
    queryKey: ["vault", "folders"],
    enabled: Boolean(accessToken),
    queryFn: ({ signal }) => fetchVaultFolders(accessToken as string, signal)
  });

  const itemsQuery = useQuery({
    queryKey: ["vault", "items", { limit: 100, offset: 0 }],
    enabled: Boolean(accessToken),
    queryFn: ({ signal }) => fetchVaultItems(accessToken as string, signal, { limit: 100, offset: 0 })
  });

  const items = itemsQuery.data?.items ?? [];
  const total = itemsQuery.data?.total ?? 0;

  useEffect(() => {
    if (items.length === 0) {
      setSelectedItemId(null);
      return;
    }

    const selectedStillExists = selectedItemId !== null && items.some((item) => item.id === selectedItemId);
    if (!selectedStillExists) {
      setSelectedItemId(items[0].id);
    }
  }, [items, selectedItemId]);

  const selectedItem = useMemo(
    () => (selectedItemId ? items.find((item) => item.id === selectedItemId) ?? null : null),
    [items, selectedItemId]
  );

  function openCreateItemModal() {
    setItemModalMode("create");
    setItemModalOpen(true);
  }

  function openEditItemModal() {
    if (!selectedItem || !isSupportedEditableVaultItemType(selectedItem.type)) {
      return;
    }

    setItemModalMode("edit");
    setItemModalOpen(true);
  }

  if (!accessToken) {
    return (
      <section className="vault-dashboard" aria-labelledby="vault-login-required-title">
        <header className="vault-dashboard-header">
          <div>
            <p className="auth-kicker">Vault</p>
            <h1 id="vault-login-required-title">Sign in required</h1>
            <p className="vault-subtitle">
              The vault dashboard fetches folders and items from protected endpoints. Sign in to continue.
            </p>
          </div>
          <Link to="/login" className="btn btn-primary">
            Go to Login
          </Link>
        </header>
      </section>
    );
  }

  return (
    <>
      <VaultDashboardLayout
        userName={user?.name ?? null}
        mobileSidebarOpen={mobileSidebarOpen}
        onToggleSidebar={() => setMobileSidebarOpen((open) => !open)}
        onClearSession={() => clearSession()}
        sidebar={
          <PanelBody title="Folders">
            <FolderSidebarContent
              folders={foldersQuery.data ?? []}
              isLoading={foldersQuery.isLoading}
              isError={foldersQuery.isError}
              errorMessage={foldersQuery.isError ? formatQueryError(foldersQuery.error) : null}
            />
          </PanelBody>
        }
        list={
          <PanelBody
            title="Items"
            actions={
              <button type="button" className="btn btn-primary btn-sm" onClick={openCreateItemModal}>
                New Item
              </button>
            }
          >
            <VaultItemListContent
              items={items}
              total={total}
              selectedItemId={selectedItemId}
              onSelectItem={(itemId) => {
                setSelectedItemId(itemId);
                setMobileSidebarOpen(false);
              }}
              isLoading={itemsQuery.isLoading}
              isError={itemsQuery.isError}
              errorMessage={itemsQuery.isError ? formatQueryError(itemsQuery.error) : null}
            />
          </PanelBody>
        }
        detail={
          <PanelBody
            title="Detail"
            actions={
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={openEditItemModal}
                disabled={!selectedItem || !isSupportedEditableVaultItemType(selectedItem.type)}
              >
                Edit
              </button>
            }
          >
            <VaultDetailContent item={selectedItem} />
          </PanelBody>
        }
      />

      <VaultItemModal
        accessToken={accessToken}
        open={itemModalOpen}
        mode={itemModalMode}
        item={itemModalMode === "edit" ? selectedItem : null}
        folders={foldersQuery.data ?? []}
        onOpenChange={setItemModalOpen}
        onSaved={(savedItemId) => {
          setSelectedItemId(savedItemId);
          setMobileSidebarOpen(false);
        }}
      />
    </>
  );
}

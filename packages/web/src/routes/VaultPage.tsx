import { Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { motion, useReducedMotion } from "framer-motion";
import { type ReactNode, useEffect, useMemo, useState } from "react";
import { ApiError } from "../api/http";
import { useAuthStore } from "../features/auth/store";
import { fetchVaultFolders, fetchVaultItems, type VaultFolderTreeNode, type VaultItemRecord } from "../features/vault/api";

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
  children: ReactNode;
};

type PanelTone = "default" | "detail";

type PanelProps = {
  className?: string;
  tone?: PanelTone;
  children: ReactNode;
};

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

function Panel({ className, tone = "default", children }: PanelProps) {
  return <section className={mergeClassNames("vault-panel-card", `vault-panel-card--${tone}`, className)}>{children}</section>;
}

function PanelBody({ title, children }: PanelBodyProps) {
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
  if (!item) {
    return <p className="vault-panel-state">Select an item to view details.</p>;
  }

  return (
    <div className="vault-detail">
      <div className="vault-detail-header">
        <p className="auth-kicker">Item Detail</p>
        <h3>{item.name}</h3>
        <p className="vault-detail-subtitle">
          {itemTypeLabel(item.type)} - Updated {formatDate(item.updated_at)}
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
        <div>
          <dt>Encrypted Data</dt>
          <dd className="vault-code-block">{item.encrypted_data}</dd>
        </div>
        <div>
          <dt>Encrypted Key</dt>
          <dd className="vault-code-block">{item.encrypted_key}</dd>
        </div>
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
        <PanelBody title="Items">
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
        <PanelBody title="Detail">
          <VaultDetailContent item={selectedItem} />
        </PanelBody>
      }
    />
  );
}

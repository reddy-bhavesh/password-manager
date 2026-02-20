# 🔐 VaultGuard — Enterprise Password Manager

### Product Design & Requirements Document (PDR)

**Version:** 1.0.0  
**Date:** February 20, 2026  
**Status:** Draft  
**Author:** [Organization Name]  
**Classification:** Internal — Confidential

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Product Vision & Goals](#2-product-vision--goals)
3. [Market Analysis](#3-market-analysis)
4. [Stakeholders](#4-stakeholders)
5. [User Personas](#5-user-personas)
6. [Functional Requirements](#6-functional-requirements)
7. [Non-Functional Requirements](#7-non-functional-requirements)
8. [System Architecture](#8-system-architecture)
9. [Security Design](#9-security-design)
10. [Data Model](#10-data-model)
11. [API Design](#11-api-design)
12. [UI/UX Design Principles](#12-uiux-design-principles)
13. [Feature Roadmap](#13-feature-roadmap)
14. [Technology Stack](#14-technology-stack)
    - 14.5 [Development Standards & Mandates](#145-development-standards--mandates)
15. [Compliance & Standards](#15-compliance--standards)
16. [Testing Strategy](#16-testing-strategy)
17. [Deployment Strategy](#17-deployment-strategy)
18. [Disaster Recovery & Business Continuity](#18-disaster-recovery--business-continuity)
19. [Pricing & Licensing Model](#19-pricing--licensing-model)
20. [Glossary](#20-glossary)

---

## 1. Executive Summary

**VaultGuard** is a fully self-hosted, enterprise-grade password management platform designed to give organizations complete sovereignty over their credentials and sensitive data. Unlike SaaS-based solutions (e.g., 1Password Teams, NordPass Business), VaultGuard operates entirely within the organization's own infrastructure — ensuring zero-knowledge encryption, no vendor lock-in, and full regulatory compliance.

The platform enables employees to securely store, share, and auto-fill passwords, API keys, secure notes, and identity documents across all devices and browsers. Administrators receive granular audit trails, RBAC (Role-Based Access Control), policy enforcement, and SSO integration.

### Key Differentiators

> [!IMPORTANT]
> **Development Standards Mandate:** All engineering, architecture, and security decisions throughout VaultGuard's development lifecycle **MUST** conform to **NIST Special Publications** (SP 800 series) and **OWASP Standards** (ASVS, MASVS, Top 10, Testing Guide, Cryptographic Standards). Adherence is non-negotiable and will be enforced via automated gates in the CI/CD pipeline, mandatory peer review checklists, and periodic third-party audits. See [Section 14.5 — Development Standards & Mandates](#145-development-standards--mandates) for full details.

| Feature                      | VaultGuard   | 1Password | NordPass | Bitwarden |
| ---------------------------- | ------------ | --------- | -------- | --------- |
| Fully Self-Hosted            | ✅           | ❌        | ❌       | ✅        |
| Zero-Knowledge Architecture  | ✅           | ✅        | ✅       | ✅        |
| Custom RBAC                  | ✅ Advanced  | ✅ Basic  | ✅ Basic | ✅ Basic  |
| On-Prem SSO (SAML/OIDC)      | ✅           | ✅        | ❌       | ✅        |
| Compliance-Ready (SOC2, ISO) | ✅           | ✅        | ✅       | Partial   |
| Built-in Secret Scanning     | ✅           | ❌        | ❌       | ❌        |
| Custom Vault Policies        | ✅           | Partial   | ❌       | Partial   |
| NIST + OWASP Full Compliance | ✅ Mandatory | Partial   | Partial  | Partial   |

---

## 2. Product Vision & Goals

### 2.1 Vision Statement

> _"Empower every employee across the organization to operate with maximum security and zero friction — ensuring that strong credentials are the path of least resistance."_

### 2.2 Strategic Goals

| Goal                                       | Success Metric                                                             |
| ------------------------------------------ | -------------------------------------------------------------------------- |
| Eliminate credential-related breaches      | 0 incidents traced to weak/reused passwords within 12 months of deployment |
| Achieve 90%+ employee adoption             | 90% of workforce actively using VaultGuard within 6 months                 |
| Reduce IT help desk password reset tickets | 70% reduction in password reset requests                                   |
| Enable seamless compliance auditing        | Full audit trail exportable within 5 minutes                               |
| Achieve sub-100ms vault unlock time        | P99 latency < 100ms on vault decryption                                    |

### 2.3 Non-Goals (Out of Scope for v1.0)

- Mobile application (iOS / Android) — VaultGuard is a **web-only** platform
- Hardware Security Module (HSM) key management (planned for v2.0)
- Privileged Access Management (PAM) / session recording
- Password broker integrations (CyberArk, Thycotic) in v1.0

---

## 3. Market Analysis

### 3.1 Problem Statement

Organizations of all sizes face an escalating credential security crisis:

- **80%** of data breaches involve compromised credentials _(Verizon DBIR 2024)_
- The average organization has **191 business passwords** per employee
- **57%** of employees reuse passwords across work and personal accounts
- Password reset tickets cost **$70 per incident** on average _(Gartner)_
- Compliance mandates (ISO 27001, SOC 2, GDPR, HIPAA) require demonstrable access controls

### 3.2 Competitive Landscape

**Tier 1 — Direct Competitors**

- **1Password Teams/Business**: Market leader; cloud-hosted; strong UX; high cost
- **Bitwarden**: Open-source; self-hostable; weaker enterprise UX; active community
- **NordPass Business**: Strong encryption; limited SSO; no self-hosting

**Tier 2 — Adjacent Competitors**

- **HashiCorp Vault**: Secrets management, not end-user focused
- **CyberArk**: PAM-focused; extremely expensive; overkill for most orgs
- **Keeper Security**: Strong enterprise; US-cloud only

### 3.3 Target Market

- **Primary**: Mid-to-large enterprises (200–10,000 employees) in regulated industries (Finance, Healthcare, Legal, Government)
- **Secondary**: Technology companies with compliance requirements
- **Geography**: Global — with on-prem data residency requirements (EU GDPR, India PDPB)

---

## 4. Stakeholders

| Role                      | Responsibilities                               | Priority |
| ------------------------- | ---------------------------------------------- | -------- |
| CISO / Security Team      | Define security policies, approve architecture | High     |
| IT Administrators         | Deploy, manage, provision users & groups       | High     |
| HR / People Ops           | Onboarding/offboarding integration             | Medium   |
| End Users (All Employees) | Daily credential storage & retrieval           | High     |
| Compliance / Legal        | Audit trail access, regulatory alignment       | High     |
| DevOps / Platform Team    | Deployment, infrastructure, monitoring         | Medium   |
| C-Suite / Finance         | Budget approval, ROI measurement               | Medium   |

---

## 5. User Personas

### 👤 Persona 1: Alex — The End User (Software Developer)

- **Age:** 28 | **Role:** Backend Engineer
- **Pain Points:** Has 200+ passwords; tired of resetting; doesn't trust sticky notes; needs fast CLI access
- **Goals:** Seamlessly access credentials in IDE, terminal, browser; share secrets with teammates safely
- **Key Features Needed:** Browser extension, CLI tool, team vault sharing, SSH key storage

---

### 👤 Persona 2: Priya — The IT Admin

- **Age:** 38 | **Role:** Senior IT Administrator
- **Pain Points:** No visibility into who has access to what; struggles with offboarding (revoking credentials); compliance audits take weeks
- **Goals:** Enforce password policies org-wide; instantly revoke access when employees leave; generate audit reports
- **Key Features Needed:** RBAC, audit logs, SSO, automated offboarding, policy enforcement

---

### 👤 Persona 3: James — The CISO

- **Age:** 52 | **Role:** Chief Information Security Officer
- **Pain Points:** Cannot demonstrate credential hygiene to auditors; concerned about cloud-vendor breaches; needs data residency guarantees
- **Goals:** Pass SOC 2 / ISO 27001 audits; ensure zero vendor access to org secrets; maintain full encryption key ownership
- **Key Features Needed:** Self-hosted deployment, encryption key management, compliance reporting, dark web monitoring

---

### 👤 Persona 4: Maria — The Non-Technical Employee

- **Age:** 45 | **Role:** HR Manager
- **Pain Points:** Overwhelmed by security tools; forgets master password; doesn't understand encryption
- **Goals:** Simple tool that works like magic; emergency access for shared accounts
- **Key Features Needed:** Simple browser extension, biometric unlock, emergency access, guided setup

---

## 6. Functional Requirements

### 6.1 Authentication & Access

| ID      | Requirement                                                                  | Priority |
| ------- | ---------------------------------------------------------------------------- | -------- |
| AUTH-01 | Users must authenticate with a Master Password (never transmitted or stored) | Critical |
| AUTH-02 | Support Multi-Factor Authentication: TOTP, WebAuthn (FIDO2), SMS (fallback)  | Critical |
| AUTH-03 | SAML 2.0 and OpenID Connect (OIDC) SSO integration                           | High     |
| AUTH-04 | Biometric unlock (Touch ID / Face ID / Windows Hello) on supported devices   | High     |
| AUTH-05 | Auto-lock vault after configurable idle timeout                              | Critical |
| AUTH-06 | Emergency Access with time-delayed approval workflow                         | Medium   |
| AUTH-07 | Session management with active device listing and remote kill                | High     |
| AUTH-08 | Passwordless authentication via hardware security key (YubiKey)              | Medium   |

### 6.2 Vault & Credential Management

| ID       | Requirement                                                                             | Priority |
| -------- | --------------------------------------------------------------------------------------- | -------- |
| VAULT-01 | Store unlimited passwords, secure notes, credit cards, identities, SSH keys, API tokens | Critical |
| VAULT-02 | Custom fields for each vault item (text, hidden, URL, file attachment)                  | High     |
| VAULT-03 | Organize items into nested folders and collections                                      | High     |
| VAULT-04 | Tag-based item labeling and advanced search                                             | Medium   |
| VAULT-05 | Soft-delete with configurable retention period (trash bin)                              | High     |
| VAULT-06 | Version history for each vault item (minimum 10 revisions)                              | High     |
| VAULT-07 | Favorite items for quick access                                                         | Low      |
| VAULT-08 | Bulk import from CSV, 1Password, LastPass, Bitwarden, Dashlane                          | High     |
| VAULT-09 | Secure export in encrypted JSON and CSV formats                                         | High     |
| VAULT-10 | File attachments per item (up to 100 MB per vault)                                      | Medium   |

### 6.3 Password Generator

| ID    | Requirement                                                                       | Priority |
| ----- | --------------------------------------------------------------------------------- | -------- |
| PG-01 | Configurable password generator: length, character sets, symbols, ambiguous chars | Critical |
| PG-02 | Passphrase generator with word list support (EFF word list)                       | High     |
| PG-03 | PIN generator for numeric-only requirements                                       | Medium   |
| PG-04 | One-click copy with auto-clear clipboard after configurable timeout               | High     |
| PG-05 | Remember last-used generator settings per user                                    | Low      |

### 6.4 Auto-fill & Browser Integration

| ID    | Requirement                                                      | Priority |
| ----- | ---------------------------------------------------------------- | -------- |
| BX-01 | Browser extensions for Chrome, Firefox, Edge, Safari, Brave      | Critical |
| BX-02 | Auto-detect login forms and suggest matching credentials         | Critical |
| BX-03 | Auto-fill on keyboard shortcut (configurable)                    | High     |
| BX-04 | Auto-save newly created/changed credentials                      | High     |
| BX-05 | Save and fill credit card, identity, and address forms           | High     |
| BX-06 | Phishing protection — warn when site URL doesn't match saved URI | Critical |
| BX-07 | Support for passkey (FIDO2 discoverable credential) storage      | Medium   |
| BX-08 | Inline menu for multi-account disambiguation                     | High     |

### 6.5 Team & Organization Management

| ID     | Requirement                                                               | Priority |
| ------ | ------------------------------------------------------------------------- | -------- |
| ORG-01 | Hierarchical organization structure: Org → Departments → Groups → Users   | Critical |
| ORG-02 | RBAC with predefined roles: Owner, Admin, Manager, Member, Viewer         | Critical |
| ORG-03 | Custom role creation with granular permission sets                        | High     |
| ORG-04 | Shared collections visible to selected groups                             | Critical |
| ORG-05 | Granular item-level sharing permissions (view, edit, share, delete)       | High     |
| ORG-06 | User invitation via email with magic link / SSO                           | Critical |
| ORG-07 | Automated provisioning and deprovisioning via SCIM 2.0                    | High     |
| ORG-08 | Guest/contractor accounts with limited vault access and time-based expiry | Medium   |
| ORG-09 | Bulk user operations: import, export, migrate                             | High     |

### 6.6 Security Controls & Policies

| ID     | Requirement                                                                 | Priority |
| ------ | --------------------------------------------------------------------------- | -------- |
| SEC-01 | Org-wide password strength policy enforcement (minimum entropy)             | Critical |
| SEC-02 | Breach detection: check against HaveIBeenPwned database (k-anonymity model) | Critical |
| SEC-03 | Reused password detection across personal and shared vaults                 | High     |
| SEC-04 | Weak password reporting dashboard for admins                                | High     |
| SEC-05 | Enforce MFA requirements for specific user groups                           | Critical |
| SEC-06 | IP allowlist / blocklist for vault access                                   | High     |
| SEC-07 | Device trust management with approved device registry                       | High     |
| SEC-08 | Configurable session timeout policies per group                             | High     |
| SEC-09 | Vault access time restrictions (e.g., business hours only)                  | Medium   |
| SEC-10 | Dormant account detection and automatic suspension                          | Medium   |

### 6.7 Audit & Compliance

| ID     | Requirement                                                                         | Priority |
| ------ | ----------------------------------------------------------------------------------- | -------- |
| AUD-01 | Immutable audit log for all actions: login, view, copy, edit, share, delete         | Critical |
| AUD-02 | Audit logs exportable as CSV, JSON, and SIEM-compatible formats (CEF, LEEF)         | High     |
| AUD-03 | Real-time SIEM integration (Splunk, Elastic, Microsoft Sentinel) via syslog/webhook | High     |
| AUD-04 | Admin dashboard with security health score                                          | High     |
| AUD-05 | Automated compliance reports for SOC 2, ISO 27001, GDPR, HIPAA                      | Medium   |
| AUD-06 | Failed login attempt detection and alerting                                         | Critical |
| AUD-07 | Activity alerts via email, Slack, Microsoft Teams                                   | High     |

### 6.8 Developer & CLI Features

| ID     | Requirement                                                            | Priority |
| ------ | ---------------------------------------------------------------------- | -------- |
| DEV-01 | REST API for programmatic vault access (with API token authentication) | High     |
| DEV-02 | CLI tool for macOS, Linux, Windows (`vaultguard` CLI)                  | High     |
| DEV-03 | SSH key agent integration (add, list, load SSH keys from vault)        | High     |
| DEV-04 | CI/CD integration via environment variable injection                   | High     |
| DEV-05 | Kubernetes secret sync (store K8s secrets in vault)                    | Medium   |
| DEV-06 | HashiCorp Vault secrets engine plugin                                  | Medium   |
| DEV-07 | Webhooks for credential rotation events                                | Medium   |

---

## 7. Non-Functional Requirements

### 7.1 Performance

| Metric                            | Target                           |
| --------------------------------- | -------------------------------- |
| Vault unlock (decryption) latency | < 100ms (P99)                    |
| API response time                 | < 200ms (P95), < 500ms (P99)     |
| Browser extension auto-fill       | < 300ms                          |
| Sync across devices               | < 3 seconds to propagate changes |
| Dashboard load time               | < 1.5 seconds                    |
| Concurrent active users           | 10,000+ without degradation      |

### 7.2 Availability & Reliability

| Metric                         | Target                                |
| ------------------------------ | ------------------------------------- |
| Uptime SLA                     | 99.9% (< 8.76 hrs/year downtime)      |
| RTO (Recovery Time Objective)  | < 1 hour                              |
| RPO (Recovery Point Objective) | < 5 minutes                           |
| Failover                       | Automatic with active-passive replica |

### 7.3 Scalability

- Horizontal scaling via containerized microservices (Kubernetes)
- Support up to 1,000,000 vault items per organization
- Database sharding strategy for > 100,000 users
- CDN-backed static assets and encrypted blob storage

### 7.4 Security (Non-Functional)

- Zero-knowledge architecture: server never sees plaintext passwords
- All data encrypted at rest (AES-256-GCM) and in transit (TLS 1.3)
- Memory-safe implementation for cryptographic operations
- Automated dependency vulnerability scanning (SBOM + CVE tracking)
- Penetration testing every 6 months by certified third party

### 7.5 Usability

- Onboarding completion rate target: > 85% without IT assistance
- Browser extension rated 4.5+ stars on Chrome Web Store
- Accessibility: WCAG 2.1 AA compliance across all web surfaces

---

## 8. System Architecture

### 8.1 High-Level Architecture

```
┌──────────────────────────────────────────────────────┐
│                    CLIENT LAYER                      │
│   ┌─────────────────┐      ┌──────────────────────┐  │
│   │   Web App       │      │   Browser Extension  │  │
│   │  (React/TS)     │      │   (MV3 / CRXJS)      │  │
│   └────────┬────────┘      └──────────┬───────────┘  │
└────────────┼─────────────────────────┼──────────────┘
             │      HTTPS/TLS 1.3 only │
┌────────────▼─────────────────────────▼──────────────┐
│                   API GATEWAY                        │
│     (Rate limiting, Auth validation, Routing)        │
└──────────────────────────┬──────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────┐
│                MICROSERVICES LAYER                   │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────┐  │
│  │  Auth        │  │  Vault       │  │  Org       │  │
│  │  Service     │  │  Service     │  │  Service   │  │
│  └──────────────┘  └──────────────┘  └────────────┘  │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────┐  │
│  │  Sync        │  │  Audit       │  │  Notif.    │  │
│  │  Service     │  │  Service     │  │  Service   │  │
│  └──────────────┘  └──────────────┘  └────────────┘  │
└─────────────────────────────────────────────────────┘
           │                    │                │
┌──────────▼──────┐  ┌──────────▼──────┐  ┌─────▼──────────────┐
│   MySQL DB      │  │  Redis Cache    │  │  Object Storage    │
│  (Encrypted)    │  │  (Sessions)     │  │  (Attachments)     │
└─────────────────┘  └─────────────────┘  └────────────────────┘
```

### 8.2 Zero-Knowledge Encryption Flow

```
Client Side (NEVER leaves device in plaintext)
──────────────────────────────────────────────
1. User enters Master Password
2. PBKDF2 (SHA-256, 600,000 iterations) → Stretched Master Key
3. HKDF(Stretched Master Key) → Encryption Key + MAC Key
4. AES-256-GCM encrypt vault data locally
5. Upload ONLY encrypted ciphertext to server

Server Side (Never sees plaintext)
───────────────────────────────────
• Stores only the encrypted blob + metadata
• Server authentication uses separate derived key (SRP or OPAQUE protocol)
• Master Password hash NEVER sent to server
```

### 8.3 Sync Architecture

- **Event-driven sync** using WebSocket connections for real-time updates
- **Conflict resolution**: Last-write-wins with vector clocks per vault item
- **Offline support**: Local IndexedDB cache in the browser with queue-based sync on reconnect
- **Delta sync**: Only changed items transmitted (not full vault on each sync)

---

## 9. Security Design

### 9.1 Cryptographic Specifications

| Parameter                 | Algorithm / Specification                                 |
| ------------------------- | --------------------------------------------------------- |
| Master Key Derivation     | Argon2id (memory: 64MB, iterations: 3, parallelism: 4)    |
| Symmetric Encryption      | AES-256-GCM (authenticated encryption)                    |
| Asymmetric Keys (sharing) | X25519 (key agreement) + XSalsa20-Poly1305                |
| Key Wrapping              | AES-KW (RFC 3394)                                         |
| Password Hashing (auth)   | OPAQUE protocol (asymmetric PAKE)                         |
| TLS                       | TLS 1.3 only; TLS 1.2 disabled                            |
| Token Signing             | RS256 (JWT) with 2048-bit RSA keys, rotated every 30 days |
| TOTP                      | RFC 6238 compliant, SHA-1/SHA-256                         |

### 9.2 Secure Sharing Protocol

When sharing vault items between users:

1. Each user has an asymmetric key pair (X25519)
2. Public keys are stored server-side and signed by the org admin
3. Sender encrypts item with a random DEK (Data Encryption Key)
4. DEK is encrypted with recipient's public key
5. Recipient decrypts DEK, uses it to decrypt item
6. Server never sees DEK or item plaintext

### 9.3 Threat Model

| Threat                 | Mitigation                                                            |
| ---------------------- | --------------------------------------------------------------------- |
| Server compromise      | Zero-knowledge: server has only ciphertext                            |
| Network interception   | TLS 1.3 + HSTS + CORS strict-origin; CSP headers on all web responses |
| Brute force login      | OPAQUE protocol + rate limiting + account lockout                     |
| Phishing               | Phishing-resistant WebAuthn MFA + URL verification on auto-fill       |
| Insider threat (admin) | Audit logs + admin cannot decrypt user vaults                         |
| Memory scraping        | Sensitive values cleared from memory immediately after use            |
| Supply chain attack    | SBOM tracking + dependency pinning + reproducible builds              |
| Credential stuffing    | Breach detection + anomalous login detection via ML                   |

### 9.4 Secret Scanner (Built-in)

VaultGuard includes an optional **Secret Scanning Engine** that:

- Monitors configured code repositories (GitHub, GitLab, Azure DevOps)
- Detects accidentally committed credentials using regex + ML patterns
- Automatically alerts the credential owner and admin
- Provides one-click credential rotation initiation

---

## 10. Data Model

### 10.1 Core Entities (ERD Overview)

```
Organization
 ├── id (UUID)
 ├── name
 ├── subscription_tier
 ├── created_at
 └── settings (JSON)

User
 ├── id (UUID)
 ├── org_id (FK → Organization)
 ├── email
 ├── name
 ├── role (enum: owner, admin, manager, member, viewer)
 ├── status (enum: active, suspended, invited)
 ├── public_key (X25519)
 ├── encrypted_private_key
 ├── master_password_hint (optional)
 ├── mfa_enabled
 └── created_at

VaultItem
 ├── id (UUID)
 ├── owner_id (FK → User)
 ├── org_id (FK → Organization)
 ├── type (enum: login, note, card, identity, ssh_key, api_token, file)
 ├── encrypted_data (blob — AES-256-GCM ciphertext)
 ├── encrypted_key (blob — DEK wrapped with owner's public key)
 ├── name (plaintext metadata for search indexing)
 ├── folder_id (FK → Folder, nullable)
 ├── favorite (bool)
 ├── created_at
 ├── updated_at
 └── deleted_at (soft delete)

VaultItemRevision
 ├── id (UUID)
 ├── item_id (FK → VaultItem)
 ├── encrypted_data (blob)
 ├── encrypted_key (blob)
 ├── revision_number
 └── created_at

Collection (shared vault)
 ├── id (UUID)
 ├── org_id (FK → Organization)
 ├── name
 ├── created_by (FK → User)
 └── created_at

CollectionMember
 ├── collection_id (FK → Collection)
 ├── user_or_group_id
 └── permission (enum: view, edit, share, manage)

AuditLog
 ├── id (UUID)
 ├── org_id (FK → Organization)
 ├── actor_id (FK → User)
 ├── action (enum: login, view_item, edit_item, delete_item, share_item, ...)
 ├── target_id (nullable)
 ├── ip_address
 ├── user_agent
 ├── geo_location
 └── timestamp (immutable)
```

---

## 11. API Design

### 11.1 API Standards

- **Protocol**: REST over HTTPS (TLS 1.3)
- **Format**: JSON request/response bodies
- **Authentication**: Bearer JWT (access token: 15-min TTL) + Refresh Token (7-day TTL, rotated)
- **Versioning**: URI-based (`/api/v1/`, `/api/v2/`)
- **Rate Limiting**: 1000 req/min per user; 10,000 req/min per org
- **Error Format**: RFC 7807 (Problem Details for HTTP APIs)

### 11.2 Core API Endpoints

#### Authentication

```
POST   /api/v1/auth/preauth        → Get KDF parameters for user
POST   /api/v1/auth/login          → Authenticate, receive tokens
POST   /api/v1/auth/refresh        → Rotate refresh token
POST   /api/v1/auth/logout         → Revoke tokens
POST   /api/v1/auth/mfa/verify     → Complete MFA challenge
DELETE /api/v1/auth/sessions/{id}  → Revoke specific session
```

#### Vault

```
GET    /api/v1/vault               → Get full encrypted vault sync
GET    /api/v1/vault/sync?since=   → Delta sync since timestamp
POST   /api/v1/vault/items         → Create vault item
GET    /api/v1/vault/items/{id}    → Get single item (audit logged)
PUT    /api/v1/vault/items/{id}    → Update vault item
DELETE /api/v1/vault/items/{id}    → Soft delete item
GET    /api/v1/vault/items/{id}/history → Get revision history
POST   /api/v1/vault/items/{id}/restore → Restore revision
```

#### Organization

```
GET    /api/v1/org                 → Get org details
GET    /api/v1/org/users           → List users
POST   /api/v1/org/users/invite    → Invite user
DELETE /api/v1/org/users/{id}      → Offboard user
PATCH  /api/v1/org/users/{id}/role → Change user role
GET    /api/v1/org/groups          → List groups
POST   /api/v1/org/groups          → Create group
POST   /api/v1/org/collections     → Create shared collection
```

#### Audit

```
GET    /api/v1/audit/logs          → Query audit logs (paginated)
GET    /api/v1/audit/logs/export   → Export logs (CSV/JSON)
GET    /api/v1/audit/reports/security → Security health report
```

### 11.3 Webhook Events

```json
{
  "event": "vault_item.created",
  "timestamp": "2026-02-20T09:00:00Z",
  "org_id": "uuid",
  "actor": { "id": "uuid", "email": "user@org.com" },
  "payload": { "item_id": "uuid", "item_type": "login" }
}
```

**Supported Events:** `user.invited`, `user.offboarded`, `vault_item.created`, `vault_item.updated`, `vault_item.deleted`, `vault_item.shared`, `login.success`, `login.failed`, `mfa.disabled`, `policy.violated`

---

## 12. UI/UX Design Principles

### 12.1 Design Philosophy

VaultGuard's interface follows the principle of **"Security through Simplicity"** — powerful protection should feel effortless.

- **Clarity over Complexity**: Always show users what they need, hide what they don't
- **Friction where it matters**: Deliberate confirmation dialogs only for destructive/sensitive actions
- **Trust signals**: Encryption status, breach alerts, and security scores surfaced prominently
- **Progressive disclosure**: Advanced settings hidden by default; available on demand

### 12.2 Design System

| Token         | Value                                                         |
| ------------- | ------------------------------------------------------------- |
| Primary Color | `#1A1F36` (Deep Navy)                                         |
| Accent Color  | `#6C63FF` (Electric Violet)                                   |
| Success Color | `#0FB76B` (Emerald)                                           |
| Danger Color  | `#FF4D4D` (Alert Red)                                         |
| Typography    | Inter (UI), JetBrains Mono (secrets)                          |
| Border Radius | 8px (default), 16px (cards), 50% (avatars)                    |
| Animations    | Framer Motion, 200ms easing, respect `prefers-reduced-motion` |

### 12.3 Key Screens

| Screen                      | Description                                                                    |
| --------------------------- | ------------------------------------------------------------------------------ |
| **Onboarding**              | 4-step guided setup: Master Password → MFA → Browser Extension → First Import  |
| **Vault Dashboard**         | 3-panel layout: sidebar (folders/collections), item list, item detail          |
| **Item Detail**             | Encrypted fields shown as `••••••`, reveal on hover/click; inline copy buttons |
| **Security Dashboard**      | Weak passwords count, breached passwords, reused passwords, overall score      |
| **Admin Panel**             | User management table, policy settings, audit log viewer, SCIM/SSO config      |
| **Browser Extension Popup** | 320x480px popup with search, matching credentials, generator                   |

### 12.4 Accessibility

- WCAG 2.1 AA compliant
- Full keyboard navigation (Ctrl+K command palette)
- Screen reader compatible (ARIA labels on all interactive elements)
- High-contrast mode support
- Minimum 4.5:1 contrast ratio for all text

---

## 13. Feature Roadmap

### 🏁 Phase 1 — MVP (Months 1–4)

- [ ] Core zero-knowledge vault with AES-256-GCM encryption
- [ ] Master Password + TOTP MFA
- [ ] Web application (React + TypeScript)
- [ ] Chrome & Firefox browser extensions
- [ ] Password generator (configurable)
- [ ] Basic organization management (users, basic roles)
- [ ] Auto-fill (login forms)
- [ ] Audit logging (view, edit, delete)
- [ ] Import from CSV, 1Password, Bitwarden
- [ ] Self-hosted Docker deployment

### 🚀 Phase 2 — Enterprise (Months 5–8)

- [ ] SSO: SAML 2.0 + OIDC
- [ ] SCIM 2.0 provisioning
- [ ] Advanced RBAC & custom roles
- [ ] Shared collections (team vaults)
- [ ] Security dashboard (breach detection, weak/reused passwords)
- [ ] SIEM integration (Splunk, Elastic)
- [ ] WebAuthn / FIDO2 hardware key support
- [ ] Vault item version history
- [ ] CLI tool (`vaultguard`)
- [ ] IP allowlist / device trust
- [ ] Kubernetes Helm chart for deployment

### 🔮 Phase 3 — Advanced (Months 9–12)

- [ ] Secret scanning (GitHub, GitLab, Azure DevOps)
- [ ] Passkey (discoverable credential) support
- [ ] Emergency access workflow
- [ ] API token / SSH key storage
- [ ] CI/CD secret injection (GitHub Actions, Azure Pipelines)
- [ ] Automated compliance report generation
- [ ] HSM key management support
- [ ] Edge/Safari browser extensions
- [ ] Dark web monitoring integration
- [ ] Credential rotation automation

### 🔬 Phase 4 — Intelligence (Year 2)

- [ ] ML-based anomaly detection (unusual access patterns)
- [ ] AI-powered password strength suggestions
- [ ] Automated just-in-time access provisioning
- [ ] Privileged Access Management (PAM) module
- [ ] Marketplace for third-party integrations

---

## 14. Technology Stack

### 14.1 Backend

| Layer          | Technology                | Rationale                                           |
| -------------- | ------------------------- | --------------------------------------------------- |
| Language       | **Go 1.22+**              | Memory safety, performance, concurrency             |
| Web Framework  | **Gin**                   | Fast HTTP, minimal overhead                         |
| Database       | **MySQL 8.0**             | ACID compliance, JSON column support, wide adoption |
| Cache          | **Redis 7**               | Session storage, rate limiting                      |
| Message Queue  | **NATS JetStream**        | Lightweight, fast pub/sub for sync events           |
| Object Storage | **MinIO** (S3-compatible) | Self-hosted file attachments                        |
| Search         | **Meilisearch**           | Typo-tolerant item search                           |
| Migrations     | **golang-migrate**        | Version-controlled schema migrations                |
| ORM            | **sqlc**                  | Type-safe SQL, no magic                             |

### 14.2 Frontend

| Layer            | Technology                          | Rationale                             |
| ---------------- | ----------------------------------- | ------------------------------------- |
| Framework        | **React 19 + TypeScript**           | Mature ecosystem, type safety         |
| Build Tool       | **Vite 6**                          | Fast HMR, optimized bundling          |
| State Management | **Zustand**                         | Simple, scalable state                |
| Cryptography     | **libsodium.js (WASM)**             | Audited, WASM-based crypto in browser |
| UI Components    | **Radix UI + custom design system** | Accessible primitives                 |
| Animations       | **Framer Motion**                   | Smooth, production-grade animations   |
| Forms            | **React Hook Form + Zod**           | Performant, type-safe validation      |
| HTTP Client      | **TanStack Query**                  | Cache, sync, refetch logic            |
| Routing          | **TanStack Router**                 | Type-safe routing                     |

### 14.3 Browser Extension

| Component     | Technology                               |
| ------------- | ---------------------------------------- |
| Manifest      | Manifest V3                              |
| Build         | Vite + CRXJS                             |
| Shared Code   | Monorepo (Turborepo) shared with web app |
| Communication | Chrome/WebExtension message passing API  |

### 14.4 Infrastructure

| Component                | Technology                                                     |
| ------------------------ | -------------------------------------------------------------- |
| Containerization         | Docker + Docker Compose (dev)                                  |
| Orchestration            | Kubernetes + Helm charts                                       |
| Service Mesh             | Istio (mTLS between microservices)                             |
| Ingress                  | NGINX Ingress Controller                                       |
| Cert Management          | cert-manager (Let's Encrypt / internal CA)                     |
| Observability            | Prometheus + Grafana + Loki                                    |
| Tracing                  | OpenTelemetry + Jaeger                                         |
| CI/CD                    | GitHub Actions / Azure DevOps Pipelines                        |
| Secrets (Infrastructure) | HashiCorp Vault (for infrastructure secrets, not user secrets) |

---

### 14.5 Development Standards & Mandates

> [!IMPORTANT]
> Compliance with the following standards is **mandatory for every engineer, architect, and security reviewer** working on VaultGuard. These are not optional guidelines — they are enforced through automated tooling, PR checklists, and auditor review.

#### 🛡️ OWASP Standards (Mandatory)

| Standard                                    | Scope                          | Enforcement                                              |
| ------------------------------------------- | ------------------------------ | -------------------------------------------------------- |
| **OWASP Top 10 (2021)**                     | All web components             | SAST scan must show 0 Top-10 findings before merge       |
| **OWASP ASVS Level 3**                      | Backend API, Auth, Crypto      | ASVS checklist required in every security-critical PR    |
| **OWASP Testing Guide (OTG)**               | QA & penetration testing       | All test cases must be documented against OTG categories |
| **OWASP Cryptographic Storage Cheat Sheet** | Any data-at-rest               | Crypto primitives must be reviewed against this guide    |
| **OWASP Secure Coding Practices**           | All languages (Go, TypeScript) | Included in onboarding and enforced in code review       |
| **OWASP Dependency-Check**                  | All third-party libraries      | Run in CI pipeline; HIGH/CRITICAL CVEs block merge       |
| **OWASP ZAP (DAST)**                        | Staging environment            | Automated DAST scan on every release candidate           |

#### 🏛️ NIST Standards (Mandatory)

| Standard                                   | Scope                        | Key Requirements                                                    |
| ------------------------------------------ | ---------------------------- | ------------------------------------------------------------------- |
| **NIST SP 800-63B**                        | Authentication & Identity    | Password policies, MFA requirements, authenticator assurance levels |
| **NIST SP 800-57**                         | Cryptographic Key Management | Key lifecycle, algorithm selection, key length minimums             |
| **NIST SP 800-132**                        | Password Hashing (PBKDF)     | KDF algorithm selection, iteration count minimums                   |
| **NIST SP 800-52 Rev. 2**                  | TLS Configuration            | TLS 1.3 required; TLS 1.2 only with approved cipher suites          |
| **NIST SP 800-53 Rev. 5**                  | Security & Privacy Controls  | Control baseline for all system components                          |
| **NIST SP 800-61**                         | Incident Response            | Incident classification, escalation, and reporting playbooks        |
| **NIST SP 800-92**                         | Log Management               | Audit log format, retention, and protection requirements            |
| **NIST SP 800-171**                        | Protecting CUI               | Required for government/federal customer deployments                |
| **NIST Cybersecurity Framework (CSF 2.0)** | Org-wide security posture    | Govern, Identify, Protect, Detect, Respond, Recover domains         |
| **NIST SP 800-190**                        | Container Security           | Docker/Kubernetes hardening, image scanning, runtime security       |

#### ⚙️ Enforcement Mechanisms

```
Developer Workflow Gates
────────────────────────────────────────────────────────
1. Pre-commit hooks     → Secret detection (gitleaks), lint, format
2. PR checks           → SAST (CodeQL + Semgrep with OWASP ruleset)
3. CI Build Gate       → Dependency CVE scan (OWASP Dependency-Check)
4. Staging Deploy Gate → DAST scan (OWASP ZAP automated baseline)
5. Release Gate        → Manual ASVS checklist sign-off by Security Lead
6. Quarterly Review    → Internal audit against NIST SP 800-53 controls
7. Annual Review       → Third-party penetration test + NIST CSF maturity assessment
```

#### 📋 Developer Responsibility Checklist

Every feature PR **must** include confirmation that:

- [ ] Input validation follows OWASP Input Validation Cheat Sheet
- [ ] No sensitive data logged (OWASP Logging Cheat Sheet)
- [ ] Authentication changes reviewed against NIST SP 800-63B
- [ ] Any cryptographic code reviewed against NIST SP 800-57
- [ ] Error messages do not leak internal state (OWASP Error Handling)
- [ ] New dependencies scanned and approved (OWASP Dependency-Check)
- [ ] SQL/NoSQL queries are parameterized (OWASP SQL Injection prevention)
- [ ] Authorization checks applied at both API gateway and service layer

---

## 15. Compliance & Standards

### 15.1 Regulatory Compliance

| Standard           | Applicability        | Key Controls                                            |
| ------------------ | -------------------- | ------------------------------------------------------- |
| **SOC 2 Type II**  | All tiers            | Access control, audit logging, availability, encryption |
| **ISO 27001**      | Enterprise tier      | ISMS policies, risk management, incident response       |
| **GDPR / UK GDPR** | EU data subjects     | Data minimization, right to erasure, DPA agreements     |
| **HIPAA**          | Healthcare customers | PHI protection, BAA agreements, audit controls          |
| **India PDPB**     | Indian customers     | Data localization, consent management                   |
| **NIST CSF**       | Government customers | Identify, Protect, Detect, Respond, Recover framework   |

### 15.2 Security & Development Standards

> [!NOTE]
> All standards listed below are **mandatory baselines** for development, not aspirational targets. See [Section 14.5](#145-development-standards--mandates) for full enforcement details.

**OWASP Standards**

- **OWASP Top 10 (2021)** — Zero tolerance for Top-10 class vulnerabilities in production
- **OWASP ASVS Level 3** — Highest verification level applied to all security-sensitive modules
- **OWASP Testing Guide (OTG)** — All QA test plans mapped to OTG test case IDs
- **OWASP Dependency-Check** — Automated in CI; HIGH/CRITICAL findings block release
- **OWASP ZAP** — DAST on every staging deployment

**NIST Standards**

- **NIST SP 800-63B** — Authentication, identity, and credential management policies
- **NIST SP 800-57** — Cryptographic key management throughout the key lifecycle
- **NIST SP 800-53 Rev. 5** — Security and privacy controls for all system components
- **NIST SP 800-61** — Incident response procedures and playbooks
- **NIST SP 800-92** — Audit log management, format, and retention
- **NIST SP 800-190** — Container security hardening (Docker + Kubernetes)
- **NIST Cybersecurity Framework (CSF 2.0)** — Organization-wide security posture
- **NIST SP 800-171** — Required for federal/government customer deployments

**Infrastructure Security**

- **CIS Benchmarks** — Docker and Kubernetes hardening baselines (Level 2)
- **FIPS 140-3** — FIPS-compliant cryptographic module option for government deployments

### 15.3 Certifications Roadmap

| Phase   | Certification    | Target Date |
| ------- | ---------------- | ----------- |
| Phase 2 | SOC 2 Type I     | Month 9     |
| Phase 3 | SOC 2 Type II    | Month 15    |
| Phase 3 | ISO 27001        | Month 18    |
| Phase 4 | FedRAMP Moderate | Month 24    |

---

## 16. Testing Strategy

### 16.1 Testing Pyramid

```
         ▲
        /█\           E2E Tests (5%)
       /███\          Playwright — critical user journeys
      /█████\
     /███████\        Integration Tests (20%)
    /█████████\       API contract tests, DB integration
   /███████████\
  /█████████████\     Unit Tests (75%)
 /███████████████\    Each service, crypto functions, validators
/─────────────────\
```

### 16.2 Test Requirements

| Type                | Target Coverage           | Tooling                                 |
| ------------------- | ------------------------- | --------------------------------------- |
| Unit Tests          | > 80% line coverage       | Go: `testing` + `testify`; TS: `Vitest` |
| Integration Tests   | All API endpoints         | `httptest` (Go), `supertest` (Node)     |
| E2E Tests           | 20 critical user journeys | Playwright                              |
| Security Tests      | DAST on every release     | OWASP ZAP automated scan                |
| Cryptography Tests  | 100% of crypto functions  | Known-answer tests (KATs)               |
| Performance Tests   | P95 < SLA thresholds      | k6 load testing                         |
| Accessibility Tests | WCAG 2.1 AA               | axe-core + manual screen reader         |

### 16.3 Security Testing

- **SAST**: Semgrep + CodeQL on every PR
- **DAST**: OWASP ZAP on staging post-deploy
- **Dependency Scanning**: Dependabot + `govulncheck` + `npm audit`
- **Container Scanning**: Trivy on all Docker images
- **Penetration Testing**: External firm every 6 months
- **Bug Bounty Program**: Private program via HackerOne (Phase 3)

---

## 17. Deployment Strategy

### 17.1 Self-Hosted Deployment Options

#### Option A: Docker Compose (Small Teams, < 100 users)

```yaml
# Quickstart: 5-minute setup
docker compose -f vaultguard-compose.yml up -d
# Includes: API server, Web app, MySQL, Redis, MinIO
```

#### Option B: Kubernetes / Helm (Enterprise, 100+ users)

```bash
helm repo add vaultguard https://charts.vaultguard.io
helm install vaultguard vaultguard/vaultguard \
  --namespace vaultguard \
  --values custom-values.yaml
```

#### Option C: Managed by Organization's Platform Team

- Custom IaC (Terraform / Pulumi modules provided)
- Supports: AWS EKS, Azure AKS, GCP GKE, on-premises Kubernetes

### 17.2 Update Strategy

- **Zero-downtime rolling updates** via Kubernetes rolling deployment
- **Blue/green deployment** support for major version upgrades
- **Database migrations**: Backward-compatible, run pre-deployment
- **Client updates**: Browser extensions auto-update via store; clients check for updates on launch

### 17.3 Environment Strategy

| Environment | Purpose                | Data                      |
| ----------- | ---------------------- | ------------------------- |
| Development | Active development     | Synthetic data only       |
| Staging     | Pre-release validation | Anonymized prod-like data |
| Production  | Live system            | Real encrypted vault data |

---

## 18. Disaster Recovery & Business Continuity

### 18.1 Backup Strategy

| Data Type                    | Frequency  | Retention          | Method                                  |
| ---------------------------- | ---------- | ------------------ | --------------------------------------- |
| MySQL (full backup)          | Daily      | 30 days            | `mysqldump` → S3/MinIO (encrypted)      |
| MySQL (binary log streaming) | Continuous | 7 days             | MySQL binlog replication to hot-standby |
| Object Storage (files)       | Nightly    | 90 days            | MinIO bucket replication                |
| Audit Logs                   | Real-time  | 1 year (immutable) | Write-once S3 bucket                    |
| Configuration                | On change  | 90 days            | Git-backed config repo                  |

### 18.2 Recovery Procedures

- **Database failure**: Automatic failover to hot-standby replica (< 30 seconds)
- **Full site disaster**: Restore from backup to secondary region (RTO < 1 hour)
- **Ransomware scenario**: Immutable backups in isolated storage; point-in-time recovery

### 18.3 Incident Response

| Severity      | Response Time | Examples                               |
| ------------- | ------------- | -------------------------------------- |
| P0 — Critical | 15 minutes    | Data breach, total outage              |
| P1 — High     | 1 hour        | Partial outage, authentication failure |
| P2 — Medium   | 4 hours       | Degraded performance, sync failures    |
| P3 — Low      | 24 hours      | UI bugs, non-critical feature issues   |

---

## 19. Pricing & Licensing Model

> _(For internal chargeback/cost-center model or future external commercialization)_

### 19.1 Tier Structure

| Tier           | Users     | Key Features                                               | Suggested Monthly Cost |
| -------------- | --------- | ---------------------------------------------------------- | ---------------------- |
| **Starter**    | Up to 10  | Core vault, basic MFA, browser extension                   | Free (self-hosted)     |
| **Team**       | Up to 50  | + Shared collections, basic RBAC, audit log                | $4/user/month          |
| **Business**   | Up to 500 | + SSO, SCIM, advanced RBAC, SIEM integration               | $8/user/month          |
| **Enterprise** | Unlimited | + All features, SLA, dedicated support, compliance reports | Custom                 |

### 19.2 Licensing

- **Open Core Model**: Core vault engine open-source (MIT License) on GitHub
- **Enterprise Features**: Proprietary add-ons distributed under commercial license
- **Self-Hosted**: Perpetual license per deployment; annual maintenance fee
- **Source Code Escrow**: Available for enterprise customers (business continuity protection)

---

## 20. Glossary

| Term               | Definition                                                                                |
| ------------------ | ----------------------------------------------------------------------------------------- |
| **AES-256-GCM**    | Advanced Encryption Standard, 256-bit key, Galois/Counter Mode — authenticated encryption |
| **Argon2id**       | Memory-hard password hashing algorithm recommended by OWASP                               |
| **DEK**            | Data Encryption Key — symmetric key used to encrypt a specific vault item                 |
| **FIDO2/WebAuthn** | W3C standard for hardware-based, phishing-resistant authentication                        |
| **HKDF**           | HMAC-based Key Derivation Function — derives multiple keys from one master key            |
| **KDF**            | Key Derivation Function — derives cryptographic keys from a password                      |
| **Zero-Knowledge** | Architecture where the service provider cannot access user data in plaintext              |
| **OPAQUE**         | Asymmetric Password-Authenticated Key Exchange — prevents password exposure during auth   |
| **PBKDF2**         | Password-Based Key Derivation Function 2 — strengthens passwords against brute force      |
| **RBAC**           | Role-Based Access Control — permissions assigned via roles, not per-user                  |
| **SAML 2.0**       | Security Assertion Markup Language — XML-based SSO federation protocol                    |
| **SCIM 2.0**       | System for Cross-domain Identity Management — automated user provisioning                 |
| **SIEM**           | Security Information and Event Management — security monitoring platform                  |
| **SRP**            | Secure Remote Password — password authentication without exposing the password            |
| **Binlog**         | MySQL Binary Log — used for replication and point-in-time recovery                        |
| **X25519**         | Elliptic-curve Diffie-Hellman key exchange using Curve25519                               |

---

## Appendix A — Security Review Checklist

- [ ] Cryptographic primitives reviewed by qualified cryptographer
- [ ] Penetration test completed by certified third-party firm
- [ ] OWASP ASVS Level 3 self-assessment passed
- [ ] Data flow diagram (DFD) reviewed for all trust boundaries
- [ ] Threat model documented and reviewed
- [ ] All secrets removed from codebase (git history clean)
- [ ] Dependency CVE scan — zero critical/high unresolved
- [ ] TLS configuration validated (SSL Labs A+ rating)
- [ ] CSP, HSTS, X-Frame-Options, CORS headers configured

## Appendix B — References

1. OWASP Password Storage Cheat Sheet — https://cheatsheetseries.owasp.org
2. NIST SP 800-63B — Digital Identity Guidelines
3. RFC 9106 — Argon2 Memory-Hard Function
4. Bitwarden Security White Paper — https://bitwarden.com/images/resources/security-white-paper.pdf
5. 1Password Security Design — https://1password.com/files/1Password-White-Paper.pdf
6. Verizon DBIR 2024 — Data Breach Investigations Report

---

_Document maintained in version control. For updates, submit PR to `docs/pdr/` branch._  
_Questions? Contact Security Team: security@[organization].com_

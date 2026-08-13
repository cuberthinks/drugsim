# TDS §7 — Security Architecture

---

## 7.1 Threat Model

DrugSim's security posture is shaped by one fact that distinguishes it from most SaaS:

> **A molecular structure uploaded by a customer is that customer's most commercially sensitive asset.**

A novel compound structure represents years of research and, before filing, its disclosure can destroy patentability. A pharmaceutical company evaluating DrugSim will assess this before it assesses prediction accuracy — and correctly so.

| Asset | Sensitivity | Primary threat |
|---|---|---|
| **Customer structures** | **Critical — trade secret, pre-patent** | Cross-tenant leakage; log exposure; use in training; insider access |
| Customer prediction results | High | Reveals research direction |
| Audit trail | High (regulatory) | Tampering, gaps |
| Model artefacts | Medium | Theft of trained models |
| Public reference data | Low | Integrity only |
| Credentials, keys | Critical | Standard |

| Threat actor | Concern |
|---|---|
| Competitor of a customer | Cross-tenant access to structures |
| External attacker | Data exfiltration, ransomware |
| **Malicious upload** | Chemical file parsers as an attack surface (§7.7) |
| Insider / operator | Access to customer structures without business need |
| Supply chain | Compromised dependency or base image |

---

## 7.2 Customer IP Protection

The controls that follow exist because §7.1 makes this the defining requirement, not a generic one.

### 7.2.1 Tenant isolation
- `tenant_id` on every customer-owned row; **never accepted from the client**, always derived from the authenticated credential
- **PostgreSQL row-level security** as the enforcement layer, not application `WHERE` clauses. An application-layer filter is one forgotten predicate away from a breach; an RLS policy fails closed
- Cross-tenant access returns **404, not 403** — a 403 confirms existence, which is itself a disclosure (§5.3)
- Automated cross-tenant probes on every tenant-scoped endpoint are a required CI check (§5.9)

### 7.2.2 Structures are never used for training
**Policy, contractual commitment, and technical control.** Training-set selection queries the public-data partition only; a customer compound is structurally excluded because training queries filter on `source_id` values from the registry, and customer uploads carry a tenant source that is never in that set.

Any future opt-in data-sharing programme would require explicit written consent per tenant and a separate, clearly partitioned data path. It is out of scope and should be treated as a product decision with legal review, not an engineering toggle.

### 7.2.3 Structures never appear in logs
Covered in §3.10; restated here because it is a security control, not an operational preference. A SMILES string in an exception message is an IP disclosure into a system with different access controls, different retention, and typically wider fan-out than the database.

Five layers, of which the last is the one that actually holds: pattern-based redaction filter · reference by `compound_uid` only · payload scrubbing in exception handlers · lint rule on structure-bearing variables in log calls · **CI test asserting a request with a known structure produces no log line containing it**.

### 7.2.4 Evidence must not leak across tenants
Nearest-neighbour evidence (§4.3.4) is drawn **exclusively from public reference data**. Returning another tenant's compound as a similar structure would disclose both its existence and its structure — a severe and non-obvious leak, and one that a naive similarity search over all rows would produce by default.

### 7.2.5 Operator access
Production database access requires a documented business justification, is time-boxed, and is logged. Support tooling shows `compound_uid` and computed properties by default; structure display requires an explicit, audited elevation. Bulk export of customer structures is not available through any operational tool.

---

## 7.3 Authentication

**Keycloak, OIDC** (§3.5). No homegrown authentication.

| Control | Requirement | Basis |
|---|---|---|
| Unique accounts | One identity per person; **no shared accounts** | Part 11 §11.10(d) |
| MFA | Required for `reviewer`, `admin`, `curator`; available to all | Part 11 §11.300 |
| Password policy | Length, complexity, history, ageing | Part 11 §11.300(b) |
| Lockout | After N failed attempts; alert on repetition | Part 11 §11.300(d) |
| Session | Idle and absolute timeouts; revocation on role change | — |
| **Re-authentication for signing** | MFA challenge at signature, even in an active session | Part 11 §11.200 |
| API keys | Scoped, expiring, revocable, hashed at rest, shown once | — |
| Federation | SAML/OIDC to customer IdP | Enterprise requirement |

**Shared accounts are prohibited, technically and contractually.** Under Part 11 an electronic signature must be attributable to one individual; a shared login makes every signature in the system unattributable and voids the audit trail's evidentiary value.

---

## 7.4 Authorisation

Two enforcement layers, deliberately redundant:

1. **Application layer** — role checks at the endpoint boundary
2. **Database layer** — RLS policies on `tenant_id`

The redundancy is the point. An application bug that omits a check is caught by RLS; an RLS misconfiguration is caught by the application. Neither alone is sufficient for data of this sensitivity.

| Resource class | Rule |
|---|---|
| Public reference (models, datasets, endpoints, proteins) | Any authenticated user |
| Tenant-owned (compounds, predictions, experiments) | Same tenant only, RLS-enforced |
| Validation records, QMRF | `reviewer`+ |
| Signing | `reviewer` + `can_sign` + MFA |
| User administration | `admin`, own tenant only |

---

## 7.5 Encryption

| Layer | Control |
|---|---|
| In transit, external | TLS 1.3 minimum; HSTS; modern ciphers only |
| In transit, internal | mTLS between services where the network is not fully trusted |
| At rest, database | Full-disk/volume encryption; column-level encryption evaluated for structures (§7.5.1) |
| At rest, object storage | SSE-KMS or MinIO encryption |
| Backups | Encrypted; keys managed separately from backup storage |
| Key management | External KMS; rotation policy; no keys in application config |

### 7.5.1 On column-level encryption of structures
Considered and **not adopted for Phase 2**, with the reasoning recorded because it will be asked again.

Encrypting SMILES columns would break the RDKit cartridge entirely — substructure and similarity search operate on the `mol` and `bfp` types and cannot function over ciphertext. The capability loss is total, and searchable-encryption schemes that preserve similarity leak enough to undermine the protection.

The chosen posture is **volume encryption plus strict access control plus RLS plus audit**, which addresses the realistic threats (stolen disk, compromised backup, cross-tenant bug) without disabling the platform's core function. If a customer contractually requires structure-level encryption at rest, the correct answer is a **single-tenant deployment** with a dedicated database, not a degraded shared one — and that should be a priced product tier, not a retrofit.

---

## 7.6 Secrets Management

- No secrets in the repository, images, or environment files committed to git
- External secret manager (Vault, AWS Secrets Manager, or equivalent) injected at runtime
- Distinct credentials per environment; production secrets inaccessible from non-production
- Rotation policy with documented intervals; rotation is exercised, not merely documented
- `gitleaks` in pre-commit **and** CI — pre-commit is bypassable, CI is not
- Any leaked credential is rotated immediately and treated as an incident regardless of apparent exposure

---

## 7.7 Input Validation — Chemical Files as an Attack Surface

This is the least conventional security concern in the system and the most likely to be underestimated.

DrugSim accepts SDF, MOL and SMILES from users and parses them with RDKit — a large C++ library processing untrusted, structurally complex input. That is a classic memory-safety attack surface, and SDF in particular is an unbounded, record-structured format that invites resource exhaustion.

| Vector | Control |
|---|---|
| Oversized upload | 100 MB cap enforced by streaming; **compressed uploads rejected** (zip-bomb surface) |
| Excessive record count | ≤ 10,000, counted by streaming |
| Pathological single record | ≤ 100 KB per record |
| Parser hang / catastrophic backtracking | 5 s hard timeout per record |
| Memory exhaustion | Parsing in a **sandboxed subprocess** with `rlimit`; OOM kills the child, not the worker |
| Memory-safety exploit in RDKit | Subprocess isolation; non-root, read-only filesystem, dropped capabilities, seccomp profile |
| Malicious property fields | Length-capped; treated as opaque text; **never evaluated, interpolated, or rendered as HTML** |
| Encoding attacks | UTF-8 only; null bytes and control characters rejected |
| Filename attacks | Original filenames never used for storage paths; generated identifiers only |

**Parsing untrusted structures in the API process is prohibited.** It happens in an isolated subprocess whose crash is a handled error, not an outage. This is defence in depth against a class of bug we cannot audit away in a large third-party C++ codebase.

Standard web validation applies additionally: parameterised queries throughout (no string-built SQL), output encoding, strict CORS, CSP on the frontend, and request size limits at the edge.

---

## 7.8 Rate Limiting & Abuse

| Scope | Limit (initial) |
|---|---|
| Per tenant, prediction jobs | Quota per hour, plan-dependent |
| Per tenant, API requests | Token bucket, burst-tolerant |
| Per IP, unauthenticated | Strict — `/health` and auth endpoints only |
| Batch uploads | Concurrency cap per tenant |
| Substructure search | Statement timeout + `422 query-too-broad` |

`429` with `Retry-After`. Sustained abuse alerts rather than silently degrading.

**A specific abuse case worth naming:** systematic similarity search could be used to probe whether a particular structure exists in the corpus. Because search is scoped to public data by default and never crosses tenants, this cannot reveal another customer's compounds — but the search scope default is a security control, not merely a convenience, and should not be relaxed without review.

---

## 7.9 Audit Logging

Implemented in the Core DB (Phase 1 Step 3 §3.4). Security-relevant properties:

- **Append-only.** `UPDATE` and `DELETE` revoked at the database level, not by convention
- Records old **and** new values, actor, timestamp, and **reason** (`change_reason NOT NULL`)
- Monthly range partitions; retention per the compliance policy
- Covers data mutations, authentication events, authorisation failures, signatures, exports, and privileged access
- **Audit failure blocks the operation.** If the audit write fails, the transaction fails — an unaudited change is worse than a rejected one

Audit records are included in backups and their continuity is verified at G7 (Phase 1 Step 2 addendum §3.3).

---

## 7.10 Supply Chain Security

| Control | Implementation |
|---|---|
| Dependency pinning | `uv.lock` committed; exact versions, hash-verified |
| Vulnerability scanning | `pip-audit`/`osv-scanner` in CI; fails on high/critical |
| SBOM | CycloneDX generated per build, retained per release |
| Base images | Digest-pinned, not tag-pinned; rebuilt and rescanned on a schedule |
| Image scanning | Trivy or equivalent in CI |
| Provenance | Signed images (cosign); deployment verifies signatures |
| Licence compliance | Dependency licences checked in CI alongside the data licence audit |
| Update policy | Security patches expedited; feature updates batched and reviewed |

**The `postgres-rdkit` image is the highest-value supply-chain target** — it is custom, it runs the database, and its RDKit version participates in `toolchain_id`. It is built from a pinned Dockerfile in-repo, scanned, signed, and changed only through change control. Pulling a community image with a cartridge pre-installed would be faster and is explicitly rejected.

---

## 7.11 Incident Response

| Phase | Action |
|---|---|
| Detect | Alerting on auth anomalies, cross-tenant attempts, unusual export volume, audit gaps |
| Contain | Credential revocation, tenant isolation, service disable |
| Assess | Audit log reconstructs scope: who accessed what, when |
| Notify | **Customer notification for any incident touching customer structures**, regardless of exfiltration certainty |
| Remediate | Fix, rotate, verify |
| Review | Blameless post-incident review; controls updated |

**The notification threshold is deliberately low for structure exposure.** For pre-patent chemical matter, a customer needs to know about *possible* disclosure to make their own filing and legal decisions — waiting for certainty removes their ability to act. This should be written into customer agreements rather than decided during an incident.

---

*End §7.*

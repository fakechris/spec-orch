# Linear API Surface Used by SpecOrch

This document exhaustively lists every Linear API interaction made by
spec-orch.  Its purpose is to serve as the **compatibility contract** for
a future self-hosted, Linear-compatible project management backend.

Any replacement system must implement the GraphQL operations, entities,
fields, and filter semantics described below.

---

## 1. Transport

| Property | Value |
|----------|-------|
| Protocol | HTTPS POST |
| Endpoint | `https://api.linear.app/graphql` |
| Auth | `Authorization: <token>` header (no `Bearer` prefix) |
| Content-Type | `application/json` |
| Client library | `httpx.Client` (Python) |
| Timeout | 30 s |

The entire API surface is a single GraphQL endpoint.  No REST endpoints,
webhooks, or CLI tools from Linear are used.

---

## 2. Entities and Fields

### 2.1 Issue

The primary entity.  SpecOrch reads and writes Issues.

**Fields read:**

| Field | Type | Used by |
|-------|------|---------|
| `id` | `ID!` | All write operations (mutations reference UUID) |
| `identifier` | `String!` | Human-readable key (e.g. `SON-42`), used for matching and display |
| `title` | `String!` | PR title generation, display |
| `description` | `String` | Spec content extraction, readiness checking, mission detection |
| `state.name` | `String!` | Workflow state filtering and display |
| `labels.nodes[].name` | `String!` | Label-based filtering and triage logic |
| `assignee.name` | `String` | Display |
| `assignee.email` | `String` | Display |
| `children.nodes[].id` | `ID` | Parent-issue exclusion filter |

**Fields written (via `issueUpdate` / `issueCreate`):**

| Field | Type | Used by |
|-------|------|---------|
| `teamId` | `ID!` | Issue creation |
| `title` | `String!` | Issue creation |
| `description` | `String` | Issue creation |
| `stateId` | `ID!` | Workflow state transitions |
| `labelIds` | `[ID!]!` | Adding / removing labels |
| `parentId` | `ID` | Setting parent issue (promotion) |

### 2.2 Comment

Used for daemon-to-user communication and conversation adapters.

**Fields read:**

| Field | Type | Used by |
|-------|------|---------|
| `id` | `ID!` | Tracking already-seen comments |
| `body` | `String!` | Content parsing |
| `createdAt` | `DateTime!` | Ordering, new-comment detection |
| `user.id` | `ID!` | Distinguishing bot vs human replies |
| `user.name` | `String` | Display |
| `user.email` | `String` | Display |

**Fields written:**

| Field | Type | Used by |
|-------|------|---------|
| `issueId` | `ID!` | Target issue for comment |
| `body` | `String!` | Comment content |

### 2.3 Team

Read-only.  Used for issue creation and configuration validation.

| Field | Type | Used by |
|-------|------|---------|
| `id` | `ID!` | Required for `issueCreate` |
| `key` | `String!` | Team identifier (e.g. `SON`) |
| `name` | `String!` | Display during config check |
| `states.nodes[].id` | `ID!` | State ID resolution |
| `states.nodes[].name` | `String!` | State name matching |

### 2.4 WorkflowState

Read-only.  Resolved by name to obtain the UUID for state transitions.

| Field | Type | Used by |
|-------|------|---------|
| `id` | `ID!` | Used in `issueUpdate` stateId |
| `name` | `String!` | Human-readable state matching |

**States actively used by spec-orch:**

| State name | Usage |
|------------|-------|
| `Backlog` | Default for new issues |
| `Ready` | Daemon poll target; daemon resets issues here after review-loop |
| `In Progress` | Set when daemon claims an issue |
| `In Review` | Set after PR creation |
| `Done` | Set after merge (or by Linear-GitHub App) |
| `Canceled` | Recognised as terminal state |

### 2.5 IssueLabel

Read-only for resolution; write via `labelIds` on Issue.

| Field | Type | Used by |
|-------|------|---------|
| `id` | `ID!` | Label ID for `issueUpdate` |
| `name` | `String!` | Human-readable label matching |

**Labels actively used by spec-orch:**

| Label | Purpose |
|-------|---------|
| `task` | Marks executable work packets |
| `epic` | Marks parent feature issues |
| `spec` | Marks spec-related issues |
| `needs-clarification` | Daemon triage: blocks execution until user responds |
| `blocked` | Daemon exclusion filter |
| `agent-ready` | Legacy readiness signal (no longer required) |
| `Feature` / `Bug` / `Improvement` | Classification labels |
| `spec-orch` | Conversation adapter watch label |

### 2.6 User

Read-only.  Accessed through Issue.assignee and Comment.user.

| Field | Type | Used by |
|-------|------|---------|
| `id` | `ID!` | Bot vs human comment distinction |
| `name` | `String` | Display |
| `email` | `String` | Display |
| `isMe` | `Boolean` | Filter: `assignee.isMe` |

---

## 3. GraphQL Operations

### 3.1 Queries (Read)

#### Q1: Get single issue

```graphql
query($id: String!) {
  issue(id: $id) {
    id
    identifier
    title
    description
    state { name }
    labels { nodes { name } }
    assignee { name email }
  }
}
```

**Callers:** `LinearClient.get_issue()`, `add_label()`, `remove_label()`

---

#### Q2: List issues with filters

```graphql
query($first: Int!, $teamKey: String!, $filterState: String!) {
  issues(
    filter: {
      and: [
        { team: { key: { eq: $teamKey } } }
        { state: { name: { eq: $filterState } } }
        { assignee: { isMe: { eq: true } } }
        { labels: { some: { name: { in: ["task"] } } } }
        { labels: { every: { name: { nin: ["blocked", "needs-clarification"] } } } }
      ]
    }
    first: $first
  ) {
    nodes {
      id identifier title description
      state { name }
      labels { nodes { name } }
      assignee { name email }
      children { nodes { id } }
    }
  }
}
```

The filter parts are dynamically assembled.  Required filter capabilities:

| Filter | Semantics |
|--------|-----------|
| `team.key.eq` | Exact match on team key |
| `state.name.eq` | Exact match on state name |
| `assignee.isMe.eq` | Current authenticated user |
| `labels.some.name.in` | Issue has at least one label whose name is in the list |
| `labels.every.name.nin` | No label on the issue has a name in the exclusion list |
| `and: [...]` | All filter parts must match |

**Callers:** `LinearClient.list_issues()`, daemon poll, conversation adapter,
promotion service

---

#### Q3: List comments on an issue

```graphql
query($issueId: String!, $first: Int!) {
  issue(id: $issueId) {
    comments(first: $first, orderBy: createdAt) {
      nodes {
        id
        body
        createdAt
        user { id name email }
      }
    }
  }
}
```

**Callers:** `LinearClient.list_comments()`, daemon clarification reply
detection, conversation adapter polling

---

#### Q4: Resolve team by key

```graphql
query($key: String!) {
  teams(filter: { key: { eq: $key } }) {
    nodes { id }
  }
}
```

**Callers:** `LinearClient.create_issue()` (resolves team key → UUID)

---

#### Q5: Resolve workflow states for a team (via issue)

```graphql
query($issueId: String!) {
  issue(id: $issueId) {
    team {
      states { nodes { id name } }
    }
  }
}
```

**Callers:** `LinearClient.resolve_state_id()`

---

#### Q6: List all teams with states (config check)

```graphql
query {
  teams {
    nodes {
      key
      name
      states { nodes { name } }
    }
  }
}
```

**Callers:** `ConfigChecker.check_linear()` — validates team key and states
exist

---

#### Q7: Resolve label by name

```graphql
query($name: String!) {
  issueLabels(filter: { name: { eq: $name } }) {
    nodes { id name }
  }
}
```

**Callers:** `LinearClient._resolve_label_id()`

---

### 3.2 Mutations (Write)

#### M1: Create issue

```graphql
mutation($teamId: String!, $title: String!, $description: String) {
  issueCreate(input: {
    teamId: $teamId
    title: $title
    description: $description
  }) {
    success
    issue { id identifier title }
  }
}
```

**Callers:** `LinearClient.create_issue()`, `PromotionService`

---

#### M2: Update issue (state)

```graphql
mutation($issueId: String!, $stateId: String!) {
  issueUpdate(id: $issueId, input: { stateId: $stateId }) {
    success
    issue { id state { name } }
  }
}
```

**Callers:** `LinearClient.update_issue_state()`

---

#### M3: Update issue (labels)

```graphql
mutation($id: String!, $labelIds: [String!]!) {
  issueUpdate(id: $id, input: { labelIds: $labelIds }) {
    success
  }
}
```

**Callers:** `LinearClient.add_label()`, `LinearClient.remove_label()`

---

#### M4: Update issue (labels + parent)

```graphql
mutation($id: String!, $input: IssueUpdateInput!) {
  issueUpdate(id: $id, input: $input) {
    success
  }
}
```

Where `$input` contains `{ labelIds: [...], parentId: "..." }`.

**Callers:** `PromotionService._promote_to_linear()` — sets labels and parent
after issue creation

---

#### M5: Create comment

```graphql
mutation($issueId: String!, $body: String!) {
  commentCreate(input: { issueId: $issueId, body: $body }) {
    success
    comment { id body }
  }
}
```

**Callers:** `LinearClient.add_comment()`

---

## 4. Feature Usage by Component

| Component | Operations used | Purpose |
|-----------|----------------|---------|
| **Daemon (poll)** | Q2 (list issues) | Poll `Ready` issues for execution |
| **Daemon (triage)** | Q1, M5, M3 | Check issue, post clarification, add `needs-clarification` |
| **Daemon (claim)** | M2 | Move issue to `In Progress` |
| **Daemon (complete)** | M5, M2 | Post summary comment, move to `In Review` or `Done` |
| **Daemon (reply detect)** | Q2, Q3, M3 | Find `needs-clarification` issues, check for replies, remove label |
| **Daemon (review loop)** | Q2, M2 | Find `In Review` issues, reset to `Ready` |
| **LinearIssueSource** | Q1 | Load issue content for execution |
| **LinearWriteBackService** | M5, M2 | Post run summary/gate update, mark `Done` |
| **LinearConversationAdapter** | Q2, Q3, Q1, M5 | Poll for new comments, reply |
| **PromotionService** | Q4, M1, Q7, M4, Q2 | Create issues from plan, set labels/parent |
| **ConfigChecker** | Q6 | Validate Linear team and states |
| **CLI (run/gate)** | Q1, M5, M2 | Write back PR link, update state |

---

## 5. What Is NOT Used

The following Linear features are **not** used by spec-orch and do not
need to be implemented in a compatible replacement:

- Webhooks (all interaction is polling-based)
- OAuth / SSO (token-based auth only)
- Projects / Roadmaps / Cycles / Milestones
- Issue relations / dependencies (only `parentId` hierarchy)
- Issue priority / estimates / due dates
- Attachments / file uploads
- Notifications API
- Custom views / favorites
- Audit log API
- Issue history / activity feed
- Pagination cursors (uses simple `first: N` limit)
- Batch mutations / bulk operations
- Subscriptions (GraphQL subscriptions)

---

## 6. Minimum Viable Replacement

A compatible self-hosted backend must support:

### Data model
- **Team**: `id`, `key`, `name`, has many WorkflowStates
- **WorkflowState**: `id`, `name`, belongs to Team
- **IssueLabel**: `id`, `name`, workspace-scoped
- **Issue**: `id`, `identifier` (auto-generated), `title`, `description`,
  belongs to Team, has one State, has many Labels, has optional `parentId`,
  has optional Assignee, has many Comments, has many Children
- **Comment**: `id`, `body`, `createdAt`, belongs to Issue, belongs to User
- **User**: `id`, `name`, `email`, `isMe` filter support

### GraphQL API
- Single `POST /graphql` endpoint
- Token-based auth via `Authorization` header
- 7 query patterns (Q1–Q7 above)
- 5 mutation patterns (M1–M5 above)
- `and` combinator for issue filters
- Filter operators: `eq`, `in`, `nin`, `some`, `every`, `isMe`
- `orderBy` on comments
- `first` limit on collections
- Standard `{ data: { ... }, errors: [...] }` response shape

### External integrations
- **GitHub App**: auto-close issues when linked PR merges (maps PR merge →
  issue state `Done`). This is handled by the Linear-GitHub integration
  today; a replacement must support equivalent webhook-based PR tracking.

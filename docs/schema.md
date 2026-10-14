# Database Schema

## Overview

The Feedback platform uses a relational database managed by **SQLAlchemy ORM** with
**Flask-Migrate** (Alembic) for schema versioning. Development uses **SQLite**;
production should use **PostgreSQL** (see [Switching to PostgreSQL](#switching-to-postgresql)).

**7 tables** store all application data: users, forms, questions, responses,
answers, rewards, and notifications.

---

## Entity-Relationship Diagram

```mermaid
erDiagram
    users ||--o{ forms : "owns"
    users ||--o{ responses : "submits"
    users ||--o{ rewards : "earns"
    users ||--o{ notifications : "receives"

    forms ||--o{ questions : "contains"
    forms ||--o{ responses : "collects"
    forms ||--o{ rewards : "awards"
    forms ||--o{ notifications : "triggers"

    responses ||--o{ answers : "includes"
    questions ||--o{ answers : "answered_by"

    users {
        int id PK
        string name
        string email UK
        string role
        datetime created_at
    }

    forms {
        string id PK "UUID-4"
        string title
        text description
        int owner_id FK
        datetime created_at
        datetime closes_at
        boolean is_published
    }

    questions {
        int id PK
        string form_id FK
        text question_text
        string question_type
        text options "JSON"
        int order
    }

    responses {
        int id PK
        string form_id FK
        int respondent_id FK
        datetime submitted_at
    }

    answers {
        int id PK
        int response_id FK
        int question_id FK
        text answer_value
    }

    rewards {
        int id PK
        string form_id FK
        int user_id FK
        int rank
        float reward_points
        datetime calculated_at
    }

    notifications {
        int id PK
        string form_id FK
        int recipient_id FK
        string notification_type
        string status
        text error_message
        datetime sent_at
        datetime created_at
    }
```

---

## Table Descriptions

### `users`

Platform users who can either own forms or submit responses.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | INTEGER | PK, auto-increment | Internal user ID |
| `name` | VARCHAR(150) | NOT NULL | Display name |
| `email` | VARCHAR(254) | NOT NULL, UNIQUE, INDEXED | Email for login and notifications |
| `role` | VARCHAR(20) | NOT NULL, DEFAULT `'employee'`, INDEXED | `owner` or `employee` |
| `created_at` | DATETIME(tz) | NOT NULL, DEFAULT `now()` | Account creation timestamp (UTC) |

**Relationships:**
- `1:N` → `forms` (as owner)
- `1:N` → `responses` (as respondent)
- `1:N` → `rewards` (as recipient)
- `1:N` → `notifications` (as email recipient)

---

### `forms`

Questionnaire/feedback forms, each identified by a UUID.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | VARCHAR(36) | PK (UUID-4, auto-generated) | Unique form identifier |
| `title` | VARCHAR(255) | NOT NULL | Form title shown to respondents |
| `description` | TEXT | NULLABLE | Optional instructions/description |
| `owner_id` | INTEGER | FK → `users.id`, NOT NULL, INDEXED, ON DELETE CASCADE | Creator of the form |
| `created_at` | DATETIME(tz) | NOT NULL, DEFAULT `now()` | Creation timestamp (UTC) |
| `closes_at` | DATETIME(tz) | NULLABLE | Deadline for accepting responses |
| `is_published` | BOOLEAN | NOT NULL, DEFAULT `FALSE` | Whether employees can see and fill the form |

**Relationships:**
- `N:1` → `users` (owner)
- `1:N` → `questions` (cascade delete)
- `1:N` → `responses` (cascade delete)
- `1:N` → `rewards` (cascade delete)
- `1:N` → `notifications` (cascade delete)

**Business rules:**
- Published forms cannot be updated (`PUT` returns `409`).
- A form must have ≥ 1 question to be published.
- Responses are rejected after `closes_at` (if set).

---

### `questions`

Individual questions within a form.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | INTEGER | PK, auto-increment | Question ID |
| `form_id` | VARCHAR(36) | FK → `forms.id`, NOT NULL, INDEXED, ON DELETE CASCADE | Parent form |
| `question_text` | TEXT | NOT NULL | The question displayed to respondents |
| `question_type` | VARCHAR(20) | NOT NULL, DEFAULT `'text'` | One of: `text`, `multiple_choice`, `rating`, `checkbox` |
| `options` | TEXT | NULLABLE | JSON-encoded array of choices (for `multiple_choice` / `checkbox`) |
| `order` | INTEGER | NOT NULL, DEFAULT `0` | Display order within the form (ascending) |

**Question types:**

| Type | `options` field | Answer format |
|---|---|---|
| `text` | Not used (`NULL`) | Free-text string |
| `multiple_choice` | JSON array of ≥ 2 strings | One of the option strings |
| `rating` | Not used (`NULL`) | Numeric string (e.g. `"5"`) |
| `checkbox` | JSON array of ≥ 2 strings | JSON array of selected options |

---

### `responses`

One submission of a form by a respondent.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | INTEGER | PK, auto-increment | Response ID |
| `form_id` | VARCHAR(36) | FK → `forms.id`, NOT NULL, INDEXED, ON DELETE CASCADE | Which form was answered |
| `respondent_id` | INTEGER | FK → `users.id`, NOT NULL, INDEXED, ON DELETE CASCADE | Who submitted |
| `submitted_at` | DATETIME(tz) | NOT NULL, DEFAULT `now()`, INDEXED | Submission timestamp (used for reward ranking) |

**Unique constraint:** `(form_id, respondent_id)` — one response per user per form.

The `submitted_at` column is indexed because it is used in `ORDER BY` for reward ranking.

---

### `answers`

One answer to one question within a response.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | INTEGER | PK, auto-increment | Answer ID |
| `response_id` | INTEGER | FK → `responses.id`, NOT NULL, INDEXED, ON DELETE CASCADE | Parent response |
| `question_id` | INTEGER | FK → `questions.id`, NOT NULL, INDEXED, ON DELETE CASCADE | Which question was answered |
| `answer_value` | TEXT | NOT NULL | The answer (plain text, numeric string, or JSON array for checkboxes) |

**Unique constraint:** `(response_id, question_id)` — one answer per question per response.

---

### `rewards`

Time-based reward calculated after a form's collection period ends.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | INTEGER | PK, auto-increment | Reward ID |
| `form_id` | VARCHAR(36) | FK → `forms.id`, NOT NULL, INDEXED, ON DELETE CASCADE | Which form |
| `user_id` | INTEGER | FK → `users.id`, NOT NULL, INDEXED, ON DELETE CASCADE | Who earned the reward |
| `rank` | INTEGER | NOT NULL | 1-based submission rank (1 = first to submit) |
| `reward_points` | FLOAT | NOT NULL | Points awarded (higher for earlier submissions) |
| `calculated_at` | DATETIME(tz) | NOT NULL, DEFAULT `now()` | When the reward was computed |

**Unique constraint:** `(form_id, user_id)` — one reward per user per form.

See [docs/rewards.md](rewards.md) for the full algorithm explanation.

---

### `notifications`

Log of every email notification sent (or attempted) by the platform.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | INTEGER | PK, auto-increment | Notification ID |
| `form_id` | VARCHAR(36) | FK → `forms.id`, NOT NULL, INDEXED, ON DELETE CASCADE | Related form |
| `recipient_id` | INTEGER | FK → `users.id`, NOT NULL, INDEXED, ON DELETE CASCADE | Email recipient |
| `notification_type` | VARCHAR(20) | NOT NULL, DEFAULT `'publish'` | `publish` or `reminder` |
| `status` | VARCHAR(20) | NOT NULL, DEFAULT `'pending'`, INDEXED | `pending`, `sent`, or `failed` |
| `error_message` | TEXT | NULLABLE | Error details when `status='failed'`; `"dry_run"` when `MAIL_ENABLED=false` |
| `sent_at` | DATETIME(tz) | NULLABLE | Timestamp of successful delivery |
| `created_at` | DATETIME(tz) | NOT NULL, DEFAULT `now()` | When the notification was queued |

---

## Relationships Summary

```
users ──1:N──► forms         (owner creates forms)
users ──1:N──► responses     (employee submits responses)
users ──1:N──► rewards       (employee earns rewards)
users ──1:N──► notifications (employee receives emails)

forms ──1:N──► questions     (form contains questions)
forms ──1:N──► responses     (form collects responses)
forms ──1:N──► rewards       (form awards rewards)
forms ──1:N──► notifications (form triggers notifications)

responses ──1:N──► answers   (response includes answers)
questions ──1:N──► answers   (question is answered by answers)
```

All foreign keys use `ON DELETE CASCADE` — deleting a form removes all its
questions, responses, answers, rewards, and notifications.

---

## Indexes

| Table | Column(s) | Purpose |
|---|---|---|
| `users` | `email` | Fast lookup by email (login, notifications) |
| `users` | `role` | Filter owners vs. employees |
| `forms` | `owner_id` | List forms by owner |
| `questions` | `form_id` | List questions for a form |
| `responses` | `form_id` | List responses for a form |
| `responses` | `respondent_id` | Check duplicate submissions |
| `responses` | `submitted_at` | Reward ranking ORDER BY |
| `answers` | `response_id` | Load answers for a response |
| `answers` | `question_id` | Aggregate answers per question |
| `rewards` | `form_id` | Leaderboard query |
| `rewards` | `user_id` | User's reward history |
| `notifications` | `form_id` | List notifications for a form |
| `notifications` | `recipient_id` | User's notification history |
| `notifications` | `status` | Filter pending/sent/failed |

---

## Migrations

Managed by **Flask-Migrate** (Alembic). Migration files live in `migrations/versions/`.

| Migration | Description |
|---|---|
| `dbc8c442b305` | Initial schema — users, forms, questions, responses, answers, rewards |
| `075d3348dbf3` | Add notifications table |

```bash
flask db upgrade          # Apply all pending migrations
flask db downgrade        # Roll back one step
flask db migrate -m "..."  # Auto-generate a new migration after model changes
flask db current          # Show current migration revision
flask db history          # Show migration history
```

---

## Switching to PostgreSQL

1. Install the PostgreSQL driver:

```bash
pip install psycopg2-binary
```

2. Set the connection string in `.env`:

```bash
DATABASE_URL=postgresql://user:password@host:5432/feedback
```

3. Apply migrations:

```bash
flask db upgrade
```

No model changes are needed — SQLAlchemy abstracts the dialect. The UUID primary
key on `forms` works natively in PostgreSQL (stored as a proper UUID type when
using `sa.String(36)`).

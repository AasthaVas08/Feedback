# System Architecture

## Overview

The Feedback platform is a **monolithic Flask application** with a clean
separation between API endpoints, server-rendered pages, and background
services. The frontend uses Jinja2 templates with client-side JavaScript
that calls the JSON API.

---

## Component Diagram

```mermaid
graph TB
    subgraph "Browser"
        UI["HTML/CSS/JS Frontend<br/>(Jinja2 templates + app.js)"]
    end

    subgraph "Flask Application"
        direction TB
        Views["views.py<br/>Page Routes"]
        API["api/<br/>REST Endpoints"]
        Services["services/<br/>Email Service"]
        CLI["cli.py<br/>CLI Commands"]
        Models["models/<br/>SQLAlchemy ORM"]
    end

    subgraph "External"
        DB["SQLite / PostgreSQL"]
        Graph["Microsoft 365<br/>Graph API"]
    end

    UI -->|"GET /, /create, /form/:id,<br/>/dashboard, /leaderboard/:id"| Views
    UI -->|"AJAX calls<br/>JSON API"| API
    Views -->|"render_template()"| UI
    API --> Models
    Views --> Models
    Services --> Models
    Services -->|"OAuth2 + sendMail"| Graph
    CLI --> Services
    Models -->|"SQLAlchemy"| DB

    style UI fill:#e0e7ff,stroke:#4f46e5
    style API fill:#dcfce7,stroke:#16a34a
    style Services fill:#fef3c7,stroke:#d97706
    style DB fill:#f3f4f6,stroke:#6b7280
    style Graph fill:#fce7f3,stroke:#db2777
```

---

## Layer Architecture

```
┌─────────────────────────────────────────────────────┐
│                    Browser                           │
│  HTML templates + CSS + JavaScript (app.js)          │
│  Chart.js for dashboard visualisations               │
├─────────────────────────────────────────────────────┤
│                 Flask Application                    │
│                                                      │
│  ┌──────────────┐  ┌──────────────┐                 │
│  │  views.py    │  │  api/        │  ← HTTP layer   │
│  │  Page routes │  │  REST JSON   │                  │
│  └──────┬───────┘  └──────┬───────┘                 │
│         │                  │                         │
│  ┌──────┴──────────────────┴───────┐                │
│  │         models/                  │  ← ORM layer  │
│  │  User, Form, Question, Response │                │
│  │  Answer, Reward, Notification   │                │
│  └──────────────┬──────────────────┘                │
│                  │                                   │
│  ┌──────────────┴──────────────────┐                │
│  │       services/                  │  ← Service    │
│  │  email_service.py               │    layer       │
│  │  (MS Graph API integration)     │                │
│  └─────────────────────────────────┘                │
│                                                      │
│  ┌─────────────────────────────────┐                │
│  │       cli.py                     │  ← CLI layer  │
│  │  flask notify send-reminders    │                │
│  │  flask notify send-publish      │                │
│  │  flask notify status            │                │
│  └─────────────────────────────────┘                │
├─────────────────────────────────────────────────────┤
│  SQLite (dev) / PostgreSQL (prod)                    │
│  Managed by Flask-Migrate (Alembic)                  │
└─────────────────────────────────────────────────────┘
```

---

## Key Components

### 1. Application Factory (`app/__init__.py`)

The `create_app()` function:
1. Loads configuration by name (`development`, `testing`, `production`)
2. Initialises SQLAlchemy and Flask-Migrate
3. Imports all models (so Alembic can detect them)
4. Registers the API blueprint (`/api` prefix)
5. Registers the views blueprint (page routes)
6. Registers CLI commands (`flask notify ...`)
7. Adds a `/health` endpoint

### 2. API Layer (`app/api/`)

Seven route modules registered under a single Blueprint with `/api` prefix:

| Module | Responsibility |
|---|---|
| `forms.py` | Form CRUD + publish (6 endpoints) |
| `questions.py` | Question CRUD within forms (3 endpoints) |
| `responses.py` | Response submission + listing (2 endpoints) |
| `rewards.py` | Reward calculation + leaderboard (2 endpoints) |
| `dashboard.py` | Aggregate statistics (1 endpoint) |
| `notifications.py` | Notification log queries (2 endpoints) |
| `users.py` | User listing (1 endpoint) |

### 3. Models Layer (`app/models/`)

Seven SQLAlchemy models mapping to database tables. All relationships use
`cascade="all, delete-orphan"` for clean cascading deletes. See
[docs/schema.md](schema.md) for full details.

### 4. Service Layer (`app/services/`)

Currently contains `email_service.py` — the Microsoft 365 Graph API
integration. Handles OAuth2 token acquisition, email composition, and
per-recipient error tracking.

### 5. Frontend (`app/templates/` + `app/static/`)

Server-rendered Jinja2 templates that use client-side JavaScript (`app.js`)
to call the API endpoints via `fetch()`. Chart.js powers the dashboard
visualisations.

### 6. CLI (`app/cli.py`)

Flask CLI commands for scheduled/operational tasks:
- `flask notify send-reminders` — cron-friendly reminder sender
- `flask notify send-publish <id>` — retry/resend publish notifications
- `flask notify status` — notification statistics

---

## Data Flows

### Flow 1: Form Creation → Publish → Email Notification

```mermaid
sequenceDiagram
    participant Owner as Owner (Browser)
    participant API as Flask API
    participant DB as Database
    participant Thread as Background Thread
    participant Graph as MS Graph API
    participant Employee as Employee (Email)

    Owner->>API: POST /api/forms {title, owner_id}
    API->>DB: INSERT INTO forms (UUID generated)
    DB-->>API: Form created
    API-->>Owner: 201 {id: "uuid-..."}

    Owner->>API: POST /api/forms/:id/questions
    API->>DB: INSERT INTO questions
    API-->>Owner: 201 Question created

    Owner->>API: POST /api/forms/:id/publish
    API->>DB: UPDATE forms SET is_published=true
    API->>DB: INSERT INTO notifications (one per employee, status=pending)
    API->>Thread: Spawn daemon thread
    API-->>Owner: 200 {notifications_queued: 3}

    Thread->>Graph: POST /oauth2/v2.0/token (client credentials)
    Graph-->>Thread: access_token

    loop For each pending notification
        Thread->>Graph: POST /users/{sender}/sendMail
        Graph-->>Thread: 202 Accepted
        Thread->>DB: UPDATE notification SET status=sent
    end

    Graph->>Employee: Email with form link
```

### Flow 2: Response Submission

```mermaid
sequenceDiagram
    participant Emp as Employee (Browser)
    participant API as Flask API
    participant DB as Database

    Emp->>API: GET /api/forms/:id
    API->>DB: SELECT form + questions
    DB-->>API: Form data
    API-->>Emp: 200 {form with questions}

    Note over Emp: Employee fills in the form

    Emp->>API: POST /api/forms/:id/responses {respondent_id, answers}
    API->>DB: Validate: form published? not closed? not duplicate?
    API->>DB: Validate: all questions answered?
    API->>DB: INSERT INTO responses + answers
    DB-->>API: Response created
    API-->>Emp: 201 {response with answers}
```

### Flow 3: Reward Calculation

```mermaid
sequenceDiagram
    participant Owner as Owner (Browser)
    participant API as Flask API
    participant DB as Database

    Owner->>API: POST /api/forms/:id/rewards/calculate {max: 100, min: 10}
    API->>DB: SELECT responses ORDER BY submitted_at ASC
    DB-->>API: [resp1, resp2, resp3, ...]

    Note over API: Delete existing rewards for this form
    API->>DB: DELETE FROM rewards WHERE form_id=:id

    Note over API: Calculate: points = max - (max-min) × (rank-1)/(total-1)
    API->>DB: INSERT INTO rewards (one per respondent)
    DB-->>API: Rewards created
    API-->>Owner: 201 {rewards: [{rank:1, points:100}, ...]}
```

### Flow 4: Dashboard View

```mermaid
sequenceDiagram
    participant User as User (Browser)
    participant Page as Flask Views
    participant JS as JavaScript (app.js)
    participant API as Flask API
    participant DB as Database

    User->>Page: GET /dashboard
    Page-->>User: dashboard.html (template)

    JS->>API: GET /api/dashboard
    API->>DB: COUNT forms, responses, employees
    API->>DB: For each form: response count, reward stats
    DB-->>API: Aggregated data
    API-->>JS: 200 {total_forms, forms: [...]}

    Note over JS: Render charts (Chart.js) + stats cards
```

### Flow 5: Closing Reminder (Cron)

```mermaid
sequenceDiagram
    participant Cron as Cron Job
    participant CLI as flask notify send-reminders
    participant Service as email_service
    participant DB as Database
    participant Graph as MS Graph API

    Cron->>CLI: Execute hourly
    CLI->>Service: send_closing_reminders(app)
    Service->>DB: SELECT forms WHERE closes_at BETWEEN now AND now+24h
    DB-->>Service: [form1, form2]

    loop For each closing form
        Service->>DB: SELECT employees who have NOT responded
        Service->>DB: INSERT INTO notifications (type=reminder, status=pending)
        Service->>Graph: Send emails (background thread)
        Graph-->>Service: Delivery status
        Service->>DB: UPDATE notification status
    end

    CLI-->>Cron: Done (exit 0)
```

---

## Configuration Architecture

Three configuration classes inherit from a shared `Config` base:

| Class | `FLASK_ENV` | Database | Email | Debug |
|---|---|---|---|---|
| `DevelopmentConfig` | `development` | SQLite (file) | Disabled by default | ✅ |
| `TestingConfig` | `testing` | SQLite (in-memory) | Always disabled | ❌ |
| `ProductionConfig` | `production` | PostgreSQL (via `DATABASE_URL`) | Enabled by default | ❌ |

All sensitive values come from environment variables (see `.env.example`).

---

## Security Considerations

> **Note:** The current version does not implement authentication. User
> identity is passed via `owner_id` / `respondent_id` in request bodies.
> This is suitable for internal/trusted environments. For public deployment,
> add authentication middleware (e.g. Flask-Login, OAuth2, or JWT).

**Current protections:**
- Role-based access: only `owner` users can create forms; only `employee` users can submit responses
- One response per user per form (unique constraint)
- Published forms are immutable (no edits after publish)
- Deadline enforcement (responses rejected after `closes_at`)
- Per-recipient error isolation in email sending
- Background threading for email sends (API never blocks)

---

## Technology Stack

| Layer | Technology | Version |
|---|---|---|
| **Backend** | Python + Flask | 3.10+ / 3.0.3 |
| **ORM** | SQLAlchemy (via Flask-SQLAlchemy) | 3.1.1 |
| **Migrations** | Alembic (via Flask-Migrate) | 4.0.7 |
| **Database** | SQLite (dev) / PostgreSQL (prod) | — |
| **Email** | Microsoft 365 Graph API | v1.0 |
| **HTTP Client** | Requests | 2.32.3 |
| **Frontend** | Jinja2 + vanilla JS + Chart.js | — |
| **Testing** | pytest + pytest-cov | 8.2.2 / 5.0.0 |

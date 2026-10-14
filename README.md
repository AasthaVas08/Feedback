# 📋 Feedback — Questionnaire & Feedback Platform

A full-stack web application for creating questionnaire/feedback forms, each
identified by a **unique UUID**. Features time-based reward scoring, email
notifications via Microsoft 365, and a real-time analytics dashboard.

![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)
![Flask](https://img.shields.io/badge/Flask-3.0-green?logo=flask)
![SQLite](https://img.shields.io/badge/SQLite-dev-lightgrey?logo=sqlite)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-prod-blue?logo=postgresql)
![Tests](https://img.shields.io/badge/tests-112%20passing-brightgreen)

---

## ✨ Features

| Feature | Description |
|---|---|
| **Form Builder** | Create forms with 4 question types: text, multiple choice, rating, checkbox. Drag-to-reorder questions. |
| **Unique Form IDs** | Every form gets a UUID-4 identifier — safe for sharing via URL without exposing sequential IDs. |
| **Response Collection** | Employees fill in published forms. One response per user per form, with deadline enforcement. |
| **Time-Based Rewards** | First responder gets max points, last gets min. Linear interpolation for everyone in between. |
| **Email Notifications** | Publish a form → all employees receive an email via Microsoft 365 Graph API. 24-hour closing reminders. |
| **Dashboard** | Aggregate stats: form counts, response rates, reward distributions, per-form breakdowns. |
| **Leaderboard** | Per-form ranked list of respondents with their reward points. |

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.10+** (with `pip`)
- **Git**

### 1. Clone and enter the project

```bash
git clone https://github.com/AasthaVas08/Feedback.git
cd Feedback
```

### 2. Create a virtual environment

```bash
python -m venv venv
source venv/bin/activate        # macOS / Linux
venv\Scripts\activate           # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment

```bash
cp .env.example .env
# Edit .env — at minimum, set SECRET_KEY to a random string
```

### 5. Initialise the database

```bash
export FLASK_APP=run.py         # Windows: set FLASK_APP=run.py
flask db upgrade
```

### 6. (Optional) Load sample data

```bash
python -m seeds.seed
```

This creates:
- 1 owner user (Alice) and 3 employee users (Bob, Carol, Dave)
- 1 published form with 4 questions (rating, multiple choice, text, checkbox)
- 3 responses with staggered timestamps and pre-calculated rewards

### 7. Run the development server

```bash
python run.py
# → http://localhost:5000
```

---

## 📁 Project Structure

```
Feedback/
├── app/
│   ├── __init__.py              # Flask app factory, extensions init
│   ├── views.py                 # Server-rendered page routes (/, /create, /form/<id>, etc.)
│   ├── cli.py                   # Flask CLI commands (notify send-reminders, etc.)
│   ├── models/
│   │   ├── __init__.py          # Re-exports all models
│   │   ├── user.py              # User model (owner / employee roles)
│   │   ├── form.py              # Form model (UUID primary key)
│   │   ├── question.py          # Question model (text/MC/rating/checkbox)
│   │   ├── response.py          # Response model (one per user per form)
│   │   ├── answer.py            # Answer model (one per question per response)
│   │   ├── reward.py            # Reward model (time-based ranking)
│   │   └── notification.py      # Notification model (email log)
│   ├── api/
│   │   ├── __init__.py          # API blueprint registration
│   │   ├── forms.py             # Form CRUD + publish endpoints
│   │   ├── questions.py         # Question CRUD endpoints
│   │   ├── responses.py         # Response submission + listing
│   │   ├── rewards.py           # Reward calculation + leaderboard
│   │   ├── dashboard.py         # Aggregate statistics endpoint
│   │   ├── notifications.py     # Notification log endpoints
│   │   └── users.py             # User listing endpoint
│   ├── services/
│   │   ├── __init__.py          # Service layer package
│   │   └── email_service.py     # MS Graph API email integration
│   ├── templates/
│   │   ├── base.html            # Base layout with navbar
│   │   ├── home.html            # Landing page — published forms grid
│   │   ├── form_builder.html    # Two-step form creation wizard
│   │   ├── form_filler.html     # Form response submission
│   │   ├── dashboard.html       # Analytics dashboard with charts
│   │   └── leaderboard.html     # Per-form reward leaderboard
│   └── static/
│       ├── css/                 # Stylesheets (tokens, main, components, pages)
│       └── js/
│           ├── app.js           # Client-side application logic
│           └── chart.umd.js     # Chart.js for dashboard visualisations
├── migrations/                  # Alembic migration scripts
│   └── versions/
│       ├── dbc8c442b305_initial_schema_...py
│       └── 075d3348dbf3_add_notifications_table.py
├── seeds/
│   └── seed.py                  # Sample data loader (idempotent)
├── tests/
│   ├── conftest.py              # Shared pytest fixtures
│   ├── test_models.py           # Model unit tests
│   ├── test_api_forms.py        # Form endpoint tests
│   ├── test_api_questions.py    # Question endpoint tests
│   ├── test_api_responses.py    # Response endpoint tests
│   ├── test_api_rewards.py      # Reward endpoint tests
│   ├── test_api_dashboard.py    # Dashboard endpoint tests
│   └── test_notifications.py    # Notification model/API/service tests
├── docs/
│   ├── api.md                   # Full API reference
│   ├── schema.md                # Database schema + ER diagram
│   ├── architecture.md          # System architecture + data flows
│   └── rewards.md               # Reward algorithm explained
├── config.py                    # Dev / Testing / Production configs
├── run.py                       # Flask entry point
├── requirements.txt             # Python dependencies
├── .env.example                 # Environment variable template
└── .gitignore
```

---

## 🌐 Pages

| Page | URL | Description |
|---|---|---|
| **Home** | `/` | Hero section + grid of published forms with Open/Closed badges |
| **Form Builder** | `/create` | Two-step wizard: form details → dynamic question builder |
| **Form Filler** | `/form/<uuid>` | Renders all question types, validates, submits via AJAX |
| **Dashboard** | `/dashboard` | Charts + stats: form counts, response rates, reward distributions |
| **Leaderboard** | `/leaderboard/<uuid>` | Per-form ranked list of respondents with reward points |

---

## 🔌 API Endpoints

All endpoints are under `/api` and return JSON. Full reference: **[docs/api.md](docs/api.md)**

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/forms` | Create a new form |
| `GET` | `/api/forms` | List all forms |
| `GET` | `/api/forms/:id` | Get form with questions |
| `PUT` | `/api/forms/:id` | Update a draft form |
| `POST` | `/api/forms/:id/publish` | Publish + notify employees |
| `DELETE` | `/api/forms/:id` | Delete form (cascade) |
| `POST` | `/api/forms/:id/questions` | Add a question |
| `PUT` | `/api/forms/:id/questions/:qid` | Update a question |
| `DELETE` | `/api/forms/:id/questions/:qid` | Delete a question |
| `POST` | `/api/forms/:id/responses` | Submit a response |
| `GET` | `/api/forms/:id/responses` | List responses |
| `POST` | `/api/forms/:id/rewards/calculate` | Calculate rewards |
| `GET` | `/api/forms/:id/rewards` | Get leaderboard |
| `GET` | `/api/dashboard` | Aggregate statistics |
| `GET` | `/api/forms/:id/notifications` | Notification log for a form |
| `GET` | `/api/notifications/stats` | Global notification stats |
| `GET` | `/api/users` | List all users |
| `GET` | `/health` | Health check |

---

## 🗄️ Database

- **Development:** SQLite — auto-created at `instance/feedback.db`
- **Production:** PostgreSQL — set `DATABASE_URL` in `.env`

Full schema documentation with ER diagram: **[docs/schema.md](docs/schema.md)**

### 7 Tables

| Table | PK | Purpose |
|---|---|---|
| `users` | `id` (int) | Owners and employees |
| `forms` | `id` (UUID-4) | Questionnaire/feedback forms |
| `questions` | `id` (int) | Individual questions within forms |
| `responses` | `id` (int) | One submission per user per form |
| `answers` | `id` (int) | One answer per question per response |
| `rewards` | `id` (int) | Time-based reward for each respondent |
| `notifications` | `id` (int) | Email notification log |

### Migrations

```bash
flask db upgrade                          # Apply all migrations
flask db downgrade                        # Roll back one step
flask db migrate -m "describe change"     # Generate new migration after model changes
```

---

## 🏆 Reward System

Rewards are calculated based on **submission order** — earlier responses earn more points.

```
points = max_reward − (max_reward − min_reward) × (rank − 1) / (total − 1)
```

**Example** with `max_reward=100`, `min_reward=10`, 5 respondents:

| Rank | Points |
|------|--------|
| 1st (first) | 100.00 |
| 2nd | 77.50 |
| 3rd | 55.00 |
| 4th | 32.50 |
| 5th (last) | 10.00 |

Full algorithm explanation with edge cases: **[docs/rewards.md](docs/rewards.md)**

---

## 📧 Email Notifications

The platform sends emails via **Microsoft 365 Graph API** using OAuth2 client credentials.

### Setup

1. Register an app in **Azure AD → App registrations**
2. Grant **`Mail.Send`** application permission + admin consent
3. Set these environment variables in `.env`:

```bash
MAIL_ENABLED=true
MAIL_SENDER_EMAIL=noreply@yourcompany.com
MS_GRAPH_CLIENT_ID=your-client-id
MS_GRAPH_CLIENT_SECRET=your-client-secret
MS_GRAPH_TENANT_ID=your-tenant-id
```

### Notification Types

| Type | Trigger | Content |
|---|---|---|
| **Publish** | Owner publishes a form | "New feedback form published" with link |
| **Reminder** | Cron job / CLI command | "Form closing in 24 hours" for non-respondents |

### CLI Commands

```bash
flask notify send-reminders              # Send 24-hour closing reminders
flask notify send-publish <form-uuid>    # (Re)send publish notifications
flask notify status                      # Show notification statistics
```

### Dry-Run Mode

When `MAIL_ENABLED=false` (default in dev/test), notifications are created in the database and marked as "sent" with `error_message="dry_run"`. No actual emails are sent. This lets you test the full flow without Graph API credentials.

---

## 🧪 Testing

```bash
pytest                      # Run all 112 tests
pytest -v                   # Verbose output
pytest --cov=app            # With coverage report
pytest tests/test_api_forms.py   # Run a specific test file
```

The test suite uses an **in-memory SQLite** database (configured in `TestingConfig`). Each test function gets a fresh database via the `db` fixture.

---

## ⚙️ Environment Variables

| Variable | Default | Description |
|---|---|---|
| `FLASK_APP` | — | Set to `run.py` |
| `FLASK_ENV` | `development` | `development`, `testing`, or `production` |
| `SECRET_KEY` | `dev-secret-change-me` | **Change in production!** |
| `DATABASE_URL` | `sqlite:///instance/feedback.db` | Database connection string |
| `MAIL_ENABLED` | `false` | Enable email sending via Graph API |
| `MAIL_SENDER_EMAIL` | — | Email address to send from |
| `MAIL_SENDER_NAME` | `Feedback Platform` | Display name on sent emails |
| `MS_GRAPH_CLIENT_ID` | — | Azure AD app client ID |
| `MS_GRAPH_CLIENT_SECRET` | — | Azure AD app client secret |
| `MS_GRAPH_TENANT_ID` | — | Azure AD tenant ID |
| `APP_BASE_URL` | `http://localhost:5000` | Base URL for form links in emails |
| `DEFAULT_MAX_REWARD` | `100` | Maximum reward points (first responder) |
| `DEFAULT_MIN_REWARD` | `10` | Minimum reward points (last responder) |

---

## 🚢 Production Deployment

### 1. Switch to PostgreSQL

```bash
# Install the PostgreSQL driver
pip install psycopg2-binary

# Set the connection string
export DATABASE_URL=postgresql://user:password@host:5432/feedback

# Apply migrations
flask db upgrade
```

No model changes are needed — SQLAlchemy handles the dialect difference.

### 2. Use a production WSGI server

```bash
pip install gunicorn

# Run with 4 worker processes
gunicorn -w 4 -b 0.0.0.0:8000 run:app
```

### 3. Configure a reverse proxy (Nginx)

```nginx
server {
    listen 80;
    server_name feedback.yourcompany.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static/ {
        alias /path/to/Feedback/app/static/;
        expires 30d;
    }
}
```

### 4. Enable email notifications

```bash
export MAIL_ENABLED=true
export MAIL_SENDER_EMAIL=noreply@yourcompany.com
export MS_GRAPH_CLIENT_ID=...
export MS_GRAPH_CLIENT_SECRET=...
export MS_GRAPH_TENANT_ID=...
export APP_BASE_URL=https://feedback.yourcompany.com
```

### 5. Set up closing reminders (cron)

```bash
# Check every hour for forms closing within 24 hours
0 * * * * cd /path/to/Feedback && /path/to/venv/bin/flask notify send-reminders
```

### 6. Production checklist

- [ ] Set a strong, random `SECRET_KEY`
- [ ] Set `FLASK_ENV=production`
- [ ] Use PostgreSQL (not SQLite)
- [ ] Run behind gunicorn + nginx
- [ ] Enable HTTPS (Let's Encrypt / your CA)
- [ ] Configure email (MS Graph credentials)
- [ ] Set `APP_BASE_URL` to the public URL
- [ ] Set up cron for `flask notify send-reminders`
- [ ] Back up the database regularly

---

## 📚 Documentation

| Document | Description |
|---|---|
| [docs/api.md](docs/api.md) | Full API reference — every endpoint, request/response examples, error codes |
| [docs/schema.md](docs/schema.md) | Database schema — ER diagram (Mermaid), table descriptions, relationships |
| [docs/architecture.md](docs/architecture.md) | System architecture — component diagram, data flows |
| [docs/rewards.md](docs/rewards.md) | Time-based reward algorithm — formula, examples, edge cases |

---

## 📄 License

MIT

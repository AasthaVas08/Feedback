# API Reference

All endpoints are prefixed with `/api` and return JSON.  
Base URL: `http://localhost:5000/api`

---

## Table of Contents

- [Forms](#forms)
- [Questions](#questions)
- [Responses](#responses)
- [Rewards](#rewards)
- [Dashboard](#dashboard)
- [Notifications](#notifications)
- [Users](#users)
- [Health Check](#health-check)
- [Error Format](#error-format)
- [HTTP Status Codes](#http-status-codes)

---

## Forms

### `POST /api/forms`

Create a new feedback form. A UUID-4 is auto-assigned as the form ID.

**Request body:**

```json
{
  "title": "Q3 Employee Survey",
  "description": "Please share your feedback on the last quarter.",
  "owner_id": 1,
  "closes_at": "2026-12-31T23:59:59+00:00"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `title` | string | ✅ | Non-empty, whitespace-trimmed |
| `owner_id` | integer | ✅ | Must reference a user with `role=owner` |
| `description` | string | ❌ | Optional longer description |
| `closes_at` | ISO-8601 datetime | ❌ | Deadline after which responses are rejected |

**Success response:** `201 Created`

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Q3 Employee Survey",
  "description": "Please share your feedback on the last quarter.",
  "owner_id": 1,
  "owner_name": "Alice Owner",
  "is_published": false,
  "created_at": "2026-10-13T10:00:00+00:00",
  "closes_at": "2026-12-31T23:59:59+00:00",
  "question_count": 0,
  "response_count": 0
}
```

**Error responses:**

| Status | Condition |
|---|---|
| `400` | Missing or empty `title`; missing `owner_id`; invalid `closes_at` format |
| `403` | User exists but has `role=employee` (not an owner) |
| `404` | `owner_id` does not match any user |

---

### `GET /api/forms`

List all forms, newest first.

**Response:** `200 OK` — array of form objects (without nested questions).

```json
[
  {
    "id": "a1b2c3d4-...",
    "title": "Q3 Employee Survey",
    "description": "...",
    "owner_id": 1,
    "owner_name": "Alice Owner",
    "is_published": true,
    "created_at": "2026-10-13T10:00:00+00:00",
    "closes_at": "2026-12-31T23:59:59+00:00",
    "question_count": 4,
    "response_count": 3
  }
]
```

---

### `GET /api/forms/:id`

Get a single form with its questions.

**Response:** `200 OK` — form object with `questions` array.

```json
{
  "id": "a1b2c3d4-...",
  "title": "Q3 Employee Survey",
  "questions": [
    {
      "id": 1,
      "question_text": "How satisfied are you?",
      "question_type": "rating",
      "options": [],
      "order": 1
    },
    {
      "id": 2,
      "question_text": "Which benefits do you value?",
      "question_type": "multiple_choice",
      "options": ["Health insurance", "Remote work", "Gym"],
      "order": 2
    }
  ]
}
```

**Errors:** `404` — form not found.

---

### `PUT /api/forms/:id`

Update a form's title, description, or closing date. **Published forms cannot be updated** (returns `409`).

**Request body** (all fields optional):

```json
{
  "title": "Updated Title",
  "description": "Updated description",
  "closes_at": "2027-01-31T23:59:59+00:00"
}
```

Pass `"closes_at": null` to remove the deadline.

**Response:** `200 OK` — updated form object.

**Errors:** `400` (empty title, invalid date), `404` (not found), `409` (already published).

---

### `POST /api/forms/:id/publish`

Mark a form as published. Triggers email notifications to all employees in a background thread.

**Preconditions:**
- Form must exist and not already be published.
- Form must have at least one question.

**Response:** `200 OK`

```json
{
  "message": "Form published successfully",
  "form": { "id": "...", "is_published": true, "..." : "..." },
  "notifications_queued": 3,
  "notified_employees": [
    { "id": 2, "name": "Bob Employee", "email": "bob@example.com" },
    { "id": 3, "name": "Carol Employee", "email": "carol@example.com" }
  ]
}
```

**Errors:** `400` (no questions), `404` (not found), `409` (already published).

---

### `DELETE /api/forms/:id`

Delete a form and **all** related data (questions, responses, answers, rewards, notifications) via cascade.

**Response:** `200 OK`

```json
{ "message": "Form deleted successfully" }
```

**Errors:** `404` — form not found.

---

## Questions

### `POST /api/forms/:id/questions`

Add a question to a draft form. Cannot add to published forms.

**Request body:**

```json
{
  "question_text": "How satisfied are you with your role?",
  "question_type": "rating",
  "options": ["Option A", "Option B", "Option C"],
  "order": 1
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `question_text` | string | ✅ | The question shown to respondents |
| `question_type` | string | ❌ | `text` (default), `multiple_choice`, `rating`, `checkbox` |
| `options` | string[] | Conditional | **Required** for `multiple_choice` and `checkbox` (≥ 2 items) |
| `order` | integer | ❌ | Auto-increments after the last question if omitted |

**Response:** `201 Created` — the created question object.

**Errors:** `400` (validation), `404` (form not found), `409` (form is published).

---

### `PUT /api/forms/:id/questions/:qid`

Update a question's text, type, options, or order. Only on draft forms.

**Request body** (all fields optional):

```json
{
  "question_text": "Updated question text",
  "question_type": "multiple_choice",
  "options": ["New A", "New B"],
  "order": 2
}
```

**Response:** `200 OK` — updated question object.

**Errors:** `400`, `404` (form or question not found), `409` (form published).

---

### `DELETE /api/forms/:id/questions/:qid`

Delete a question from a draft form.

**Response:** `200 OK`

```json
{ "message": "Question deleted successfully" }
```

**Errors:** `404`, `409`.

---

## Responses

### `POST /api/forms/:id/responses`

Submit a response to a published form. Every question must be answered exactly once. One response per user per form.

**Request body:**

```json
{
  "respondent_id": 2,
  "answers": [
    { "question_id": 1, "answer_value": "5" },
    { "question_id": 2, "answer_value": "Remote work" },
    { "question_id": 3, "answer_value": "Great workplace!" },
    { "question_id": 4, "answer_value": "[\"Communication\"]" }
  ]
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `respondent_id` | integer | ✅ | Must be a user with `role=employee` |
| `answers` | array | ✅ | One entry per question in the form |
| `answers[].question_id` | integer | ✅ | Must belong to this form |
| `answers[].answer_value` | string | ✅ | Non-empty answer text |

**Validations performed:**
1. Form exists and is published
2. Form has not passed its `closes_at` deadline
3. Respondent exists and has `role=employee`
4. No duplicate submission (unique per user+form)
5. Every question in the form is answered exactly once
6. No duplicate answers for the same question
7. No answers for questions outside this form

**Response:** `201 Created` — the response with all answers.

```json
{
  "id": 1,
  "form_id": "a1b2c3d4-...",
  "respondent_id": 2,
  "respondent_name": "Bob Employee",
  "respondent_email": "bob@example.com",
  "submitted_at": "2026-10-13T10:30:00+00:00",
  "answers": [
    {
      "id": 1,
      "question_id": 1,
      "question_text": "How satisfied are you?",
      "answer_value": "5"
    }
  ]
}
```

**Errors:** `400` (validation), `403` (not an employee), `404` (form/user not found), `409` (duplicate submission).

---

### `GET /api/forms/:id/responses`

List all responses for a form, ordered by submission time (earliest first).

**Query parameters:**

| Param | Default | Description |
|---|---|---|
| `include_answers` | `false` | Set to `true` to include each response's answers |

**Response:** `200 OK`

```json
{
  "form_id": "a1b2c3d4-...",
  "form_title": "Q3 Employee Survey",
  "total_responses": 3,
  "responses": [
    {
      "id": 1,
      "respondent_id": 2,
      "respondent_name": "Bob Employee",
      "submitted_at": "2026-10-08T10:00:00+00:00"
    }
  ]
}
```

**Errors:** `404` — form not found.

---

## Rewards

### `POST /api/forms/:id/rewards/calculate`

Calculate time-based rewards for all respondents. Responses are ranked by `submitted_at` (earliest = rank 1). Existing rewards for this form are **deleted and recalculated** (idempotent).

**Optional request body:**

```json
{
  "max_reward": 100,
  "min_reward": 10
}
```

Defaults come from `DEFAULT_MAX_REWARD` / `DEFAULT_MIN_REWARD` in config.

**Formula:**

```
points = max_reward − (max_reward − min_reward) × (rank − 1) / (total − 1)
```

**Response:** `201 Created`

```json
{
  "form_id": "a1b2c3d4-...",
  "total_respondents": 3,
  "max_reward": 100,
  "min_reward": 10,
  "rewards": [
    { "rank": 1, "user_id": 2, "user_name": "Bob", "reward_points": 100.0, "submitted_at": "..." },
    { "rank": 2, "user_id": 3, "user_name": "Carol", "reward_points": 55.0, "submitted_at": "..." },
    { "rank": 3, "user_id": 4, "user_name": "Dave", "reward_points": 10.0, "submitted_at": "..." }
  ]
}
```

**Errors:** `400` (no responses, `max_reward ≤ min_reward`), `404` (form not found).

---

### `GET /api/forms/:id/rewards`

Leaderboard — rewards ranked by submission order (rank 1 = first responder).

**Response:** `200 OK`

```json
{
  "form_id": "a1b2c3d4-...",
  "form_title": "Q3 Employee Survey",
  "total_respondents": 3,
  "leaderboard": [
    {
      "rank": 1,
      "user_id": 2,
      "user_name": "Bob Employee",
      "user_email": "bob@example.com",
      "reward_points": 100.0,
      "calculated_at": "2026-10-13T12:00:00+00:00"
    }
  ]
}
```

If no rewards have been calculated yet, `leaderboard` is `[]` and a `message` field says so.

**Errors:** `404` — form not found.

---

## Dashboard

### `GET /api/dashboard`

Aggregate statistics across all forms — counts, response rates, reward distributions.

**Response:** `200 OK`

```json
{
  "total_forms": 5,
  "published_forms": 3,
  "draft_forms": 2,
  "total_responses": 42,
  "total_employees": 10,
  "forms": [
    {
      "id": "a1b2c3d4-...",
      "title": "Q3 Employee Survey",
      "is_published": true,
      "created_at": "2026-10-06T10:00:00+00:00",
      "closes_at": "2026-12-31T23:59:59+00:00",
      "response_count": 8,
      "employee_count": 10,
      "response_rate": 80.0,
      "rewards_calculated": true,
      "reward_distribution": {
        "max_points": 100.0,
        "min_points": 10.0,
        "avg_points": 55.0,
        "total_points": 440.0
      }
    }
  ]
}
```

`response_rate` is `(response_count / total_employees) × 100`, rounded to 1 decimal.  
`reward_distribution` is `null` if rewards have not been calculated for that form.

---

## Notifications

### `GET /api/forms/:id/notifications`

List all notification records for a specific form, newest first.

**Response:** `200 OK`

```json
{
  "form_id": "a1b2c3d4-...",
  "total": 3,
  "sent": 3,
  "failed": 0,
  "pending": 0,
  "notifications": [
    {
      "id": 1,
      "form_id": "a1b2c3d4-...",
      "recipient_id": 2,
      "recipient_name": "Bob Employee",
      "recipient_email": "bob@example.com",
      "notification_type": "publish",
      "status": "sent",
      "error_message": "dry_run: MAIL_ENABLED=false",
      "sent_at": "2026-10-13T10:00:00+00:00",
      "created_at": "2026-10-13T10:00:00+00:00"
    }
  ]
}
```

**Errors:** `404` — form not found.

---

### `GET /api/notifications/stats`

Global notification statistics across all forms.

**Response:** `200 OK`

```json
{
  "total": 15,
  "sent": 12,
  "failed": 1,
  "pending": 2,
  "by_type": {
    "publish": 10,
    "reminder": 5
  }
}
```

---

## Users

### `GET /api/users`

List all users, ordered by role (owners first) then name.

**Response:** `200 OK`

```json
[
  { "id": 1, "name": "Alice Owner", "email": "alice@example.com", "role": "owner" },
  { "id": 2, "name": "Bob Employee", "email": "bob@example.com", "role": "employee" }
]
```

---

## Health Check

### `GET /health`

Minimal health check (not under `/api` prefix).

**Response:** `200 OK`

```json
{ "status": "ok" }
```

---

## Error Format

All errors return a JSON object with an `error` field:

```json
{
  "error": "Human-readable error message"
}
```

Some validation errors include additional fields:

```json
{
  "error": "All questions must be answered",
  "missing_question_ids": [3, 4]
}
```

---

## HTTP Status Codes

| Code | Meaning | When |
|---|---|---|
| `200` | OK | Successful read or update |
| `201` | Created | Successful creation (form, question, response, rewards) |
| `400` | Bad Request | Validation error, missing fields, invalid data |
| `403` | Forbidden | Wrong role (employee trying to create form, owner trying to respond) |
| `404` | Not Found | Form, user, or question does not exist |
| `409` | Conflict | Duplicate submission, form already published, editing published form |

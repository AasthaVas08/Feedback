# Time-Based Reward Algorithm

## Motivation

The reward system incentivises **early responses** to feedback forms. The
first person to submit gets the maximum reward, the last person gets the
minimum, and everyone in between is scaled proportionally. This encourages
prompt participation and gives the form owner faster data collection.

---

## Formula

```
points = max_reward − (max_reward − min_reward) × (rank − 1) / (total − 1)
```

Where:

| Variable | Description | Default |
|---|---|---|
| `max_reward` | Points awarded to the first respondent (rank 1) | 100 |
| `min_reward` | Points awarded to the last respondent (rank N) | 10 |
| `rank` | 1-based submission rank (1 = first to submit) | — |
| `total` | Total number of respondents | — |

This is **linear interpolation** between `max_reward` (rank 1) and
`min_reward` (rank N), distributed evenly across all ranks.

---

## How Ranking Works

1. All responses for a form are queried, **ordered by `submitted_at` ascending**
   (earliest submission first).
2. Each response is assigned a **1-based rank**: the first submission is rank 1,
   the second is rank 2, and so on.
3. The formula is applied to each rank to compute the reward points.

The ranking is purely based on **submission timestamp** — the content of the
response does not affect the reward.

---

## Examples

### Example 1: Three Respondents (default settings)

`max_reward = 100`, `min_reward = 10`, `total = 3`

| Rank | Submitted | Calculation | Points |
|------|-----------|-------------|--------|
| 1 | Oct 8, 10:00 | `100 − 90 × (1−1)/(3−1) = 100 − 0` | **100.00** |
| 2 | Oct 10, 14:30 | `100 − 90 × (2−1)/(3−1) = 100 − 45` | **55.00** |
| 3 | Oct 12, 09:15 | `100 − 90 × (3−1)/(3−1) = 100 − 90` | **10.00** |

### Example 2: Five Respondents

`max_reward = 100`, `min_reward = 10`, `total = 5`

| Rank | Calculation | Points |
|------|-------------|--------|
| 1 | `100 − 90 × 0/4` | **100.00** |
| 2 | `100 − 90 × 1/4` | **77.50** |
| 3 | `100 − 90 × 2/4` | **55.00** |
| 4 | `100 − 90 × 3/4` | **32.50** |
| 5 | `100 − 90 × 4/4` | **10.00** |

### Example 3: Custom Reward Bounds

`max_reward = 50`, `min_reward = 20`, `total = 4`

| Rank | Calculation | Points |
|------|-------------|--------|
| 1 | `50 − 30 × 0/3` | **50.00** |
| 2 | `50 − 30 × 1/3` | **40.00** |
| 3 | `50 − 30 × 2/3` | **30.00** |
| 4 | `50 − 30 × 3/3` | **20.00** |

### Example 4: Ten Respondents

`max_reward = 100`, `min_reward = 10`, `total = 10`

| Rank | Points |
|------|--------|
| 1 | 100.00 |
| 2 | 90.00 |
| 3 | 80.00 |
| 4 | 70.00 |
| 5 | 60.00 |
| 6 | 50.00 |
| 7 | 40.00 |
| 8 | 30.00 |
| 9 | 20.00 |
| 10 | 10.00 |

With 10 respondents and the default bounds, each rank step is exactly 10 points.

---

## Edge Cases

### Single Respondent

When `total = 1`, the formula would divide by zero (`total − 1 = 0`). The
implementation handles this by returning `max_reward` directly:

```python
if total <= 1:
    return max_pts
```

| Rank | Points |
|------|--------|
| 1 | 100.00 (max_reward) |

**Rationale:** A sole respondent deserves the full reward — they responded
when nobody else did.

### Two Respondents

`total = 2`: the first gets `max_reward`, the second gets `min_reward`. No
interpolation needed.

| Rank | Points |
|------|--------|
| 1 | 100.00 |
| 2 | 10.00 |

### No Respondents

If a form has zero responses, the calculate endpoint returns `400 Bad Request`
with the message `"No responses to calculate rewards for"`. No reward rows
are created.

### Recalculation

Calling the calculate endpoint **again** for the same form:
1. Deletes all existing reward rows for that form
2. Recalculates from scratch based on current responses

This makes the operation **idempotent** — you can recalculate after new
responses come in, or after changing the reward bounds.

---

## Reward Distribution Visualisation

For `max=100`, `min=10`, the reward curve is a straight line:

```
Points
100 ┤ ●
 90 ┤   ●
 80 ┤     ●
 70 ┤       ●
 60 ┤         ●
 55 ┤           ●
 50 ┤             ●
 40 ┤               ●
 30 ┤                 ●
 20 ┤                   ●
 10 ┤                     ●
    └──┬──┬──┬──┬──┬──┬──┬──┬──┬──┬──
       1  2  3  4  5  6  7  8  9  10 11
                    Rank
```

The slope depends on the number of respondents:
- **Fewer respondents** → steeper drop between ranks
- **More respondents** → gentler drop between ranks

---

## Configuration

Reward bounds are configurable at two levels:

### 1. Global defaults (environment variables)

```bash
DEFAULT_MAX_REWARD=100
DEFAULT_MIN_REWARD=10
```

These are used when the calculate endpoint is called without explicit bounds.

### 2. Per-calculation override (request body)

```json
POST /api/forms/:id/rewards/calculate
{
  "max_reward": 200,
  "min_reward": 25
}
```

The API validates that `max_reward > min_reward` and returns `400` if not.

---

## Implementation

The core function lives in `app/api/rewards.py`:

```python
def _calculate_reward_points(
    rank: int,
    total: int,
    max_pts: float,
    min_pts: float,
) -> float:
    """Compute reward points for a given rank using linear interpolation.

    Returns max_pts when total <= 1 (single respondent edge case).
    Result is rounded to 2 decimal places.
    """
    if total <= 1:
        return max_pts
    return round(max_pts - (max_pts - min_pts) * (rank - 1) / (total - 1), 2)
```

The calculate endpoint:
1. Fetches all responses ordered by `submitted_at ASC`
2. Deletes existing rewards for the form (idempotent recalculation)
3. Iterates through responses, assigning rank 1, 2, 3, ...
4. Calls `_calculate_reward_points()` for each rank
5. Creates `Reward` rows in the database
6. Returns the full leaderboard in the response

---

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/forms/:id/rewards/calculate` | `POST` | Calculate (or recalculate) rewards |
| `/api/forms/:id/rewards` | `GET` | Get the leaderboard |

See [docs/api.md](api.md) for full request/response documentation.

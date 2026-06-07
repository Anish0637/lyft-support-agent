# Agent Builder Guide

The Agent Builder at **http://localhost:8000/builder** lets anyone on the Ops, PM, or VoC team create and edit self-serve support agents — no code or deployment needed.

---

## Step-by-Step: Create a New Agent

### Step 1 — Open the builder

Go to `http://localhost:8000/builder`. You'll see the sidebar with all existing agents on the left and an empty panel on the right.

Click **"New Agent"** (pink button, top of sidebar).

---

### Step 2 — Fill in Identity

| Field | Description | Example |
|-------|-------------|---------|
| **Intent Slug** | Unique snake_case ID — used internally to route messages | `driver_bonus` |
| **User Type** | Who this agent serves | `driver` |
| **Description** | One-line summary shown in the sidebar | `Handles driver bonus and incentive inquiries` |

> Intent slugs are permanent — you can't rename them after creation (delete and recreate instead).

---

### Step 3 — Select Tools

Check only the tools this agent actually needs. Granting unnecessary tools increases cost and the chance of incorrect tool calls.

| Tool | Use for |
|------|---------|
| `get_rider_info` | Look up a rider's account status |
| `get_trip_info` | Fetch fare breakdown, pickup/dropoff |
| `process_refund` | Issue a refund to a rider |
| `get_driver_info` | Look up driver account, vehicle, rating |
| `get_driver_earnings` | Check weekly earnings and bonuses |
| `submit_damage_claim` | File a vehicle damage claim |
| `create_support_ticket` | Open a ticket for follow-up |
| `escalate_to_human` | Hand off to a live agent |
| `send_notification` | Send push/email/SMS to user |
| `update_account` | Update email, phone, payment method |

---

### Step 4 — Write the Prompt

Click **"Full Template"** in the template bar to load the scaffold, then fill in each section:

```
## Identity
You are a Lyft Driver Bonus support specialist.
You handle driver inquiries about bonuses and incentives.

## Scope
IN-SCOPE: streak bonuses, ride challenges, referral bonuses, bonus eligibility
OUT-OF-SCOPE: earnings disputes (route to driver earnings agent), 
              account deactivations (route to driver_intent)

## Phased Workflow

Phase 1 — Understand the issue:
- Ask what specific bonus the driver is asking about if not specified

Phase 2 — Gather information:
- Call get_driver_info to verify the driver account is active
- Call get_driver_earnings to check current stats and any existing bonuses

Phase 3 — Resolve:
- If eligible: explain the bonus amount and when it will be paid
- If not eligible: explain the specific reason (trips short, hours short, etc.)
- If unclear: create_support_ticket for manual review

Phase 4 — Confirm:
- Summarize what you found and any next steps in 2-3 sentences

## Content Guidelines
- DO say: "Based on your stats this week…"
- DO NOT say: "You will definitely receive…" (never promise specific amounts)
- DO NOT discuss competitor bonus programs
- Keep responses under 150 words
- Sign off as: Lyft Driver Support Team
```

#### Template Sections (insert button)

| Button | Inserts |
|--------|---------|
| **Identity** | `## Identity` block |
| **Scope** | `## Scope` IN/OUT block |
| **Workflow** | 4-phase `## Phased Workflow` |
| **Guidelines** | `## Content Guidelines` block |
| **Full Template** | All sections pre-filled |

---

### Step 5 — Check the Lint Panel

The **Lint** panel (right side) auto-runs 600ms after you stop typing.

```
✓ All checks passed — good to save
```

| Severity | Meaning | Action |
|----------|---------|--------|
| 🔴 Error  | Prompt will likely fail (missing `## Identity`, unsafe instruction, etc.) | Fix before saving |
| 🟡 Warning | Best-practice gap | Strongly recommended to fix |
| ✅ Pass  | Good to go | Save |

Common lint errors:

| Rule | Message | Fix |
|------|---------|-----|
| `missing_identity` | No `## Identity` section found | Add an Identity section |
| `missing_scope` | No `## Scope` section found | Add Scope with IN/OUT lists |
| `no_workflow` | No phased workflow defined | Add a Phased Workflow section |
| `tool_not_in_registry` | Tool X is listed but not registered | Check spelling or add the tool |
| `prompt_too_short` | Prompt under 100 chars | Write a real prompt |

---

### Step 6 — Test the Agent

1. Click the **Test** tab in the right panel
2. Type a realistic message, e.g. `"Did I qualify for the weekend streak bonus?"`
3. Click **▶ Run Test**

The panel shows:
- **Tool calls** fired (blue badges) — e.g. `get_driver_earnings`
- **Final response** — the actual text the agent would return to the user

> The test runs against mock data. Use IDs like `driver_001`, `driver_002` if the agent asks for one.

---

### Step 7 — Save

Click **Create Agent**. The config is saved to `config/agents/driver_bonus.json` and the agent goes **live immediately** — no server restart needed.

---

### Step 8 — Verify in Chat

1. Open `http://localhost:8000`
2. Switch to the **Driver** tab
3. Type: `"Did I qualify for the weekend streak bonus?"`
4. The meta-router should classify and dispatch to your new `driver_bonus` agent
5. The agent name badge below the response will confirm: `🤖 driver_bonus`

---

## Edit an Existing Agent

1. Click the agent in the sidebar
2. Modify the prompt, tools, or description
3. Lint panel updates in real time
4. Click **Save Agent**

Changes take effect on the **next message** — in-flight conversations are not affected.

---

## Delete an Agent

1. Select the agent in the sidebar
2. Click the red **Delete** button (top right)
3. Confirm in the dialog

> After deletion, messages that would have routed to this agent will fall through to `rider_general` or `driver_intent` as a fallback.

---

## Agent Config Format

Each agent is stored as a JSON file in `config/agents/`:

```json
{
  "intent": "driver_bonus",
  "user_type": "driver",
  "description": "Handles driver bonus and incentive inquiries",
  "tools": [
    "get_driver_info",
    "get_driver_earnings",
    "create_support_ticket"
  ],
  "prompt": "## Identity\nYou are a Lyft Driver Bonus support specialist…"
}
```

You can also edit these files directly — the server picks up changes on the next request.

---

## Prompt Writing Tips

1. **Be explicit about scope** — agents should know what they handle and what to escalate
2. **Use phased workflows** — `Phase 1 / 2 / 3 / 4` maps directly to how the ReAct agent thinks
3. **Name the tools you expect** — e.g. "Call `get_driver_earnings` to check stats" makes tool selection more reliable
4. **Set word limits** — `"Keep responses under 150 words"` prevents verbose agent replies
5. **Define the sign-off** — consistent `"Lyft [Team] Support Team"` branding across all agents

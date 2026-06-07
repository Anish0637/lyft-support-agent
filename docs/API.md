# API Reference

Base URL: `http://localhost:8000`

All request and response bodies are JSON. All endpoints return `Content-Type: application/json`.

---

## Health

### `GET /health`

Returns server status.

**Response**
```json
{
  "status": "ok",
  "service": "lyft-support-agent"
}
```

---

## Chat

### `POST /api/chat`

Send a customer message and receive an agent response.

**Request body**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `message` | string | ✅ | The user's message |
| `user_type` | `"rider"` \| `"driver"` | ✅ | Affects routing and agent selection |
| `conversation_id` | string | ❌ | Pass to continue an existing conversation; omit to start a new one |

```json
{
  "message": "I was overcharged on my last trip",
  "user_type": "rider",
  "conversation_id": "abc-123"
}
```

**Response**

| Field | Type | Description |
|-------|------|-------------|
| `response` | string | Agent's reply text |
| `conversation_id` | string | ID to pass in follow-up messages |
| `intent` | string | Classified intent, e.g. `"charge_review"` |
| `agent_name` | string | Sub-agent that handled this message |
| `tool_calls` | array | Tools invoked (see below) |
| `safety_passed` | bool | `false` if the safety gate blocked the message |

```json
{
  "response": "I've reviewed your trip and processed a $13.00 refund…",
  "conversation_id": "abc-123",
  "intent": "charge_review",
  "agent_name": "charge_review",
  "tool_calls": [
    { "name": "get_trip_info",   "result": "..." },
    { "name": "process_refund",  "result": "..." }
  ],
  "safety_passed": true
}
```

---

### `GET /api/conversations`

List all conversation summaries (in-memory, reset on server restart).

**Response**
```json
[
  {
    "conversation_id": "abc-123",
    "user_type": "rider",
    "message_count": 4,
    "preview": "I was overcharged on my last trip"
  }
]
```

---

### `GET /api/conversations/{conversation_id}`

Get the full message history for a conversation.

**Response**
```json
{
  "conversation_id": "abc-123",
  "messages": [
    {
      "role": "user",
      "content": "I was overcharged on my last trip",
      "intent": null,
      "agent_name": null,
      "tool_calls": []
    },
    {
      "role": "agent",
      "content": "I've reviewed your trip…",
      "intent": "charge_review",
      "agent_name": "charge_review",
      "tool_calls": ["get_trip_info", "process_refund"]
    }
  ]
}
```

---

### `DELETE /api/conversations/{conversation_id}`

Delete a conversation from memory.

**Response**
```json
{ "deleted": true }
```

---

## Agents

### `GET /api/agents`

List all configurable agents loaded from `config/agents/`.

**Response**
```json
{
  "agents": [
    {
      "intent": "charge_review",
      "user_type": "rider",
      "description": "Handles charge disputes and refund requests",
      "tools": ["get_trip_info", "process_refund", "create_support_ticket"],
      "prompt": "## Identity\n…"
    }
  ]
}
```

---

### `GET /api/agents/{intent}`

Get a single agent config by intent slug.

**Response** — same shape as a single item from `GET /api/agents`.

**Error (404)**
```json
{ "detail": "Agent 'foo' not found" }
```

---

### `POST /api/agents`

Create a new agent. Saves `config/agents/{intent}.json`.

**Request body**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `intent` | string | ✅ | Snake_case slug, must be unique |
| `user_type` | `"rider"` \| `"driver"` | ✅ | |
| `description` | string | ❌ | One-line summary |
| `tools` | string[] | ✅ | List of tool names from `GET /api/agents/tools` |
| `prompt` | string | ✅ | Full system prompt (min 100 chars) |

```json
{
  "intent": "driver_bonus",
  "user_type": "driver",
  "description": "Handles driver bonus inquiries",
  "tools": ["get_driver_info", "get_driver_earnings", "create_support_ticket"],
  "prompt": "## Identity\nYou are a Lyft Driver Bonus specialist…"
}
```

**Response (201)**
```json
{ "created": true, "intent": "driver_bonus" }
```

**Error (422) — lint errors block save**
```json
{
  "detail": {
    "errors": [
      { "rule": "missing_identity", "message": "No ## Identity section found", "severity": "error" }
    ]
  }
}
```

---

### `PUT /api/agents/{intent}`

Update an existing agent. Same request body as `POST /api/agents` (except `intent` must match the URL param).

**Response**
```json
{ "updated": true, "intent": "driver_bonus" }
```

---

### `DELETE /api/agents/{intent}`

Delete an agent config file.

**Response**
```json
{ "deleted": true, "intent": "driver_bonus" }
```

---

### `GET /api/agents/tools`

List all available tool names that can be assigned to agents.

**Response**
```json
{
  "tools": [
    "get_rider_info",
    "get_trip_info",
    "process_refund",
    "get_driver_info",
    "get_driver_earnings",
    "submit_damage_claim",
    "create_support_ticket",
    "escalate_to_human",
    "send_notification",
    "update_account"
  ]
}
```

---

### `POST /api/agents/lint`

Run static lint checks on a prompt without saving. Used by the builder UI in real time.

**Request body**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `prompt` | string | ✅ | Prompt text to lint |
| `config` | object | ✅ | Partial agent config for context |
| `config.intent` | string | ✅ | |
| `config.user_type` | string | ✅ | |
| `config.tools` | string[] | ❌ | |

```json
{
  "prompt": "You are a support agent. Help the user.",
  "config": {
    "intent": "driver_bonus",
    "user_type": "driver",
    "tools": ["get_driver_earnings"]
  }
}
```

**Response**
```json
{
  "errors": [
    {
      "rule": "missing_identity",
      "message": "No ## Identity section found in prompt",
      "severity": "error"
    }
  ],
  "warnings": [
    {
      "rule": "no_word_limit",
      "message": "Prompt does not specify a response word/length limit",
      "severity": "warning"
    }
  ],
  "passed": false
}
```

---

### `POST /api/agents/test`

Live-invoke an agent config against a test message (does not save).

**Request body**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `message` | string | ✅ | Test message to send |
| `config` | object | ✅ | Full agent config (same shape as `POST /api/agents`) |

```json
{
  "message": "Did I qualify for the weekend streak bonus?",
  "config": {
    "intent": "driver_bonus",
    "user_type": "driver",
    "description": "...",
    "tools": ["get_driver_earnings"],
    "prompt": "## Identity\n…"
  }
}
```

**Response**
```json
{
  "tool_calls": [
    { "name": "get_driver_earnings", "result": "{\"gross\": 842.50, ...}" }
  ],
  "final_response": "Based on your stats this week (32 trips, 28.5 hours)…"
}
```

**Error response**
```json
{
  "tool_calls": [],
  "final_response": "",
  "error": "OpenAI API error: ..."
}
```

---

## Error Codes

| Status | Meaning |
|--------|---------|
| `200` | Success |
| `201` | Created |
| `404` | Agent or conversation not found |
| `422` | Validation error (lint failure or missing fields) |
| `500` | Internal server error |

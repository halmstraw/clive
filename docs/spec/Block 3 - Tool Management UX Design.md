*Experience Agent artefact — produced May 2026.*

---

# Block 3 — Tool Management UX Design

**Version:** v0.1  
**Status:** Design complete — ready for implementation  
**Produced by:** Experience Agent  
**Date:** May 2026  
**Governing decisions:** D-006, D-051, D-053, D-137, D-138  
**Commands specified:** /tools, /tool_disable, /tool_enable

---

## Scope

This document specifies the UX for the three tool management commands introduced
in CLIVE v0.8 (D-137). These commands surface Block 17 (Tool Registry) to the
owner via Telegram. The specification covers response format, confirmation gate
design, error states, and tone.

This is a design document. It does not specify implementation technology. The
Access & Security Agent implements Block 23 (Telegram surface); this document
tells that agent exactly what the owner should see in each state.

---

## Design Principles

**Functional, not conversational.** Tool management is a control-plane operation.
Responses should read like a reliable instrument panel, not a chat assistant.
State clearly, confirm cleanly, acknowledge and stop.

**Concise by default.** Match the personality register (D-051, D-053): short
sentences, no filler, no throat-clearing. The owner already knows what they
asked for — don't explain it back to them.

**Honest about errors.** Error messages name the specific condition. Generic
"something went wrong" messages are not acceptable. If the tool is not found,
say which tool was not found. If the registry is down, say the registry is down.

**Consistent with existing patterns.** The tool management commands follow the
same confirmation gate pattern as /delete (D-109), using the live /confirm_action
and /cancel_action commands. New commands must not introduce new UX conventions
without a recorded decision.

---

## Shared Reference: Tool Registry Fields

The tool_registry table (D-138) contains the following fields. This document
references these fields by name throughout.

| Field | Type | Notes |
|---|---|---|
| tool_name | string (PK) | The identifier used in all commands |
| display_name | string | Human-readable label |
| version | string | Semver string |
| description | string | One-line functional description |
| enabled | boolean | Whether the tool is currently available |
| deprecated | boolean | Whether the tool is deprecated |
| deprecation_note | string or null | Explanation when deprecated is true |
| health_status | string | ok \| degraded \| error |
| permission_scope | array | Not surfaced in owner-facing messages |
| registered_at | timestamp | Not surfaced in owner-facing messages |
| updated_at | timestamp | Not surfaced in owner-facing messages |

permission_scope, registered_at, and updated_at are internal fields. They do
not appear in any owner-facing message.

health_status is surfaced only when it is not "ok" — surface "degraded" or
"error" states only, not the nominal state.

---

## 1 — /tools

### 1.1 Purpose

Lists all registered tools with their status. Gives the owner a complete view
of what CLIVE can and cannot currently do.

### 1.2 Success response — tools exist

**Format:**

```
Tools — {N} registered

`{tool_name}` {version} — {status_label}
{display_name}. {description}

`{tool_name}` {version} — {status_label}
{display_name}. {description}
```

**status_label** is one of:
- `enabled` — tool is active
- `disabled` — tool has been disabled by the owner
- `enabled [deprecated]` — enabled but flagged for replacement
- `disabled [deprecated]` — disabled and flagged for replacement

When health_status is "degraded" or "error", append `[health: {health_status}]`
to the status label, e.g. `enabled [health: degraded]`.

When a tool is deprecated, add a third line to its entry:
```
Deprecated: {deprecation_note}
```

**Blank line** separates each tool entry.

**Example — three tools, one deprecated, one unhealthy:**

```
Tools — 3 registered

`web_search` v1.0 — enabled
Web Search. Search the web for current information.

`reminder` v1.0 — enabled [health: degraded]
Reminder. Set timed reminders and notifications.

`calculate_route` v0.3 — disabled [deprecated]
Calculate Route. Route planning between locations.
Deprecated: use navigation_v2 instead.
```

### 1.3 Empty response — no tools registered

```
No tools are registered.
```

No further explanation. The owner knows how to reach the registry if needed.

### 1.4 Field display rules

| Field | Shown | Notes |
|---|---|---|
| tool_name | Yes | Shown in backticks — this is the identifier used in commands |
| version | Yes | Shown inline on the first line |
| enabled | Yes | Shown as status label |
| display_name | Yes | Shown on the second line, before the description |
| description | Yes | Shown on the second line, after display_name |
| deprecated | Yes | Shown as suffix on status label when true |
| deprecation_note | Yes (conditional) | Shown on a third line when deprecated is true |
| health_status | Conditional | Shown as suffix only when degraded or error |
| permission_scope | No | Internal only |
| registered_at | No | Internal only |
| updated_at | No | Internal only |

### 1.5 Message length and pagination

Telegram enforces a 4096-character message limit.

Estimated character budget per tool entry:
- Standard entry: ~100 characters (two lines + blank separator)
- Deprecated entry: ~140 characters (three lines + blank separator)
- Header: ~25 characters

A list of 35 standard entries uses approximately 3525 characters, within limit.
At 40 entries the list approaches the limit; at 45 entries it may exceed it.

**Strategy:** If the rendered tool list exceeds 3800 characters, split into
sequential messages. The first message carries the header and as many entries
as fit within 3800 characters. Each continuation message carries a reduced
header: `Tools (continued)` with no count, then the remaining entries.

No pagination commands. Sequential messages are sent automatically. This is a
personal system (D-001) and the tool count is expected to remain well below the
split threshold in normal use. The split mechanism is a safety rail, not a
primary navigation pattern.

---

## 2 — /tool_disable \<name\>

### 2.1 Purpose

Disables a registered tool. When disabled, the tool is unavailable for action
dispatch. Block 13 will reject action events for disabled tools (D-138 criterion
4). The owner re-enables with /tool_enable.

Disabling is reversible. It routes through the Block 9 confirmation gate per
D-138 (criterion 5, explicit) and D-006. The gate prevents accidental command
triggering — one mistyped command should not silently disable a running tool.

### 2.2 Omitted name — usage hint

When the command is sent with no argument:

```
Usage: /tool_disable <tool_name>
Use /tools to see registered tool names.
```

### 2.3 Tool not found

When \<name\> does not match any tool_name in the registry:

```
No tool named {name} is registered.
Use /tools to see registered tool names.
```

The value {name} is echoed exactly as the owner typed it. This helps the owner
spot typos.

### 2.4 Tool is already disabled

When the tool exists but is already disabled:

```
{tool_name} is already disabled.
```

No confirmation gate. No state change. Clean acknowledgement and stop.

### 2.5 Confirmation gate — the prompt the owner sees

After the tool is found and confirmed to be currently enabled, CLIVE sends
the confirmation prompt before any state change occurs. This is the D-006
confirmation gate mediated by Block 9.

**Confirmation prompt format:**

```
Disable {tool_name}?

{display_name} · v{version}
{description}

When disabled, this tool will be unavailable until re-enabled.

/confirm_action — confirm disable
/cancel_action — cancel
```

**Example — disabling web_search:**

```
Disable web_search?

Web Search · v1.0
Search the web for current information.

When disabled, this tool will be unavailable until re-enabled.

/confirm_action — confirm disable
/cancel_action — cancel
```

**Timeout behaviour:** Per Block 9's existing timeout. No response within the
timeout window is treated as /cancel_action. This is a D-006 requirement and
must not be overridden at the Block 23 layer.

**Cancellation response:**

```
Cancelled. web_search remains enabled.
```

### 2.6 Success response — after /confirm_action

```
{tool_name} disabled.
```

Example: `web_search disabled.`

No elaboration. The owner confirmed the action; they know what happened.

---

## 3 — /tool_enable \<name\>

### 3.1 Purpose

Re-enables a registered tool that has been disabled. Mirrors the disable flow.
All confirmation gate requirements apply equally.

### 3.2 Omitted name — usage hint

```
Usage: /tool_enable <tool_name>
Use /tools to see registered tool names.
```

### 3.3 Tool not found

```
No tool named {name} is registered.
Use /tools to see registered tool names.
```

Same pattern as /tool_disable. The value {name} is echoed exactly.

### 3.4 Tool is already enabled

When the tool exists, is not deprecated, and is already enabled:

```
{tool_name} is already enabled.
```

When the tool exists, is enabled, and is also deprecated:

```
{tool_name} is already enabled.
Note: this tool is deprecated. {deprecation_note}
```

The deprecation note is surfaced even in the already-enabled case so the owner
has context. It is not a warning they must act on — it is information.

### 3.5 Confirmation gate — standard (non-deprecated tool)

**Confirmation prompt format:**

```
Enable {tool_name}?

{display_name} · v{version}
{description}

This tool will be available immediately.

/confirm_action — confirm enable
/cancel_action — cancel
```

**Example — enabling reminder:**

```
Enable reminder?

Reminder · v1.0
Set timed reminders and notifications.

This tool will be available immediately.

/confirm_action — confirm enable
/cancel_action — cancel
```

**Cancellation response:**

```
Cancelled. {tool_name} remains disabled.
```

### 3.6 Confirmation gate — deprecated tool

When the tool's deprecated field is true, the confirmation prompt includes the
deprecation note. The owner is allowed to enable the tool; CLIVE surfaces the
risk honestly and stops.

**Deprecated confirmation prompt format:**

```
Enable {tool_name}?

{display_name} · v{version} [deprecated]
{description}

Deprecated: {deprecation_note}

/confirm_action — enable anyway
/cancel_action — cancel
```

**Example — enabling a deprecated tool:**

```
Enable calculate_route?

Calculate Route · v0.3 [deprecated]
Route planning between locations.

Deprecated: use navigation_v2 instead.

/confirm_action — enable anyway
/cancel_action — cancel
```

Key difference: the confirm button text reads `— enable anyway` rather than
`— confirm enable`. This distinguishes a deprecated-tool enable from a routine
enable at a glance. The owner is not blocked, but the word "anyway" makes clear
they are proceeding with full awareness of the deprecation flag.

**Timeout and cancellation** behave identically to the standard enable flow.

### 3.7 Success response — after /confirm_action

Standard tool:
```
{tool_name} enabled.
```

Deprecated tool:
```
{tool_name} enabled. Note: this tool is deprecated.
```

The deprecated flag is repeated on success. This ensures the owner has it in
view immediately after confirmation — not buried in the earlier prompt that has
now scrolled away.

---

## 4 — Shared Error States

These apply across all three commands.

### 4.1 Tool not found

```
No tool named {name} is registered.
Use /tools to see registered tool names.
```

This is the canonical not-found response. Consistent across /tools, /tool_disable,
and /tool_enable. The tool_name the owner typed is echoed; the /tools referral
gives them a recovery path.

### 4.2 Registry unavailable

When Block 17 (Tool Registry) is unreachable — database down, timeout, or
similar infrastructure failure — all three commands respond with:

```
Tool registry is unavailable. Try again shortly.
```

Do not say "something went wrong." Do not say "an error occurred." Name the
component that is unavailable. The owner can infer the scope of the problem
from knowing it is the registry specifically.

This message does not vary by command. It is the same for /tools, /tool_disable,
and /tool_enable.

### 4.3 Unauthorised

**Status: Not enforced until v0.10 (Block 6/7 activation). Design specified now
for consistency — do not implement the enforcement yet.**

When Block 6/7 access control is active and the requesting surface is not
authorised to manage tools:

```
Tool management requires owner access.
```

This is forward-compatible. When v0.10 introduces multi-user trust zones, Block
23 will enforce this path. The message text is defined here so it is consistent
when the enforcement arrives. It must not appear until the enforcement is live.

---

## 5 — Tone and Register

These commands operate at the control-plane level. The register is functional
and direct — closer to a system confirmation dialog than to a conversational
reply. This is consistent with D-051 (trusted advisor) and D-053 (concise by
default): the owner issued a command; CLIVE acknowledges cleanly.

**Rules for this command set:**

- State what will happen, not what is happening. "web_search disabled." not
  "Disabling web_search now..." — the action is synchronous from the owner's
  perspective.

- Echo the tool_name exactly. The owner typed it; repeat it back so they know
  the right tool was matched.

- No hedging. "web_search is already disabled." not "It looks like web_search
  may already be disabled." One declarative sentence.

- No apology language. "No tool named {name} is registered." not "Sorry, I
  couldn't find a tool with that name."

- Error messages name the specific condition. See Section 4 — each error is
  named, not genericised.

- The deprecated tool path is the one exception where information density
  increases. Deprecation is a signal that warrants the extra line. It is not
  filler — it is an honest disclosure.

**Checked against Block 1 personality document (v0.1):**

The personality document specifies: concise by default, short sentences, no
filler, no throat-clearing, say the hard thing when it needs saying, do not
soften uncomfortable assessments.

The confirmation prompts in this document state the consequence of the action
plainly ("When disabled, this tool will be unavailable until re-enabled.") and
stop. The deprecated tool path states the deprecation note and stops. These are
consistent with the character: a colleague with a clear brief, not a chatbot
managing the owner's feelings.

---

## 6 — /help Update

When these commands ship, /help must be updated in the same change set (D-119:
stale help text is treated as a defect).

Additions to the /help command inventory:

| Input | Description |
|---|---|
| /tools | List all registered tools and their status |
| /tool_disable `<tool_name>` | Disable a tool (requires confirmation) |
| /tool_enable `<tool_name>` | Enable a tool (requires confirmation) |

The existing /help rows remain unchanged.

---

## 7 — Implementation Notes for Block 23

This section is addressed to the Access & Security Agent implementing Block 23.

**Command routing:** All three commands are new handlers in the Telegram surface.
They emit events to Block 13, which routes to Block 17 (Tool Registry) for
registry reads and to Block 9 (Action Layer) for the confirmation gate on
disable/enable.

**Confirmation gate mechanics:** The /confirm_action and /cancel_action commands
are already registered and live. The disable/enable flow reuses them. Block 9
owns the gate state; Block 23 sends the confirmation prompt and waits.

**String literals:** The message text in this document is the canonical spec.
Implement it exactly. Minor formatting differences (trailing whitespace, etc.)
are acceptable; word changes require a new version of this document.

**tool_name display in backticks:** Telegram parses backtick-wrapped text as
inline code. This is intentional — tool_name is an identifier, not prose. Use
monospace formatting for tool_name values throughout.

**Atomic state:** Block 9 owns the state transition. Block 23 does not write to
the tool_registry table directly. The enable/disable state change is the result
of a confirmed action flowing through Block 9, not a direct database write from
the Telegram handler.

**Error detection:** Block 23 must distinguish between "tool not found" (returns
not-found response) and "registry unreachable" (returns registry unavailable
response). These are different failure modes and must not be conflated.

---

*Block 3 — Tool Management UX Design v0.1*  
*Experience Agent artefact. Reviewed against Block 1 personality document v0.1.*  
*Next version required for: any change to message text, any new tool management command.*

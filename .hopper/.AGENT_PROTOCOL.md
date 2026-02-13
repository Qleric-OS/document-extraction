# Hopper Agent Protocol (v1.0) 🛰️

This document defines how AI Agents (Cursor, Aider, etc.) should interact with the `.hopper/state.json` file.

## 1. The Golden Rule
**Agents MUST ONLY execute tasks where `agent_directive` is explicitly set to `"READY"`.**

## 2. Directive Glossary
| Directive | Meaning | Agent Action |
| :--- | :--- | :--- |
| **`READY`** | Intent is groomed and authorized. | **EXECUTE NOW.** Focus on `context_files`. |
| **`USER_REVIEW`** | Task is stopped at the Quality Gate. | **DO NOT TOUCH.** Wait for user to release. |
| **`WAIT`** | Blocked by dependencies. | **STAND BY.** Wait for dependencies to finish. |
| **`DONE`** | Task is completed. | **ARCHIVE.** Ignore in current cycle. |

## 3. Best Practices for Agents
1.  **Context Loading**: Look at the `context_files` array. These are the verified files related to the intent.
2.  **Goal Alignment**: Use `goal_description` as the primary definition of "Done".
3.  **Dependency Awareness**: Even if a task is `READY`, check the `dependencies` list to understand the broader context of what was just completed.

## 4. Hand-off Pattern
When a user says: *"Execute Task #ID from @.hopper/state.json"*, the agent should:
1. Read the JSON.
2. Verify `agent_directive == "READY"`.
3. Perform the work described in `prompt`.
4. Ask the user to mark the task as **Completed** in the Hopper UI to trigger the next step in the pipeline.

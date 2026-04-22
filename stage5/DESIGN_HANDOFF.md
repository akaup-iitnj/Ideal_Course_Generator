# Stage 5 UI — design handoff

Paste your Claude design output here (or attach screenshots) so implementation stays aligned.

## Developer mapping (API / form)

| UI region | Data field or API key | Notes |
|-----------|------------------------|--------|
| Course title | `course_title` | POST body |
| PDF path | `pdf` (optional) | `null` if empty |
| Mode: Full | `from_stage1`: false, `heygen_only`: false, `no_heygen`: false | default |
| Mode: From stage1 | `from_stage1`: true | others false |
| Mode: HeyGen only | `heygen_only`: true | |
| Mode: No HeyGen | `no_heygen`: true | |
| Force HeyGen | `force_heygen` | bool |
| Force batch1 | `force_stage1` | bool |
| Job id | `id` in response | GET poll `/api/jobs/{id}` |
| Status line | `status` + `current_step` | |
| Log | `log` | may truncate on server |
| Error | `error` | on failure |

## Design tokens (from designer — fill in)

| Token | Value |
|-------|--------|
| Family |  |
| Background |  |
| Surface / card |  |
| Border |  |
| Text primary / secondary |  |
| Accent |  |
| Danger |  |
| Code background |  |
| Spacing scale |  |
| Radii |  |

## Wireframe / notes

_(Paste ASCII wireframe or link.)_

## Component / state notes

_(e.g. empty status card, running, complete, error.)_

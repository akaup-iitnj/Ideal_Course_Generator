# Prompt for “Claude design” (Course Generator / Stage 5 UI)

Use the block below in Claude (design/spec mode) or any design tool. Choose one visual direction in the bracketed line and an optional brand color.

---

```text
You are a senior product designer. Design a single-page web UI for a desktop-first internal tool: “Udemy Course Generator — Batch runner.”

**Product (keep behavior, improve presentation)**  
- Users run a long-running “pipeline” job on a server: PDF → scripts → TTS/Stage1 → optional HeyGen video.  
- The page has: (1) Course title (text), (2) optional server PDF path (text; placeholder explains empty = default PDF in a folder), (3) Mode: radio group with exactly four options — “Full: extract + scripts + stage1 + HeyGen”, “From stage1: skip extract, run batch + HeyGen”, “HeyGen only”, “No HeyGen (local MP4s only)”, (4) two optional checkboxes: “Force re-render HeyGen” and “Pass --force to batch1 (compatibility)”, (5) primary action “Start job” (disabled while a job is running), (6) a status area that appears after start: job ID, human-readable current step, scrollable log (monospace), error line in destructive styling. Polling every 2s; show subtle “updating…” or last-updated time—no WebSockets.

**Users & tone**  
- Power users (course authors / ops). Clear labels, no marketing fluff. Technical but friendly. Explain risky options (e.g. force flags) in one line of helper text.

**Visual direction (pick a cohesive system)**  
- [Choose one: “Dark devtools / GitHub-like” | “Calm light SaaS” | “High-contrast accessible”]  
- [Optional brand: primary accent #______; prefer neutral grays, one accent, one danger color.]  
- Generous spacing, 12–16px base grid, 8px minimum tap targets where relevant.

**Layout**  
- Single column on small screens; on wide screens use a 2-column layout: left = form, right = job status (sticky on desktop) OR stacked with clear section headers.  
- Show empty state for the status card before any job.  
- Running state: primary button disabled, show skeleton or pulsing step line.

**Components to specify**  
- Text field, radio group, checkbox row, primary/secondary buttons, card, inline code path styling, log viewer (height-limited, scroll, optional “Copy log”).  
- States: default, focus-visible rings, error alert if API fails, success when job “complete”.

**Accessibility**  
- WCAG AA contrast, visible focus, labels tied to inputs, don’t rely on color alone for errors.

**Deliverables (must output all)**  
1) Short design rationale (2–3 sentences).  
2) ASCII or structured **wireframe** of the page.  
3) **Design tokens**: spacing scale, radii, shadows (if any), type scale (font family suggestions: system UI stack is OK), and full color roles (background, surface, border, text primary/secondary, accent, danger, code background).  
4) **Component spec**: for each block, list content, default values, and states.  
5) **Responsive**: breakpoints (e.g. <640, 640–1024, >1024) and what moves where.  
6) **Optional**: one “developer handoff” table mapping UI regions to data fields: course_title, pdf, from_stage1, heygen_only, no_heygen, force_heygen, force_stage1, job id, current_step, log, error.

No stock photo placeholders. No lorem for real labels—use the real field names and mode labels above.
```

## After you get a design

Paste tokens, wireframe, and component spec into [DESIGN_HANDOFF.md](DESIGN_HANDOFF.md) (or share them in chat) so the app template in `templates/index.html` can be updated to match.

Optional: a wider product shell (nav + stages 1–5) is not in the default scope; request that as a separate design pass if needed.

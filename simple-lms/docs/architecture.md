# Architecture

A simple LMS built entirely from StoreConnect primitives — Articles, a custom
progress object, theme templates, and hosted video. No app server, no Apex (Flows only).

## The three layers

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. CONTENT — StoreConnect Articles (s_c__Article__c)              │
│    • One Article per lesson, in an article category of            │
│      type "course_lessons".                                       │
│    • Sequence__c gives lesson order (1..N).                       │
│    • Body split across up to 4 fields → 4 paginated "pages":      │
│        body_content + Content_Body_2/3/4_Markdown__c              │
│    • Hosted video embedded in the body (e.g. Vimeo/YouTube).      │
│    • A self-scored quiz lives at the end (Markdown task lists).   │
└─────────────────────────────────────────────────────────────────┘
            │  read (gating, status badges)      ▲  write (completion)
            ▼                                     │
┌─────────────────────────────────────────────────────────────────┐
│ 2. PROGRESS — Lesson_Progress__c (one row per learner+course)    │
│    • Contact__c, Course__c, Lesson_01..NN__c + _Progress__c.     │
│    • custom_data map read by Liquid; updated by the controller.  │
└─────────────────────────────────────────────────────────────────┘
            ▲                                     │
            │  auto-create on enroll              ▼  sync to read-store
┌─────────────────────────────────────────────────────────────────┐
│ 3. AUTOMATION — record-triggered Flows                           │
│    • Auto-create a progress row when a learner enrolls.          │
│    • Sync each progress change to the Postgres replica that      │
│      Liquid reads (s_c__SyncRecordChangesInvocable).             │
└─────────────────────────────────────────────────────────────────┘
```

## Templates and what each does

| Template | Role |
|---|---|
| `templates/snippets/articles/grid.liquid` | **Course dashboard.** Detects access state (public / signed-in-no-membership / member), shows a progress bar or buy CTA, renders lesson cards with **sequential unlocking** (a lesson unlocks only when all prior lessons are `Completed`). |
| `templates/snippets/articles/card.liquid` | A single lesson card: status glyph (○ / ◐ / ● / 🔒), title, sequence. |
| `templates/pages/article.liquid` | **The lesson player.** Paginates the lesson into ≤4 sections with prev/next nav + progress bar; renders Markdown client-side; runs the **self-scored quiz engine**; gates the "Mark as Complete" button until the quiz is checked; fires an "In Progress" beacon on first Next. |
| `templates/controllers/articles/index.liquid` | **The write-back.** Reads `?sequence&articleId&status` and patches the matching `Lesson_NN__c` / `Lesson_NN_Progress__c` fields on the learner's progress row. |
| `assets/lms-pagination.js` / `.css` | Section pagination (prev/next, deep-link via `?step=`, keyboard nav, progress bar). |

## Request flow: completing a lesson

1. Learner finishes the lesson, takes the quiz, clicks **Mark as Complete** — an
   `<a>` to the course index with `?sequence=03&articleId=<path>&status=Completed`.
2. The **controller** (`controllers/articles/index`) runs on that request: finds the
   learner's `Lesson_Progress__c` row (via email → Contact), resolves the Article by
   path, and `{% update %}`s `Lesson_03__c` + `Lesson_03_Progress__c`.
3. The **Sync flow** replicates the change so Liquid sees it immediately.
4. The dashboard re-renders: lesson 3 shows ●, lesson 4 unlocks, progress bar advances.
5. A tiny client script strips the `?status=…` query string from the URL.

## Front-end behavior (the JavaScript)

The lesson player is mostly progressive enhancement — small, namespaced scripts that run
after the page loads. Here's what each does and why:

- **Markdown rendering.** Sections 2–4 are stored as raw Markdown; the `marked.js` CDN
  library converts them to HTML in the browser on load. (Section 1 is server-rendered
  rich text, so video/Liquid tags resolve there.)
- **Section pagination** (`assets/lms-pagination.js`). Shows one section at a time by
  toggling an `is-active` class; wires the top/bottom **Previous/Next** buttons, a
  progress bar/stepper, **left/right arrow** keyboard nav, and **deep-linking** — the
  current step is written to the URL as `?step=N` (via `history.replaceState`, so it
  doesn't spam browser history) and read back on load.
- **Scroll to top on advance.** Because changing sections doesn't reload the page, the
  browser would otherwise keep your scroll position. A handler on **Next** scrolls the
  page back to a `#lms-top` anchor (`scrollIntoView`, with `scrollTo(0,0)` fallbacks) so
  each new step opens at the top.
- **Show/hide controls by context** (a `MutationObserver` watching which section is
  active):
  - On the **last section** the bottom **Next** button is hidden (there's nowhere to go),
    and the **"Complete this lesson"** block — which lives *below* the footer nav — is
    revealed. On earlier sections it's hidden.
- **Quiz engine** (in `pages/article.liquid`, runs after `marked.js`). Detects any list
  whose items contain checkbox options, rebuilds them as radio buttons, and adds **Check
  my answers** (scores `X / N`, marks each option ✓/✗) and **Try again** (resets).
  Scoring is entirely client-side — nothing is sent or stored.
- **Completion gating.** If the lesson contains a quiz, the **Mark as Complete** link
  starts **locked** (a `lms-complete-locked` class dims it, sets `aria-disabled`, and a
  click handler calls `preventDefault`). Pressing **Check my answers** unlocks it — so a
  learner can't mark complete without at least attempting the knowledge check.
- **"In progress" beacon.** The first time the learner clicks **Next** from Section 1, a
  fire-and-forget `fetch` hits the course index with `status=In Progress` to record that
  they've started — without navigating them away.
- **URL cleanup.** After a completion/in-progress write (which uses `?status=…`), a small
  script strips the query string with `history.replaceState({}, '', location.pathname)`
  so a refresh or share doesn't re-trigger the write (SC Liquid has no server-side redirect).

All of it degrades gracefully: the content is real HTML/Markdown, and the gating that
matters for **access** is enforced **server-side** (see the lesson page's lock check and
the dashboard), not by these client scripts.

## What's deliberately simple

- **No per-user enrollment table beyond one flat row** — numbered lesson slots.
- **No server-side quiz scoring** — quizzes are self-scored in the browser; nothing is
  stored. (Great for low-stakes knowledge checks; not for graded exams.)
- **Sequential gating only** — finish lesson N to unlock N+1. No date/drip logic.

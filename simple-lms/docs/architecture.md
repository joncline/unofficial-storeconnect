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

## What's deliberately simple

- **No per-user enrollment table beyond one flat row** — numbered lesson slots.
- **No server-side quiz scoring** — quizzes are self-scored in the browser; nothing is
  stored. (Great for low-stakes knowledge checks; not for graded exams.)
- **Sequential gating only** — finish lesson N to unlock N+1. No date/drip logic.

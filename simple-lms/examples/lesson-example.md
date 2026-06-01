# Example lesson — how to author an Article (and a real starter lesson)

A lesson is one StoreConnect **Article** (`s_c__Article__c`) in an article category
of type `course_lessons`. The lesson player paginates it into up to **4 sections**:

| Section | Article field | Rendered |
|---|---|---|
| 1 | `body_content` (rich text) | **server-side** — put video / Liquid tags here |
| 2 | `Content_Body_2_Markdown__c` | client-side (`marked.js`) |
| 3 | `Content_Body_3_Markdown__c` | client-side |
| 4 | `Content_Body_4_Markdown__c` | client-side — end with the **quiz** |

Set lesson order with **`Sequence__c`** (1, 2, 3, …). Keep video in Section 1 (the
server-rendered field); client-rendered Markdown won't process server-side tags.

The example below is a **real, copy-pasteable starter lesson** — it teaches how to get
the most from this LMS alongside StoreConnect's other features. Use it as lesson 1 of
your own course, or as a template to rewrite.

---

## Section 1 — `body_content` (rich text + video)

```
# Make the Most of Simple LMS

<embed your hosted welcome video here — Vimeo / YouTube / your CDN>

Simple LMS turns Articles into lessons. On its own it delivers content and tracks
completion — but its real power shows when you combine it with the StoreConnect
features you already have: e-commerce, memberships, gated content, the custom-data
pipeline, and your theme's front-end. This lesson shows how, and how to do it securely.
```

## Section 2 — `Content_Body_2_Markdown__c` — Sell it & gate it

```markdown
## 1. Sell the course like any product

- Create the course as a **StoreConnect product** and sell it through your normal
  cart/checkout. No separate billing system.
- On purchase, grant access (next step) — typically by attaching or updating a
  **membership** on the buyer's Account or Contact.

## 2. Gate access with membership

- Use a **membership** as the access key. Your "auto-create progress" Flow fires when
  a learner gains that membership and creates their `Lesson_Progress__c` row.
- The dashboard already branches on access state: **public**, **signed-in without
  access**, and **member**. Non-members see a buy CTA; members see their progress.

## 3. Site pages or a member portal

- The same templates work on a **public storefront page** or inside a **logged-in
  portal**. Gate at the page/controller level using `current_customer` + the
  membership/progress lookup — not by merely hiding markup.
```

## Section 3 — `Content_Body_3_Markdown__c` — Data pipeline & rich UX

```markdown
## 4. The custom-data pipeline

- Progress lives in one object (`Lesson_Progress__c`). Liquid **reads** it via
  `record.custom_data['lesson_03_progress__c']` and **writes** it via the controller's
  `{% update %}`.
- Keep the **sync Flow** active so a write is visible to the storefront immediately
  (StoreConnect's Liquid reads a replica — see the conventions doc).

## 5. Build rich front-end UX

- You have full **Liquid + HTML + CSS + JS**. Read `custom_data` to render progress
  bars, status badges, "continue where you left off" links, a certificate on 100%, etc.
- Reuse StoreConnect's components/utility classes first (`SC-…`, `sc-…`); add your own
  lowercase-prefixed classes only where needed. Keep custom JS in small, namespaced
  modules.
- Quizzes are authored in Markdown and become interactive automatically — no code.
```

## Section 4 — `Content_Body_4_Markdown__c` — Security + wrap-up + quiz

```markdown
## 6. Do it with the highest security

- **Gate on the server, not the client.** Hiding a locked lesson with CSS/JS is not
  protection. Enforce access on the page/controller using `current_customer` and the
  membership/progress lookup (this kit's lesson page refuses to render a locked lesson).
- **Never trust client-supplied identity.** The completion controller writes to the
  **signed-in customer's own** `Lesson_Progress__c` (resolved server-side from their
  email → Contact) — it does not let a URL param choose *whose* record to update.
- **Validate inbound params.** `current_request.params.*` is auto-escaped; `| unescape`
  only what you must, and whitelist values (e.g. accept `status` only from
  `Not Started` / `In Progress` / `Completed`) before using them in `{% update %}`.
- **Don't leak other learners' data.** Query progress by the current customer's
  Contact only; never echo another user's rows.
- **Treat quizzes as low-stakes.** Scoring is client-side and nothing is stored — great
  for reinforcement, never for grading, certification, or anything security-sensitive.
- **Load assets from trusted sources** and keep dependencies minimal.

## Key takeaways

- Sell with e-commerce, gate with membership, deliver with Articles, track with one
  custom object, and present with your theme — all native StoreConnect.
- Security is server-side: access checks and write-backs are driven by the
  authenticated customer, not by client input.

<!-- ⚠️ The [x] marks the answer key; edit by moving the x. -->

### Quiz — Make the Most of Simple LMS

1. The most secure way to keep a learner out of a locked lesson is to:
   - [ ] hide the lesson card with CSS
   - [ ] remove the link with JavaScript
   - [x] enforce the access check server-side on the page/controller

2. When recording completion, whose progress record should the controller update?
   - [ ] whichever record an `articleId` / `contactId` URL param points to
   - [x] the signed-in customer's own record, resolved server-side

3. True or False: the self-scored quizzes in this kit are safe to use for graded exams.
   - [ ] True
   - [x] False

4. What keeps a storefront write visible to Liquid right away?
   - [ ] nothing — it's instant
   - [x] the sync Flow that replicates changes to the read-store
   - [ ] re-saving the record by hand
```

When rendered, Section 4 shows the wrap-up, then the interactive quiz, then (below the
nav) the **Mark as Complete** button — locked until the learner presses *Check my answers*.

See `docs/quizzes.md` for the quiz convention and `examples/quiz-test-harness.html`
to preview a quiz in your browser.

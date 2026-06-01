# Simple SC LMS

Turn StoreConnect **Articles** into a self-paced **learning management system** —
no app server and no Apex (Flows only). Built entirely from StoreConnect primitives:
Articles for lessons, a custom object for progress, theme templates for the UI, and
your own hosted video.

> Originally built for a gated, cohort-based course at peoplefirstcrm.com and
> generalized here so any StoreConnect store can drop it in.

## What you get

- 📚 **Course dashboard** with three access states — public, signed-in-without-access,
  and member — showing a buy CTA or a live progress bar accordingly.
- 🔒 **Sequential lesson unlocking** — a lesson opens only when all prior lessons are
  `Completed` (defense-in-depth: enforced on both the dashboard and the lesson page).
- 📖 **Paginated lesson player** — up to 4 sections with prev/next, a progress stepper,
  keyboard nav, deep-linking (`?step=`), and scroll-to-top on advance.
- 🎥 **Hosted video** embedded per lesson (Vimeo/YouTube/your CDN).
- ✅ **Self-scored quizzes** authored in plain Markdown (`- [x]` = answer key), scored
  client-side; the **Mark as Complete** button stays locked until the quiz is checked.
- 🟢 **Completion tracking** written back to a single custom object via a Liquid controller.

## Contents

```
simple-lms/
├── README.md                         ← you are here
├── docs/
│   ├── architecture.md               three layers + request flow (start here)
│   ├── storeconnect-liquid-conventions.md   the SC Liquid gotchas this relies on
│   └── quizzes.md                    the Markdown quiz convention + engine
├── salesforce/
│   ├── lesson-progress-object.md     the one custom object to create (fields)
│   └── flows.md                      the two record-triggered Flows
├── templates/                        copy these into your theme (keys shown below)
│   ├── pages/article.liquid          the lesson player + quiz engine + nav
│   ├── controllers/articles/index.liquid   completion write-back
│   └── snippets/articles/
│       ├── grid.liquid               the course dashboard
│       └── card.liquid               a single lesson card
├── assets/
│   ├── lms-pagination.js             section pagination (upload as a theme asset)
│   └── lms-pagination.css            pagination styles
└── examples/
    ├── lesson-example.md             how to author a lesson Article
    └── quiz-test-harness.html        preview/score a quiz in your browser (no org)
```

## Installation & setup

### 1. Create the progress object (Salesforce)
Create `Lesson_Progress__c` with the fields in
[`salesforce/lesson-progress-object.md`](salesforce/lesson-progress-object.md):
`Contact__c`, `Course__c` (picklist), the lesson slots `Lesson_01..NN__c`
(Lookup → Article) and `Lesson_01..NN_Progress__c` (picklist: `Not Started` /
`In Progress` / `Completed`). Ship as many slots as your longest course needs.

### 2. Add the Flows (Salesforce)
Per [`salesforce/flows.md`](salesforce/flows.md):
- **Sync flow (required)** — on every `Lesson_Progress__c` change, call
  `s_c__SyncRecordChangesInvocable` so storefront writes are visible to Liquid.
- **Auto-create flow (recommended)** — create a progress row when a learner enrolls
  (trigger on whatever your store uses to grant access; create-if-missing).

### 3. Create the course content (StoreConnect)
- Add an **article category** of type **`course_lessons`**.
- Add one **Article per lesson**; set **`Sequence__c`** for order; split the body
  across the 4 fields and end the last with a quiz. See
  [`examples/lesson-example.md`](examples/lesson-example.md).

### 4. Upload the assets (StoreConnect admin UI)
Theme assets can't be created via API — upload `assets/lms-pagination.js` and
`assets/lms-pagination.css` through the admin UI, then note their URLs.

### 5. Add the theme templates (StoreConnect)
Create theme template records with these **keys** (no `templates/` prefix, no
`.liquid` suffix) from the files in `templates/`:

| File | Theme template key |
|---|---|
| `templates/pages/article.liquid` | `pages/article` |
| `templates/controllers/articles/index.liquid` | `controllers/articles/index` |
| `templates/snippets/articles/grid.liquid` | `snippets/articles/grid` |
| `templates/snippets/articles/card.liquid` | `snippets/articles/card` |

Also link the pagination CSS in your layout (or paste it into a style block).

### 6. Fill in the placeholders
See **Configuration** below.

## Configuration

Find-and-replace these tokens across the templates:

| Token | Replace with |
|---|---|
| `PAGINATION_JS_URL` | the uploaded `lms-pagination.js` asset URL (in `pages/article.liquid`) |
| `/articles/YOUR-COURSE-INDEX` | the path of your course dashboard page |
| `/products/YOUR-PRODUCT` | your course product/buy URL (dashboard CTA) |
| `Lesson_Progress__c` | your object's API name, **only if** you named it differently |
| `Your Course Title` / tagline / CTA copy | your course's wording (in `grid.liquid`) |
| `total_lessons = 24` | your main-track lesson count (in `grid.liquid`) |

Optional "preview tier" (e.g. an advanced course teaser): `grid.liquid` shows lessons
`>= 25` in a separate locked "Preview" section. Adjust the `<= 24` / `>= 25` bounds, or
delete that whole section for a single-tier course.

## Using this with an AI assistant

This kit is written to be handed to an AI coding assistant working in **your** org:

1. Point it at this folder and at
   [`docs/storeconnect-liquid-conventions.md`](docs/storeconnect-liquid-conventions.md)
   and [`docs/architecture.md`](docs/architecture.md) for the rules and the model.
2. Ask it to create the `Lesson_Progress__c` object + Flows
   (`salesforce/*.md` are precise enough to follow), then add the theme templates and
   apply the **Configuration** replacements for your course.
3. Have it author lessons from your content following
   [`examples/lesson-example.md`](examples/lesson-example.md) and quizzes per
   [`docs/quizzes.md`](docs/quizzes.md).

The Liquid conventions doc captures the non-obvious `{% query %}` / `custom_data` /
`{% update %}` / routing / replication rules that otherwise cost hours to rediscover.

## Troubleshooting

- **"I marked complete but the page didn't change."** The Sync flow isn't active —
  Liquid reads a Postgres replica; writes are invisible until replicated.
- **`Liquid error: internal` on a query.** Filter keys must be the **lowercased** field
  API name incl. namespace (`contact__c:`, `s_c__path__c:`); SObject names must be the
  **full** API name (`'s_c__Article__c'`).
- **`{% update %}` writes blank.** Don't use `| cast` on custom objects; and `| unescape`
  any `current_request.params.*` before using it.
- **Quiz isn't interactive.** It must render through `marked.js` (Sections 2–4), the
  options must be a nested task list (`- [ ]` / `- [x]`), and `PAGINATION_JS_URL` /
  the pagination assets must be loaded. Preview with `examples/quiz-test-harness.html`.
- **Video doesn't embed.** Keep it in Section 1 (`body_content`, server-rendered);
  client-rendered Markdown sections don't process server-side tags.

## Notes & conventions

- Custom CSS uses a lowercase `lms-` prefix (per the library's convention for custom
  styles that shouldn't collide with `SC-`/`sc-` classes). JS is wrapped in namespaced
  IIFEs. No external dependencies beyond the `marked.js` CDN used for Markdown.
- Quizzes are **client-side, low-stakes** knowledge checks — not graded/proctored exams.

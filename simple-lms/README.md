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

## Accounts & access

Learners get a StoreConnect customer account in any of the usual ways — this LMS plugs
into whichever you choose:

- **Buy a product or membership.** A normal checkout creates (or signs in) the customer
  account. Grant course access by attaching/updating a **membership**; your auto-create
  Flow then creates the learner's `Lesson_Progress__c` row.
- **Free self-signup.** Learners can register at no cost through StoreConnect's standard
  new-account registration controller (`/accounts/register` — plural for registering a
  new account) — handy for free courses, lead magnets, or trial lessons. You decide what
  (if anything) they must buy to unlock more.
- **Manual / admin grant.** Add or remove a learner's membership in Salesforce at any
  time; access and content visibility follow automatically.

Once a learner has access, the gated content becomes visible to them on the storefront,
and they can use it from the signed-in **`/account`** private area (the customer portal).
Sign-in is the standard `/account/sign_in`.

Because enrollment is just Salesforce automation, you can model it however you need:
use **Flows, custom objects, and custom fields** to grant/revoke access, group learners
into cohorts, set start dates, drip content, issue certificates, and more. The only thing
this kit requires is that a learner ends up with a `Lesson_Progress__c` row — see
[`salesforce/flows.md`](salesforce/flows.md).

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

## StoreConnect documentation

This kit builds on standard StoreConnect features — always prefer the official docs at
[support.storeconnect.com](https://support.storeconnect.com) for current, authoritative
guidance. Pages most relevant here:

- **Liquid for theming** — the [Liquid Objects hub](https://support.storeconnect.com/article/Liquid-Objects),
  the [Article object reference](https://support.storeconnect.com/articles/developer-reference/article-liquid-object-reference)
  (lessons), and the [Request object reference](https://support.storeconnect.com/articles/developer-reference/request-liquid-object-reference)
  (reading `current_request.params`).
- **Templates & assets** — [Content block templates](https://support.storeconnect.com/article/content-block-templates)
  and [Theme Assets](https://support.storeconnect.com/article/Theme-Assets) (uploading the pagination JS/CSS).
- **Data sync** — [Find and resolve sync errors](https://support.storeconnect.com/articles/videos-tutorials/how-to-find-and-resolve-sync-errors)
  (the replica/sync behavior the progress write-back depends on).
- **Forms** — [CustomForm object reference](https://support.storeconnect.com/article/custom-form-liquid-object-reference).

For **products, memberships/restricted content, customer accounts & registration,
custom objects/fields, and Flows**, search the support site — those are standard
StoreConnect/Salesforce setup topics rather than anything specific to this kit.

**Migrating an existing course/site?** Use StoreConnect's **Route Mapping** to bring
high-performing or well-known URLs over seamlessly — point a familiar URL at your course
index, keep old links working, and preserve SEO. Mappings are also added automatically as
resources move (e.g. a slug change). Search "Route Mapping" on the support site.

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

# Example lesson — how to author an Article

A lesson is one StoreConnect **Article** (`s_c__Article__c`) in an article category
of type `course_lessons`. The lesson player paginates it into up to **4 sections**
from these fields:

| Section | Article field |
|---|---|
| 1 | `body_content` (the standard rich-text body — **rendered server-side**, so Liquid tags like a video embed work here) |
| 2 | `Content_Body_2_Markdown__c` (Markdown, rendered client-side) |
| 3 | `Content_Body_3_Markdown__c` |
| 4 | `Content_Body_4_Markdown__c` — end with the **quiz** here |

Set the lesson's order with **`Sequence__c`** (1, 2, 3, …).

> **Keep the video in Section 1.** Section 1 is server-rendered, so storefront video
> embeds / Liquid tags resolve there. Sections 2–4 are rendered client-side by
> `marked.js` and won't process server-side tags.

---

## Section 1 — `body_content` (rich text)

```
# Lesson 3 — Giving Effective Feedback

<embed your hosted video here — Vimeo/YouTube/etc.>

Welcome back. In this lesson we cover how to give feedback that lands.
```

## Section 2 — `Content_Body_2_Markdown__c`

```markdown
## Why feedback fails

Most feedback fails because it is vague, late, or about the person rather than
the behavior. ...
```

## Section 3 — `Content_Body_3_Markdown__c`

```markdown
## A simple model

1. Describe the specific behavior.
2. Describe its impact.
3. Agree on a next step.
```

## Section 4 — `Content_Body_4_Markdown__c` (wrap-up + quiz)

```markdown
## Key takeaways

- Be specific, timely, and behavior-focused.

<!-- ⚠️ answer key below is the [x] marker; edit by moving the x -->

### Quiz — Giving Effective Feedback

1. Effective feedback focuses on:
   - [ ] the person's character
   - [x] specific, observable behavior
   - [ ] other team members

2. True or False: feedback is most useful when it is timely.
   - [x] True
   - [ ] False
```

When rendered, Section 4 shows the wrap-up, then the interactive quiz, then (below the
nav) the **Mark as Complete** button — which stays locked until the learner presses
*Check my answers*.

See `docs/quizzes.md` for the quiz convention and `examples/quiz-test-harness.html`
to preview a quiz in your browser.

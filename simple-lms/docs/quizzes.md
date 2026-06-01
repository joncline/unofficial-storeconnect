# Self-scored quizzes

Each lesson can end with an interactive quiz that scores **in the browser only** —
nothing is posted or stored. It's authored in plain **GitHub-Flavored Markdown**, so
non-devs can write quizzes with no special tooling.

## Authoring convention

A quiz is a numbered list; each question's options are a **nested task list**; the
correct option is `- [x]` and the rest are `- [ ]`:

```markdown
1. Which statement is true about onboarding?
   - [ ] It ends on day one
   - [x] It is an ongoing process
   - [ ] It is optional

2. True or False: feedback should be specific.
   - [x] True
   - [ ] False
```

- The `- [x]` marker **is** the answer key. To change an answer later, move the `x`.
- Put the quiz Markdown at the end of the lesson's last content field
  (`Content_Body_4_Markdown__c`). Anything that renders through `marked.js` works.
- Tip: keep the answer key out of the rendered page by leading the quiz with an HTML
  comment (Markdown passes it through; the engine ignores it and browsers don't show
  it). Useful for an editor note like "⚠️ answers provisional".

## How it works

The engine in `templates/pages/article.liquid` runs **after** the `marked.js` pass.
It finds any `<ol>` whose items contain checkbox options (a structure that only ever
appears in a quiz), converts the options to radio buttons, and:

- **Check my answers** → shows `X / N`, marks each option ✓/✗, keeps questions visible.
- **Try again** → resets.
- If a lesson has a quiz, the **Mark as Complete** button stays locked until
  *Check my answers* is pressed (so learners can't skip the knowledge check).

No configuration, no IDs — drop the Markdown in and it becomes interactive.

## Try it without an org

Open `examples/quiz-test-harness.html` in a browser. It loads `marked.js` and the
exact engine from the lesson template, renders a sample quiz, and scores it — a fast
way to preview styling and behavior or to validate a quiz you wrote.

## Scope

This is for **low-stakes knowledge checks** — self-paced reinforcement. Because
scoring is client-side and nothing is saved, it is **not** suitable for graded or
proctored exams. (Completion is still tracked separately via the progress object.)

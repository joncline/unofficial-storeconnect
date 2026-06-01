# Data layer — the `Lesson_Progress__c` custom object

This LMS tracks per-learner, per-lesson progress in **one custom object** with a
fixed set of lesson "slots". It is the only schema you must create; everything
else is theme templates.

> **Naming.** This kit uses the API name `Lesson_Progress__c` throughout the
> Liquid. If you name your object differently, find-and-replace `Lesson_Progress__c`
> in `templates/controllers/articles/index.liquid` and `templates/snippets/articles/grid.liquid`
> and `templates/pages/article.liquid`. Field API names below are referenced by the
> Liquid exactly as written — keep them.

## Object

| | |
|---|---|
| Label | Lesson Progress |
| API name | `Lesson_Progress__c` |
| One record per | learner **+** course (e.g. one row per Contact enrolled in a course) |

## Fields

| Field (API name) | Type | Purpose |
|---|---|---|
| `Contact__c` | Lookup(Contact) | The learner. The storefront finds the row via the signed-in customer's email → Contact → this lookup. |
| `Course__c` | Picklist (text) | Which course this row tracks (lets one Contact have rows for multiple courses). |
| `Program__c` | Picklist (optional) | Optional higher-level grouping (e.g. a bundle). Not required by the templates. |
| `Lesson_01__c` … `Lesson_NN__c` | Lookup(Article → `s_c__Article__c`) | One slot per lesson position. Stores the Article completed at that position. Create as many as your longest course needs (this kit ships with 30). |
| `Lesson_01_Progress__c` … `Lesson_NN_Progress__c` | Picklist | The status for that lesson position. |

### Progress picklist values (exact strings — the Liquid compares against them)

- `Not Started`
- `In Progress`
- `Completed`

A blank value is treated the same as `Not Started`.

### Why fixed `Lesson_NN` slots instead of child rows?

StoreConnect's Liquid reads a **Postgres replica** of Salesforce, and `{% query %}`
returns a record's custom fields via a single `custom_data` map. A flat object with
numbered slots lets the storefront read/write any lesson by **building the field name
as a string** (`'lesson_' | append: seq | append: '_progress__c'`) and indexing
`record.custom_data[...]`. No child-object joins, no per-lesson queries. It caps a
course at the number of slots you create (30 here), which is fine for most courses.

## How the storefront addresses these fields

- **Read** (dashboard + lesson gating): `record.custom_data['lesson_03_progress__c']`
  — note the **lowercased** field API name, the rule for `custom_data` access.
- **Write** (Mark Complete / In Progress): the controller builds the **cased** field
  name (`Lesson_03_Progress__c`) and uses `{% update record, field: ..., value: ... %}`.

## Replication note (important)

A freshly written `Lesson_Progress__c` row is **invisible** to Liquid `{% query %}`
until StoreConnect replicates it into its Postgres read-store. Keep the
**Sync flow** (see `flows.md`) active so writes show up immediately. Without it,
a learner can complete a lesson and not see the change until the next periodic sync.

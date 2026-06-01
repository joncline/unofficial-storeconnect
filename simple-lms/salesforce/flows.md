# Automation — record-triggered Flows

Two pieces of automation make the data layer work. Both are standard Salesforce
**record-triggered Flows** — no Apex required.

## 1. Sync progress to the storefront (REQUIRED)

**Why.** StoreConnect's Liquid reads a Postgres replica of Salesforce. A row your
storefront just wrote (or that an admin edited) is invisible to `{% query %}` until
it is replicated. This Flow forces an immediate replicate on every change.

**Flow:** record-triggered on `Lesson_Progress__c`, **after insert and after update**,
no entry conditions (fire on every change). Single action: call the StoreConnect
invocable that re-syncs a record to the read-store:

- **Apex action / invocable:** `s_c__SyncRecordChangesInvocable`
- **Input:** the triggering `Lesson_Progress__c` record (its Id).

That's the whole Flow. Keep it **Active**. This is the single most important piece
for "I marked it complete but the page didn't update."

## 2. Auto-create a progress row when a learner enrolls (RECOMMENDED)

**Why.** A learner with no `Lesson_Progress__c` row sees every lesson as locked /
not-started and can't record progress. You want a row created automatically the
moment they gain access, however your store grants access.

**Pattern** (adapt the trigger to your access model):

- Record-triggered Flow on whatever object signals enrollment — e.g. the Account or
  Contact gaining a membership, or an Order/Order Item for the course product.
- Use **"only when a record is updated to meet the condition"** so it fires on the
  *transition* into access, not on every save.
- In the Flow: query for an existing `Lesson_Progress__c` for that Contact + Course;
  **create one only if none exists** (idempotent — safe against re-triggers and
  duplicate enrollments).
- Set `Contact__c`, `Course__c` (and `Program__c` if you use it). Leave the
  `Lesson_NN_Progress__c` fields blank — blank reads as "Not Started".

> The reference implementation used two Flows because access was granted on the
> **Account** (membership) and Contacts could also join an existing member Account —
> two transition paths to the same "create a PCP if missing" logic. Model whichever
> path(s) match how *your* store sells the course (most stores: trigger on the Order
> Item for the course product).

## Deploy note

Flows deploy as **Draft** regardless of `<status>Active</status>` unless the org
setting *Setup → Process Automation Settings → "Deploy processes and flows as active"*
is enabled. Until then, activate each new version manually in Flow Builder after deploy.

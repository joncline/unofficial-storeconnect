# StoreConnect Liquid conventions used by this kit

These are the non-obvious SC Liquid rules this LMS depends on. They cost real
debugging time to discover — worth reading before you adapt the templates. Several
are general-purpose and useful well beyond an LMS.

## `{% query %}` — querying SObjects from Liquid

```liquid
{% query 'Lesson_Progress__c' as rows, contact__c: my_contact.sfid %}
```

- **SObject argument is the full SF API name, including any managed-package namespace.**
  `'s_c__Article__c'` works; `'Article'` does not — even though the friendly Drop name
  works for `current_article.*`.
- **Filter-key argument is the lowercased SF field name, including namespace prefix:**
  `s_c__path__c:`, `contact__c:`, `email:`. Uppercase or namespace-stripped variants
  throw `Liquid error: internal`.
- **Property access on the resulting Drop uses the same lowercased API name:**
  `r.s_c__path__c`, `r.contact__c`.

## Reading custom fields — `custom_data`

A queried custom record exposes its fields through a `custom_data` map keyed by the
**lowercased field API name**:

```liquid
{{ record.custom_data['lesson_03_progress__c'] }}
```

This is what lets the LMS address a lesson slot by building the key as a string:
`'lesson_' | append: seq | append: '_progress__c'`.

## Writing custom fields — `{% update %}`

```liquid
{% update record, field: 'Lesson_03_Progress__c', value: 'Completed' %}
```

- On **custom / managed-package objects** (like `Lesson_Progress__c`), use `{% update %}`
  **without** `| cast` — `cast` silently returns blank on those objects.
- Built-in Drops (Contact, Account) *do* need `| cast`.
- `current_request.params.*` is **auto-HTML-escaped on read** — always `| unescape`
  before using a param in an `{% update %}` value or a query filter.

## Articles

- The article URL slug lives in **`s_c__Path__c`** (not `s_c__Slug__c`). The
  `current_article.identifier` Drop attribute returns the Path value.
- `current_article.sfid` renders **blank**. To get an Article's SF Id, query it by
  path and read `.sfid` off the queried Drop (the controller does exactly this).

## Routing & redirects

- A custom URL slug routes to `pages/page.liquid` rendering `current_page.body_content`,
  **not** to a same-named `pages/<slug>.liquid`. To customise, branch on
  `current_page.slug` inside `pages/page.liquid`.
- There is **no server-side redirect tag** in SC Liquid. After a write that used
  `?param=…`, strip the query string client-side:
  `history.replaceState({}, '', location.pathname)` (the dashboard snippet does this).

## Theme records & assets

- Theme templates are Salesforce records. A template's **key stores no `templates/`
  prefix and no `.liquid` suffix** (e.g. key `pages/article`). Pushing with the raw
  repo path creates an orphan record.
- **Theme assets cannot be created via API** — upload JS/CSS through the StoreConnect
  admin UI, then reference the resulting asset URL. (That's why this kit ships the
  pagination JS/CSS as files you upload, and the lesson template references them by a
  `PAGINATION_JS_URL` placeholder you fill in.)

## Replication timing

Liquid `{% query %}` reads a **Postgres replica** of Salesforce, not the live row.
A record you just wrote is invisible until replicated — keep the **Sync flow**
(`salesforce/flows.md`) active so storefront writes appear immediately.

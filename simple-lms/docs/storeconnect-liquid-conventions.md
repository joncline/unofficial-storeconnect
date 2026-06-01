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
- For **real URL redirects/migration**, use StoreConnect's **Route Mapping** feature
  (not Liquid): it maps existing/known/high-traffic URLs to StoreConnect resources so
  they keep resolving (preserving SEO + bookmarks), and route mappings are added
  automatically as resources move (e.g. a slug change). Handy for pointing a
  well-known URL at your course index. Search "Route Mapping" on support.storeconnect.com.
- **Account routes: plural vs singular.** Use **`/accounts/register`** (plural) to
  register a *new* account; use **`/account/...`** (singular) for an existing/known
  account — e.g. `/account/sign_in` and the `/account` private portal area.

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

## Official references

These conventions are distilled from real use; for authoritative, current detail see
[support.storeconnect.com](https://support.storeconnect.com):

- [Liquid Objects hub](https://support.storeconnect.com/article/Liquid-Objects) — `{% query %}`, `custom_data`, and the object/filter naming used above.
- [Article — Liquid Object Reference](https://support.storeconnect.com/articles/developer-reference/article-liquid-object-reference) — `identifier` / `s_c__Path__c`, and Article attributes.
- [Request — Liquid Object Reference](https://support.storeconnect.com/articles/developer-reference/request-liquid-object-reference) — `current_request.params` (the auto-escape rule).
- [Content block templates](https://support.storeconnect.com/article/content-block-templates) — template keys & structure.
- [Theme Assets](https://support.storeconnect.com/article/Theme-Assets) — uploading/referencing JS & CSS.
- [Find and resolve sync errors](https://support.storeconnect.com/articles/videos-tutorials/how-to-find-and-resolve-sync-errors) — the replica/sync behavior.

> Verify any deep link against the live support site — StoreConnect's docs may move or
> add pages over time.

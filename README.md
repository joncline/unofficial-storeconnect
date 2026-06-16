# unofficial-storeconnect

Community-built tools, templates, and patterns for [StoreConnect](https://storeconnect.com)
stores — practical building blocks for other builders to learn from and adapt to their
own orgs.

> ⚠️ **Unofficial and provided "AS IS."** This is an independent, community-built project —
> **not** affiliated with, endorsed, or supported by StoreConnect. Everything here is
> shared **without warranty of any kind**; you assume all risk for evaluating, securing,
> and operating it in your own org. See the [Disclaimer](#disclaimer) and
> [`LICENSE`](LICENSE).

## Contents

Each folder is a **self-contained project** with its own README, setup instructions, and
(where useful) a `CLAUDE.md` agent brief — written to be adaptable to any StoreConnect
org, including by an AI assistant working directly in your store.

| Folder | What it is |
|---|---|
| [`simple-lms/`](simple-lms/) | A self-paced learning management system built from StoreConnect primitives (Articles, a progress object, theme templates, Flows). |
| [`site-migration/`](site-migration/) | Replicate a StoreConnect store from one org into another — or copy one within an org — catalog, content, theme, and POS, via the `sf` CLI. |
| [`ai-content-agent/`](ai-content-agent/) | A safe, scoped **API-only user** pattern for letting an AI agent edit StoreConnect content without access to pricing, orders, or customers. |

## StoreConnect documentation

These projects build on standard StoreConnect features — always prefer the official
docs at [support.storeconnect.com](https://support.storeconnect.com) for current,
authoritative guidance. Useful starting points:

- [Liquid Objects hub](https://support.storeconnect.com/article/Liquid-Objects),
  [Article object reference](https://support.storeconnect.com/articles/developer-reference/article-liquid-object-reference),
  [Request object reference](https://support.storeconnect.com/articles/developer-reference/request-liquid-object-reference)
- [Content block templates](https://support.storeconnect.com/article/content-block-templates),
  [Theme Assets](https://support.storeconnect.com/article/Theme-Assets)
- [Find and resolve sync errors](https://support.storeconnect.com/articles/videos-tutorials/how-to-find-and-resolve-sync-errors)

## Found this useful?

⭐ **If this helped, please star the repo** — it helps other StoreConnect builders find it.

## See StoreConnect in action

- **Events & meetups:** [storeconnect.com/articles/events](https://storeconnect.com/articles/events)
  — demos, webinars, and community events where you can see StoreConnect live.
- **Connect with StoreConnect:**
  [LinkedIn](https://www.linkedin.com/company/storeconnect) ·
  [X / Twitter](https://x.com/storeconnecthq) ·
  [YouTube](https://www.youtube.com/channel/UCngKdP2x8l1wcbAKW3tvU8g)

> Reminder: this is an **unofficial** community project (see Disclaimer). StoreConnect's
> own channels above are the best source for product news and official support.

## License

Released under the **MIT License** — see [`LICENSE`](LICENSE). Copyright (c) 2026 Jon Cline.
You are free to use, copy, modify, and distribute it, including commercially, provided
the copyright notice and license are retained.

## Disclaimer

**Unofficial and independent.** This is a community-built, open-source project. It is
**not** an official StoreConnect product and is **not** affiliated with, endorsed,
sponsored, certified, or supported by StoreConnect or any of its parent, related, or
affiliated companies. "StoreConnect," "Salesforce," and any other marks are the property
of their respective owners and are used here for identification and interoperability
purposes only.

**No warranty; no liability; all risk assumed by you.** This software is distributed
under the MIT License (see [`LICENSE`](LICENSE)), whose terms govern its use. As stated
there, the Software is provided **"AS IS", WITHOUT WARRANTY OF ANY KIND**, express or
implied, including but not limited to the warranties of merchantability, fitness for a
particular purpose, and noninfringement; and **in no event shall the authors or copyright
holders be liable** for any claim, damages, or other liability arising from, out of, or in
connection with the Software or its use. You assume the entire risk for evaluating,
securing, and operating it in your own environment.

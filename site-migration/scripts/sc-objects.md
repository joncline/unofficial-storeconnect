# StoreConnect Object Reference

Field notes from `sf sobject describe` so you don't have to run them again.  
Org: `sc-council-demo` · API version: `v62.0`

---

## s_c__Media__c

Stores images, videos, and other media. StoreConnect fetches and processes the asset from `s_c__Import_Url__c` asynchronously after record creation.

**Required fields:**
| Field | Type | Notes |
|---|---|---|
| `s_c__File_Type__c` | Picklist | **Required by validation.** Values: `image`, `video`, `document`, `file`, `url` |

**Key fields:**
| Field | Type | Notes |
|---|---|---|
| `Name` | String | Writable. Use a descriptive label. |
| `s_c__Identifier__c` | String | **Org-wide unique.** Auto-derived from Name as a slug — always set explicitly with `'media-' + secrets.token_hex(7)` to avoid duplicate errors on re-run. |
| `s_c__Import_Url__c` | String | URL SC fetches to import the asset. Set this instead of uploading a binary. |
| `s_c__Url__c` | URL | CDN URL written back by SC after processing (read-only in practice). |
| `s_c__Alt_Text__c` | String | Accessibility alt text. |

**Linking media to products:** do NOT set a field on Product2 directly. Create an `s_c__Product_Media__c` junction record instead (see below).

**Linking media to a Bookable Location:** set `Media_Id__c` directly on the `s_c__Bookable_Location__c` record.

**Linking media to a Product Category:** set `s_c__Media_Id__c` directly on `s_c__Product_Category__c`.

---

## s_c__Product_Media__c

Junction between `s_c__Media__c` and `Product2`.

**Key fields:**
| Field | Type | Notes |
|---|---|---|
| `Name` | String | **Read-only / auto-generated.** Do not include in POST payload. |
| `s_c__Media_Id__c` | Reference → `s_c__Media__c` | Required in practice. |
| `s_c__Product_Id__c` | Reference → `Product2` | The product this media belongs to. |
| `s_c__Position__c` | Double | Display order. Use `1` for the primary/hero image. |
| `s_c__Category__c` | Picklist | Only valid value is `manuals`. Leave null for standard product images. |

**Resume check:** query `WHERE s_c__Media_Id__c = '...' AND s_c__Product_Id__c = '...'`

---

## s_c__Bookable_Location__c

A physical venue linked to a store. Required timezone field enforced by validation rule.

**Required fields:**
| Field | Type | Notes |
|---|---|---|
| `s_c__Timezone__c` | Picklist | **Required by validation rule.** Use a valid IANA timezone, e.g. `Australia/Sydney`. Full IANA tz list available — see picklist values from describe. |

**Key fields:**
| Field | Type | Notes |
|---|---|---|
| `Name` | String | Location name. |
| `s_c__Display_Name__c` | String | Short display name. |
| `s_c__Store_Id__c` | Reference → `s_c__Store__c` | Store this location belongs to. |
| `s_c__Address1__c` | String | Street address. |
| `s_c__City__c` | String | City. |
| `s_c__State__c` | String | State/Province (text, not a reference). |
| `s_c__Zip_Code__c` | String | Postal code. |
| `s_c__Country_Id__c` | Reference | Country record. Safe to omit. |
| `s_c__Active__c` | Boolean | Set to `True`. |
| `s_c__Virtual__c` | Boolean | `True` for online/virtual locations. |
| `Media_Id__c` | Reference → `s_c__Media__c` | Hero image for the location (direct field, no junction needed). |
| `Location_Account__c` | Reference → `Account` | Optional linked account. |

**Resume check:** query `WHERE Name = '...' AND s_c__Store_Id__c = '...' ORDER BY CreatedDate ASC LIMIT 1`

---

## s_c__Product_Category__c

Groups products. Org-wide (no `s_c__Store_Id__c` field) but scoped to a store via `s_c__Taxonomy_Id__c`.

**Required fields:**
| Field | Type | Notes |
|---|---|---|
| `s_c__Taxonomy_Id__c` | Reference → `s_c__Taxonomy__c` | **Required.** Each store has one taxonomy. Query: `SELECT Id FROM s_c__Taxonomy__c WHERE s_c__Store_Id__c = '<store_id>' LIMIT 1` |

**Key fields:**
| Field | Type | Notes |
|---|---|---|
| `Name` | String | Category name. |
| `s_c__Slug__c` | String | URL slug. |
| `s_c__Introduction_Markdown__c` | Textarea | Short intro shown at top of category page. |
| `s_c__Information_Markdown__c` | Textarea | Full body content. |
| `s_c__Media_Id__c` | Reference → `s_c__Media__c` | Hero image (direct field). |
| `Bookable_Location_Id__c` | Reference → `s_c__Bookable_Location__c` | Optional default location for the category. |
| `s_c__Hide__c` | Boolean | Hide from storefront. |
| `s_c__Position__c` | Double | Display order. |

**Resume check:** query `WHERE Name = 'School Camps' LIMIT 1`

---

## s_c__Products_Product_Categories__c

Junction between `Product2` and `s_c__Product_Category__c`. Relationship name on the category: `s_c__Product_Category_Products__r`.

**Key fields:**
| Field | Type | Notes |
|---|---|---|
| `s_c__Product_Id__c` | Reference → `Product2` | |
| `s_c__Category_Id__c` | Reference → `s_c__Product_Category__c` | |
| `s_c__Active__c` | Boolean | Set to `True`. |
| `s_c__Primary__c` | Boolean | `True` if this is the product's primary category. |
| `s_c__Position__c` | Double | Display order within the category. |

**Resume check:** query `WHERE s_c__Product_Id__c = '...' AND s_c__Category_Id__c = '...' LIMIT 1`

---

## s_c__Taxonomy__c

Scopes a set of product categories to a store. One per store.

**Key fields:**
| Field | Type | Notes |
|---|---|---|
| `s_c__Store_Id__c` | Reference → `s_c__Store__c` | Use to look up the right taxonomy for a store. |

**Lookup pattern:**
```python
taxonomy_id = sf_query(org,
    f"SELECT Id FROM s_c__Taxonomy__c WHERE s_c__Store_Id__c = '{store_id}' LIMIT 1"
)[0]['Id']
```

---

## Product2 (StoreConnect fields)

Standard Salesforce object extended with SC custom fields.

**No required SC fields** (standard SF fields like `Name` and `IsActive` apply).

**Key SC fields for bookable products:**
| Field | Type | Notes |
|---|---|---|
| `s_c__Display_Name__c` | String | Short name shown on storefront. |
| `s_c__Summary_Markdown__c` | Textarea | Product description. |
| `s_c__Slug__c` | String | **Org-wide unique URL slug.** |
| `s_c__Virtual__c` | Boolean | `True` for non-physical/bookable products. |
| `s_c__Is_Master__c` | Boolean | `True` for top-level products (not variants). |
| `s_c__Booking_Duration__c` | Double | Duration in minutes. Leave null for open-ended camps. |
| `s_c__Booking_Start_Buffer__c` | Double | Lead time in minutes before booking. |
| `s_c__Booking_End_Buffer__c` | Double | Buffer after booking ends. |
| `s_c__Booking_Max_Attendees__c` | Double | Max people per booking. |
| `s_c__Booking_Require_Attendee_Details__c` | Boolean | Collect attendee info at booking. |
| `s_c__Charge_Subscription__c` | Boolean | Charge on a subscription basis. |
| `s_c__Sync_To_Google__c` | Boolean | Sync bookings to Google Calendar. |
| `s_c__Condition__c` | String | Typically `'new'`. |
| `s_c__Tax_Category_Code__c` | String | Typically `'None'`. |

**Image association:** create an `s_c__Product_Media__c` record, not a direct field on Product2.

**Resume check:** query `WHERE s_c__Slug__c = '<slug>' LIMIT 1`

---

## s_c__Product_Bookable_Location__c

Junction between `Product2` and `s_c__Bookable_Location__c`. Links a bookable product to its physical venue.

**Key fields:**
| Field | Type | Notes |
|---|---|---|
| `s_c__Product_Id__c` | Reference → `Product2` | The product. |
| `s_c__Bookable_Location_Id__c` | Reference → `s_c__Bookable_Location__c` | **Required.** The venue. |
| `s_c__Max_Bookings__c` | Double | Optional cap on concurrent bookings. |
| `s_c__Min_Bookings__c` | Double | Optional minimum bookings required. |

**Resume check:** query `WHERE s_c__Product_Id__c = '...' AND s_c__Bookable_Location_Id__c = '...' LIMIT 1`

---

## Child relationship names (for SOQL traversal)

| Parent object | Relationship name | Child object |
|---|---|---|
| `s_c__Product_Category__c` | `s_c__Product_Category_Products__r` | `s_c__Products_Product_Categories__c` |
| `s_c__Media__c` | `s_c__Product_Media__r` | `s_c__Product_Media__c` |
| `s_c__Media__c` | `Bookable_Locations__r` | `s_c__Bookable_Location__c` |
| `s_c__Media__c` | `s_c__Media_Categories__r` | `s_c__Product_Category__c` |
| `s_c__Product_Category__c` | `s_c__Child_Categories__r` | `s_c__Product_Category_Hierarchy__c` |

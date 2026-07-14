RIG INTELLIGENCE API — INTEGRATION PACKAGE
==========================================

Base URL:  https://api.rig360media.com/v1
Version:   v1
Auth:      Authorization: Bearer <your key>      (or  X-API-Key: <your key>)

WHAT'S IN THIS PACKAGE
----------------------
1. RIG-Intelligence-API-Reference.pdf
   The full reference — every endpoint, field, and example. Start here.

2. openapi.json
   Machine-readable OpenAPI 3.1 spec. Load it into Swagger UI / Redoc, or
   generate a typed client in your language of choice.

3. RIG-Intelligence-API.postman_collection.json
   Import into Postman for a ready-to-run collection of every endpoint.
   After importing, open the collection's Variables tab and set:
       apiKey  =  <your key>
   Every request is then authenticated automatically.

YOUR API KEY
------------
Your key is NOT in this package. It is delivered separately, once, over a
secure channel. Treat it like a password: never commit it to source control
or paste it into shared tools. If it is ever lost or exposed, contact us and
we will revoke and reissue it.

MANAGING YOUR COVERAGE
----------------------
Your key can configure its own scope (the entities, keywords, regions and
mutes you track) via PATCH /v1/scope — add any entity by name or any keyword,
on demand. See section 5 of the reference PDF.

SUPPORT
-------
Questions and key delivery are handled through your RIG account contact.
Confidential — not for redistribution.

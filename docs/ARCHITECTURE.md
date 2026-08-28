# Architecture

```text
Next.js UI
   ↓ HTTP/JSON
Django REST API
   ↓
Application services
   ↓
Django ORM
   ↓
SQLite (MVP)
   ↓ later
PostgreSQL
```

## Important boundaries

- Frontend never knows the database engine.
- Views/serializers never call SQLite directly.
- All user-owned records are scoped to `request.user`.
- Quiz/case scoring happens on the backend.
- Seed content uses stable slugs, not hardcoded numeric IDs.
- Search is intentionally implemented with portable ORM filters for MVP.
- PostgreSQL-specific full-text search can replace the search service later without changing frontend contracts.

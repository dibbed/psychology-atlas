# PostgreSQL migration

1. Ensure every schema change is represented by Django migrations.
2. Add psycopg.
3. Configure `DB_ENGINE=postgresql`.
4. Create a clean PostgreSQL database.
5. Run `python manage.py migrate`.
6. Run `python manage.py seed_mvp`.
7. Transfer only mutable user-owned data:
   - users
   - bookmarks
   - progress
   - quiz attempts/answers
   - case attempts/answers
8. Resolve content relationships by stable slug during import.
9. Run the complete test suite against PostgreSQL.
10. Add PostgreSQL-only search/index optimizations only after functional parity is verified.

Never assume seeded SQLite PK values will equal PostgreSQL PK values.

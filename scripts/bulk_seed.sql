-- Realistic data volume for Lab 4 / Lab 5 (cache and load tests).
--   docker compose exec -T db psql -U libra -d libra < scripts/bulk_seed.sql
-- Adds 10 000 books, 2 000 members and 300 000 *returned* historical loans
-- spread over the last 365 days (stock is not affected). Idempotent: re-running
-- skips existing ISBNs / e-mails and does not duplicate the history.
\timing on
BEGIN;

INSERT INTO books (isbn, title, author, published_year, total_copies, available_copies)
SELECT '97888' || lpad(g::text, 8, '0'),
       (ARRAY['Clean','Distributed','Domain','Systems','Patterns','Design','Data','Scalable',
              'Reliable','Concurrent','Functional','Modern','Practical','Effective'])[1 + g % 14] || ' ' ||
       (ARRAY['Architecture','Code','Databases','Networks','Algorithms','Microservices',
              'Testing','Security','Operations','Python','Kubernetes'])[1 + (g / 14) % 11] || ' vol. ' || g,
       'Author ' || (g % 700),
       1970 + g % 56,
       1 + g % 5,
       1 + g % 5
FROM generate_series(1, 10000) AS g
ON CONFLICT (isbn) DO NOTHING;

INSERT INTO members (full_name, email, password_hash, max_active_loans)
SELECT 'Bulk Reader ' || g, 'bulk' || g || '@seed.test', 'pbkdf2_sha256$1$x$disabled', 3
FROM generate_series(1, 2000) AS g
ON CONFLICT (email) DO NOTHING;

-- history only once (marker: loans of bulk members)
INSERT INTO loans (member_id, book_id, borrowed_at, due_at, returned_at, fine_amount)
SELECT m.id, b.id, t.borrowed, t.borrowed + interval '14 days',
       t.borrowed + (random() * 20)::int * interval '1 day', 0
FROM (
    SELECT g,
           now() - (random() * 365) * interval '1 day' AS borrowed,
           -- skewed popularity: low book numbers are borrowed far more often
           1 + floor(10000 * power(random(), 3))::int AS book_no,
           1 + floor(2000 * random())::int AS member_no
    FROM generate_series(1, 300000) AS g
) t
JOIN books b ON b.isbn = '97888' || lpad(t.book_no::text, 8, '0')
JOIN members m ON m.email = 'bulk' || t.member_no || '@seed.test'
WHERE NOT EXISTS (SELECT 1 FROM loans l JOIN members mm ON mm.id = l.member_id
                  WHERE mm.email = 'bulk1@seed.test' LIMIT 1);

COMMIT;
ANALYZE books; ANALYZE members; ANALYZE loans;
SELECT (SELECT count(*) FROM books) AS books, (SELECT count(*) FROM members) AS members,
       (SELECT count(*) FROM loans) AS loans;

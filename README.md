# Libra: Library Lending API

Сервіс видачі книг у бібліотеці: читачі (`members`), книги (`books`) і видачі (`loans`).
Стек: **Python 3.12 · FastAPI · SQLAlchemy 2 · Alembic · PostgreSQL 16 · Redis 7 · Docker Compose**.

| Лабораторна | Тема | Розділи README | Git-тег |
|---|---|---|---|
| №1 | System Design та базовий прототип | 2–6 | `lab1` |
| №2 | Stateless-архітектура, винесення стану | 7 | `lab2` |
| №3 | Горизонтальне масштабування та балансування навантаження | 8 | `lab3` |
| №4 | Розподілене кешування | 9 | `lab4` |
| №5 | Навантажувальне тестування, Performance Baseline | 10 | `lab5` |

`git checkout labN` показує стан проєкту після відповідної лаби, а гілка `main` містить поточний
стан (усі лаби).

---

## 1. Швидкий старт

Потрібен лише **Docker Desktop**. Python локально потрібен тільки для демо-скриптів, а k6
для навантажувальних тестів можна запускати теж у Docker (розділ 10).

```bash
git clone <repo-url> libra && cd libra
docker compose up --build -d      # db + redis + cache -> migrate -> app1..app3 -> lb
```

Клієнт бачить **лише балансувальник**: інстанси не мають опублікованих портів.

| Що | URL |
|---|---|
| API (єдина точка входу) | http://localhost:8080 |
| Swagger UI | http://localhost:8080/docs |
| OpenAPI-специфікація | http://localhost:8080/openapi.json |
| Readiness (БД + сесії) | http://localhost:8080/health |
| Дашборд HAProxy (стан вузлів, розподіл) | http://localhost:8404 |

Порядок старту детермінований. Спочатку `db` і сховища Redis проходять healthcheck. Потім
`migrate` один раз виконує `alembic upgrade head` і завершується. Лише після успішних міграцій
стартують `app1..app3`, а за ними `lb`. Інстанси ніколи не виконують міграції паралельно.

```bash
docker compose ps                       # стан контейнерів
docker compose logs -f app1 app2 app3   # логи (кожен рядок містить [app-1] / [app-2] / [app-3])
docker compose down                     # зупинити (дані лишаються у volume)
docker compose down -v                  # зупинити і ВИДАЛИТИ дані
```

Для перевірок лаби 2, яким потрібен прямий доступ до конкретного інстансу, є override-файл, що
публікує порти 8001–8003:

```bash
docker compose -f docker-compose.yml -f docker-compose.direct.yml up -d
```

### Демонстрація

```bash
python scripts/seed.py                               # демо-дані (20 читачів, 50 книг, видачі)
python scripts/demo.py                               # усі основні endpoint-и (лаба 1)
python scripts/cross_instance_check.py               # консистентність між інстансами (лаба 2, override)
python scripts/failover_check.py --kill app1 --restart   # аварійна зупинка інстансу (лаба 2, override)
python scripts/lb_distribution.py                    # розподіл запитів балансувальником (лаба 3)
python scripts/cache_demo.py                         # HIT / MISS / інвалідація / fallback (лаба 4)
```

Скрипти використовують тільки стандартну бібліотеку Python і запускаються з кореня репозиторію.
Для VS Code / JetBrains є колекція запитів [`docs/requests.http`](docs/requests.http).

### Перевірка персистентності

```bash
python scripts/demo.py                       # створили дані
docker compose restart db                    # перезапуск СУБД
# або повністю: docker compose down && docker compose up -d
curl http://localhost:8080/api/v1/books      # дані на місці (volume pgdata)
```

### Тести

Інтеграційні тести (18 шт.) працюють зі справжніми PostgreSQL і Redis:

```bash
pip install -r requirements-dev.txt
set TEST_DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/libra_test   # Windows
set TEST_REDIS_URL=redis://localhost:6379/15
pytest -q
```

---

## 2. Доменний аналіз

### Сутності

| Сутність | Опис | Ключові правила |
|---|---|---|
| **Member** (читач) | Користувач бібліотеки, автентифікується e-mail + паролем | e-mail унікальний (без урахування регістру); `max_active_loans` від 1 до 10 |
| **Book** (книга) | Позиція каталогу з кількістю примірників | ISBN унікальний, 10 або 13 цифр; `0 ≤ available_copies ≤ total_copies` |
| **Loan** (видача) | Факт видачі примірника книги читачу | активна, поки `returned_at IS NULL`; штраф за кожен розпочатий день прострочення |

Зв'язки: `Member 1 — N Loan N — 1 Book` (Loan є асоціативною сутністю з власними атрибутами).

![ER diagram](docs/er-diagram.png)

### Бізнес-правила видачі (`POST /api/v1/loans`)

1. Книга існує і має вільні примірники, інакше `409`.
2. У читача менше активних видач, ніж `max_active_loans`, інакше `409`.
3. У читача немає іншої активної видачі цієї ж книги, інакше `409`. Додатково це гарантує
   частковий унікальний індекс `ux_loans_member_book_active`.
4. `available_copies` зменшується в тій самій транзакції, що створює видачу.

Повернення (`POST /api/v1/loans/{id}/return`): повернути можна лише свою видачу (`403`) і лише
один раз (`409`). Штраф = `FINE_PER_DAY` (5.00) × кількість розпочатих днів прострочення.

---

## 3. Специфікація API

Префікс `/api/v1`, формат JSON. Повна специфікація доступна у Swagger: `/docs`.

| Метод | Endpoint | Опис | Успіх | Помилки |
|---|---|---|---|---|
| GET | `/health` | readiness: з'єднання з БД і Redis | 200 | 503 |
| GET | `/health/live` | liveness: процес живий | 200 | |
| POST | `/api/v1/members` | реєстрація читача | 201 | 409, 422 |
| GET | `/api/v1/members?q=&limit=&offset=` | список із пошуком і пагінацією | 200 | 422 |
| GET | `/api/v1/members/{id}` | читач | 200 | 404 |
| PATCH | `/api/v1/members/{id}` | змінити ім'я або ліміт | 200 | 404, 422 |
| DELETE | `/api/v1/members/{id}` | видалити (якщо немає історії видач) | 204 | 404, 409 |
| GET | `/api/v1/members/{id}/loans?active=` | видачі читача (адмін) | 200 | 404 |
| POST | `/api/v1/books` | додати книгу | 201 | 409, 422 |
| GET | `/api/v1/books?q=&author=&available_only=&limit=&offset=` | каталог із фільтрами | 200 | 422 |
| GET | `/api/v1/books/{id}` | книга | 200 | 404 |
| PATCH | `/api/v1/books/{id}` | змінити, зокрема `total_copies` (з перерахунком `available`) | 200 | 404, 409, 422 |
| DELETE | `/api/v1/books/{id}` | видалити (якщо немає історії) | 204 | 404, 409 |
| POST | `/api/v1/auth/login` | вхід, повертає bearer-токен | 200 | 401, 422, 429 |
| POST | `/api/v1/auth/logout` | інвалідувати токен | 204 | 401 |
| GET | `/api/v1/me` 🔒 | поточний читач | 200 | 401 |
| POST | `/api/v1/loans` 🔒 | **взяти книгу** (бізнес-логіка вище) | 201 | 401, 404, 409, 422 |
| POST | `/api/v1/loans/{id}/return` 🔒 | **повернути книгу**, розрахунок штрафу | 200 | 401, 403, 404, 409 |
| GET | `/api/v1/me/loans?active=` 🔒 | мої видачі | 200 | 401 |
| GET | `/api/v1/reports/popular-books?days=&limit=` | **топ популярних книг** (high-load) | 200 | 422 |

🔒 означає заголовок `Authorization: Bearer <token>`. `POST /loans` також приймає необов'язковий
заголовок `Idempotency-Key` (лаба 2). Кожна відповідь містить заголовок `X-Instance-ID`.

Єдиний формат помилки:

```json
{ "error": { "code": "conflict", "message": "No available copies of this book" } }
```

Коди: `validation_error` (422, з полем `details`), `not_found` (404), `conflict` (409),
`unauthorized` (401), `forbidden` (403), `too_many_attempts` (429),
`dependency_unavailable` (503, Redis недоступний), `internal_error` (500).

### Піковий сценарій навантаження (High-Load Scenario)

**«Ранковий пік + звітність».** Бібліотека анонсує новий бестселер:

1. Сотні читачів одночасно виконують `POST /auth/login` → `GET /books?q=...` → `POST /loans` на
   **одну й ту саму** книгу. Конкурентні записи йдуть в один рядок `books`, і всі вони конкурують за
   блокування цього рядка.
2. Паралельно дашборд бібліотекарів кожні кілька секунд викликає
   `GET /reports/popular-books?days=30`. Це агрегація `loans JOIN books GROUP BY ... ORDER BY count`,
   тобто найдорожча операція читання, вартість якої росте лінійно з кількістю видач.

Найбільше обчислень та I/O дають саме ці дві операції. Їх розбирає розділ 6.

---

## 4. Архітектура

**Стиль:** модульний моноліт із шаровою архітектурою (Layered: Router → Service → Persistence).
Для MVP це обґрунтовано: один домен, одна команда, транзакції охоплюють кілька таблиць (видача
змінює `loans` і `books` атомарно). Шари відокремлені, тож сервіс можна масштабувати
горизонтально (лаби 2–3) без зміни бізнес-логіки.

Схема стану після лаби 1 (один інстанс). Оновлена схема лаби 2 наведена в розділі 7.6.

![Architecture](docs/architecture-lab1.png)

| Компонент | Технологія | Відповідальність |
|---|---|---|
| `app` | FastAPI + Uvicorn | HTTP API, валідація (Pydantic), бізнес-логіка, обробка помилок |
| `migrate` | Alembic | одноразове застосування міграцій схеми перед стартом `app` |
| `db` | PostgreSQL 16 | первинне сховище, обмеження цілісності (FK, UNIQUE, CHECK) |
| `pgdata` | Docker volume | збереження даних між перезапусками контейнерів |

Мережа: усі контейнери в мережі `backend`. Назовні опубліковано лише порт `app:8000`, а БД доступна
тільки всередині мережі. Протоколи: клієнт ↔ app через HTTP/1.1 + JSON, app ↔ db через
PostgreSQL wire protocol (TCP 5432, драйвер psycopg 3, пул з'єднань SQLAlchemy). Черг і зовнішніх
інтеграцій на цьому етапі немає.

### Структура коду

```
app/
  main.py            # збірка застосунку, middleware логування
  config.py          # налаштування з env-змінних
  db.py              # engine, пул з'єднань, сесія на запит
  redis_client.py    # з'єднання зі спільним Redis (лаба 2)
  models.py          # ORM-моделі (Member, Book, Loan)
  schemas.py         # Pydantic DTO + валідація вводу
  errors.py          # доменні винятки -> HTTP-коди
  security.py        # хешування паролів (PBKDF2)
  sessions.py        # сесії входу (лаба 2: у Redis)
  deps.py            # FastAPI-залежності (автентифікація)
  routers/           # HTTP-шар
  services/          # бізнес-логіка (+ login_guard.py: спільний лічильник невдалих входів)
migrations/          # Alembic (DDL): 0001 схема, 0002 idempotency_key
tests/               # інтеграційні тести (pytest + PostgreSQL + Redis)
scripts/             # demo / seed / cross_instance_check / failover_check
docs/                # діаграми, колекція запитів
```

---

## 5. Розподіл відповідальності (RACI)

> Заповніть реальними іменами учасників команди.

| Модуль / артефакт | Учасник 1 | Учасник 2 | Учасник 3 |
|---|---|---|---|
| Доменна модель, міграції (`models.py`, `migrations/`) | **R/A** | C | I |
| Books + Members API (`routers/`, `services/books.py`, `members.py`) | C | **R/A** | I |
| Loans, бізнес-правила, штрафи (`services/loans.py`) | C | I | **R/A** |
| Auth / sessions (`sessions.py`, `security.py`, `deps.py`) | I | **R/A** | C |
| Reports (high-load) | **R/A** | I | C |
| Docker / docker-compose | C | I | **R/A** |
| Тести | R | R | **A** |
| Архітектурна схема, bottleneck analysis, README | **A** | R | R |

R означає «виконує», A «відповідає за результат», C «консультує», I «інформується».

---

## 6. Аналіз вузьких місць (Bottleneck Analysis)

### B1. Звіт `GET /reports/popular-books`: агрегація по всій історії видач

- **Компонент:** PostgreSQL, запит `loans ⋈ books GROUP BY book_id ORDER BY count(*) DESC LIMIT N`.
- **Root cause:** вартість росте як O(кількість видач за період). Індекс `ix_loans_borrowed_at`
  відсікає лише старі рядки, а агрегацію (HashAggregate + Sort) все одно виконує CPU БД на кожен
  запит. Кеш у лабі 1 є **локальним для процесу**, тож кожен інстанс прогріває його окремо, а після
  рестарту кеш порожній (cold start → лавина запитів у БД).
- **Симптоматика:** зростання CPU БД, `p99` звіту з одиниць мс до сотень мс і секунд на мільйонах
  рядків. Довгі запити утримують з'єднання з пулу і погіршують латентність *усіх* інших
  endpoint-ів (див. B3).
- **Напрям виправлення:** спільний кеш (Redis, лаба 2), матеріалізоване представлення або таблиця
  лічильників `book_stats`, що оновлюється при видачі, read-репліка для звітів.

### B2. `POST /loans` на популярну книгу: Lock Contention

- **Компонент:** сервіс видачі та рядок таблиці `books` з `available_copies`.
- **Root cause:** усі конкурентні видачі однієї книги змінюють *один і той самий рядок*. У лабі 1
  вони додатково серіалізуються глобальним `threading.Lock` у процесі, тобто **всі** видачі (навіть
  різних книг) виконуються строго по одній. При кількох інстансах цей lock ще й не діє, і виникає
  race condition (лаба 2 замінює його на `SELECT … FOR UPDATE`).
- **Симптоматика:** пропускна здатність `POST /loans` упирається у стелю ≈ 1 / (час транзакції)
  незалежно від кількості потоків і CPU. `p99` росте лінійно з кількістю конкурентних клієнтів,
  у `pg_stat_activity` видно `wait_event_type = Lock`, CPU при цьому низький.
- **Напрям виправлення:** блокування на рівні рядка БД замість глобального, атомарний
  `UPDATE books SET available_copies = available_copies - 1 WHERE id = ? AND available_copies > 0`,
  коротші транзакції, черга бронювань для «гарячих» книг.

### B3. Вичерпання пулу з'єднань (Connection Pool Exhaustion)

- **Компонент:** SQLAlchemy QueuePool (`pool_size=10`, `max_overflow=5`) ↔ потоки Uvicorn.
- **Root cause:** sync-endpoint-и FastAPI виконуються у threadpool (до 40 потоків), а з'єднань
  лише 15. Повільні запити (B1) і очікування блокувань (B2) утримують з'єднання довше, і решта
  потоків чекає `pool_timeout` (30 с). До того ж PostgreSQL має `max_connections=100` на **всі**
  інстанси разом, що стане обмеженням при масштабуванні.
- **Симптоматика:** раптові «сходинки» latency до 30 с, помилки `QueuePool limit … reached`,
  `500` під навантаженням. Throughput падає, хоча CPU застосунку й БД не завантажені.
- **Напрям виправлення:** підбір розміру пулу під кількість воркерів і інстансів, PgBouncer
  (transaction pooling), `statement_timeout`, винесення звітів на окремий пул або репліку.

### B4. `POST /auth/login`: CPU-bound хешування пароля

- **Компонент:** `security.verify_password` (PBKDF2-SHA256, 200 000 ітерацій).
- **Root cause:** хешування навмисно повільне (≈ 50–150 мс CPU на виклик), щоб ускладнити
  перебір. Хвиля логінів у ранковий пік (сценарій вище) повністю займає CPU застосунку.
- **Симптоматика:** CPU контейнера `app` ~100 %, RPS логіну впирається приблизно в
  `кількість ядер × 10`, решта endpoint-ів на тому самому інстансі теж сповільнюються (CPU throttling
  у контейнері з лімітами).
- **Напрям виправлення:** горизонтальне масштабування compute (лаба 3), rate limiting на логін,
  довші за TTL сесії, щоб рідше логінитися.

### B5. Пошук `GET /books?q=`: `ILIKE '%…%'` + `COUNT(*)` + OFFSET-пагінація

- **Компонент:** PostgreSQL, запит каталогу.
- **Root cause:** шаблон з `%` на початку не використовує B-tree індекс, тому виконується Seq Scan
  таблиці `books`. Для поля `total` виконується окремий `COUNT(*)` того самого фільтра, а великий
  `offset` змушує БД прочитати й відкинути всі попередні рядки.
- **Симптоматика:** `p99` пошуку росте лінійно з розміром каталогу і номером сторінки, підвищений
  I/O (shared buffers read), у `EXPLAIN` видно `Seq Scan on books`.
- **Напрям виправлення:** індекс `pg_trgm` (GIN) або повнотекстовий пошук, keyset-пагінація
  (`WHERE id > :last_id`), приблизний `total`.

---

## 7. Лабораторна №2: Stateless-архітектура

**Мета:** будь-який інстанс сервісу має бути взаємозамінним (*interchangeable worker*), тобто
здатним обробити довільний запит без sticky sessions і без втрати бізнес-стану при раптовій
зупинці будь-якого вузла.

### 7.1. Аудит та класифікація стану (State Audit)

Проаналізовано весь код `app/` у стані тегу `lab1`.

| # | Що | Де (лаба 1) | Категорія | Рішення в лабі 2 |
|---|---|---|---|---|
| 1 | Логи, час обробки запиту (access log) | `main.py`, middleware | **Ephemeral / Local Safe** | лишається локальним; до рядка логу додано `[instance_id]` |
| 2 | Конфігурація з env-змінних | `config.py` | **Ephemeral / Local Safe** | незмінна і однакова для всіх інстансів, тож це не стан |
| 3 | Пул з'єднань SQLAlchemy / Redis | `db.py`, `redis_client.py` | **Ephemeral / Local Safe** | це ресурс процесу, а не бізнес-стан |
| 4 | Об'єкти запиту (ORM-сесія, DTO) | `routers/*` | **Ephemeral / Local Safe** | створюються і знищуються в межах запиту |
| 5 | Читачі, книги, видачі, штрафи | PostgreSQL | **Shared / Externalized** | уже були в БД, без змін |
| 6 | **Сесії входу** `_sessions: dict` | `sessions.py` | **Critical: файлові або in-memory сесії** | ❌ видалено → Redis `session:<sha256(token)>` з TTL |
| 7 | **Глобальний `threading.Lock` при видачі** | `services/loans.py` `_borrow_lock` | **Critical: application-level lock** | ❌ видалено → `SELECT … FOR UPDATE` на рядках `members` і `books` |
| 8 | **Локальний кеш звіту** `_cache: dict` | `services/reports.py` | **Critical: локальний кеш** | ❌ видалено → спільний кеш у Redis з версіонуванням ключів |
| 9 | `threading.Lock` навколо dict-а сесій | `sessions.py` `_lock` | **Critical: static state** | ❌ видалено разом із dict-ом |
| 10 | Захист від підбору пароля | (не було) | **Shared / Externalized** | ➕ лічильник `login_fail:<email>` у Redis (локальний лічильник давав би N × ліміт спроб на N інстансах) |
| 11 | Повторні запити клієнта після збою вузла | (не було) | **Shared / Externalized** | ➕ `Idempotency-Key` зберігається в `loans` в тій самій транзакції |

**Чому лаба 1 не працювала на кількох інстансах** (перевірено запуском коду з тегу `lab1` на
двох процесах):

```
 6. [OK ] I1 (-     ) POST  /api/v1/auth/login        -> 200  login on I1
 7. [FAIL] I2 (-     ) GET   /api/v1/me               -> 401  token from I1 accepted by I2
 8. [FAIL] I2 (-     ) POST  /api/v1/loans            -> 401  borrow on I2
```

Крім того: `threading.Lock` не синхронізує два процеси, тому дві видачі останнього примірника
на різних інстансах могли пройти обидві (від'ємний залишок рятував лише CHECK-обмеження в БД,
і клієнт отримував 409 замість коректної відмови). Кеш звіту на кожному інстансі жив своїм
життям і не інвалідовувався записами з інших вузлів.

### 7.2. Рефакторинг

| Було (лаба 1) | Стало (лаба 2) |
|---|---|
| `sessions._sessions[token] = (member_id, expires)` | `SET session:<sha256> member_id EX 3600` у Redis; у сховищі лежить лише хеш токена |
| `with _borrow_lock:` (один процес) | транзакція PostgreSQL: `FOR UPDATE` на `members` (ліміт видач), потім на `books` (залишок); завжди однаковий порядок блокувань, тому deadlock неможливий |
| `_cache[(days, limit)]` | `report:popular:v{N}:{days}:{limit}` у Redis із TTL 60 с; кожна видача або повернення виконує `INCR report:popular:version`, і всі інстанси одночасно перестають бачити застарілий кеш |
| Redis відсутній | Без Redis сесії неможливі (`503 dependency_unavailable`), а звіт деградує до прямого запиту в БД (`X-Cache: BYPASS`) |
| `/health` перевіряє лише БД | `/health` (readiness) перевіряє БД і Redis та повертає 503 при проблемі; `/health/live` (liveness) лише процес |

Гарантія взаємозамінності: у `app/` немає жодної змінної рівня модуля, яку змінює обробка
запиту. Перевірити можна так: `grep -rn "^_" app/` знаходить лише константи.

### 7.3. Stateless Request Flow: «Взяти книгу» (`POST /api/v1/loans`)

![Request flow](docs/request-flow-borrow.png)

| Етап | Що відбувається | Де живе стан |
|---|---|---|
| **Вхідні параметри** | тіло `{book_id, days}`, контекстний токен `Authorization: Bearer …`, необов'язковий `Idempotency-Key` | у запиті |
| **Вичитування контексту** | `GET session:<sha256(token)>` дає `member_id`; `SELECT … FOR UPDATE` читача і книги | Redis, PostgreSQL |
| **Атомарна зміна стану** | в одній транзакції `INSERT loans (…, idempotency_key)` + `UPDATE books SET available_copies = available_copies - 1`, потім `COMMIT`; після коміту `INCR report:popular:version` | PostgreSQL, Redis |
| **Після запиту** | ORM-сесія закривається (`get_db` → `finally: db.close()`), об'єкти збирає GC, у глобальних змінних нічого не змінено | нічого в пам'яті процесу |

Якщо інстанс загинув після `COMMIT`, але до відповіді, клієнт повторює запит з тим самим
`Idempotency-Key` на інший інстанс і отримує ту саму видачу (`Idempotent-Replayed: true`) без
подвійного списання примірника. Якщо інстанс загинув до `COMMIT`, PostgreSQL відкочує
транзакцію, і повтор виконується як новий запит.

### 7.4. Мульти-інстансне розгортання та ідентифікація

`docker-compose.yml` запускає **два інстанси одного образу** `libra-app` (`app1`, `app2`), спільна
конфігурація задана через YAML-якір `x-app`. Вони відрізняються лише `INSTANCE_ID` і портом
публікації (8001 / 8002), щоб можна було адресувати конкретний вузол. Балансувальник перед ними
буде предметом лаби 3.

Кожна відповідь містить заголовок `X-Instance-ID` (значення `INSTANCE_ID` або hostname
контейнера, якщо змінну не задано):

```bash
curl -i http://localhost:8001/health/live    # X-Instance-ID: app-1
curl -i http://localhost:8002/health/live    # X-Instance-ID: app-2
```

### 7.5. Тестування консистентності та відмовостійкості

#### Cross-Instance Consistency (без sticky sessions)

```bash
python scripts/cross_instance_check.py
```

Скрипт явно надсилає кожен крок на конкретний інстанс. Результат прогону:

```
-- Scenario A: POST -> I1, GET -> I2, PUT(PATCH) -> I2, GET -> I1 --
 1. [OK ] I1 (app-1 ) POST  /api/v1/books                  -> 201  create book
 2. [OK ] I2 (app-2 ) GET   /api/v1/books/102              -> 200  I2 sees the book created on I1
 3. [OK ] I2 (app-2 ) PATCH /api/v1/books/102              -> 200  update on I2
 4. [OK ] I1 (app-1 ) GET   /api/v1/books/102              -> 200  I1 sees the update from I2
-- Scenario B: session created on I1 is valid on I2 --
 5. [OK ] I2 (app-2 ) POST  /api/v1/members                -> 201  register on I2
 6. [OK ] I1 (app-1 ) POST  /api/v1/auth/login             -> 200  login on I1
 7. [OK ] I2 (app-2 ) GET   /api/v1/me                     -> 200  token from I1 accepted by I2
-- Scenario C: business flow alternates between instances --
 8. [OK ] I2 (app-2 ) POST  /api/v1/loans                  -> 201  borrow on I2
 9. [OK ] I1 (app-1 ) POST  /api/v1/loans                  -> 201  retry with same key on I1 -> same loan
10. [OK ] I1 (app-1 ) GET   /api/v1/books/102              -> 200  available_copies = 1 (not 0)
11. [OK ] I1 (app-1 ) GET   /api/v1/me/loans?active=true   -> 200  I1 lists the loan made on I2
12. [OK ] I1 (app-1 ) GET   /api/v1/reports/popular-books  -> 200  report on I1 includes the loan
13. [OK ] I1 (app-1 ) POST  /api/v1/loans/68/return        -> 200  return on I1
14. [OK ] I2 (app-2 ) POST  /api/v1/loans/68/return        -> 409  second return on I2 is rejected
15. [OK ] I2 (app-2 ) GET   /api/v1/books/102              -> 200  available_copies back to 2
-- Scenario D: logout on I2 invalidates the token on I1 --
16. [OK ] I2 (app-2 ) POST  /api/v1/auth/logout            -> 204  logout on I2
17. [OK ] I1 (app-1 ) GET   /api/v1/me                     -> 401  I1 rejects the revoked token
RESULT: PASSED
```

Те саме вручну через curl (Git Bash; у PowerShell пишіть `curl.exe`):

```bash
curl -i -X POST localhost:8001/api/v1/members -H "Content-Type: application/json" \
     -d '{"full_name":"Demo","email":"demo@example.com","password":"password123"}'
curl -s -X POST localhost:8001/api/v1/auth/login -H "Content-Type: application/json" \
     -d '{"email":"demo@example.com","password":"password123"}'            # -> access_token
curl -i localhost:8002/api/v1/me -H "Authorization: Bearer <access_token>"  # 200, X-Instance-ID: app-2
```

#### Restart / Instance Loss

```bash
python scripts/failover_check.py --kill app1 --restart
```

6 клієнтів паралельно виконують цикли «взяти → повернути» на обох інстансах. На ⅓ прогону
`app1` отримує `SIGKILL` (`docker compose kill`), на ⅔ стартує знову. Клієнт, що натрапив на
мертвий вузол, повторює **той самий** запит (з тим самим `Idempotency-Key`) на живому. Наприкінці
скрипт звіряє з сервером кількість видач кожного клієнта та інваріант
`available_copies = total_copies − активні видачі`. Результат прогону:

```
[  5.0s] KILL   -> docker compose kill -s SIGKILL app1
[ 10.0s] START  -> docker compose start app1
requests handled per instance: {'app-1': 714, 'app-2': 953}
client stats: {'failovers': 118}
client 0: borrowed(client)=138  loans(server)=138  active(server)=0  OK
...
client 5: borrowed(client)=141  loans(server)=141  active(server)=0  OK
book: total=1000 available=1000 active_loans=0 -> invariant available = total - active: OK
RESULT: PASSED - no state lost or duplicated
```

Додатково на захисті:
- `docker compose restart redis`: сесії переживають рестарт (AOF + volume `redisdata`), токени
  лишаються дійсними;
- `docker compose stop redis`: `/health` → 503 `degraded`, звіт відповідає з `X-Cache: BYPASS`,
  автентифіковані запити отримують 503 (а не 500), після `start` усе відновлюється без рестарту
  застосунку.

Автоматичні тести лаби 2 (`tests/test_stateless.py`) перевіряють: 20 паралельних видач на 5
примірників дають рівно 5 × 201 і 15 × 409 без жодного app-level lock; ідемпотентний повтор;
спільний кеш та його інвалідацію; спільний лічильник невдалих входів; сесію, що не залежить від
пам'яті модуля.

### 7.6. Оновлена архітектурна схема

![Architecture lab 2](docs/architecture-lab2.png)

Шар застосунку складається з N однакових stateless-контейнерів. Увесь стан, що має пережити
запит, розміщено у двох централізованих сховищах:

| Сховище | Що зберігає | Довговічність |
|---|---|---|
| PostgreSQL | бізнес-дані, ключі ідемпотентності; блокування рядків як механізм узгодженості | volume `pgdata` |
| Redis | сесії (TTL), кеш звітів (TTL + версія), лічильники невдалих входів (TTL) | AOF, volume `redisdata` |

### 7.7. Теоретичні питання до захисту

**Stateless ≠ відсутність даних.** Система має стан (читачі, видачі, сесії), але *процес
застосунку* його не тримає між запитами. Увесь контекст запит або приносить із собою (токен,
`Idempotency-Key`), або отримує зі спільного сховища. Тому вузол можна вбити, додати чи замінити
в будь-який момент, а стан при цьому не втрачається. Стан не зник, він переїхав у шар, який
спроєктований бути надійним (БД з реплікацією, Redis з persistence).

**Ризики прихованої affinity:**
- локальні кеші або `lru_cache` на функціях, що читають змінні дані: різні вузли повертають
  різні відповіді;
- запис файлів на локальний диск контейнера (аватари, експорти): файл є лише на одному вузлі
  (рішення: об'єктне сховище S3/MinIO);
- in-process черги, `BackgroundTasks`, таймери: задача губиться разом із вузлом (рішення: брокер
  повідомлень);
- WebSocket / SSE-з'єднання: «прив'язані» до вузла за природою, тож потрібен pub/sub (Redis) для
  розсилки;
- sticky sessions на балансувальнику: маскують проблему, бо поки вузол живий, усе працює, а при
  його падінні користувачі втрачають сесії;
- локальні лічильники (rate limit, генерація номерів): кожен вузол рахує своє.

**Ціна винесення стану:** +1 мережевий хоп до Redis на кожен автентифікований запит (~0.2–0.5 мс
у локальній мережі); Redis стає критичною залежністю (для production потрібні Sentinel або
Cluster); блокування в БД переносять конкуренцію з процесу в СУБД, що є новим потенційним
вузьким місцем при масштабуванні (див. B2, B3 і лабу 3).

---

## 8. Лабораторна №3: Горизонтальне масштабування та балансування навантаження

### 8.1. Пул backend-сервісів

Три репліки одного образу `libra-app` (`app1`, `app2`, `app3`) зі спільними PostgreSQL і Redis.
Кожна:
- має власний життєвий цикл: окремий контейнер, `restart: unless-stopped`, `stop_grace_period: 15s`
  для коректного завершення in-flight запитів;
- має однакові обмеження ресурсів `cpus: 1.0`, `mem_limit: 512m` і рівно 1 процес Uvicorn, тож
  порівняння 1/2/3 інстансів чесне;
- повертає свій `X-Instance-ID` (`app-1` / `app-2` / `app-3`).

### 8.2. Єдина точка входу: HAProxy

Конфігурація: [`lb/haproxy.cfg`](lb/haproxy.cfg). Чому HAProxy, а не Nginx OSS: HAProxy має
безкоштовні **активні** health checks (`option httpchk`), runtime API і вбудований дашборд.
У Nginx OSS є лише пасивні перевірки (`max_fails`).

**Інкапсуляція:** назовні опубліковано тільки `lb:8080` (API) і `lb:8404` (дашборд). Інстанси та
сховища живуть у приватній мережі `backend` і не мають `ports:`, тому з хоста до них не
достукатися:

```bash
curl http://localhost:8080/api/v1/books   # ✅ через балансувальник
curl http://localhost:8001/health         # ❌ connection refused (порт не опубліковано)
```

HAProxy знаходить інстанси через вбудований DNS Docker (`resolvers docker`), тож після рестарту
контейнера з новою IP-адресою балансувальник підхоплює її автоматично. Реальну IP-адресу клієнта
застосунок отримує в `X-Forwarded-For`.

### 8.3. Алгоритми балансування

Алгоритм і ваги задаються змінними середовища, без редагування конфігу:

| Алгоритм | Як увімкнути | Коли доречний |
|---|---|---|
| Round Robin | `LB_ALGO=roundrobin` (за замовчуванням) | однорідні вузли, короткі однакові запити |
| Weighted Round Robin | `APP1_WEIGHT=3 APP2_WEIGHT=2 APP3_WEIGHT=1` | гетерогенне залізо, canary-реліз (вага 1 з 10) |
| Least Connections | `LB_ALGO=leastconn` | різна тривалість запитів (звіти поряд із CRUD), деградовані вузли |
| IP Hash | `LB_ALGO=source` (+ `hash-type consistent`) | прив'язка клієнта до вузла на рівні L4 (локальні кеші, WebSocket) |

**Live-переключення** (перестворюється лише контейнер `lb`, а backend і дані не зачіпаються):

```bash
LB_ALGO=leastconn docker compose up -d lb             # Git Bash
$env:LB_ALGO="leastconn"; docker compose up -d lb     # PowerShell
python scripts/lb_distribution.py                     # заголовок X-LB-Algorithm покаже новий алгоритм
```

Ваги можна міняти й **без перезапуску** через runtime API:
`docker compose exec lb sh -c "echo 'set weight libra_pool/app1 3' | nc 127.0.0.1 9999"`.

#### Розподіл запитів (`scripts/lb_distribution.py`, GET `/api/v1/books`, 10 паралельних клієнтів)

```
LB algorithm: roundrobin   requests: 300
  app-1      100   33.3%  #############
  app-2      100   33.3%  #############
  app-3      100   33.3%  #############

LB algorithm: roundrobin (weights 3:2:1)   requests: 600
  app-1      300   50.0%  ####################
  app-2      200   33.3%  #############
  app-3      100   16.7%  #######

LB algorithm: source (IP hash)   requests: 300
  app-2      300  100.0%  ########################################

LB algorithm: leastconn   requests: 300
  app-1       96   32.0%  #############
  app-2       97   32.3%  #############
  app-3      107   35.7%  ##############
```

- **Round Robin** дає ідеально рівний розподіл 1:1:1 незалежно від стану вузлів.
- **Weighted RR** відтворює ваги 3:2:1 точно: 50 % / 33 % / 17 %.
- **IP Hash**: усі запити з однієї IP-адреси потрапляють на один вузол. Це sticky-поведінка без
  cookie. Мінус: нерівномірність, коли клієнтів мало або багато з них за одним NAT. Для
  stateless-сервісу така прив'язка не потрібна.
- **Least Connections** на однорідних вузлах поводиться майже як RR (32/32/36 %). Різниця з'являється,
  коли вузли або запити неоднакові (див. нижче).

#### Експеримент з асиметричним навантаженням

На `app-3` увімкнено синтетичну затримку 200 мс на кожен `/api`-запит (`APP3_DELAY_MS=200`, модель
деградованого вузла: повільний диск, «шумний сусід», GC-пауза). Навантаження: k6, 30 VU, 30 с,
`GET /api/v1/books/{id}` ([`load-tests/lb_experiment.js`](load-tests/lb_experiment.js)).

| Метрика | Round Robin | Least Connections |
|---|---|---|
| **Throughput** | 409 req/s | **667 req/s (+63 %)** |
| Avg latency | 73 ms | **45 ms (−38 %)** |
| p50 latency | **5.6 ms** | 29 ms |
| p95 latency | 211 ms | 206 ms |
| p99 latency | **219 ms** | 249 ms |
| Частка запитів на повільному `app-3` | 33.3 % (4118 з 12 354) | **6.7 %** (1334 з 20 058) |
| Avg latency на `app-1` / `app-2` | 5.2 / 5.3 ms | 32.4 / 31.5 ms |
| Avg latency на `app-3` | 208 ms | 224 ms |
| Помилки | 0 % | 0 % |

**Висновки:**
- **Round Robin «сліпий»**: повільний вузол отримує ту саму третину трафіку, тож рівно третина
  запитів чекає ≥ 200 мс. У моделі із замкненим циклом (VU чекає відповіді) третина віртуальних
  користувачів постійно «застрягає» на `app-3`, а швидкі вузли недовантажені (6 мс на запит).
  Звідси низький загальний throughput. p99 тут дорівнює затримці повільного вузла (218 мс).
- **Least Connections** бачить, що на `app-3` накопичуються відкриті з'єднання, і відправляє туди
  лише 6.7 % трафіку. Швидкі вузли беруть на себе більше роботи (з 5 до 32 мс через вищу утилізацію
  CPU), але загальна пропускна здатність зростає на 63 %, а середня затримка падає на 38 %. p99
  трохи зростає, бо запити, що все ж потрапили на `app-3`, конкурують там у черзі.
- **Вибір для Libra:** `leastconn`, бо у сервісу дуже різна тривалість запитів (`GET /books/{id}` ≈
  5 мс проти звіту `popular-books` чи логіну з PBKDF2 ≈ 100 мс). Повільний вузол, що деградує, але
  ще проходить health check, автоматично отримує менше трафіку.

### 8.4. Health Check та відмовостійкість

**Endpoint-и** (розділ 7.2): `GET /health` (readiness) перевіряє з'єднання з PostgreSQL і
сховищем сесій та повертає 503 при проблемі; `GET /health/live` (liveness) перевіряє лише процес.

**Активна перевірка** (`option httpchk`): HAProxy кожні 2 с робить `GET /health`. Після 2 невдач
вузол виключається з пулу (≤ 4 с), після 2 успішних перевірок повертається. Протягом
`slowstart 10s` вага відновленого вузла плавно росте від 0 до 100 %, щоб холодний вузол не
отримав одразу повну третину навантаження.

**Пасивна перевірка** (`observe layer7` + `error-limit 10` + `on-error mark-down`): якщо реальні
запити отримують 10 помилок поспіль (відмова з'єднання, 5xx), вузол виключається негайно, не
чекаючи наступного активного опитування.

**Повтор запиту на іншому вузлі** (`retries 2`, `option redispatch`, `retry-on conn-failure …`):
запит, який не вдалося доставити, прозоро перенаправляється на інший вузол. L7-повтори
(порожня відповідь, 502/503/504) дозволені тільки для GET/HEAD, тож POST ніколи не виконується
двічі. Для безпечних повторів POST із боку клієнта є `Idempotency-Key` (лаба 2).

**Degraded-вузол:** якщо в інстансу пропадає з'єднання з БД, `/health` повертає 503, і HAProxy
виводить його з пулу, хоча процес живий.

#### Симуляція аварії (k6, 30 VU, 25 с, RR, через `lb:8080`)

```bash
k6 run -e DURATION=25s load-tests/lb_experiment.js   # термінал 1
docker compose stop app2                             # термінал 2, на ~7-й секунді
docker compose start app2                            # на ~15-й секунді
```

| Сценарій | Запитів | Помилок 5xx / мережевих | Throughput | p99 |
|---|---|---|---|---|
| `docker compose stop app2` (SIGTERM, graceful) | 13 136 | **0 (0.00 %)** | 524 req/s | 189 ms |
| `kill -9` (crash посеред обробки) | 12 692 | **1 (0.01 %)** | 507 req/s | 198 ms |

Лог HAProxy при crash:

```
Server libra_pool/app2 is DOWN, reason: Health analyze, info: "Detected 10 consecutive errors,
  last one was: L4 unsuccessful connection". 2 active and 0 backup servers left.
Server libra_pool/app2 is UP, reason: Layer7 check passed, code: 200, check duration: 8ms.
  3 active and 0 backup servers online.
```

- **Graceful stop:** Uvicorn отримує SIGTERM, перестає приймати нові з'єднання і дообробляє
  поточні. Нові запити отримують `connection refused`, і HAProxy прозоро повторює їх на
  `app1`/`app3`. Клієнт не бачить жодної помилки.
- **Crash (`kill -9`):** пасивна перевірка виключила вузол за мілісекунди, раніше за активну.
  Єдина помилка припала на запит, який уже обробляв вбитий процес, коли частина відповіді вже
  була в мережі. Такий запит неможливо безпечно повторити на рівні балансувальника.
- Після старту `app2` повернувся в пул автоматично (Layer7 check passed) і поступово отримав
  трафік (slowstart).

### 8.5. Scale-out експеримент: 1 / 2 / 3 інстанси

k6, 50 VU, 20 с, `leastconn`, `GET /api/v1/books/{id}`. Зайві інстанси зупинялися через
`docker compose stop`.

| Інстансів | Throughput | Приріст | Scalability efficiency* | Avg | p50 | p95 | p99 | Помилки |
|---|---|---|---|---|---|---|---|---|
| 1 | 312 req/s | 1.00× | 100 % | 159 ms | 157 ms | 285 ms | 392 ms | 0 % |
| 2 | 627 req/s | **2.01×** | **100 %** | 79 ms | 70 ms | 148 ms | 218 ms | 0 % |
| 3 | 597 req/s | 1.91× | 64 % | 83 ms | 60 ms | 218 ms | 370 ms | 0 % |

\* efficiency = throughput(N) / (N × throughput(1)).

![Scale-out](docs/lab3-scaleout.png)

> **Середовище вимірювань:** стенд, де проводились виміри, має **2 vCPU / 8 GB RAM**, і на тих самих
> ядрах працюють генератор навантаження, HAProxy, PostgreSQL і Redis. На вашому ПК абсолютні
> цифри будуть іншими. Відтворити: `python load-tests/run_lab3.py` (див. розділ 10).

Профіль CPU під час прогону з 3 інстансами (`top`, 50 VU):

```
%CPU  COMMAND
56.2  uvicorn (app)     54.7  uvicorn (app)     26.5  uvicorn (app)
14.1  k6                 7.2  haproxy            ~5   postgres (усі процеси)
load average 3.95 на 2 ядрах; PostgreSQL: 30 з'єднань у стані idle
```

### 8.6. Системний аналіз: що стає наступним bottleneck

1. **Перехід 1 → 2 інстанси дав лінійний приріст (2.01×, efficiency 100 %).** Один процес Python
   обмежений одним ядром (GIL) і власним threadpool, тож при 50 VU черга всередині процесу
   роздувала затримки (p50 157 мс). Другий процес задіяв друге ядро, і затримки впали вдвічі.
2. **Третій інстанс погіршив результат**, бо в стенді лише 2 ядра: три процеси конкурують за CPU
   (load average ≈ 4), додаються перемикання контексту. **Наступним обмеженням тут став CPU
   хоста**, а не БД (PostgreSQL ≈ 5 % CPU, 30 idle-з'єднань) і не балансувальник (HAProxy ≈ 7 %).
   Це класичне «масштабування на одному вузлі»: репліки додають паралелізм лише доти, доки є
   вільні ядра.
3. **У реальному розгортанні** (окремі хости для реплік) наступні обмеження в порядку появи:
   - **Пул з'єднань БД / `max_connections`.** Кожен інстанс тримає до 15 з'єднань (10 + 5
     overflow), а PostgreSQL за замовчуванням має `max_connections = 100`, тож уже на 7 інстансах
     маємо 105 > 100 і помилки `too many clients`. Рішення: PgBouncer (transaction pooling).
   - **Shared Storage Locks** на запис: видачі популярної книги серіалізуються на одному рядку
     `books` (`SELECT … FOR UPDATE`, розділ 6, B2). Додавання інстансів не прискорює запис у
     гарячий рядок, лише подовжує чергу блокувань.
   - **CPU / I/O PostgreSQL** на важких читаннях (звіт, пошук з `ILIKE`). Рішення: кеш (лаба 4) і
     read-репліки.
   - **CPU балансувальника** стане проблемою останнім: HAProxy обробляє десятки тисяч req/s на
     одному ядрі, у нас ≈ 7 % ядра на 600 req/s.

### 8.7. Балансувальник як Single Point of Failure

Зараз `lb` є єдиним контейнером. Якщо він впаде, система недоступна, хоча всі backend-вузли
живі. Шляхи усунення:
- **Keepalived + VRRP:** два HAProxy (active / standby) на різних хостах ділять одну віртуальну
  IP-адресу (VIP). Standby щосекунди отримує VRRP-оголошення і при їх зникненні забирає VIP собі
  (gratuitous ARP) за 1–3 с. Клієнти й DNS нічого не помічають.
- **DNS Round Robin:** доменне ім'я має кілька A-записів (по одному на кожен LB). Це дешево, але
  відмова виявляється повільно (кеш DNS / TTL), і клієнти, що закешували «мертву» IP-адресу,
  отримують помилки.
- **Хмарні керовані LB** (AWS ALB/NLB, GCP LB): відмовостійкість на рівні провайдера, anycast.
- **Комбінація:** DNS → кілька пар Keepalived у різних зонах доступності.

---

## 9. Лабораторна №4: Розподілене кешування

### 9.1. Аналіз і вибір об'єктів кешування

Профіль навантаження бібліотеки: каталог переглядають у десятки разів частіше, ніж змінюють, а
звіт для дашборда опитують кожні кілька секунд. Кандидати оцінено за чотирма критеріями
(виміри на реалістичному обсязі: 10 тис. книг, 300 тис. видач, `scripts/bulk_seed.sql`):

| Endpoint | Читання : запис | Допустима застарілість | Вартість запиту в БД | Рішення |
|---|---|---|---|---|
| `GET /reports/popular-books` | ~1000 : 1 (дашборд) | хвилини | **87 мс** (за рік: JOIN + GROUP BY по 300 тис. рядків), 24 мс (за 30 днів) | ✅ **кешувати**, найбільший виграш |
| `GET /books?q=…` (пошук, сторінки) | ~100 : 1 | секунди | 8–26 мс (`ILIKE '%…%'` = Seq Scan + `COUNT(*)`) | ✅ **кешувати** |
| `GET /books/{id}` (картка) | ~50 : 1 | 0 (наявність примірників) | ~1 мс (PK lookup) | ✅ кешувати, бо це найчастіший запит; свіжість гарантує інвалідація |
| `GET /me`, `GET /me/loans` | низька повторюваність, персональні | 0 | дешеві, за індексом | ❌ персональні дані, малий hit rate, ризик витоку між користувачами |
| `POST/PATCH/DELETE`, видача, повернення | — | — | — | ❌ запис не кешується, але **інвалідує** кеш |

**Основний сценарій для кешування — звіт `popular-books` і пошук по каталогу.** Це
read-intensive операції з дорогими агрегаціями (вузькі місця B1 і B5 з лаби 1), а дані в них
змінюються рідко порівняно з частотою читання.

### 9.2. Розподілене сховище

Окремий контейнер `cache` (Redis 7) у спільній мережі `backend`, однаково доступний усім
інстансам через `CACHE_URL=redis://cache:6379/0`. Це **окремий** Redis, а не той, що зберігає
сесії, бо в цих двох сховищ протилежні вимоги:

| | `redis` (сесії, лаба 2) | `cache` (лаба 4) |
|---|---|---|
| Втрата даних | неприпустима: усіх розлогінить | допустима: це лише копія БД |
| Персистентність | AOF + volume | вимкнена (`--save "" --appendonly no`) |
| Пам'ять | без ліміту | `maxmemory 128mb`, `volatile-lfu` (витіснення рідко вживаних ключів із TTL) |
| Відмова | 503 на автентифікованих запитах | система працює далі напряму з БД |

### 9.3. Cache-Aside (Lazy Loading)

Реалізація: [`app/cache.py`](app/cache.py) → `cache_aside()`. Використання:
`services/books.py` (картка, сторінки), `services/reports.py` (звіт).

![Cache-aside flow](docs/cache-aside-flow.png)

1. **Key lookup:** `GET libra:book:42:v7` (номер версії береться з `libra:ver:book:42`).
2. **Cache Hit:** повертаємо JSON із Redis, **без звернення до БД**. Сесія SQLAlchemy відкривається
   ліниво, тому при HIT з'єднання з пулу навіть не береться.
3. **Cache Miss:** читаємо з PostgreSQL, `SET key value EX ttl`, повертаємо клієнту.

Додатково:
- **Захист від stampede / thundering herd:** при MISS у БД іде лише запит, який виграв
  `SET <key>:lock NX PX 2000`. Інші конкурентні запити за тим самим ключем чекають до ~200 мс,
  поки значення з'явиться в кеші, і лише потім (якщо не дочекалися) читають з БД самі.
- **Захист від avalanche:** TTL із джитером ±10 %, тож ключі, створені одночасно (наприклад,
  після рестарту), не протухають одночасно.
- **Запобіжник (circuit breaker):** після першої помилки Redis кеш пропускається 5 с, тож мертвий
  кеш коштує один таймаут (0.3 с), а не таймаут на кожен запит.

### 9.4. Схема ключів і політика TTL

Шаблон: **`libra:<entity>:<id | params_hash>:v<version>`**

| Ключ | Приклад | TTL | Чому такий TTL |
|---|---|---|---|
| Картка книги | `libra:book:42:v7` | 300 с ±10 % | свіжість забезпечує інвалідація, а TTL лише прибирає непотрібне з пам'яті |
| Сторінка / пошук каталогу | `libra:books:list:3f9a1c0d2b7e4a55:v120` | 60 с ±10 % | багато комбінацій параметрів, хвіст рідкісних запитів має швидко звільняти пам'ять |
| Звіт | `libra:report:popular:8be0…:v311` | 120 с ±10 % | дорогий запит; бізнес допускає застарілість до 2 хв навіть без інвалідації |
| Лічильник версії | `libra:ver:book:42`, `libra:ver:books:list`, `libra:ver:report:popular` | без TTL | ніколи не витісняються (`volatile-lfu` чіпає лише ключі з TTL) |
| Замок stampede | `libra:book:42:v7:lock` | 2 с | живе лише на час завантаження |

- **`params_hash`** = перші 16 hex-символів `sha256` від канонічного JSON усіх параметрів
  (`sort_keys`, усі значення за замовчуванням явно, `q` нормалізується: `trim` + `lower`). Тому
  `?q=Data` і `?q=data ` дають один ключ, а `limit=5` і `limit=6` різні ключі. Колізія між
  сутностями неможлива (різні префікси), а всередині сутності має ймовірність 2⁻⁶⁴.
- Префікс `libra:` дозволяє ділити Redis з іншими сервісами.

### 9.5. Інвалідація

Після успішного `COMMIT` будь-якої мутації сервіс виконує `INCR` лічильників версій, які
стосуються зміненої сутності (функція `invalidate_book()` / `cache.invalidate()`):

| Операція | `ver:book:{id}` | `ver:books:list` | `ver:report:popular` |
|---|---|---|---|
| `POST /books` | | ✅ (нова книга в пошуку) | |
| `PATCH /books/{id}` | ✅ | ✅ | ✅ (назва в звіті) |
| `DELETE /books/{id}` | ✅ | ✅ | ✅ |
| `POST /loans` (видача) | ✅ (`available_copies`) | ✅ (фільтр `available_only`) | ✅ (лічильник видач) |
| `POST /loans/{id}/return` | ✅ | ✅ | ✅ |

**Чому версії, а не `DEL`:**
1. Сторінок пошуку тисячі (різні `q`, `offset`), тож видалити всі `DEL`-ом можна лише через
   `SCAN` по шаблону, а це O(N) і блокує Redis. `INCR` однієї версії миттєво робить недосяжними
   *всі* старі сторінки на *всіх* інстансах, а пам'ять звільняє TTL.
2. Версії закривають класичну гонку Cache-Aside: читач прочитав із БД старий рядок, письменник
   зробив `COMMIT` і `DEL`, і читач кладе в кеш застаріле значення, яке живе до кінця TTL. З
   версіями запізнілий `SET` потрапляє під **стару** версію, яку вже ніхто не читає (тест
   `test_stale_writer_race_is_harmless`).

Гарантія: наступний `GET` після відповіді на мутацію завжди отримує `MISS` і свіжі дані.
Перевіряють тести `tests/test_cache.py` (10 шт.) і крок 3 `scripts/cache_demo.py`.

### 9.6. Метрики та демонстрація

Джерело даних видно в кожній відповіді:
- `X-Cache: HIT | MISS | BYPASS | DISABLED`;
- `X-Instance-ID`: показує, що HIT часто обслуговує *інший* інстанс, ніж той, що заповнив кеш,
  тобто кеш справді спільний;
- `GET /api/v1/cache/stats`: лічильники hit / miss / invalidations / bypass цього інстансу та
  статистика сервера Redis (`keyspace_hits/misses`, `evicted_keys`, пам'ять);
- з `LOG_LEVEL=DEBUG` кожна операція (`cache HIT/MISS/INVALIDATE <key>`) пишеться в лог.

```bash
python scripts/cache_demo.py               # кроки 1-3
python scripts/cache_demo.py --fallback    # + зупинка/запуск контейнера cache
```

#### Cold (MISS) vs Hot (HIT): 40 вимірів на кожен endpoint, через балансувальник

Перед кожним холодним запитом виконується `PATCH` книги, що інвалідовує всі три типи ключів.

| Endpoint | Cold p50 | Cold p95 | Hot p50 | Hot p95 | Прискорення (p50) |
|---|---|---|---|---|---|
| `GET /books/{id}` | 4.5 ms | 6.7 ms | 2.6 ms | 3.5 ms | **1.7×** |
| `GET /books?q=…` | 26.0 ms | 36.0 ms | 3.1 ms | 4.0 ms | **8.4×** |
| `GET /reports/popular-books?days=365` | 73.8 ms | 97.6 ms | 3.5 ms | 4.8 ms | **21.3×** |

- Чим дорожчий запит у БД, тим більший ефект. Для звіту відповідь із кешу у 21 раз швидша.
- Для картки книги (PK lookup ≈ 1 мс) виграш у латентності скромний (1.7×), але кожен HIT знімає
  з БД запит і не займає з'єднання з пулу. Під навантаженням це головне (див. лабу 5).
- Hot-латентність ≈ 3 мс майже повністю складається з HTTP + HAProxy + FastAPI-серіалізації, а
  внесок Redis ≈ 0.2 мс.

#### Fallback: `docker compose stop cache`

```
4) Fallback: stopping the cache container
  book card    GET /books/{id}            HTTP 200  X-Cache: BYPASS   instance: app-2     11.2 ms
  catalogue    GET /books?q=demo          HTTP 200  X-Cache: BYPASS   instance: app-3     10.0 ms
  report       GET /reports/popular-books HTTP 200  X-Cache: BYPASS   instance: app-1      9.4 ms
  PATCH while cache is down -> HTTP 200
  /health -> status=ok cache='unavailable (degraded mode: reads go to the DB)'
  starting the cache container again
  GET book card (cache back, cold)        HTTP 200  X-Cache: MISS     instance: app-2      5.7 ms
  GET book card (cache back, hot)         HTTP 200  X-Cache: HIT      instance: app-3      3.2 ms
```

- Усі запити (читання і запис) обслуговуються з БД (`BYPASS`), помилок немає.
- `/health` лишається 200: кеш опційний, тож HAProxy **не** виводить вузли з пулу, а лише
  показує `cache: unavailable`.
- Після `start` кеш підхоплюється автоматично (після 5 с запобіжника), без рестарту застосунку.
- Компроміс: запис під час відмови кешу не зміг підняти версії. Кеш після `stop` порожній
  (persistence вимкнено), тож застарілих даних немає. Якби Redis був недоступний лише частині
  інстансів (мережевий розділ), застарілість обмежена TTL.

### 9.7. Оновлена архітектура

![Architecture lab 4](docs/architecture-lab4.png)

### 9.8. Теоретичні питання

- **Cache Stampede / Thundering Herd:** популярний ключ протухає, і сотні одночасних запитів
  отримують MISS та всі разом ідуть у БД з тим самим дорогим запитом. Захист: замок на
  перезавантаження (single-flight, реалізовано), probabilistic early expiration (оновлювати ключ
  трохи раніше TTL з імовірністю, що зростає ближче до кінця), stale-while-revalidate.
- **Cache Avalanche:** масове одночасне протухання (однаковий TTL у ключів, створених разом) або
  падіння кеш-сервера, після чого вся навантага одночасно падає на БД. Захист: джитер TTL
  (реалізовано), circuit breaker і обмеження конкуренції (реалізовано), прогрів кешу, кластер
  Redis.
- **Cache Penetration** (суміжне): запити неіснуючих ключів (`/books/999999`) завжди проходять
  до БД. Захист: короткий негативний кеш або Bloom-фільтр. У нас 404 не кешується, бо це дешевий
  PK lookup.
- **Eviction: LRU vs LFU.** LRU витісняє те, до чого найдовше не зверталися, і вразливий до
  разового сканування, яке вимиває гарячі ключі. LFU витісняє найрідше вживане (лічильник частоти
  з загасанням), тож гарячі картки бестселерів тримаються, навіть якщо їх на мить не читали.
  Обрано `volatile-lfu`: LFU, але лише серед ключів із TTL, тож лічильники версій не витісняються.
- **Expiration vs Invalidation.** Expiration (TTL) пасивна: дані застарівають «самі» після
  таймауту, але до того можуть бути неактуальні. Invalidation активна: застосунок явно робить
  запис недійсним у момент зміни, і свіжість гарантується одразу. Ми використовуємо обидва:
  інвалідацію для коректності, TTL для звільнення пам'яті та як страховку від пропущеної
  інвалідації.

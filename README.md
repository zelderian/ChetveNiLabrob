# Libra: Library Lending API

Сервіс видачі книг у бібліотеці: читачі (`members`), книги (`books`) і видачі (`loans`).
Стек: **Python 3.12 · FastAPI · SQLAlchemy 2 · Alembic · PostgreSQL 16 · Redis 7 · Docker Compose**.

| Лабораторна | Тема | Розділи README | Git-тег |
|---|---|---|---|
| №1 | System Design та базовий прототип | 2–6 | `lab1` |
| №2 | Stateless-архітектура, винесення стану | 7 | `lab2` |

`git checkout lab1` показує стан проєкту після лаби 1 (один інстанс на порту 8000), а гілка
`main` містить поточний стан.

---

## 1. Швидкий старт

Потрібен лише **Docker Desktop**. Python локально потрібен тільки для демо-скриптів.

```bash
git clone <repo-url> libra && cd libra
docker compose up --build -d      # db + redis -> migrate -> app1 + app2
```

Після старту доступні:

| Що | Інстанс 1 | Інстанс 2 |
|---|---|---|
| API | http://localhost:8001 | http://localhost:8002 |
| Swagger UI | http://localhost:8001/docs | http://localhost:8002/docs |
| OpenAPI-специфікація | http://localhost:8001/openapi.json | … |
| Readiness (БД + Redis) | http://localhost:8001/health | http://localhost:8002/health |

Порядок старту детермінований. Спочатку `db` і `redis` проходять healthcheck. Потім `migrate`
один раз виконує `alembic upgrade head` і завершується. Лише після успішних міграцій стартують
`app1` і `app2`, тож інстанси ніколи не виконують міграції паралельно.

```bash
docker compose ps                 # стан контейнерів
docker compose logs -f app1 app2  # логи (кожен рядок містить [app-1] / [app-2])
docker compose down               # зупинити (дані лишаються у volume pgdata / redisdata)
docker compose down -v            # зупинити і ВИДАЛИТИ дані
```

### Демонстрація

```bash
python scripts/seed.py                               # демо-дані (20 читачів, 50 книг, видачі)
python scripts/demo.py                               # усі основні endpoint-и (лаба 1)
python scripts/cross_instance_check.py               # консистентність між інстансами (лаба 2)
python scripts/failover_check.py --kill app1 --restart   # аварійна зупинка інстансу (лаба 2)
```

Скрипти використовують тільки стандартну бібліотеку Python і запускаються з кореня репозиторію.
Для VS Code / JetBrains є колекція запитів [`docs/requests.http`](docs/requests.http).

### Перевірка персистентності

```bash
python scripts/demo.py                       # створили дані
docker compose restart db                    # перезапуск СУБД
# або повністю: docker compose down && docker compose up -d
curl http://localhost:8001/api/v1/books      # дані на місці (volume pgdata)
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

# Libra: Library Lending API

Сервіс видачі книг у бібліотеці: читачі (`members`), книги (`books`) і видачі (`loans`).
Стек: **Python 3.12 · FastAPI · SQLAlchemy 2 · Alembic · PostgreSQL 16 · Docker Compose**.

> Лабораторна робота №1: System Design та базовий прототип.

---

## 1. Швидкий старт

Потрібен лише **Docker Desktop**. Python локально не потрібен.

```bash
git clone <repo-url> libra && cd libra
docker compose up --build -d      # піднімає db -> migrate -> app
```

Після старту доступні:

| Що | URL |
|---|---|
| API | http://localhost:8000 |
| Swagger UI (інтерактивна документація) | http://localhost:8000/docs |
| OpenAPI-специфікація | http://localhost:8000/openapi.json |
| Health check | http://localhost:8000/health |

Порядок старту детермінований: `db` (чекаємо `pg_isready`) → `migrate` (одноразово виконує
`alembic upgrade head` і завершується) → `app` (стартує лише після успішних міграцій).

```bash
docker compose ps                 # стан контейнерів
docker compose logs -f app        # логи застосунку
docker compose down               # зупинити (дані зберігаються у volume pgdata)
docker compose down -v            # зупинити і ВИДАЛИТИ дані
```

### Демонстрація

```bash
python scripts/seed.py            # наповнити демо-даними (20 читачів, 50 книг, ~60 видач)
python scripts/demo.py            # пройтися по всіх основних endpoint-ах
```

Скрипти використовують тільки стандартну бібліотеку Python. Для VS Code / JetBrains є
колекція запитів [`docs/requests.http`](docs/requests.http).

### Перевірка персистентності

```bash
python scripts/demo.py                       # створили дані
docker compose restart db                    # перезапуск СУБД
# або повністю: docker compose down && docker compose up -d
curl http://localhost:8000/api/v1/books      # дані на місці (volume pgdata)
```

### Тести

Інтеграційні тести працюють зі справжнім PostgreSQL:

```bash
pip install -r requirements-dev.txt
set TEST_DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/libra_test   # Windows
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
| GET | `/health` | стан сервісу та з'єднання з БД | 200 | 503 |
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
| POST | `/api/v1/auth/login` | вхід, повертає bearer-токен | 200 | 401, 422 |
| POST | `/api/v1/auth/logout` | інвалідувати токен | 204 | 401 |
| GET | `/api/v1/me` 🔒 | поточний читач | 200 | 401 |
| POST | `/api/v1/loans` 🔒 | **взяти книгу** (бізнес-логіка вище) | 201 | 401, 404, 409, 422 |
| POST | `/api/v1/loans/{id}/return` 🔒 | **повернути книгу**, розрахунок штрафу | 200 | 401, 403, 404, 409 |
| GET | `/api/v1/me/loans?active=` 🔒 | мої видачі | 200 | 401 |
| GET | `/api/v1/reports/popular-books?days=&limit=` | **топ популярних книг** (high-load) | 200 | 422 |

🔒 означає заголовок `Authorization: Bearer <token>`.

Єдиний формат помилки:

```json
{ "error": { "code": "conflict", "message": "No available copies of this book" } }
```

Коди: `validation_error` (422, з полем `details`), `not_found` (404), `conflict` (409),
`unauthorized` (401), `forbidden` (403), `internal_error` (500).

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
  models.py          # ORM-моделі (Member, Book, Loan)
  schemas.py         # Pydantic DTO + валідація вводу
  errors.py          # доменні винятки -> HTTP-коди
  security.py        # хешування паролів (PBKDF2)
  sessions.py        # сесії входу
  deps.py            # FastAPI-залежності (автентифікація)
  routers/           # HTTP-шар
  services/          # бізнес-логіка
migrations/          # Alembic (DDL)
tests/               # інтеграційні тести (pytest + PostgreSQL)
scripts/             # demo / seed
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

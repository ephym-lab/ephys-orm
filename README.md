# ephyorm

A lightweight, chainable, and transaction-safe Object-Relational Mapper (ORM) for PostgreSQL, built specifically for Python 3.12+ using `psycopg2`.

[![Python Version](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)
[![Database](https://img.shields.io/badge/database-postgresql-blue.svg)](https://www.postgresql.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

---

## Key Features

* **Context-Managed Connections:** Explicit lifecycle management with `PostgresConnection` ensuring connections and cursors are cleanly opened and closed.
* **Transaction Guards:** Automatic detection and blocking of raw transaction keywords (`BEGIN`, `COMMIT`, etc.) to prevent manual transaction corruption, with automatic rollback on execution errors.
* **Escape Hatch (`execute_raw`):** Fully bypass guards for complex, manual transaction controls like nested savepoints.
* **Active Record Pattern:** Define models easily with auto-resolving table names, dynamic configuration (`__table__`, `__primary_key__`, `_dsn`), and private attribute filtering.
* **Fluent Query Builder:** Chainable, immutable, and lazy-evaluated internal DSL supporting filtering, sorting, selecting specific fields, and pagination.
* **SQL Injection Safe:** Column validation guards and parameterized query compilation prevent malicious SQL payloads.
* **Granular Exceptions:** Descriptive and hierarchical custom exception tree inheriting from `EphyormError`.

---

## Getting Started

### 1. Setup Virtual Environment
Initialize your environment using `uv` (recommended) or use the helper script:

```bash
# Using setup script
chmod +x setup.sh && ./setup.sh

# Or manually:
uv venv --python 3.12 .venv
source .venv/bin/activate
```

### 2. Install Dependencies
```bash
uv pip install -r requirements.txt
```

---

## Feature Walkthrough & Examples

### 1. Database Connection Management

At the core is the `PostgresConnection` class, which handles transaction logic and yields query results as dictionaries using `RealDictCursor`.

```python
from ephyorm.db.connection import PostgresConnection

DSN = "dbname=my_db user=postgres password=secret host=127.0.0.1 port=5432"

# Safe execution with transaction guards
with PostgresConnection(DSN) as conn:
    # Inserts require an explicit commit
    conn.execute("INSERT INTO users (name, email) VALUES (%s, %s)", ("Alice", "alice@example.com"))
    conn.commit()

    # Returns results as a list of dictionaries
    rows = conn.execute("SELECT * FROM users WHERE name = %s", ("Alice",))
    print(rows[0]["email"])  # "alice@example.com"
```

#### Safe Mode vs Escape Hatch
To ensure connection integrity, standard executions block transaction-modifying raw SQL:

```python
with PostgresConnection(DSN) as conn:
    # Raises DBError: Raw 'BEGIN' is not allowed in execute().
    conn.execute("BEGIN")

    # Use explicit commit method
    conn.commit()

    # Or use the escape hatch for custom SQL transactions
    conn.execute_raw("BEGIN")
    conn.execute_raw("SAVEPOINT my_sp")
    conn.execute_raw("ROLLBACK TO SAVEPOINT my_sp")
    conn.execute_raw("COMMIT")
```

---

### 2. Model Definitions

Define database tables as Python classes by subclassing `Model`. 

```python
from ephyorm.orm.model_v2 import Model

class User(Model):
    __table__ = 'users'            # Optional: defaults to class name + 's' ('users')
    __primary_key__ = 'id'         # Optional: defaults to 'id'
    _dsn = DSN                     # Connection string

    # Annotate your fields
    name: str
    email: str
    age: int
```

* **Attributes starting with `_`** are treated as private and are automatically ignored during INSERT and UPDATE operations.
* **Primary Key Auto-generation:** Instantiating a new model automatically sets its primary key to `None` to mark it as unsaved.

---

### 3. CRUD Operations

#### Create
Instantiate and save, or use the `.create()` class method:

```python
# Option 1: Instantiate & Save
user = User(name="John Doe", email="john@example.com", age=30)
user.save()  # Triggers Naive INSERT, updates user.id automatically
print(user.id)  # Returns generated SERIAL PK

# Option 2: Inline Creation
user = User.create(name="Jane Doe", email="jane@example.com", age=28)
```

#### Read
Read operations dynamically delegate to the fluent Query Builder under the hood.

```python
# Fetch by primary key (returns Model instance or None)
user = User.get(1)

# Get all records
all_users = User.all()

# Simple equality filters
active_users = User.filter(age=30)
```

#### Update
Updating fields on a model instance and calling `save()` detects the set primary key and runs a targeted SQL `UPDATE`.

```python
user = User.get(1)
user.age = 31
user.save()  # Triggers Naive UPDATE
```

#### Delete
Delete a record by primary key:

```python
user = User.get(1)
user.delete()  # Triggers DELETE FROM users WHERE id = 1
```

---

### 4. Chainable Query Builder

For advanced queries, use the `Query` builder which lazily compiles and executes immutable chains. Chaining a query always yields a **new copy** of the builder, keeping the original query unchanged.

```python
from ephyorm.orm.query import Query

# 1. Build query lazily (Nothing is sent to the database yet)
query = (
    Query(User)
    .select("id", "name", "email")
    .where(age=30)
    .order_by_desc("name")
    .limit(10)
    .offset(5)
)

# 2. Execute query
users = query.all()  # Executes: SELECT id, name, email FROM users WHERE age = %s ORDER BY name DESC LIMIT 10 OFFSET 5
```

#### Builder Methods

* `.select(*fields)`: Specify projection fields. Defaults to `*`.
* `.where(**conditions)`: Add field equality checks. Validates that column names are clean and alphanumeric to prevent SQL Injection.
* `.order_by(*fields)`: Orders records in ascending (`ASC`) order.
* `.order_by_desc(*fields)`: Orders records in descending (`DESC`) order.
* `.limit(n)`: Sets limits on rows fetched.
* `.offset(n)`: Offsets the starting cursor for rows.

#### Terminal Execution Methods

* `.all()`: Returns a list of all model instances matching the query.
* `.first()`: Appends `LIMIT 1` to the query and returns the first instance, or `None`.
* `.get()`: Fetch exactly one match. Raises `ModelError` if no record exists or if multiple records match.
* `.count()`: Executes a lightweight `SELECT COUNT(*)` using the current query filters.

---

## Error Handling System

All custom exceptions inherit from `EphyormError` and are designed to make debugging straightforward:

```
EphyormError (Base Exception)
├── DBError (Database connectivity, execution, and transaction guard failures)
├── ModelError (Semantic failures, like .get() matching multiple rows)
├── RuntimeConfigError (Missing DSN configurations)
├── ValueValidationError (SQL Injection injection prevention, deleting without PK, etc.)
├── QueryError (Query composition issues)
└── ExecutionError (Error executing generated DSL queries)
```

---

## Running Tests

Run the test suite using `pytest`:

```bash
uv run pytest
```

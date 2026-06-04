"""
Tests for Query Builder
"""

import pytest
import psycopg2
from src.ephyorm.db.connection import PostgresConnection
from src.ephyorm.orm.model import Model
from src.ephyorm.orm.query import Query
from src.ephyorm.exceptions import ModelError, ValueValidationError

# ─────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────

TEST_DB_NAME = "orm_test_day3"
POSTGRES_DSN = "dbname=postgres user=myuser password='8%7Pkc&8;JULH' host=127.0.0.1 port=5432"
TEST_DSN = f"dbname={TEST_DB_NAME} user=myuser password='8%7Pkc&8;JULH' host=127.0.0.1 port=5432"


class User(Model):
    __table__ = 'users'
    __primary_key__ = 'id'
    _dsn = TEST_DSN


class Product(Model):
    __primary_key__ = 'id'
    _dsn = TEST_DSN


# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def setup_database():
    conn = psycopg2.connect(POSTGRES_DSN)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(f"DROP DATABASE IF EXISTS {TEST_DB_NAME}")
    cur.execute(f"CREATE DATABASE {TEST_DB_NAME}")
    cur.close()
    conn.close()

    conn = psycopg2.connect(TEST_DSN)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            email VARCHAR(100) UNIQUE,
            age INTEGER DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id SERIAL PRIMARY KEY,
            title VARCHAR(200) NOT NULL,
            price DECIMAL(10, 2) DEFAULT 0.00
        )
    """)
    conn.commit()
    cur.close()
    conn.close()
    yield

    conn = psycopg2.connect(POSTGRES_DSN)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(f"DROP DATABASE IF EXISTS {TEST_DB_NAME}")
    cur.close()
    conn.close()


@pytest.fixture(autouse=True)
def clean_tables(setup_database):
    conn = psycopg2.connect(TEST_DSN)
    cur = conn.cursor()
    cur.execute("TRUNCATE TABLE users RESTART IDENTITY CASCADE")
    cur.execute("TRUNCATE TABLE products RESTART IDENTITY CASCADE")
    conn.commit()
    cur.close()
    conn.close()


# ─────────────────────────────────────────────────────────────
# Tests: Basic Query Building
# ─────────────────────────────────────────────────────────────

class TestQueryBuilder:
    def test_query_init(self):
        q = Query(User)
        assert q._model == User
        assert q._select_fields == []
        assert q._where_conditions == []
        assert q._order_by == []
        assert q._limit is None
        assert q._offset is None

    def test_where_adds_conditions(self):
        q = Query(User).where(name="Alice")
        assert len(q._where_conditions) == 1
        assert q._where_conditions[0] == ("name", "=", "Alice")

    def test_where_multiple_conditions(self):
        q = Query(User).where(name="Alice", age=25)
        assert len(q._where_conditions) == 2

    def test_where_validates_column_names(self):
        with pytest.raises(ValueValidationError, match="Invalid column name"):
            Query(User).where(**{"name; DROP": "bad"})

    def test_order_by(self):
        q = Query(User).order_by("name", "id")
        assert q._order_by == [("name", "ASC"), ("id", "ASC")]

    def test_order_by_desc(self):
        q = Query(User).order_by_desc("age")
        assert q._order_by == [("age", "DESC")]

    def test_limit(self):
        q = Query(User).limit(10)
        assert q._limit == 10

    def test_offset(self):
        q = Query(User).offset(5)
        assert q._offset == 5

    def test_select_fields(self):
        q = Query(User).select("name", "email")
        assert q._select_fields == ["name", "email"]


# ─────────────────────────────────────────────────────────────
# Tests: Immutability (chaining creates new copies)
# ─────────────────────────────────────────────────────────────

class TestQueryImmutability:
    def test_where_does_not_mutate_original(self):
        base = Query(User)
        filtered = base.where(name="Alice")
        assert base._where_conditions == []          # unchanged
        assert filtered._where_conditions == [("name", "=", "Alice")]

    def test_limit_does_not_mutate_original(self):
        base = Query(User).where(name="Alice")
        limited = base.limit(10)
        assert base._limit is None                   # unchanged
        assert limited._limit == 10
        assert limited._where_conditions == base._where_conditions  # shared conditions

    def test_chaining_preserves_all_state(self):
        q1 = Query(User).where(name="Alice")
        q2 = q1.order_by("id")
        q3 = q2.limit(10)

        assert q1._order_by == []     # q1 unchanged
        assert q1._limit is None
        assert q2._limit is None      # q2 unchanged
        assert q3._limit == 10
        assert q3._where_conditions == [("name", "=", "Alice")]
        assert q3._order_by == [("id", "ASC")]


# ─────────────────────────────────────────────────────────────
# Tests: SQL Generation
# ─────────────────────────────────────────────────────────────

class TestQuerySQL:
    def test_build_select_basic(self):
        q = Query(User)
        sql, params = q._build_select()
        assert sql == "SELECT * FROM users"
        assert params == ()

    def test_build_select_with_where(self):
        q = Query(User).where(name="Alice")
        sql, params = q._build_select()
        assert sql == "SELECT * FROM users WHERE name = %s"
        assert params == ("Alice",)

    def test_build_select_with_order(self):
        q = Query(User).order_by("name")
        sql, params = q._build_select()
        assert sql == "SELECT * FROM users ORDER BY name ASC"

    def test_build_select_with_limit(self):
        q = Query(User).limit(10)
        sql, params = q._build_select()
        assert sql == "SELECT * FROM users LIMIT 10"

    def test_build_select_with_offset(self):
        q = Query(User).offset(5)
        sql, params = q._build_select()
        assert sql == "SELECT * FROM users OFFSET 5"

    def test_build_select_full(self):
        q = Query(User).where(name="Alice", age=25).order_by("id").limit(10).offset(5)
        sql, params = q._build_select()
        assert "SELECT * FROM users" in sql
        assert "WHERE name = %s AND age = %s" in sql
        assert "ORDER BY id ASC" in sql
        assert "LIMIT 10" in sql
        assert "OFFSET 5" in sql
        assert params == ("Alice", 25)

    def test_build_count(self):
        q = Query(User).where(name="Alice")
        sql, params = q._build_count()
        assert sql == "SELECT COUNT(*) as count FROM users WHERE name = %s"
        assert params == ("Alice",)

    def test_build_count_ignores_select_and_order(self):
        q = Query(User).select("name").where(name="Alice").order_by("id")
        sql, params = q._build_count()
        assert "COUNT(*)" in sql
        assert "ORDER BY" not in sql
        assert "name" not in sql.split("FROM")[0]  # not in SELECT clause


# ─────────────────────────────────────────────────────────────
# Tests: Execution (integration with real DB)
# ─────────────────────────────────────────────────────────────

class TestQueryExecution:
    def test_all_returns_instances(self, setup_database):
        User.create(name="Alice", email="alice@example.com", age=25)
        User.create(name="Bob", email="bob@example.com", age=30)

        users = Query(User).all()
        assert len(users) == 2
        assert all(isinstance(u, User) for u in users)

    def test_all_with_where(self, setup_database):
        User.create(name="Alice", email="alice@example.com", age=25)
        User.create(name="Bob", email="bob@example.com", age=30)

        users = Query(User).where(name="Alice").all()
        assert len(users) == 1
        assert users[0].name == "Alice"

    def test_first_returns_one_or_none(self, setup_database):
        User.create(name="Alice", email="alice@example.com", age=25)
        User.create(name="Bob", email="bob@example.com", age=30)

        first = Query(User).order_by("id").first()
        assert first is not None
        assert first.name == "Alice"

        none = Query(User).where(name="Nobody").first()
        assert none is None

    def test_count(self, setup_database):
        User.create(name="Alice", email="alice@example.com", age=25)
        User.create(name="Bob", email="bob@example.com", age=30)

        total = Query(User).count()
        assert total == 2

        filtered = Query(User).where(age=25).count()
        assert filtered == 1

    def test_limit_and_offset(self, setup_database):
        for i in range(5):
            User.create(name=f"User{i}", email=f"user{i}@example.com", age=20+i)

        users = Query(User).order_by("id").limit(2).all()
        assert len(users) == 2

        users = Query(User).order_by("id").limit(2).offset(2).all()
        assert len(users) == 2
        assert users[0].name == "User2"

    def test_order_by_desc(self, setup_database):
        User.create(name="Alice", email="alice@example.com", age=25)
        User.create(name="Bob", email="bob@example.com", age=30)

        users = Query(User).order_by_desc("age").all()
        assert users[0].name == "Bob"   # age 30 first
        assert users[1].name == "Alice"  # age 25 second

    def test_select_specific_fields(self, setup_database):
        User.create(name="Alice", email="alice@example.com", age=25)

        users = Query(User).select("name", "age").all()
        assert len(users) == 1
        assert users[0].name == "Alice"
        assert users[0].age == 25
        # email not selected, but RealDictCursor still has it as None? No —
        # actually PostgreSQL returns only selected columns


# ─────────────────────────────────────────────────────────────
# Tests: Challenge — get() method
# ─────────────────────────────────────────────────────────────

class TestQueryGet:
    def test_get_returns_instance(self, setup_database):
        User.create(name="Alice", email="alice@example.com", age=25)

        user = Query(User).where(name="Alice").get()
        assert isinstance(user, User)
        assert user.name == "Alice"

    def test_get_raises_when_no_match(self, setup_database):
        with pytest.raises(ModelError, match="does not exist"):
            Query(User).where(name="Nobody").get()

    def test_get_raises_when_multiple_matches(self, setup_database):
        User.create(name="Alice", email="alice1@example.com", age=25)
        User.create(name="Alice", email="alice2@example.com", age=30)

        with pytest.raises(ModelError, match="Expected 1"):
            Query(User).where(name="Alice").get()


# ─────────────────────────────────────────────────────────────
# Tests: Model integration (Model.all, Model.filter, Model.get use Query)
# ─────────────────────────────────────────────────────────────

class TestModelIntegration:
    def test_model_all_uses_query(self, setup_database):
        User.create(name="Alice", email="alice@example.com", age=25)
        users = User.all()
        assert len(users) == 1
        assert isinstance(users[0], User)

    def test_model_filter_uses_query(self, setup_database):
        User.create(name="Alice", email="alice@example.com", age=25)
        User.create(name="Bob", email="bob@example.com", age=30)

        users = User.filter(name="Alice")
        assert len(users) == 1
        assert users[0].name == "Alice"

    def test_model_get_uses_query(self, setup_database):
        created = User.create(name="Alice", email="alice@example.com", age=25)
        fetched = User.get(created.id)
        assert fetched is not None
        assert fetched.name == "Alice"

    def test_model_get_none_for_missing(self, setup_database):
        assert User.get(99999) is None


# ─────────────────────────────────────────────────────────────
# Tests: Reuse — same query executed multiple times
# ─────────────────────────────────────────────────────────────

class TestQueryReuse:
    def test_query_can_be_executed_multiple_times(self, setup_database):
        User.create(name="Alice", email="alice@example.com", age=25)

        q = Query(User).where(name="Alice")

        r1 = q.all()
        r2 = q.all()

        assert len(r1) == 1
        assert len(r2) == 1
        assert r1[0].name == r2[0].name


# ─────────────────────────────────────────────────────────────
# Manual test runner
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    # Setup
    conn = psycopg2.connect(POSTGRES_DSN)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(f"DROP DATABASE IF EXISTS {TEST_DB_NAME}")
    cur.execute(f"CREATE DATABASE {TEST_DB_NAME}")
    cur.close()
    conn.close()

    conn = psycopg2.connect(TEST_DSN)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            email VARCHAR(100) UNIQUE,
            age INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    cur.close()
    conn.close()

    print("\n=== Manual Query Tests ===\n")

    # Test 1: Basic query
    print("1. Basic query...")
    User.create(name="Alice", email="alice@example.com", age=25)
    User.create(name="Bob", email="bob@example.com", age=30)
    users = Query(User).all()
    print(f"   All users: {len(users)}")

    # Test 2: Filter
    print("\n2. Filter...")
    filtered = Query(User).where(age=25).all()
    print(f"   Age 25: {len(filtered)} user(s)")

    # Test 3: First
    print("\n3. First...")
    first = Query(User).order_by("id").first()
    print(f"   First: {first}")

    # Test 4: Count
    print("\n4. Count...")
    total = Query(User).count()
    filtered_count = Query(User).where(age=25).count()
    print(f"   Total: {total}, Age 25: {filtered_count}")

    # Test 5: Immutability
    print("\n5. Immutability...")
    base = Query(User).where(age=25)
    limited = base.limit(1)
    print(f"   Base limit: {base._limit} (should be None)")
    print(f"   Limited limit: {limited._limit} (should be 1)")

    # Test 6: get() challenge
    print("\n6. get() challenge...")
    try:
        Query(User).where(name="Nobody").get()
    except ModelError as e:
        print(f"   Caught expected: {e}")

    print("\n=== All manual tests passed! ===")

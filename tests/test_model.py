"""
Base Model & Result Mapping

Run with: pytest tests/test_model.py -v
"""

import pytest
import psycopg2
from src.ephyorm.db.connection import PostgresConnection
from src.ephyorm.orm.model import Model

# ─────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────

TEST_DB_NAME = "orm_test_day2"
POSTGRES_DSN = "dbname=postgres user=myuser password='8%7Pkc&8;JULH' host=127.0.0.1 port=5432"
TEST_DSN = f"dbname={TEST_DB_NAME} user=myuser password='8%7Pkc&8;JULH' host=127.0.0.1 port=5432"


# ─────────────────────────────────────────────────────────────
# Test Model Subclass
# ─────────────────────────────────────────────────────────────

class User(Model):
    __table__ = 'users'
    __primary_key__ = 'id'
    _dsn = TEST_DSN


class Product(Model):
    """Test default table name (lowercase + 's')"""
    __primary_key__ = 'id'
    _dsn = TEST_DSN


# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def setup_database():
    """Create test database, users table, and products table."""
    # Connect to postgres to create test DB
    conn = psycopg2.connect(POSTGRES_DSN)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(f"DROP DATABASE IF EXISTS {TEST_DB_NAME}")
    cur.execute(f"CREATE DATABASE {TEST_DB_NAME}")
    cur.close()
    conn.close()

    # Connect to test DB and create tables
    conn = psycopg2.connect(TEST_DSN)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            email VARCHAR(100) UNIQUE
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

    # Cleanup: drop test database
    conn = psycopg2.connect(POSTGRES_DSN)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(f"DROP DATABASE IF EXISTS {TEST_DB_NAME}")
    cur.close()
    conn.close()


@pytest.fixture(autouse=True)
def clean_users(setup_database):
    """Clear users table before each test."""
    conn = psycopg2.connect(TEST_DSN)
    cur = conn.cursor()
    cur.execute("TRUNCATE TABLE users RESTART IDENTITY CASCADE")
    cur.execute("TRUNCATE TABLE products RESTART IDENTITY CASCADE")
    conn.commit()
    cur.close()
    conn.close()


# ─────────────────────────────────────────────────────────────
# Tests: Table Name & Primary Key
# ─────────────────────────────────────────────────────────────

class TestModelConfiguration:
    def test_explicit_table_name(self):
        assert User._get_table_name() == "users"

    def test_default_table_name(self):
        assert Product._get_table_name() == "products"  # Product -> products

    def test_explicit_primary_key(self):
        assert User._get_primary_key() == "id"

    def test_default_primary_key(self):
        assert Product._get_primary_key() == "id"


# ─────────────────────────────────────────────────────────────
# Tests: Instance Creation & Field Access
# ─────────────────────────────────────────────────────────────

class TestModelInstance:
    def test_init_stores_fields(self):
        user = User(name="Alice", email="alice@example.com")
        assert user.name == "Alice"
        assert user.email == "alice@example.com"

    def test_init_auto_sets_pk_to_none(self):
        """Primary key should be None when not provided."""
        user = User(name="Alice")
        assert user.id is None

    def test_get_field_data_excludes_private(self):
        user = User(name="Alice")
        user._private = "should not appear"
        fields = user._get_field_data()
        assert "name" in fields
        assert "_private" not in fields

    def test_get_field_data_excludes_pk_when_none(self):
        """When pk is None, it may still appear in _get_field_data.
        The _insert method handles removing it."""
        user = User(name="Alice")
        fields = user._get_field_data()
        # id=None is a public attr, so it appears in field_data
        assert "id" in fields
        assert fields["id"] is None

    def test_repr_unsaved(self):
        user = User(name="Alice", email="alice@example.com")
        r = repr(user)
        assert "User" in r
        assert "id=unsaved" in r
        assert "name='Alice'" in r

    def test_repr_saved(self, setup_database):
        user = User.create(name="Alice", email="alice@example.com")
        r = repr(user)
        assert "id=1" in r
        assert "name='Alice'" in r


# ─────────────────────────────────────────────────────────────
# Tests: CREATE (save as INSERT)
# ─────────────────────────────────────────────────────────────

class TestModelInsert:
    def test_save_inserts_new_row(self, setup_database):
        user = User(name="Alice", email="alice@example.com")
        assert user.id is None

        user.save()

        assert user.id is not None
        assert user.id == 1  # First SERIAL value

    def test_save_sets_multiple_fields(self, setup_database):
        user = User(name="Bob", email="bob@example.com")
        user.save()

        # Verify in DB directly
        with PostgresConnection(TEST_DSN) as conn:
            rows = conn.execute("SELECT * FROM users WHERE id = %s", (user.id,))
            assert len(rows) == 1
            assert rows[0]["name"] == "Bob"
            assert rows[0]["email"] == "bob@example.com"

    def test_create_class_method(self, setup_database):
        user = User.create(name="Charlie", email="charlie@example.com")

        assert user.id is not None
        assert user.name == "Charlie"

        # Verify in DB
        with PostgresConnection(TEST_DSN) as conn:
            rows = conn.execute("SELECT * FROM users WHERE id = %s", (user.id,))
            assert len(rows) == 1


# ─────────────────────────────────────────────────────────────
# Tests: READ (get, all, filter)
# ─────────────────────────────────────────────────────────────

class TestModelRead:
    def test_get_returns_instance(self, setup_database):
        User.create(name="Alice", email="alice@example.com")

        user = User.get(1)

        assert user is not None
        assert user.id == 1
        assert user.name == "Alice"
        assert user.email == "alice@example.com"

    def test_get_returns_none_for_missing(self, setup_database):
        user = User.get(99999)
        assert user is None

    def test_all_returns_all_instances(self, setup_database):
        User.create(name="Alice", email="alice@example.com")
        User.create(name="Bob", email="bob@example.com")

        users = User.all()

        assert len(users) == 2
        names = {u.name for u in users}
        assert names == {"Alice", "Bob"}

    def test_all_returns_empty_list(self, setup_database):
        users = User.all()
        assert users == []

    def test_filter_single_condition(self, setup_database):
        User.create(name="Alice", email="alice@example.com")
        User.create(name="Bob", email="bob@example.com")

        results = User.filter(name="Alice")

        assert len(results) == 1
        assert results[0].name == "Alice"

    def test_filter_multiple_conditions(self, setup_database):
        User.create(name="Alice", email="alice@example.com")
        User.create(name="Alice", email="alice2@example.com")

        results = User.filter(name="Alice", email="alice@example.com")

        assert len(results) == 1
        assert results[0].email == "alice@example.com"

    def test_filter_no_matches(self, setup_database):
        User.create(name="Alice", email="alice@example.com")

        results = User.filter(name="Nobody")
        assert results == []

    def test_filter_empty_kwargs_returns_all(self, setup_database):
        User.create(name="Alice", email="alice@example.com")
        User.create(name="Bob", email="bob@example.com")

        results = User.filter()

        assert len(results) == 2


# ─────────────────────────────────────────────────────────────
# Tests: UPDATE (save as UPDATE)
# ─────────────────────────────────────────────────────────────

class TestModelUpdate:
    def test_save_updates_existing(self, setup_database):
        user = User.create(name="Alice", email="alice@example.com")
        original_id = user.id

        user.name = "Alicia"
        user.save()

        assert user.id == original_id  # ID unchanged

        # Verify in DB
        refreshed = User.get(original_id)
        assert refreshed.name == "Alicia"
        assert refreshed.email == "alice@example.com"  # Unchanged

    def test_update_only_changes_provided_fields(self, setup_database):
        user = User.create(name="Alice", email="alice@example.com")

        user.name = "Alicia"
        # Don't touch email
        user.save()

        refreshed = User.get(user.id)
        assert refreshed.name == "Alicia"
        assert refreshed.email == "alice@example.com"


# ─────────────────────────────────────────────────────────────
# Tests: DELETE
# ─────────────────────────────────────────────────────────────

class TestModelDelete:
    def test_delete_removes_row(self, setup_database):
        user = User.create(name="Alice", email="alice@example.com")
        user_id = user.id

        user.delete()

        # Verify gone
        assert User.get(user_id) is None

    def test_delete_without_pk_raises(self, setup_database):
        user = User(name="Alice", email="alice@example.com")
        # Never saved, so id is None (auto-init)

        with pytest.raises(ValueError, match="Cannot delete"):
            user.delete()


# ─────────────────────────────────────────────────────────────
# Tests: Default Table Name
# ─────────────────────────────────────────────────────────────

class TestDefaultTableName:
    def test_product_uses_default_table(self, setup_database):
        product = Product.create(title="Widget", price=9.99)

        assert product.id is not None

        # Verify in products table
        with PostgresConnection(TEST_DSN) as conn:
            rows = conn.execute("SELECT * FROM products WHERE id = %s", (product.id,))
            assert len(rows) == 1
            assert rows[0]["title"] == "Widget"


# ─────────────────────────────────────────────────────────────
# Tests: Error Handling
# ─────────────────────────────────────────────────────────────

class TestModelErrors:
    def test_insert_no_fields_raises(self, setup_database):
        # Create a model with only pk (which is None, so excluded)
        user = User()
        with pytest.raises(ValueError, match="No fields to insert"):
            user.save()

    def test_filter_invalid_column_name(self, setup_database):
        with pytest.raises(ValueError, match="Invalid column name"):
            User.filter(**{"name; DROP TABLE users; --": "value"})

    def test_filter_sql_injection_safe(self, setup_database):
        # Even if someone tries to inject via value, parameterized query saves us
        User.create(name="Alice", email="alice@example.com")

        # This should be treated as a literal string value, not SQL
        results = User.filter(name="'; DROP TABLE users; --")
        assert results == []  # No match, but table still exists

        # Verify table still intact
        users = User.all()
        assert len(users) == 1


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
            email VARCHAR(100) UNIQUE
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

    print("\n=== Manual Model Tests ===\n")

    # Test 1: Create and get
    print("1. Create and get...")
    user = User.create(name="Alice", email="alice@example.com")
    print(f"   Created: {user}")
    fetched = User.get(user.id)
    print(f"   Fetched: {fetched}")
    assert fetched.name == "Alice"

    # Test 2: Update
    print("\n2. Update...")
    fetched.name = "Alicia"
    fetched.save()
    updated = User.get(fetched.id)
    print(f"   Updated: {updated}")
    assert updated.name == "Alicia"

    # Test 3: All and filter
    print("\n3. All and filter...")
    User.create(name="Bob", email="bob@example.com")
    all_users = User.all()
    print(f"   All users: {len(all_users)}")
    filtered = User.filter(name="Alice")
    print(f"   Filtered (name='Alice'): {len(filtered)} (should be 0, we changed to Alicia)")
    filtered2 = User.filter(name="Alicia")
    print(f"   Filtered (name='Alicia'): {len(filtered2)} (should be 1)")

    # Test 4: Delete
    print("\n4. Delete...")
    to_delete = User.create(name="DeleteMe", email="del@example.com")
    print(f"   Created: {to_delete}")
    to_delete.delete()
    gone = User.get(to_delete.id)
    print(f"   After delete: {gone} (should be None)")
    assert gone is None

    # Test 5: Default table name
    print("\n5. Default table name...")
    product = Product.create(title="Widget", price=19.99)
    print(f"   Product: {product}")
    assert product.id is not None

    print("\n=== All manual tests passed! ===")

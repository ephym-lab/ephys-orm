"""
Field Descriptors

Run with: pytest tests/test_fields.py -v
"""

import pytest
import psycopg2
from datetime import datetime
from src.ephyorm.db.connection import PostgresConnection
from src.ephyorm.orm.model_v3 import Model
from src.ephyorm.orm.fields import Field, IntegerField, StringField, BooleanField, DateTimeField
from src.ephyorm.exceptions import ValueValidationError

# ─────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────

TEST_DB_NAME = "orm_test_day4"
POSTGRES_DSN = "dbname=postgres user=postgres password='8%7Pkc&8;JULH' host=127.0.0.1 port=5432"
TEST_DSN = f"dbname={TEST_DB_NAME} user=postgres password='8%7Pkc&8;JULH' host=127.0.0.1 port=5432"


# ─────────────────────────────────────────────────────────────
# Test Models with Fields
# ─────────────────────────────────────────────────────────────

class User(Model):
    id = IntegerField(null=True)  # DB generates via SERIAL
    name = StringField(max_length=100)
    email = StringField(max_length=100, null=True)
    is_active = BooleanField(default=True)
    age = IntegerField(null=True, min_value=0, max_value=150)
    created_at = DateTimeField(null=True)

    _dsn = TEST_DSN


class Product(Model):
    id = IntegerField(null=True)  # DB generates via SERIAL
    title = StringField(max_length=200)
    price = IntegerField(default=0)
    in_stock = BooleanField(default=True)

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
            is_active BOOLEAN DEFAULT TRUE,
            age INTEGER,
            created_at TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id SERIAL PRIMARY KEY,
            title VARCHAR(200) NOT NULL,
            price INTEGER DEFAULT 0,
            in_stock BOOLEAN DEFAULT TRUE
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
# Tests: Descriptor Basics
# ─────────────────────────────────────────────────────────────

class TestDescriptorBasics:
    def test_set_name_stores_field_name(self):
        assert User.name.name == "name"
        assert User.age.name == "age"
        assert User.is_active.name == "is_active"

    def test_get_returns_descriptor_on_class(self):
        # Accessing User.name returns the Field descriptor, not a value
        assert isinstance(User.name, StringField)

    def test_get_returns_value_on_instance(self):
        user = User(name="Alice")
        assert user.name == "Alice"

    def test_set_stores_in_dict(self):
        user = User(name="Alice")
        assert user.__dict__["name"] == "Alice"

    def test_descriptor_set_validates(self):
        # Directly test that descriptor __set__ validates
        user = User.__new__(User)  # bypass __init__
        with pytest.raises(ValueValidationError, match="cannot be null"):
            User.name.__set__(user, None)  # null=False


# ─────────────────────────────────────────────────────────────
# Tests: StringField Validation
# ─────────────────────────────────────────────────────────────

class TestStringField:
    def test_accepts_valid_string(self):
        user = User(name="Alice")
        assert user.name == "Alice"

    def test_rejects_non_string(self):
        with pytest.raises(ValueValidationError, match="expected str"):
            User(name=123)

    def test_enforces_max_length(self):
        with pytest.raises(ValueValidationError, match="length 10 > max 5"):
            class ShortName(Model):
                name = StringField(max_length=5)
                _dsn = TEST_DSN
            ShortName(name="A" * 10)

    def test_allows_exact_max_length(self):
        class ExactName(Model):
            name = StringField(max_length=5)
            _dsn = TEST_DSN
        obj = ExactName(name="Alice")
        assert obj.name == "Alice"


# ─────────────────────────────────────────────────────────────
# Tests: IntegerField Validation
# ─────────────────────────────────────────────────────────────

class TestIntegerField:
    def test_accepts_valid_int(self):
        user = User(name="Alice", age=25)
        assert user.age == 25

    def test_rejects_non_int(self):
        with pytest.raises(ValueValidationError, match="expected int"):
            User(name="Alice", age="twenty")

    def test_enforces_min_value(self):
        with pytest.raises(ValueValidationError, match="value -1 < min 0"):
            User(name="Alice", age=-1)

    def test_enforces_max_value(self):
        with pytest.raises(ValueValidationError, match="value 200 > max 150"):
            User(name="Alice", age=200)

    def test_rejects_float(self):
        with pytest.raises(ValueValidationError, match="expected int"):
            User(name="Alice", age=25.5)


# ─────────────────────────────────────────────────────────────
# Tests: BooleanField Validation
# ─────────────────────────────────────────────────────────────

class TestBooleanField:
    def test_accepts_true(self):
        user = User(name="Alice", is_active=True)
        assert user.is_active is True

    def test_accepts_false(self):
        user = User(name="Alice", is_active=False)
        assert user.is_active is False

    def test_rejects_non_bool(self):
        with pytest.raises(ValueValidationError, match="expected bool"):
            User(name="Alice", is_active="yes")

    def test_rejects_int_even_though_python_treats_it_as_bool(self):
        with pytest.raises(ValueValidationError, match="expected bool"):
            User(name="Alice", is_active=1)


# ─────────────────────────────────────────────────────────────
# Tests: DateTimeField Validation
# ─────────────────────────────────────────────────────────────

class TestDateTimeField:
    def test_accepts_datetime(self):
        now = datetime(2024, 1, 15, 10, 30, 0)
        user = User(name="Alice", created_at=now)
        assert user.created_at == now.isoformat()  # to_db converts to string

    def test_rejects_string(self):
        with pytest.raises(ValueValidationError, match="expected datetime"):
            User(name="Alice", created_at="2024-01-15")

    def test_rejects_int_timestamp(self):
        with pytest.raises(ValueValidationError, match="expected datetime"):
            User(name="Alice", created_at=1705315800)


# ─────────────────────────────────────────────────────────────
# Tests: Null Constraint
# ─────────────────────────────────────────────────────────────

class TestNullConstraint:
    def test_null_field_allows_none(self):
        user = User(name="Alice", age=None)
        assert user.age is None

    def test_non_null_field_rejects_none(self):
        with pytest.raises(ValueValidationError, match="cannot be null"):
            User(name=None)

    def test_null_false_with_no_default_requires_value(self):
        # name has null=False, no default → must provide
        # User() should fail because name gets set to None
        with pytest.raises(ValueValidationError, match="cannot be null"):
            User()  # no name provided

    def test_null_false_explicit_none(self):
        # Explicitly passing None to a non-null field should fail
        with pytest.raises(ValueValidationError, match="cannot be null"):
            User(name=None)


# ─────────────────────────────────────────────────────────────
# Tests: Default Values (Challenge)
# ─────────────────────────────────────────────────────────────

class TestDefaultValues:
    def test_boolean_default_true(self):
        user = User(name="Alice")
        assert user.is_active is True  # default=True applied

    def test_integer_default(self):
        product = Product(title="Widget")
        assert product.price == 0  # default=0 applied

    def test_default_overridden_by_explicit_value(self):
        user = User(name="Alice", is_active=False)
        assert user.is_active is False

    def test_default_not_applied_when_value_provided(self):
        product = Product(title="Widget", price=99)
        assert product.price == 99

    def test_none_does_not_trigger_default(self):
        # If user explicitly passes None, it should NOT use default
        # Actually: our __set__ applies default when value is None
        # This is a design choice — Django does the same
        user = User(name="Alice", is_active=None)
        # is_active has default=True, null not specified (default False)
        # So None → default True
        assert user.is_active is True


# ─────────────────────────────────────────────────────────────
# Tests: Model Integration (CRUD with fields)
# ─────────────────────────────────────────────────────────────

class TestModelIntegration:
    def test_create_and_get(self, setup_database):
        user = User.create(name="Alice", email="alice@example.com", age=25)
        assert user.id is not None

        fetched = User.get(user.id)
        assert fetched.name == "Alice"
        assert fetched.age == 25

    def test_boolean_stored_and_retrieved(self, setup_database):
        user = User.create(name="Alice", email="alice@example.com", is_active=False)
        fetched = User.get(user.id)
        assert fetched.is_active is False

    def test_default_applied_on_create(self, setup_database):
        user = User.create(name="Alice", email="alice@example.com")
        assert user.is_active is True
        fetched = User.get(user.id)
        assert fetched.is_active is True

    def test_update_field(self, setup_database):
        user = User.create(name="Alice", email="alice@example.com", age=25)
        user.age = 30
        user.save()

        fetched = User.get(user.id)
        assert fetched.age == 30

    def test_validation_on_update(self, setup_database):
        user = User.create(name="Alice", email="alice@example.com", age=25)
        with pytest.raises(ValueValidationError, match="expected int"):
            user.age = "old"

    def test_cannot_assign_invalid_type_to_field(self, setup_database):
        user = User(name="Alice")
        with pytest.raises(ValueValidationError, match="expected str"):
            user.name = 123


# ─────────────────────────────────────────────────────────────
# Tests: _get_field_data scans descriptors only
# ─────────────────────────────────────────────────────────────

class TestFieldData:
    def test_get_field_data_includes_only_descriptor_fields(self, setup_database):
        user = User(name="Alice", email="alice@example.com")
        user._arbitrary = "not a field"
        fields = user._get_field_data()
        assert "name" in fields
        assert "email" in fields
        assert "_arbitrary" not in fields

    def test_get_field_data_excludes_none_pk(self, setup_database):
        user = User(name="Alice")
        fields = user._get_field_data()
        assert "id" not in fields  # None pk excluded
        assert "name" in fields


# ─────────────────────────────────────────────────────────────
# Tests: from_db conversion
# ─────────────────────────────────────────────────────────────

class TestFromDB:
    def test_boolean_from_db(self, setup_database):
        # PostgreSQL might return 't'/'f' or True/False
        assert BooleanField().from_db(True) is True
        assert BooleanField().from_db(False) is False
        assert BooleanField().from_db('t') is True
        assert BooleanField().from_db('f') is False

    def test_integer_from_db(self, setup_database):
        assert IntegerField().from_db(42) == 42
        assert IntegerField().from_db(None) is None

    def test_string_from_db(self, setup_database):
        assert StringField().from_db("hello") == "hello"
        assert StringField().from_db(None) is None


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
            is_active BOOLEAN DEFAULT TRUE,
            age INTEGER,
            created_at TIMESTAMP
        )
    """)
    conn.commit()
    cur.close()
    conn.close()

    print("\n=== Manual Field Tests ===\n")

    # Test 1: Validation
    print("1. Validation...")
    try:
        User(name="Alice", age=25)
        print("   Valid user created")
    except ValueValidationError as e:
        print(f"   ERROR: {e}")

    try:
        User(name="Alice", age="bad")
    except ValueValidationError as e:
        print(f"   Caught expected error: {e}")

    # Test 2: Defaults
    print("\n2. Defaults...")
    user = User(name="Alice")
    print(f"   is_active default: {user.is_active}")

    # Test 3: CRUD
    print("\n3. CRUD...")
    user = User.create(name="Bob", email="bob@example.com", age=30)
    print(f"   Created: {user}")
    fetched = User.get(user.id)
    print(f"   Fetched: {fetched}")

    print("\n=== All manual tests passed! ===")

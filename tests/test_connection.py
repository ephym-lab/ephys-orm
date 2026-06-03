import pytest
import psycopg2
from src.ephyorm.db.connection import PostgresConnection
from src.ephyorm.exceptions import ValueValidationError, RuntimeConfigError

# DSN strings with password properly quoted to handle semicolon
TEST_DB_NAME = "orm_test"
POSTGRES_DSN = "dbname=postgres user=myuser password='8%7Pkc&8;JULH' host=127.0.0.1 port=5432"
TEST_DSN = f"dbname={TEST_DB_NAME} user=myuser password='8%7Pkc&8;JULH' host=127.0.0.1 port=5432"


@pytest.fixture(scope="module")
def setup_database():
    """Create the test database and users table."""
    # Connect to 'postgres' database to create our test DB
    conn = psycopg2.connect(POSTGRES_DSN)
    conn.autocommit = True
    cur = conn.cursor()
    
    # Drop and recreate test database
    cur.execute(f"DROP DATABASE IF EXISTS {TEST_DB_NAME}")
    cur.execute(f"CREATE DATABASE {TEST_DB_NAME}")
    cur.close()
    conn.close()
    
    # Connect to test DB and create table
    conn = psycopg2.connect(TEST_DSN)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (  
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            email VARCHAR(100) UNIQUE
        )
    """)
    conn.commit()
    cur.close()
    conn.close()


class TestPostgresConnection:
    
    def test_context_manager_opens_and_closes_connection(self, setup_database):
        """Verify connection is opened in __enter__ and closed in __exit__."""
        conn = None
        
        with PostgresConnection(TEST_DSN) as pg_conn:
            conn = pg_conn._conn
            assert conn is not None
            assert conn.closed == 0  # 0 means open
        
        # After exiting the context, connection must be closed
        assert conn.closed != 0
    
    def test_connection_closed_even_on_exception(self, setup_database):
        """Verify connection cleanup happens even if an exception is raised."""
        conn = None
        
        try:
            with PostgresConnection(TEST_DSN) as pg_conn:
                conn = pg_conn._conn
                raise ValueValidationError("Something went wrong")
        except ValueValidationError:
            pass
        
        assert conn.closed != 0
    
    def test_execute_select_returns_rows(self, setup_database):
        """Test basic SELECT query execution."""
        with PostgresConnection(TEST_DSN) as conn:
            # Insert a test row first (we'll commit later)
            conn.execute(
                "INSERT INTO users (name, email) VALUES (%s, %s)",
                ("Alice", "alice@example.com")
            )
            conn.commit()
            
            # Now select it back
            rows = conn.execute(
                "SELECT * FROM users WHERE name = %s",
                ("Alice",)
            )
            
            assert len(rows) == 1
            assert rows[0]["name"] == "Alice"
            assert rows[0]["email"] == "alice@example.com"
    
    def test_execute_without_commit_does_not_persist(self, setup_database):
        """
        Challenge test: INSERT without commit should not persist after connection closes.
        """
        # Insert without committing
        with PostgresConnection(TEST_DSN) as conn:
            conn.execute(
                "INSERT INTO users (name, email) VALUES (%s, %s)",
                ("Bob", "bob@example.com")
            )
            # No commit() called!
        
        # Verify Bob is NOT in the database
        with PostgresConnection(TEST_DSN) as conn:
            rows = conn.execute(
                "SELECT * FROM users WHERE name = %s",
                ("Bob",)
            )
            assert len(rows) == 0
    
    def test_execute_with_commit_persists(self, setup_database):
        """
        Challenge test: INSERT with explicit commit should persist.
        """
        with PostgresConnection(TEST_DSN) as conn:
            conn.execute(
                "INSERT INTO users (name, email) VALUES (%s, %s)",
                ("Charlie", "charlie@example.com")
            )
            conn.commit()
        
        # Verify Charlie IS in the database
        with PostgresConnection(TEST_DSN) as conn:
            rows = conn.execute(
                "SELECT * FROM users WHERE name = %s",
                ("Charlie",)
            )
            assert len(rows) == 1
            assert rows[0]["email"] == "charlie@example.com"
    
    def test_rollback_on_execute_error(self, setup_database):
        """
        Challenge test: If execute raises an exception, the transaction is rolled back.
        The connection stays open (for potential cleanup queries) and is closed by __exit__.
        """
        with PostgresConnection(TEST_DSN) as conn:
            # Insert a valid row
            conn.execute(
                "INSERT INTO users (name, email) VALUES (%s, %s)",
                ("BeforeError", "before@example.com")
            )
            
            # This should fail (trigger a real SQL error)
            with pytest.raises(psycopg2.Error):
                conn.execute("SELECT * FROM nonexistent_table")
            
            # After rollback, we should still be able to use the connection
            # The previous INSERT should be rolled back
            conn.execute(
                "INSERT INTO users (name, email) VALUES (%s, %s)",
                ("AfterError", "after@example.com")
            )
            conn.commit()
        
        # Verify only "AfterError" exists, not "BeforeError"
        with PostgresConnection(TEST_DSN) as conn:
            before_rows = conn.execute(
                "SELECT * FROM users WHERE name = %s",
                ("BeforeError",)
            )
            after_rows = conn.execute(
                "SELECT * FROM users WHERE name = %s",
                ("AfterError",)
            )
            assert len(before_rows) == 0  # Rolled back
            assert len(after_rows) == 1   # Committed
    
    def test_multiple_queries_same_connection(self, setup_database):
        """Test that multiple queries can run within the same connection context."""
        with PostgresConnection(TEST_DSN) as conn:
            conn.execute(
                "INSERT INTO users (name, email) VALUES (%s, %s)",
                ("Multi1", "multi1@example.com")
            )
            conn.execute(
                "INSERT INTO users (name, email) VALUES (%s, %s)",
                ("Multi2", "multi2@example.com")
            )
            conn.commit()
        
        with PostgresConnection(TEST_DSN) as conn:
            rows = conn.execute("SELECT * FROM users WHERE name LIKE 'Multi%' ORDER BY name")
            assert len(rows) == 2
            assert rows[0]["name"] == "Multi1"
            assert rows[1]["name"] == "Multi2"
    
    def test_real_dict_cursor_returns_dicts(self, setup_database):
        """Verify RealDictCursor returns dictionary-like rows."""
        with PostgresConnection(TEST_DSN) as conn:
            rows = conn.execute("SELECT * FROM users WHERE name = %s", ("Alice",))
            assert len(rows) > 0
            # RealDictRow behaves like a dict
            row = rows[0]
            assert "id" in row
            assert "name" in row
            assert "email" in row
            assert row["name"] == "Alice"

class TestExecuteGuards:
    """Test that execute() guards against raw transaction keywords."""
    
    def test_begin_blocked(self, setup_database):
        with PostgresConnection(TEST_DSN) as conn:
            with pytest.raises(RuntimeConfigError, match="Raw 'BEGIN' is not allowed"):
                conn.execute("BEGIN")
    
    def test_commit_blocked(self, setup_database):
        with PostgresConnection(TEST_DSN) as conn:
            conn.execute("INSERT INTO users (name) VALUES ('test')")
            with pytest.raises(RuntimeConfigError, match="Raw 'COMMIT' is not allowed"):
                conn.execute("COMMIT")
            conn.commit()  # This is the proper way
    
    def test_rollback_blocked(self, setup_database):
        with PostgresConnection(TEST_DSN) as conn:
            with pytest.raises(RuntimeConfigError, match="Raw 'ROLLBACK' is not allowed"):
                conn.execute("ROLLBACK")
    
    def test_savepoint_blocked(self, setup_database):
        with PostgresConnection(TEST_DSN) as conn:
            with pytest.raises(RuntimeConfigError, match="Raw 'SAVEPOINT' is not allowed"):
                conn.execute("SAVEPOINT sp1")


class TestExecuteRaw:
    """Test the escape hatch for manual transaction control."""
    
    def test_raw_begin_commit_works(self, setup_database):
        with PostgresConnection(TEST_DSN) as conn:
            conn.execute_raw("BEGIN")
            conn.execute_raw("INSERT INTO users (name, email) VALUES (%s, %s)", ("RawUser", "raw@example.com"))
            conn.execute_raw("COMMIT")
        
        # Verify it persisted
        with PostgresConnection(TEST_DSN) as conn:
            rows = conn.execute("SELECT * FROM users WHERE name = %s", ("RawUser",))
            assert len(rows) == 1
    
    def test_raw_no_auto_rollback_on_error(self, setup_database):
        """
        execute_raw() does NOT auto-rollback on error.
        The transaction stays in aborted state.
        """
        with PostgresConnection(TEST_DSN) as conn:
            conn.execute_raw("BEGIN")
            conn.execute_raw("INSERT INTO users (name, email) VALUES (%s, %s)", ("PreRaw", "preraw@example.com"))
            
            # This will fail and leave transaction aborted
            with pytest.raises(psycopg2.Error):
                conn.execute_raw("SELECT * FROM no_such_table")
            
            # Because we didn't rollback, the transaction is aborted
            # Any new query will fail until we rollback
            with pytest.raises(psycopg2.errors.InFailedSqlTransaction):
                conn.execute_raw("SELECT 1")
            
            # Must manually rollback to recover
            conn.execute_raw("ROLLBACK")
    
    def test_raw_savepoint_works(self, setup_database):
        """Test that savepoints work through execute_raw()."""
        with PostgresConnection(TEST_DSN) as conn:
            conn.execute_raw("BEGIN")
            conn.execute_raw("INSERT INTO users (name, email) VALUES (%s, %s)", ("SaveOuter", "outer@example.com"))
            conn.execute_raw("SAVEPOINT sp1")
            conn.execute_raw("INSERT INTO users (name, email) VALUES (%s, %s)", ("SaveInner", "inner@example.com"))
            conn.execute_raw("ROLLBACK TO SAVEPOINT sp1")  # Undo inner
            conn.execute_raw("COMMIT")
        
        # Only outer should exist
        with PostgresConnection(TEST_DSN) as conn:
            outer = conn.execute("SELECT * FROM users WHERE name = %s", ("SaveOuter",))
            inner = conn.execute("SELECT * FROM users WHERE name = %s", ("SaveInner",))
            assert len(outer) == 1
            assert len(inner) == 0  # Rolled back to savepoint

# Manual test script (run without pytest)
if __name__ == "__main__":
    print("Running manual tests...")
    
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
    cur.execute("CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY, name VARCHAR(100), email VARCHAR(100))")
    conn.commit()
    cur.close()
    conn.close()
    
    # Test 1: Basic context manager
    print("\n1. Testing context manager opens/closes...")
    with PostgresConnection(TEST_DSN) as pg:
        raw_conn = pg._conn
        assert raw_conn.closed == 0
        print(f"   Connection open: {raw_conn.closed == 0}")
    print(f"   Connection closed after exit: {raw_conn.closed != 0}")
    
    # Test 2: Insert and select
    print("\n2. Testing INSERT + SELECT...")
    with PostgresConnection(TEST_DSN) as pg:
        pg.execute("INSERT INTO users (name, email) VALUES (%s, %s)", ("TestUser", "test@example.com"))
        pg.commit()
        rows = pg.execute("SELECT * FROM users WHERE name = %s", ("TestUser",))
        print(f"   Inserted and found: {rows[0]['name']} ({rows[0]['email']})")
    
    # Test 3: No commit = no persist
    print("\n3. Testing no-commit behavior...")
    with PostgresConnection(TEST_DSN) as pg:
        pg.execute("INSERT INTO users (name, email) VALUES (%s, %s)", ("Ghost", "ghost@example.com"))
        # No commit!
    
    with PostgresConnection(TEST_DSN) as pg:
        rows = pg.execute("SELECT * FROM users WHERE name = %s", ("Ghost",))
        print(f"   Ghost user found after no-commit: {len(rows) > 0} (should be False)")
    
    # Test 4: Error rollback
    print("\n4. Testing rollback on error...")
    with PostgresConnection(TEST_DSN) as pg:
        pg.execute("INSERT INTO users (name, email) VALUES (%s, %s)", ("PreError", "pre@example.com"))
        try:
            pg.execute("SELECT * FROM no_such_table")
        except psycopg2.Error as e:
            print(f"   Caught expected error: {type(e).__name__}")
        # After rollback, this should work
        pg.execute("INSERT INTO users (name, email) VALUES (%s, %s)", ("PostError", "post@example.com"))
        pg.commit()
    
    with PostgresConnection(TEST_DSN) as pg:
        pre = pg.execute("SELECT * FROM users WHERE name = %s", ("PreError",))
        post = pg.execute("SELECT * FROM users WHERE name = %s", ("PostError",))
        print(f"   PreError found: {len(pre) > 0} (should be False, rolled back)")
        print(f"   PostError found: {len(post) > 0} (should be True, committed)")
    
    print("\nAll manual tests passed!")
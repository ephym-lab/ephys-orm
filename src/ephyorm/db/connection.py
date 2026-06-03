import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Optional, Any, List, Dict, Set


class PostgresConnection:
    """
    A context-managed PostgreSQL connection wrapper.
    
    Usage:
        with PostgresConnection(dsn) as conn:
            rows = conn.execute("SELECT * FROM users WHERE id = %s", (1,))
            conn.commit()  # explicit commit required
    """
    
    # Transaction control keywords that we guard against in execute()
    _TXN_KEYWORDS: Set[str] = {"BEGIN", "COMMIT", "ROLLBACK", "END", "ABORT", "SAVEPOINT", "RELEASE"}
    
    def __init__(self, dsn: str):
        self.dsn = dsn
        self._conn: Optional[psycopg2.extensions.connection] = None
        self._cursor: Optional[psycopg2.extensions.cursor] = None
    
    def __enter__(self) -> "PostgresConnection":
        """Open connection and return self (the wrapper, not raw connection)."""
        self._conn = psycopg2.connect(self.dsn)
        # RealDictCursor returns rows as dictionaries instead of tuples
        self._cursor = self._conn.cursor(cursor_factory=RealDictCursor)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """
        Always close the connection, even if an exception occurred.
        The context manager is the single owner of the connection lifecycle.
        """
        if self._cursor:
            try:
                self._cursor.close()
            except Exception:
                pass
            self._cursor = None
        
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None
    
    def _check_open(self) -> None:
        """Verify connection and cursor are available."""
        if not self._conn or self._conn.closed:
            raise RuntimeError("Connection is not open. Use 'with PostgresConnection(...) as conn:'")
        if not self._cursor:
            raise RuntimeError("Cursor is not available")
    
    def _is_txn_keyword(self, query: str) -> bool:
        """Check if query starts with a transaction control keyword."""
        first_word = query.strip().split(maxsplit=1)[0].upper()
        return first_word in self._TXN_KEYWORDS
    
    def execute(self, query: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
        """
        Execute a managed query and return fetched rows.
        
        Guards against raw transaction control keywords (BEGIN, COMMIT, etc.)
        to maintain the connection's state machine. Use execute_raw() if you
        need to manage transactions yourself.
        
        If an exception occurs during execution, the transaction is rolled back
        automatically (but the connection stays open — __exit__ will close it).
        """
        self._check_open()
        
        if self._is_txn_keyword(query):
            first_word = query.strip().split(maxsplit=1)[0].upper()
            raise RuntimeError(
                f"Raw '{first_word}' is not allowed in execute(). "
                f"Use conn.commit() or conn.rollback() instead, "
                f"or use conn.execute_raw() if you need manual control."
            )
        
        try:
            self._cursor.execute(query, params)
            
            # Only fetch if the cursor has results (not for INSERT/UPDATE/DELETE)
            if self._cursor.description:
                return self._cursor.fetchall()
            return []
            
        except psycopg2.Error as e:
            # Roll back on error so the connection remains usable for subsequent
            # queries within the same with block, but the failed transaction
            # is cleaned up.
            self._conn.rollback()
            raise e
    
    def execute_raw(self, query: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
        """
        Execute without transaction guards. You manage transactions yourself.
        
        This is the escape hatch for advanced use cases where you need
        explicit control over BEGIN/COMMIT/ROLLBACK/SAVEPOINT.
        
        No automatic rollback on error — the transaction stays in whatever
        state PostgreSQL puts it in.
        """
        self._check_open()
        
        self._cursor.execute(query, params)
        
        if self._cursor.description:
            return self._cursor.fetchall()
        return []
    
    def commit(self) -> None:
        """Explicitly commit the current transaction."""
        self._check_open()
        self._conn.commit()
    
    def rollback(self) -> None:
        """Explicitly roll back the current transaction."""
        self._check_open()
        self._conn.rollback()
    
    @property
    def closed(self) -> bool:
        """Check if the underlying connection is closed."""
        return self._conn is None or self._conn.closed != 0
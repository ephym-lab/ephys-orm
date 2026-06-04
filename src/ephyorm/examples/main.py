from ephyorm.db.connection import PostgresConnection
from ephyorm.orm.query import Query
from ephyorm.orm.model_v2 import Model
import psycopg2


TEST_DB_NAME = "orm_test"
POSTGRES_DSN = "dbname=postgres user=myuser password='8%7Pkc&8;JULH' host=127.0.0.1 port=5432"


class User(Model):
    __table__ = 'users'
    __primary_key__ = 'id'
    _dsn : str = "dbname=orm_test user=myuser password='8%7Pkc&8;JULH' host=127.0.0.1 port=5432"
    name : str
    email : str
    age : int

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

# def create_db():
    
#     with PostgresConnection(POSTGRES_DSN) as conn:
#         # conn.execute(f"DROP DATABASE {TEST_DB_NAME}")
#         conn.execute(f"CREATE DATABASE {TEST_DB_NAME}")
#         conn.commit()



# def create_table():
#     with PostgresConnection(User._dsn) as conn:
#         conn.execute("""
#             CREATE TABLE IF NOT EXISTS users (
#                 id SERIAL PRIMARY KEY,
#                 name VARCHAR(100) NOT NULL,
#                 email VARCHAR(100) UNIQUE,
#                 age INTEGER
#             )
#         """)
#         conn.commit()

def create_table():
    with PostgresConnection(POSTGRES_DSN) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                email VARCHAR(100) UNIQUE,
                age INTEGER
            )
        """)
        conn.commit()

def insert_user():
    user = User.create(name="John", email="ephy@gmail.com", age=30)
    print(user)

if __name__ == "__main__":
    print("Creating database...")
    setup_database()
    print("Database created.")
    print("Creating table...")
    create_table()
    print("Table created.")

    print("Inserting user...")
    insert_user()
    print("User inserted.")

    print("Fetching user...")
    user = User.filter(name="John")
    print(user)
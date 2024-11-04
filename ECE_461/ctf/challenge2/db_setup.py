import os
from time import sleep

import psycopg2

# PostgreSQL connection setup
print("Connecting to PostgreSQL...")
conn = psycopg2.connect(
    dbname="bookstore",
    user="myuser",
    password="mypassword",
    host="db"
)
cur = conn.cursor()

# Create tables if they don't exist
print("Creating users table...")
cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        username VARCHAR(50) UNIQUE NOT NULL,
        password VARCHAR(100) NOT NULL
    );
""")

# Insert a user
print("Inserting user...")
cur.execute("""
INSERT INTO users (username, password) VALUES ('parth', 'parth123');
INSERT INTO users (username, password) VALUES ('huiyun', 'pikapika');
""")

# Create books table
print("Creating books table...")
cur.execute("""
    CREATE TABLE IF NOT EXISTS books (
        id SERIAL PRIMARY KEY,
        title VARCHAR(100) NOT NULL,
        author VARCHAR(100) NOT NULL
    );
""")

# Insert some books and a user
print("Inserting books...")
cur.execute("""
INSERT INTO books (title, author) VALUES ('The Great Gatsby', 'F. Scott Fitzgerald');
INSERT INTO books (title, author) VALUES ('To Kill a Mockingbird', 'Harper Lee');
INSERT INTO books (title, author) VALUES ('1984', 'George Orwell');
INSERT INTO books (title, author) VALUES ('Animal Farm', 'George Orwell');
INSERT INTO books (title, author) VALUES ('Brave New World', 'Aldous Huxley');
INSERT INTO books (title, author) VALUES ('The Catcher in the Rye', 'J.D. Salinger');
INSERT INTO books (title, author) VALUES ('Lord of the Flies', 'William Golding');
""")

# Commit changes and close the connection
print("Committing changes and closing connection...")
conn.commit()
cur.close()
conn.close()

import os
import csv

from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL is not set")

# Set up database
engine = create_engine(os.getenv("DATABASE_URL"))
db = scoped_session(sessionmaker(bind=engine))

db.execute(
    """create table books
        (id serial primary key,
        isbn varchar not null,
        title varchar not null,
        author varchar not null,
        year integer not null)"""
)

f = open("books.csv")
reader = csv.reader(f)
next(reader)

for isbn, title, author, year in reader:
    db.execute("insert into books (isbn, title, author, year) values (:isbn, :title, :author, :year)",
                {'isbn': isbn, 'title': title, 'author': author, 'year': int(year)})
        
db.commit()

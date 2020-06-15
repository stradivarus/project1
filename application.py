import os

from flask import Flask, session, render_template, request, redirect, flash, url_for, jsonify
from flask_session import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import requests


app = Flask(__name__)

# Check for environment variable
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL is not set")

# Configure session to use filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Set up database
engine = create_engine(os.getenv("DATABASE_URL"))
db = scoped_session(sessionmaker(bind=engine))


def login_required(f):
    """
    Decorate routes to require login.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated_function


@app.route("/", methods=['GET', "POST"])
@login_required
def index():
    
    error = None
    res = None

    if request.method == 'POST':
        search = request.form.get("search")
        search_type = request.form.get("search-type")

        if not search:
            error = "Type a search phrase!"
        else:
            if search_type == "title":
                res = db.execute("""select * from books where lower(title) like :search
                                    order by author, title""",
                                    {'search': '%' + search.lower() + '%'}).fetchall()
            elif search_type == "author":
                res = db.execute("""select * from books where lower(author) like :search
                                    order by author, title""",
                                    {'search': '%' + search.lower() + '%'}).fetchall()
            else:
                res = db.execute("""select * from books where lower(isbn) like :search
                                    order by author, title""",
                                    {'search': '%' + search.lower() + '%'}).fetchall()
    
            if not res:
                error = "No search results."
        
    return render_template("index.html", res=res, error=error)


@app.route("/register", methods=["GET", "POST"])
def register():

    error = None

    if request.method == "POST":

        name = request.form.get("name")
        pw = request.form.get("password")
        conf = request.form.get("confirmation")

        # check if username available
        if not name or db.execute("select * from users where name = :name", {'name': name}).rowcount > 0:
            error = "username already exists/blank"
        
        # check if passwords match
        elif not pw or not pw == conf:
            error = "passwords don't match/blank"

        # add new user to db and log him in
        else:
            session["user_id"] = db.execute(
            "insert into users (name, hash) values (:name, :pwhash) returning id",
            {"name": name, "pwhash": generate_password_hash(pw)},
            ).fetchone()[0]
            db.commit()

            flash("You were successfully registered!")
            return redirect(url_for('index'))

    return render_template("register.html", error=error)


@app.route("/login", methods=["GET", "POST"])
def login():

    error = None

    if request.method == "POST":

        name = request.form.get("name")
        pw = request.form.get("password")
        user = db.execute("select * from users where name = :name", {'name': name}).fetchone()

        # check if username exists
        if not name or not user:
            error = "username doesn't exist/blank"
        
        # check if passwords match
        elif not check_password_hash(user.hash, pw):
            error = "wrong password"

        # log user in
        else:
            session["user_id"] = user.id

            flash("You were successfully logged in!")
            return redirect(url_for('index'))

    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()

    flash("You were successfully logged out!")
    return redirect(url_for('index'))


@app.route("/books/<int:book_id>", methods=["POST", "GET"])
@login_required
def book(book_id):
    
    book = db.execute("select * from books where id = :book_id", {'book_id': book_id}).fetchone()

    res = None
    error = None
    review = None
    reviews = None

    if book:
        if request.method == 'GET':

            res = requests.get("https://www.goodreads.com/book/review_counts.json",
                                    params={"key": "mPHEmSjRKt84vyniw4fNJA", "isbns": book.isbn})
            if res.status_code != 200:
                res = None
            else:
                res=res.json()

            # we won't let user leave a review if he did already for THIS BOOK
            review = db.execute("select * from reviews where user_id = :user_id and book_id = :book_id",
                                    {'user_id': session["user_id"], 'book_id': book_id}).fetchone()

            # also need to display all reviews for THIS BOOK
            reviews = db.execute("""select reviews.rating, reviews.title, reviews.content,
                                    users.name from reviews JOIN users on reviews.user_id = users.id
                                    where book_id = :book_id""", {'book_id': book.id}).fetchall()

        else: # 'POST'

            title = request.form.get("title")
            slider = request.form.get("slider")
            text = request.form.get("text")

            db.execute("""insert into reviews (rating, title, content, user_id, book_id)
                            values (:rating, :title, :content, :user_id, :book_id)""",
                            {'rating': int(slider), 'title': title, 'content': text,
                             'user_id': session["user_id"], 'book_id': book.id})
            db.commit()
            flash("Thanks for leaving a review!")

            return redirect(url_for('book', book_id=book_id))

    else:
        error = "No book here =("

    return render_template("book.html", book = book, error=error, res=res,
                                review=review, reviews=reviews)


@app.route("/api/<string:isbn>")
@login_required
def api(isbn):

    book = db.execute("select * from books where isbn = :isbn", {'isbn': isbn}).fetchone()

    if not book:
        return jsonify({"error": "Not a valid ISBN"}), 404

    res = requests.get("https://www.goodreads.com/book/review_counts.json",
                                    params={"key": "mPHEmSjRKt84vyniw4fNJA", "isbns": isbn}).json()

    return jsonify({
            "title": book.title,
            "author": book.author,
            "year": book.year,
            "isbn": book.isbn,
            "review_count": res["books"][0]["work_ratings_count"],
            "average_score": float(res["books"][0]["average_rating"])
    })


@app.errorhandler(404)
def handle_error(e):
    return render_template("error.html"), 404


import psycopg2
from flask import Flask, flash, redirect, render_template, request, url_for
from flask_login import (LoginManager, UserMixin, current_user, login_required,
                         login_user, logout_user)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'ctfchallenge2'

# Flask-Login manager setup
login_manager = LoginManager()
login_manager.init_app(app)

# Database connection function
def get_db_connection():
    return psycopg2.connect(
        dbname="bookstore",
        user="myuser",
        password="mypassword",
        host="db"  # Change to 'db' if using Docker
    )

# Custom User class
class User(UserMixin):
    def __init__(self, id, username, password):
        self.id = id
        self.username = username
        self.password = password

    # Flask-Login requires these properties for login management
    def is_active(self):
        return True

    def is_authenticated(self):
        return True

    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.id)

@login_manager.user_loader
def load_user(user_id):
    # Database query to fetch user by ID
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, username, password FROM users WHERE id = %s", (user_id,))
    user = cur.fetchone()
    cur.close()
    conn.close()

    # Return User object if user found
    if user:
        return User(user[0], user[1], user[2])
    return None

# Route: Home / Login page
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        # Query user by username
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, username, password FROM users WHERE username = %s", (username,))
        user = cur.fetchone()
        cur.close()
        conn.close()

        # Check if user exists and password matches
        if user and user[2] == password:
            # Create a User object with retrieved user data
            user_id, user_name, user_password = user
            user_obj = User(user_id, user_name, user_password)

            # Login the user
            login_user(user_obj)
            return redirect(url_for('book_list'))
        else:
            flash("Invalid username or password.")

    return render_template('login.html')


# Insecure book list with search
@app.route('/books', methods=['GET', 'POST'])
@login_required
def book_list():
    search_query = request.form.get('search')  # Get search input from the form

    # Insecure query
    if search_query:
        query = f"SELECT * FROM books WHERE title LIKE '%{search_query}%' OR author LIKE '%{search_query}%'"
    else:
        query = "SELECT * FROM books"

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(query)
    books = cur.fetchall()
    cur.close()
    conn.close()

    return render_template('books.html', books=books)

# Route: Secret page
@app.route('/secret')
@login_required
def secret():
    if current_user.username == 'huiyun':
        return render_template('secret.html')
    else:
        flash("Only Huiyun can access the secret page.")
        return redirect(url_for('book_list'))

# Route: Logout
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


if __name__ == '__main__':
    app.run(debug=True)

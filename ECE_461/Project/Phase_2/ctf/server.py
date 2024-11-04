import os

from flask import (Flask, abort, redirect, render_template_string, request,
                   send_file, send_from_directory, url_for)

# Initialize the Flask app
app = Flask(__name__)

# Define the path to the data folder
DATA_FOLDER = os.path.join(os.getcwd(), 'data')

# HTML template for the index page
index_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>File Server</title>
    <style>
        body { font-family: Arial, sans-serif; margin-top: 50px; text-align: center; }
        input[type="text"] { padding: 8px; width: 200px; }
        button { padding: 8px 15px; margin-top: 10px; }
    </style>
</head>
<body>
    <h1>Welcome to the File Server</h1>
    <p>Enter the file name to download:</p>
    <form action="/download" method="post">
        <input type="text" name="filename" placeholder="Enter filename" required>
        <button type="submit">Download</button>
    </form>
</body>
</html>
"""

@app.route('/')
def index():
    # Render the index page with an input form
    return render_template_string(index_html)

@app.route('/download', methods=['POST'])
def download():
    # Get the filename from the form input
    filename = request.form.get('filename')
    # Redirect to the file-serving route if a filename is provided
    return redirect(url_for('serve_file', filename=filename))

@app.route('/file')
def serve_file():
    filename = request.args.get('filename')
    filepath = os.path.join(DATA_FOLDER, filename)
    try:
        if os.path.exists(filepath):
            return send_file(filepath, as_attachment=True)
        else:
            abort(404, description="File not found or path is invalid.")
    except FileNotFoundError:
        abort(404, description="File not found.")

    # try:
    #     return send_from_directory(DATA_FOLDER, filename)
    # except FileNotFoundError:
    #     abort(404, description="File not found.")

# Run the app
if __name__ == '__main__':
    # Ensure the data folder exists
    if not os.path.exists(DATA_FOLDER):
        os.makedirs(DATA_FOLDER)
    # Start the Flask server
    app.run(debug=True)
    # Start the Flask server
    app.run(debug=True)
    app.run(debug=True)

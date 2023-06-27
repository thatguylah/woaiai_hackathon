from flask import Flask

app = Flask(__name__)

@app.route("/")
def hello():
    return "Hello, World!"

@app.route("/about")
def about():
    return {
        "body": "Hello world",
        "status_code":200
    }

@app.route("/contact")
def contact():
    return "You can contact us at example@example.com."

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)


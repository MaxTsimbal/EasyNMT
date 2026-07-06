from flask import Flask, render_template
from config import Config

app = Flask(__name__)
app.config.from_object(Config)

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/goal")
def goal():
    return render_template("goal.html")
if __name__ == "__main__":
    app.run(debug=True)
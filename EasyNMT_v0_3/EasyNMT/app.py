from flask import Flask, render_template, session, redirect, url_for
from config import Config

app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = "EasyNMT_SECRET"


def get_user_data():
    goal = session.get("goal", "Не вибрано")
    subject_key = session.get("subject", "none")
    time_key = session.get("time_left", "none")

    subject_names = {
        "math": "📐 Математика",
        "ukrainian": "🇺🇦 Українська мова",
        "history": "📜 Історія України",
        "english": "🇬🇧 Англійська мова",
        "none": "Не вибрано"
    }

    first_topics = {
        "math": "Квадратні рівняння",
        "ukrainian": "Орфографія та правопис",
        "history": "Київська Русь",
        "english": "Present Simple",
        "none": "Тема буде визначена"
    }

    lesson_goals = {
        "math": "навчитися розв’язувати базові приклади та не губитися у формулах",
        "ukrainian": "повторити ключові правила правопису для тестових завдань",
        "history": "зрозуміти головні події, дати та персоналії теми",
        "english": "пригадати правила вживання часу та типові помилки",
        "none": "почати з базового діагностичного уроку"
    }

    time_names = {
        "1-month": "1 місяць",
        "2-months": "2 місяці",
        "3-plus": "3+ місяці",
        "6-plus": "6+ місяців",
        "none": "Не вибрано"
    }

    daily_time = {
        "1-month": "60–90 хв щодня",
        "2-months": "45–60 хв щодня",
        "3-plus": "30–45 хв щодня",
        "6-plus": "25–35 хв щодня",
        "none": "25 хв сьогодні"
    }

    return {
        "goal": goal,
        "subject": subject_names.get(subject_key, "Не вибрано"),
        "first_topic": first_topics.get(subject_key, "Тема буде визначена"),
        "lesson_goal": lesson_goals.get(subject_key, "почати з базового діагностичного уроку"),
        "time_left": time_names.get(time_key, "Не вибрано"),
        "daily_time": daily_time.get(time_key, "25 хв сьогодні")
    }


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/goal")
def goal():
    return render_template("goal.html", step=1)


@app.route("/set-goal/<goal>")
def set_goal(goal):
    session["goal"] = goal
    return redirect(url_for("subject"))


@app.route("/subject")
def subject():
    return render_template("subject.html", step=2)


@app.route("/set-subject/<subject>")
def set_subject(subject):
    session["subject"] = subject
    return redirect(url_for("date"))


@app.route("/date")
def date():
    return render_template("date.html", step=3)


@app.route("/set-time/<time_left>")
def set_time(time_left):
    session["time_left"] = time_left
    return redirect(url_for("loader"))


@app.route("/loader")
def loader():
    return render_template("loader.html")


@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html", **get_user_data())


@app.route("/today")
def today():
    return render_template("today.html", **get_user_data())


if __name__ == "__main__":
    app.run(debug=True)

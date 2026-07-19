import os
import hashlib
import json
import random
import re
import secrets
import sqlite3
import time
import uuid
from datetime import date as dt_date, datetime, timedelta
from functools import wraps

from flask import Flask, Response, abort, flash, jsonify, redirect, render_template, request, send_file, session, stream_with_context, url_for
from dotenv import load_dotenv

# Load local development settings before Config reads environment variables.
load_dotenv()
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix

from config import Config
from ai_service import EasyNMT_AI
from learning_engine import MAX_SCORE, PASS_SCORE, build_quiz, grade_question
from lesson_board_engine import build_lesson_board
from solution_annotation_engine import create_annotated_solution
from vision_grading_engine import VisionGradingEngine
from easynmt_ai import AIOrchestrator, AIRepository, AIRequest, LearningContext
from easynmt_learning import LearningGenerationService, LearningRepository
from easynmt_ai.attachments import AttachmentError, normalize_attachment_ids, save_image_upload

from google_oauth import build_authorization_url, credentials_status, exchange_callback
from easynmt_core.health import health_bp


app = Flask(__name__)
app.config.from_object(Config)
# Railway terminates HTTPS at its proxy. Only trust forwarded headers there.
if app.config["TRUST_PROXY_HEADERS"]:
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.secret_key = app.config["SECRET_KEY"]
app.register_blueprint(health_bp)
ai_service = EasyNMT_AI()
vision_grader = VisionGradingEngine(ai_service.provider)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
# Railway mounts a persistent volume at RAILWAY_VOLUME_MOUNT_PATH.
# Locally, EasyNMT continues to use instance/users.db.
PERSISTENT_DIR = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", INSTANCE_DIR)
DB_PATH = os.environ.get("EASYNMT_DB_PATH", os.path.join(PERSISTENT_DIR, "users.db"))
os.makedirs(os.path.dirname(DB_PATH) or BASE_DIR, exist_ok=True)
UPLOAD_DIR = os.path.join(PERSISTENT_DIR, "solution_uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024
VALID_GOALS = frozenset({"150", "170", "190", "200"})
VALID_SUBJECTS = frozenset({"math", "ukrainian", "history", "english"})
VALID_TIME_LEFT = frozenset({"1-month", "2-months", "3-plus", "6-plus"})
EMAIL_PATTERN = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,189}\.[^@\s]{2,63}$")
LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_FAILURE_LIMIT = 8
DUMMY_PASSWORD_HASH = generate_password_hash("EasyNMT invalid login sentinel")


def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def init_db():
    conn = get_db_connection()

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT,
            provider TEXT NOT NULL DEFAULT 'email',
            google_sub TEXT UNIQUE,
            avatar_url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_plans (
            user_id INTEGER PRIMARY KEY,
            goal TEXT,
            subject TEXT,
            time_left TEXT,
            progress INTEGER NOT NULL DEFAULT 0,
            xp INTEGER NOT NULL DEFAULT 0,
            streak INTEGER NOT NULL DEFAULT 1,
            last_activity_date TEXT,
            diagnostic_required INTEGER NOT NULL DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS completed_lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            subject TEXT NOT NULL,
            lesson_id INTEGER NOT NULL,
            best_score INTEGER NOT NULL DEFAULT 0,
            total INTEGER NOT NULL DEFAULT 0,
            completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, subject, lesson_id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            usage_date TEXT NOT NULL,
            request_count INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, usage_date),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS achievements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            code TEXT NOT NULL,
            icon TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            unlocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, code),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_subject_progress (
            user_id INTEGER NOT NULL,
            subject TEXT NOT NULL,
            progress INTEGER NOT NULL DEFAULT 0,
            xp INTEGER NOT NULL DEFAULT 0,
            streak INTEGER NOT NULL DEFAULT 1,
            last_activity_date TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, subject),
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS mistakes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            subject TEXT NOT NULL,
            lesson_id INTEGER NOT NULL,
            question TEXT NOT NULL,
            user_answer TEXT,
            correct_answer TEXT NOT NULL,
            explanation TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS diagnostic_results (
            user_id INTEGER NOT NULL,
            subject TEXT NOT NULL,
            score INTEGER NOT NULL DEFAULT 0,
            total INTEGER NOT NULL DEFAULT 5,
            level TEXT NOT NULL DEFAULT 'beginner',
            completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, subject),
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS lesson_readiness (
            user_id INTEGER NOT NULL,
            subject TEXT NOT NULL,
            lesson_id INTEGER NOT NULL,
            ready_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, subject, lesson_id),
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS quiz_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            attempt_token TEXT NOT NULL UNIQUE,
            user_id INTEGER NOT NULL,
            subject TEXT NOT NULL,
            lesson_id INTEGER NOT NULL,
            score INTEGER NOT NULL DEFAULT 0,
            total INTEGER NOT NULL DEFAULT 24,
            passed INTEGER NOT NULL DEFAULT 0,
            xp_awarded INTEGER NOT NULL DEFAULT 0,
            review_json TEXT NOT NULL DEFAULT '[]',
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            finalized_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS quiz_drafts (
            user_id INTEGER NOT NULL,
            subject TEXT NOT NULL,
            lesson_id INTEGER NOT NULL,
            answers_json TEXT NOT NULL DEFAULT '{}',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, subject, lesson_id),
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS quiz_sessions (
            attempt_token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            subject TEXT NOT NULL,
            lesson_id INTEGER NOT NULL,
            quiz_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_login_failures (
            failure_key TEXT NOT NULL,
            attempted_at INTEGER NOT NULL
        )
        """
    )

    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_quiz_attempts_user_subject_lesson "
        "ON quiz_attempts(user_id, subject, lesson_id, submitted_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_auth_login_failures_key_time "
        "ON auth_login_failures(failure_key, attempted_at)"
    )
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_ci ON users(lower(email))")

    conn.execute("DELETE FROM quiz_sessions WHERE created_at < datetime('now', '-1 day')")

    def ensure_column(table, column, definition):
        columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    ensure_column("user_plans", "streak", "INTEGER NOT NULL DEFAULT 1")
    ensure_column("user_plans", "last_activity_date", "TEXT")
    ensure_column("user_plans", "diagnostic_required", "INTEGER NOT NULL DEFAULT 0")
    ensure_column("users", "google_sub", "TEXT")
    ensure_column("users", "avatar_url", "TEXT")
    ensure_column("user_subject_progress", "last_lesson_id", "INTEGER")
    ensure_column("user_subject_progress", "last_quiz_score", "INTEGER")
    ensure_column("user_subject_progress", "last_quiz_total", "INTEGER")
    ensure_column("quiz_attempts", "finalized_at", "TIMESTAMP")
    conn.execute(
        "UPDATE quiz_attempts SET finalized_at = submitted_at WHERE finalized_at IS NULL"
    )

    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_google_sub "
        "ON users(google_sub) WHERE google_sub IS NOT NULL"
    )

    # Migrate existing plans into per-subject progress without deleting old data.
    conn.execute(
        """
        INSERT INTO user_subject_progress
            (user_id, subject, progress, xp, streak, last_activity_date)
        SELECT user_id, subject, progress, xp, streak, last_activity_date
        FROM user_plans
        WHERE subject IS NOT NULL AND TRIM(subject) <> ''
        ON CONFLICT(user_id, subject) DO NOTHING
        """
    )

    conn.commit()
    conn.close()


init_db()

ai_repository = AIRepository(DB_PATH)
ai_repository.ensure_schema()
ai_orchestrator = AIOrchestrator(ai_service.provider, ai_repository)
learning_repository = LearningRepository(DB_PATH)
learning_repository.ensure_schema()
learning_service = LearningGenerationService(ai_service.provider, learning_repository)
AI_UPLOAD_DIR = os.path.join(PERSISTENT_DIR, "ai_uploads")
os.makedirs(AI_UPLOAD_DIR, exist_ok=True)
app.config["DATABASE_PATH"] = DB_PATH


def current_user_name():
    return session.get("user_name")


def is_logged_in():
    return "user_id" in session


def csrf_token():
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


@app.before_request
def protect_unsafe_requests():
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return None
    expected = session.get("_csrf_token", "")
    supplied = request.form.get("_csrf_token", "") or request.headers.get("X-CSRF-Token", "")
    if expected and supplied and secrets.compare_digest(str(expected), str(supplied)):
        return None
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": "csrf_failed"}), 400
    abort(400, description="Форма застаріла. Онови сторінку й спробуй ще раз.")


@app.after_request
def add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(self), microphone=(), geolocation=()")
    if request.is_secure:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    if is_logged_in() and request.endpoint != "static":
        response.headers.setdefault("Cache-Control", "no-store")
    return response


def wants_json_error():
    return request.path.startswith("/api/") or request.accept_mimetypes.best == "application/json"


@app.errorhandler(400)
def bad_request_error(error):
    message = getattr(error, "description", "Некоректний запит.")
    if wants_json_error():
        return jsonify({"ok": False, "error": message}), 400
    return render_template("error.html", status=400, title="Некоректний запит", message=message), 400


@app.errorhandler(404)
def not_found_error(_error):
    if wants_json_error():
        return jsonify({"ok": False, "error": "not_found"}), 404
    return render_template("error.html", status=404, title="Сторінку не знайдено", message="Перевір адресу або повернися до кабінету."), 404


@app.errorhandler(403)
def forbidden_error(_error):
    if wants_json_error():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    return render_template("error.html", status=403, title="Доступ закрито", message="Спочатку заверши попередній крок навчального маршруту."), 403


@app.errorhandler(413)
def request_too_large_error(_error):
    message = "Файл або запит завеликий. Максимальний розмір — 8 МБ."
    if wants_json_error():
        return jsonify({"ok": False, "error": message}), 413
    return render_template("error.html", status=413, title="Файл завеликий", message=message), 413


@app.errorhandler(429)
def too_many_requests_error(error):
    message = getattr(error, "description", "Забагато запитів. Спробуй трохи пізніше.")
    if wants_json_error():
        return jsonify({"ok": False, "error": message}), 429
    return render_template("error.html", status=429, title="Забагато спроб", message=message), 429


def clear_plan_session():
    session.pop("goal", None)
    session.pop("subject", None)
    session.pop("time_left", None)
    session.pop("progress", None)
    session.pop("xp", None)
    session.pop("last_score", None)
    session.pop("last_total", None)
    session.pop("last_review", None)
    session.pop("last_passed", None)
    session.pop("last_attempt_token", None)
    session.pop("last_lesson_id", None)
    session.pop("last_quiz_score", None)
    session.pop("last_quiz_total", None)
    session.pop("current_lesson_id", None)
    session.pop("diagnostic_required", None)


def load_subject_progress_to_session(user_id, subject):
    if not subject:
        session["progress"] = 0
        session["xp"] = 0
        session["streak"] = 1
        session["last_activity_date"] = None
        return

    conn = get_db_connection()
    row = conn.execute(
        "SELECT * FROM user_subject_progress WHERE user_id = ? AND subject = ?",
        (user_id, subject),
    ).fetchone()
    conn.close()

    session["progress"] = int(row["progress"] or 0) if row else 0
    session["xp"] = int(row["xp"] or 0) if row else 0
    session["streak"] = int(row["streak"] or 1) if row else 1
    session["last_activity_date"] = row["last_activity_date"] if row else None
    session["current_lesson_id"] = int(row["last_lesson_id"] or 1) if row and "last_lesson_id" in row.keys() else 1
    session["last_quiz_score"] = int(row["last_quiz_score"] or 0) if row and "last_quiz_score" in row.keys() else 0
    session["last_quiz_total"] = int(row["last_quiz_total"] or 0) if row and "last_quiz_total" in row.keys() else 0

    # completed_lessons is the source of truth for route completion.
    lesson_total = len(get_lessons_for_subject(subject))
    completed_total = len(get_completed_lessons(subject))
    computed_progress = round((completed_total / max(1, lesson_total)) * 100)
    session["progress"] = computed_progress
    if row and int(row["progress"] or 0) != computed_progress:
        conn = get_db_connection()
        try:
            conn.execute(
                "UPDATE user_subject_progress SET progress = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ? AND subject = ?",
                (computed_progress, user_id, subject),
            )
            conn.execute(
                "UPDATE user_plans SET progress = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ? AND subject = ?",
                (computed_progress, user_id, subject),
            )
            conn.commit()
        finally:
            conn.close()


def load_plan_to_session(user_id):
    conn = get_db_connection()
    plan = conn.execute("SELECT * FROM user_plans WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()

    clear_plan_session()
    if plan is None:
        session["progress"] = 0
        session["xp"] = 0
        session["streak"] = 1
        return

    if plan["goal"]:
        session["goal"] = plan["goal"]
    if plan["subject"]:
        session["subject"] = plan["subject"]
    if plan["time_left"]:
        session["time_left"] = plan["time_left"]
    session["diagnostic_required"] = bool(plan["diagnostic_required"])

    load_subject_progress_to_session(user_id, plan["subject"])



def ensure_legacy_google_plan(user_id):
    """Make an existing Google account immediately usable.

    Early EasyNMT builds could create a Google user before ``user_plans`` existed,
    or leave a partially filled plan after an interrupted onboarding flow. Such an
    account is already registered and must go straight to the dashboard on the next
    Google login. Brand-new Google users are handled separately and still complete
    onboarding once.
    """
    conn = get_db_connection()
    try:
        progress_row = conn.execute(
            """
            SELECT subject
            FROM user_subject_progress
            WHERE user_id = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
        fallback_subject = (
            progress_row["subject"]
            if progress_row and progress_row["subject"] in VALID_SUBJECTS
            else "math"
        )

        plan = conn.execute(
            "SELECT * FROM user_plans WHERE user_id = ?", (user_id,)
        ).fetchone()

        if plan is None:
            conn.execute(
                """
                INSERT INTO user_plans
                    (user_id, goal, subject, time_left, progress, xp, streak, diagnostic_required)
                VALUES (?, '170', ?, '3-plus', 0, 0, 1, 0)
                """,
                (user_id, fallback_subject),
            )
        else:
            # Fill only missing legacy values. Existing choices and progress remain intact.
            conn.execute(
                """
                UPDATE user_plans
                SET goal = COALESCE(NULLIF(goal, ''), '170'),
                    subject = COALESCE(NULLIF(subject, ''), ?),
                    time_left = COALESCE(NULLIF(time_left, ''), '3-plus'),
                    progress = COALESCE(progress, 0),
                    xp = COALESCE(xp, 0),
                    streak = COALESCE(streak, 1),
                    diagnostic_required = 0
                WHERE user_id = ?
                """,
                (fallback_subject, user_id),
            )
        conn.commit()
    finally:
        conn.close()

def save_plan_to_db():
    user_id = session.get("user_id")
    if not user_id:
        return

    subject = session.get("subject")
    conn = get_db_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        persisted = None
        if subject in VALID_SUBJECTS:
            persisted = conn.execute(
                "SELECT * FROM user_subject_progress WHERE user_id = ? AND subject = ?",
                (user_id, subject),
            ).fetchone()
        progress = int(persisted["progress"] or 0) if persisted else int(session.get("progress", 0) or 0)
        xp = int(persisted["xp"] or 0) if persisted else int(session.get("xp", 0) or 0)
        streak = int(persisted["streak"] or 1) if persisted else int(session.get("streak", 1) or 1)
        last_activity_date = persisted["last_activity_date"] if persisted else session.get("last_activity_date")
        last_quiz_score = int(persisted["last_quiz_score"] or 0) if persisted else int(session.get("last_quiz_score", 0) or 0)
        last_quiz_total = int(persisted["last_quiz_total"] or 0) if persisted else int(session.get("last_quiz_total", 0) or 0)

        conn.execute(
            """
            INSERT INTO user_plans
                (user_id, goal, subject, time_left, progress, xp, streak, last_activity_date, diagnostic_required)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                goal = excluded.goal,
                subject = excluded.subject,
                time_left = excluded.time_left,
                progress = excluded.progress,
                xp = excluded.xp,
                streak = excluded.streak,
                last_activity_date = excluded.last_activity_date,
                diagnostic_required = excluded.diagnostic_required,
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, session.get("goal"), subject, session.get("time_left"), progress, xp,
             streak, last_activity_date, int(bool(session.get("diagnostic_required", False)))),
        )

        if subject in VALID_SUBJECTS:
            conn.execute(
                """
                INSERT INTO user_subject_progress
                    (user_id, subject, progress, xp, streak, last_activity_date,
                     last_lesson_id, last_quiz_score, last_quiz_total)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, subject) DO UPDATE SET
                    last_lesson_id = excluded.last_lesson_id,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (user_id, subject, progress, xp, streak, last_activity_date,
                 session.get("current_lesson_id", 1), last_quiz_score, last_quiz_total),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    session.update({
        "progress": progress,
        "xp": xp,
        "streak": streak,
        "last_activity_date": last_activity_date,
        "last_quiz_score": last_quiz_score,
        "last_quiz_total": last_quiz_total,
    })

def login_user(user):
    session.clear()
    session.permanent = True
    session["user_id"] = user["id"]
    session["user_name"] = user["name"]
    session["user_email"] = user["email"]
    load_plan_to_session(user["id"])


def onboarding_complete():
    return (
        session.get("goal") in VALID_GOALS
        and session.get("subject") in VALID_SUBJECTS
        and session.get("time_left") in VALID_TIME_LEFT
    )


def diagnostic_is_required():
    return bool(session.get("diagnostic_required", False))


def redirect_after_auth():
    if onboarding_complete():
        if diagnostic_is_required() and not diagnostic_complete():
            return redirect(url_for("diagnostic"))
        return redirect(url_for("welcome"))

    return redirect(url_for("goal"))


def require_login(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not is_logged_in():
            flash("Спочатку створи акаунт або увійди, щоб зберегти прогрес.", "error")
            return redirect(url_for("register"))

        conn = get_db_connection()
        try:
            user = conn.execute(
                "SELECT * FROM users WHERE id = ?",
                (session.get("user_id"),),
            ).fetchone()
        finally:
            conn.close()

        if user is None:
            session.clear()
            if request.path.startswith("/api/"):
                return jsonify({"ok": False, "error": "Сесію оновлено. Увійди в акаунт ще раз."}), 401
            flash("Сесію оновлено. Увійди в акаунт ще раз.", "error")
            return redirect(url_for("login"))

        return view_func(*args, **kwargs)

    return wrapper


def login_failure_key(email):
    source = f"{str(email or '').strip().lower()}|{request.remote_addr or 'unknown'}"
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def login_is_blocked(failure_key):
    cutoff = int(time.time()) - LOGIN_WINDOW_SECONDS
    conn = get_db_connection()
    try:
        conn.execute("DELETE FROM auth_login_failures WHERE attempted_at < ?", (cutoff,))
        row = conn.execute(
            "SELECT COUNT(*) AS total FROM auth_login_failures WHERE failure_key = ? AND attempted_at >= ?",
            (failure_key, cutoff),
        ).fetchone()
        conn.commit()
        return int(row["total"] or 0) >= LOGIN_FAILURE_LIMIT
    finally:
        conn.close()


def record_login_failure(failure_key):
    conn = get_db_connection()
    try:
        conn.execute(
            "INSERT INTO auth_login_failures (failure_key, attempted_at) VALUES (?, ?)",
            (failure_key, int(time.time())),
        )
        conn.commit()
    finally:
        conn.close()


def clear_login_failures(failure_key):
    conn = get_db_connection()
    try:
        conn.execute("DELETE FROM auth_login_failures WHERE failure_key = ?", (failure_key,))
        conn.commit()
    finally:
        conn.close()



def get_completed_lessons(subject_key=None):
    user_id = session.get("user_id")
    if not user_id:
        return set()

    subject_key = subject_key or session.get("subject", "none")
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT lesson_id FROM completed_lessons WHERE user_id = ? AND subject = ?",
        (user_id, subject_key),
    ).fetchall()
    conn.close()
    return {row["lesson_id"] for row in rows}


def get_completed_lesson_stats(subject_key=None):
    user_id = session.get("user_id")
    if not user_id:
        return []

    subject_key = subject_key or session.get("subject", "none")
    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT lesson_id, best_score, total, completed_at
        FROM completed_lessons
        WHERE user_id = ? AND subject = ?
        ORDER BY lesson_id ASC
        """,
        (user_id, subject_key),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_achievements(limit=None):
    user_id = session.get("user_id")
    if not user_id:
        return []

    query = "SELECT icon, title, description, unlocked_at FROM achievements WHERE user_id = ? ORDER BY unlocked_at DESC"
    params = [user_id]
    if limit:
        query += " LIMIT ?"
        params.append(limit)

    conn = get_db_connection()
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def streak_after_activity(last_raw, current_streak, today=None):
    today = today or dt_date.today()
    try:
        last_day = datetime.strptime(str(last_raw or ""), "%Y-%m-%d").date()
    except ValueError:
        return 1, today.isoformat()
    if last_day == today:
        return max(1, int(current_streak or 1)), today.isoformat()
    if last_day == today - timedelta(days=1):
        return max(1, int(current_streak or 1)) + 1, today.isoformat()
    return 1, today.isoformat()


def finalize_quiz_attempt(*, attempt_token, lesson_id, score, total, passed, review):
    user_id = int(session["user_id"])
    subject_key = get_subject_key()
    conn = get_db_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            """
            SELECT attempt_token, lesson_id, score, total, passed, xp_awarded,
                   review_json, submitted_at
            FROM quiz_attempts
            WHERE attempt_token = ? AND user_id = ?
            """,
            (attempt_token, user_id),
        ).fetchone()
        if existing:
            conn.rollback()
            return {"duplicate": True, "attempt": dict(existing), "new_achievements": []}

        previous_attempts = conn.execute(
            "SELECT COUNT(*) AS total FROM quiz_attempts WHERE user_id = ? AND subject = ? AND lesson_id = ?",
            (user_id, subject_key, lesson_id),
        ).fetchone()["total"]
        completed_before = conn.execute(
            "SELECT 1 FROM completed_lessons WHERE user_id = ? AND subject = ? AND lesson_id = ?",
            (user_id, subject_key, lesson_id),
        ).fetchone() is not None

        xp_gain = 0
        if passed and not completed_before:
            xp_gain = 50 if previous_attempts else 60
        elif not passed and not previous_attempts:
            xp_gain = 10

        for item in review:
            if item["earned"] < item["points"]:
                conn.execute(
                    """
                    INSERT INTO mistakes
                        (user_id, subject, lesson_id, question, user_answer, correct_answer, explanation)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (user_id, subject_key, lesson_id, item["question"], item["user_answer"],
                     item["correct_answer"], item["explanation"]),
                )

        conn.execute(
            """
            INSERT INTO quiz_attempts
                (attempt_token, user_id, subject, lesson_id, score, total, passed,
                 xp_awarded, review_json, finalized_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (attempt_token, user_id, subject_key, lesson_id, score, total, int(passed),
             xp_gain, json.dumps(review, ensure_ascii=False)),
        )

        if passed:
            conn.execute(
                """
                INSERT INTO completed_lessons (user_id, subject, lesson_id, best_score, total)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, subject, lesson_id) DO UPDATE SET
                    best_score = MAX(completed_lessons.best_score, excluded.best_score),
                    total = CASE
                        WHEN excluded.best_score >= completed_lessons.best_score THEN excluded.total
                        ELSE completed_lessons.total
                    END
                """,
                (user_id, subject_key, lesson_id, score, total),
            )

        progress_row = conn.execute(
            "SELECT * FROM user_subject_progress WHERE user_id = ? AND subject = ?",
            (user_id, subject_key),
        ).fetchone()
        current_xp = int(progress_row["xp"] or 0) if progress_row else 0
        current_streak = int(progress_row["streak"] or 1) if progress_row else 1
        last_activity = progress_row["last_activity_date"] if progress_row else None
        streak, activity_date = streak_after_activity(last_activity, current_streak)
        xp = current_xp + xp_gain
        completed_count = conn.execute(
            "SELECT COUNT(*) AS total FROM completed_lessons WHERE user_id = ? AND subject = ?",
            (user_id, subject_key),
        ).fetchone()["total"]
        lessons_total = len(get_lessons_for_subject(subject_key))
        progress = round((int(completed_count) / max(1, lessons_total)) * 100)

        conn.execute(
            """
            INSERT INTO user_subject_progress
                (user_id, subject, progress, xp, streak, last_activity_date,
                 last_lesson_id, last_quiz_score, last_quiz_total)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, subject) DO UPDATE SET
                progress = excluded.progress,
                xp = excluded.xp,
                streak = excluded.streak,
                last_activity_date = excluded.last_activity_date,
                last_lesson_id = excluded.last_lesson_id,
                last_quiz_score = excluded.last_quiz_score,
                last_quiz_total = excluded.last_quiz_total,
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, subject_key, progress, xp, streak, activity_date, lesson_id, score, total),
        )
        conn.execute(
            """
            UPDATE user_plans
            SET progress = ?, xp = ?, streak = ?, last_activity_date = ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ? AND subject = ?
            """,
            (progress, xp, streak, activity_date, user_id, subject_key),
        )

        new_achievements = []

        def add_achievement(code, icon, title, description):
            cursor = conn.execute(
                "INSERT OR IGNORE INTO achievements (user_id, code, icon, title, description) VALUES (?, ?, ?, ?, ?)",
                (user_id, code, icon, title, description),
            )
            if cursor.rowcount:
                new_achievements.append({"icon": icon, "title": title, "description": description})

        if passed and not completed_before:
            add_achievement("first_lesson", "🥉", "Перший урок", "Ти завершив перший урок в EasyNMT.")
        if int(completed_count) >= 3:
            add_achievement("three_lessons", "📚", "Перший маршрут", "Ти завершив 3 уроки з одного предмета.")
        if score == total and total > 0:
            add_achievement("perfect_quiz", "💯", "Без помилок", "Усі відповіді правильні. Ти набрав максимальні 24 бали.")
        if xp >= 100:
            add_achievement("xp_100", "⭐", "100 XP", "Ти набрав перші 100 XP.")
        if xp >= 250:
            add_achievement("xp_250", "⚡", "250 XP", "Ти вже набрав 250 XP. Видно, що навчання стало регулярним.")
        if streak >= 3:
            add_achievement("streak_3", "🔥", "3 дні серії", "Ти займаєшся вже 3 дні поспіль. Продовжуй у такому ж темпі.")

        conn.execute("DELETE FROM quiz_sessions WHERE attempt_token = ? AND user_id = ?", (attempt_token, user_id))
        conn.execute(
            "DELETE FROM quiz_drafts WHERE user_id = ? AND subject = ? AND lesson_id = ?",
            (user_id, subject_key, lesson_id),
        )
        conn.commit()
        return {
            "duplicate": False,
            "attempt": {
                "attempt_token": attempt_token,
                "lesson_id": lesson_id,
                "score": score,
                "total": total,
                "passed": int(passed),
                "xp_awarded": xp_gain,
                "review_json": json.dumps(review, ensure_ascii=False),
            },
            "progress": progress,
            "xp": xp,
            "streak": streak,
            "last_activity_date": activity_date,
            "new_achievements": new_achievements,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()



def get_quiz_attempts(lesson_id=None, subject_key=None):
    user_id = session.get("user_id")
    if not user_id:
        return []
    subject_key = subject_key or session.get("subject", "none")
    query = """
        SELECT attempt_token, lesson_id, score, total, passed, xp_awarded, review_json, submitted_at
        FROM quiz_attempts
        WHERE user_id = ? AND subject = ?
    """
    params = [user_id, subject_key]
    if lesson_id is not None:
        query += " AND lesson_id = ?"
        params.append(int(lesson_id))
    query += " ORDER BY submitted_at DESC, id DESC"
    conn = get_db_connection()
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_quiz_attempt_summary(subject_key=None):
    user_id = session.get("user_id")
    if not user_id:
        return {}
    subject_key = subject_key or session.get("subject", "none")
    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT lesson_id, COUNT(*) AS attempts, MAX(score) AS best_score,
               MAX(total) AS total, MAX(passed) AS passed, MAX(submitted_at) AS last_attempt_at
        FROM quiz_attempts
        WHERE user_id = ? AND subject = ?
        GROUP BY lesson_id
        """,
        (user_id, subject_key),
    ).fetchall()
    conn.close()
    return {int(row["lesson_id"]): dict(row) for row in rows}


def get_quiz_draft(lesson_id, subject_key=None):
    user_id = session.get("user_id")
    if not user_id:
        return {}
    subject_key = subject_key or session.get("subject", "none")
    conn = get_db_connection()
    row = conn.execute(
        "SELECT answers_json FROM quiz_drafts WHERE user_id = ? AND subject = ? AND lesson_id = ?",
        (user_id, subject_key, int(lesson_id)),
    ).fetchone()
    conn.close()
    if not row:
        return {}
    try:
        data = json.loads(row["answers_json"] or "{}")
        return data if isinstance(data, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def save_quiz_draft(lesson_id, answers, subject_key=None):
    user_id = session.get("user_id")
    if not user_id:
        return
    subject_key = subject_key or session.get("subject", "none")
    safe_answers = {
        str(key)[:120]: str(value)[:4000]
        for key, value in (answers or {}).items()
        if isinstance(key, str) and isinstance(value, (str, int, float))
    }
    conn = get_db_connection()
    conn.execute(
        """
        INSERT INTO quiz_drafts (user_id, subject, lesson_id, answers_json)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id, subject, lesson_id) DO UPDATE SET
            answers_json = excluded.answers_json,
            updated_at = CURRENT_TIMESTAMP
        """,
        (user_id, subject_key, int(lesson_id), json.dumps(safe_answers, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()


def delete_quiz_draft(lesson_id, subject_key=None):
    user_id = session.get("user_id")
    if not user_id:
        return
    subject_key = subject_key or session.get("subject", "none")
    conn = get_db_connection()
    conn.execute(
        "DELETE FROM quiz_drafts WHERE user_id = ? AND subject = ? AND lesson_id = ?",
        (user_id, subject_key, int(lesson_id)),
    )
    conn.commit()
    conn.close()


def get_resume_lesson_id(subject_key=None):
    subject_key = subject_key or session.get("subject", "none")
    lessons = get_lessons_for_subject(subject_key)
    completed = get_completed_lessons(subject_key)
    unlocked_ids = [
        item["id"] for index, item in enumerate(lessons)
        if index == 0 or lessons[index - 1]["id"] in completed
    ]

    user_id = session.get("user_id")
    if user_id:
        conn = get_db_connection()
        draft = conn.execute(
            """
            SELECT lesson_id FROM quiz_drafts
            WHERE user_id = ? AND subject = ?
            ORDER BY updated_at DESC LIMIT 1
            """,
            (user_id, subject_key),
        ).fetchone()
        conn.close()
        if draft and int(draft["lesson_id"]) in unlocked_ids and int(draft["lesson_id"]) not in completed:
            return int(draft["lesson_id"])

    last_open = session.get("current_lesson_id")
    try:
        last_open = int(last_open)
    except (TypeError, ValueError):
        last_open = None
    if last_open in unlocked_ids and last_open not in completed:
        return last_open

    for lesson_item in lessons:
        if lesson_item["id"] not in completed:
            return lesson_item["id"]
    return lessons[-1]["id"]


def restore_attempt_to_session(attempt):
    session.update({
        "last_score": int(attempt.get("score") or 0),
        "last_total": int(attempt.get("total") or MAX_SCORE),
        "last_lesson_id": int(attempt.get("lesson_id") or 1),
        "last_passed": bool(attempt.get("passed")),
        "xp_gain": int(attempt.get("xp_awarded") or 0),
        "new_achievements": [],
        "last_attempt_token": attempt.get("attempt_token"),
    })


def get_next_unfinished_lesson_id():
    return get_resume_lesson_id(session.get("subject", "none"))

def get_diagnostic_result(subject_key=None):
    user_id = session.get("user_id")
    subject_key = subject_key or session.get("subject")
    if not user_id or not subject_key:
        return None
    conn = get_db_connection()
    row = conn.execute(
        "SELECT score, total, level, completed_at FROM diagnostic_results WHERE user_id = ? AND subject = ?",
        (user_id, subject_key),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def diagnostic_complete(subject_key=None):
    return get_diagnostic_result(subject_key) is not None


def get_personal_insights(subject_key=None):
    user_id = session.get("user_id")
    subject_key = subject_key or session.get("subject", "none")
    diagnostic = get_diagnostic_result(subject_key)
    level = diagnostic["level"] if diagnostic else "beginner"
    level_names = {
        "beginner": "Починаємо з основ",
        "foundation": "Основа вже є",
        "confident": "Можна рухатися швидше",
    }
    weak_topic = None
    weak_count = 0
    if user_id:
        conn = get_db_connection()
        row = conn.execute(
            """SELECT lesson_id, COUNT(*) AS cnt FROM mistakes
               WHERE user_id = ? AND subject = ?
               GROUP BY lesson_id ORDER BY cnt DESC, lesson_id ASC LIMIT 1""",
            (user_id, subject_key),
        ).fetchone()
        conn.close()
        if row:
            weak_count = int(row["cnt"] or 0)
            try:
                weak_topic = get_lesson_content(int(row["lesson_id"]))["title"]
            except Exception:
                weak_topic = None
    if weak_topic:
        focus = f"Найбільше уваги зараз потребує тема «{weak_topic}». У ній уже було {weak_count} помилок."
        action = "Спочатку переглянь розбір помилок, а потім повтори короткий тест."
    elif level == "beginner":
        focus = "Почнемо без поспіху. Спочатку зрозуміємо головну ідею, потім розберемо приклад."
        action = "Сьогодні достатньо пройти один урок і мініперевірку."
    elif level == "foundation":
        focus = "Базові знання вже є. Тепер важливо навчитися не губитися в типових завданнях НМТ."
        action = "Пройди поточний урок і зверни увагу на типові помилки."
    else:
        focus = "Ти впевнено знаєш основу. Можна швидше переходити до практики та складніших завдань."
        action = "Почни з прикладу, а потім одразу перевір себе тестом."
    return {
        "diagnostic_level": level,
        "diagnostic_level_name": level_names.get(level, level_names["beginner"]),
        "personal_focus": focus,
        "personal_action": action,
        "weak_topic": weak_topic,
        "weak_count": weak_count,
    }


def is_lesson_ready(lesson_id, subject_key=None):
    user_id = session.get("user_id")
    subject_key = subject_key or session.get("subject", "none")
    if not user_id:
        return False
    conn = get_db_connection()
    row = conn.execute(
        "SELECT 1 FROM lesson_readiness WHERE user_id = ? AND subject = ? AND lesson_id = ?",
        (user_id, subject_key, lesson_id),
    ).fetchone()
    conn.close()
    return row is not None


def get_user_data():
    goal = session.get("goal", "Ще не вибрано")
    subject_key = session.get("subject", "none")
    time_key = session.get("time_left", "none")

    subject_names = {
        "math": "📐 Математика",
        "ukrainian": "🇺🇦 Українська мова",
        "history": "📜 Історія України",
        "english": "🇬🇧 Англійська мова",
        "none": "Ще не вибрано",
    }

    time_names = {
        "1-month": "1 місяць",
        "2-months": "2 місяці",
        "3-plus": "3+ місяці",
        "6-plus": "6+ місяців",
        "none": "Ще не вибрано",
    }

    daily_time = {
        "1-month": "60–90 хв щодня",
        "2-months": "45–60 хв щодня",
        "3-plus": "30–45 хв щодня",
        "6-plus": "25–35 хв щодня",
        "none": "25 хв сьогодні",
    }

    lessons = get_lessons_for_subject(subject_key)
    completed_lessons = get_completed_lessons(subject_key)
    resume_lesson_id = get_resume_lesson_id(subject_key)
    first_lesson = next((lesson for lesson in lessons if lesson["id"] == resume_lesson_id), lessons[0])
    completed_count = len(completed_lessons)
    lessons_total = len(lessons)
    unlocked_lessons = {
        lesson["id"] for index, lesson in enumerate(lessons)
        if index == 0 or lessons[index - 1]["id"] in completed_lessons
    }
    lesson_progress = round((completed_count / max(1, lessons_total)) * 100)
    progress = lesson_progress
    session["progress"] = progress

    achievements = get_achievements(limit=4)
    insights = get_personal_insights(subject_key)
    attempt_summary = get_quiz_attempt_summary(subject_key)
    journey_complete = completed_count >= lessons_total and lessons_total > 0

    return {
        "goal": goal,
        "subject_key": subject_key,
        "subject": subject_names.get(subject_key, "Ще не вибрано"),
        "lessons": lessons,
        "completed_lessons": completed_lessons,
        "unlocked_lessons": unlocked_lessons,
        "completed_count": completed_count,
        "lessons_total": lessons_total,
        "first_topic": first_lesson["title"],
        "first_lesson_id": first_lesson["id"],
        "lesson_goal": first_lesson["goal"],
        "time_left": time_names.get(time_key, "Ще не вибрано"),
        "daily_time": daily_time.get(time_key, "25 хв сьогодні"),
        "progress": progress,
        "xp": session.get("xp", 0),
        "streak": session.get("streak", 1),
        "achievements": achievements,
        "achievement_count": len(get_achievements()),
        "attempt_summary": attempt_summary,
        "journey_complete": journey_complete,
        "resume_lesson_id": resume_lesson_id,
        "user_name": current_user_name(),
        "is_logged_in": is_logged_in(),
        "has_plan": onboarding_complete(),
        "diagnostic_complete": diagnostic_complete(subject_key),
        **insights,
    }


LESSON_CATALOG = {
    "math": [
        {
            "id": 1,
            "title": "Квадратні рівняння",
            "badge": "📐 Математика",
            "theory": "Квадратне рівняння має вигляд ax² + bx + c = 0, де a не дорівнює нулю. Щоб знайти корені, найчастіше використовують дискримінант: D = b² - 4ac.",
            "example": "Приклад: x² - 5x + 6 = 0. Тут a=1, b=-5, c=6. D = 25 - 24 = 1. Корені: x₁ = 2, x₂ = 3.",
            "goal": "Навчись впізнавати квадратне рівняння та знаходити його корені за допомогою дискримінанта.",
        },
        {
            "id": 2,
            "title": "Лінійні рівняння",
            "badge": "📐 Математика",
            "theory": "Лінійне рівняння має змінну в першому степені. Головна ідея — перенести все зі змінною в один бік, а числа в інший.",
            "example": "Приклад: 3x + 5 = 17. Віднімаємо 5: 3x = 12. Ділимо на 3: x = 4.",
            "goal": "Навчись розв’язувати прості рівняння впевнено й без зайвих кроків.",
        },
        {
            "id": 3,
            "title": "Функції та графіки",
            "badge": "📐 Математика",
            "theory": "Функція показує залежність одного значення від іншого. На НМТ часто треба читати графік: знаходити значення, нулі функції та проміжки зростання.",
            "example": "Приклад: якщо y = 2x + 1, то при x = 3 маємо y = 7. Точка (3; 7) лежить на графіку.",
            "goal": "Навчись читати прості графіки та розуміти, що показує функція.",
        },
    ],
    "ukrainian": [
        {
            "id": 1,
            "title": "Орфографія та правопис",
            "badge": "🇺🇦 Українська мова",
            "theory": "Орфографія в НМТ часто перевіряє написання слів, апостроф, м’який знак, подвоєння та спрощення. Найкраща стратегія — повторювати правила малими блоками.",
            "example": "Приклад: слово «буряк» пишемо без апострофа, а «об’єкт» — з апострофом після префікса перед я, ю, є, ї.",
            "goal": "Повторити базові правила правопису і навчитися помічати типові пастки в тестах.",
        },
        {
            "id": 2,
            "title": "Наголос у словах",
            "badge": "🇺🇦 Українська мова",
            "theory": "Завдання на наголос перевіряють не правило, а мовну норму. Найкраще працює тренування короткими списками слів.",
            "example": "Приклад: правильно казати «вИпадок», «чорнОзем», «завдАння». Такі слова варто повторювати картками.",
            "goal": "Запам’ятати типові слова з наголосом, які часто трапляються в тестах.",
        },
        {
            "id": 3,
            "title": "Складне речення",
            "badge": "🇺🇦 Українська мова",
            "theory": "Складне речення має дві або більше граматичних основ. У тестах важливо швидко знаходити підмет і присудок.",
            "example": "Приклад: «Сонце зайшло, і місто стихло». Тут дві основи: сонце зайшло, місто стихло.",
            "goal": "Навчись розпізнавати складні речення та правильно ставити розділові знаки.",
        },
    ],
    "history": [
        {
            "id": 1,
            "title": "Київська Русь",
            "badge": "📜 Історія України",
            "theory": "У темі Київської Русі важливо розуміти послідовність князів, їхні реформи, походи та значення хрещення Русі.",
            "example": "Приклад: Володимир Великий запровадив християнство у 988 році, що посилило міжнародні зв’язки Русі та вплинуло на культуру.",
            "goal": "Зрозумій ключові події Київської Русі та навчись пов’язувати князів з їхніми діями.",
        },
        {
            "id": 2,
            "title": "Козацька доба",
            "badge": "📜 Історія України",
            "theory": "Козацька доба охоплює виникнення Запорозької Січі, Національно-визвольну війну та формування Гетьманщини.",
            "example": "Приклад: 1648 рік — початок Національно-визвольної війни під проводом Богдана Хмельницького.",
            "goal": "Навчись пов’язувати події козацької доби з датами та історичними діячами.",
        },
        {
            "id": 3,
            "title": "Українська революція 1917–1921",
            "badge": "📜 Історія України",
            "theory": "У цій темі важливо розрізняти Центральну Раду, Гетьманат, Директорію та ЗУНР.",
            "example": "Приклад: Центральна Рада проголосила УНР, а IV Універсал оголосив її незалежність.",
            "goal": "Розкласти події революції по етапах і не плутати державні утворення.",
        },
    ],
    "english": [
        {
            "id": 1,
            "title": "Present Simple",
            "badge": "🇬🇧 Англійська мова",
            "theory": "Present Simple використовують для звичок, фактів і регулярних дій. У третій особі однини додаємо -s або -es.",
            "example": "Example: I study every day. She studies every day. Для заперечення: I do not study, she does not study.",
            "goal": "Повторити базову форму Present Simple і не плутати do та does.",
        },
        {
            "id": 2,
            "title": "Past Simple",
            "badge": "🇬🇧 Англійська мова",
            "theory": "Past Simple використовують для дій у минулому. Для правильних дієслів додаємо -ed, а неправильні треба запам’ятати.",
            "example": "Example: I watched a film yesterday. She went to school last Monday.",
            "goal": "Навчись упізнавати минулий час і правильно змінювати дієслова.",
        },
        {
            "id": 3,
            "title": "Reading strategies",
            "badge": "🇬🇧 Англійська мова",
            "theory": "У читанні на НМТ важливо не перекладати кожне слово, а шукати ключові ідеї, синоніми та логіку тексту.",
            "example": "Example: якщо в питанні є слово «job», у тексті може бути «work» або «profession». Це пастка на синоніми.",
            "goal": "Навчись швидше читати завдання та знаходити потрібну відповідь у тексті.",
        },
    ],
    "none": [
        {
            "id": 1,
            "title": "Стартовий урок",
            "badge": "🧠 EasyNMT",
            "theory": "Спочатку з’ясуємо, що ти вже знаєш, а потім спокійно розберемо першу тему.",
            "example": "Спочатку прочитай пояснення, потім виконай короткий тест. Після цього побачиш свій результат і прогрес.",
            "goal": "Зрозумій, з чого почати, і пройди першу тему у зручному темпі.",
        }
    ],
}

QUIZ_BANK = {
    "math": {
        1: [
            {"question": "Який вигляд має квадратне рівняння?", "options": ["ax² + bx + c = 0", "ax + b = 0", "a/b = c"], "answer": "ax² + bx + c = 0"},
            {"question": "Формула дискримінанта:", "options": ["D = b² - 4ac", "D = a² + b²", "D = 2a + b"], "answer": "D = b² - 4ac"},
            {"question": "У рівнянні x² - 5x + 6 = 0 коефіцієнт b дорівнює:", "options": ["-5", "5", "6"], "answer": "-5"},
        ],
        2: [
            {"question": "Лінійне рівняння має змінну:", "options": ["у першому степені", "у квадраті", "тільки в знаменнику"], "answer": "у першому степені"},
            {"question": "3x = 12, тоді x =", "options": ["4", "9", "36"], "answer": "4"},
            {"question": "Що робимо з 3x + 5 = 17 спочатку?", "options": ["віднімаємо 5", "множимо на 17", "додаємо x"], "answer": "віднімаємо 5"},
        ],
        3: [
            {"question": "Функція показує:", "options": ["залежність значень", "лише дату", "правопис слова"], "answer": "залежність значень"},
            {"question": "Якщо y = 2x + 1 і x = 3, то y =", "options": ["7", "6", "5"], "answer": "7"},
            {"question": "Точка (3; 7) означає:", "options": ["x=3, y=7", "x=7, y=3", "тільки y=3"], "answer": "x=3, y=7"},
        ],
    },
    "ukrainian": {
        1: [
            {"question": "Що вивчає орфографія?", "options": ["Правильне написання слів", "Будову речення", "Звуки мовлення"], "answer": "Правильне написання слів"},
            {"question": "У якому слові є апостроф?", "options": ["об’єкт", "буряк", "свято"], "answer": "об’єкт"},
            {"question": "Для НМТ важливо тренувати:", "options": ["типові правописні пастки", "лише швидкість читання", "тільки усне мовлення"], "answer": "типові правописні пастки"},
        ],
        2: [
            {"question": "Правильний наголос у слові:", "options": ["вИпадок", "випАдок", "випадОк"], "answer": "вИпадок"},
            {"question": "Наголос часто перевіряє:", "options": ["мовну норму", "розділові знаки", "частини мови"], "answer": "мовну норму"},
            {"question": "Що найкраще допомагає з наголосами?", "options": ["картки та повторення", "ігнорування", "тільки переклад"], "answer": "картки та повторення"},
        ],
        3: [
            {"question": "Складне речення має:", "options": ["дві або більше граматичних основ", "лише одне слово", "тільки звертання"], "answer": "дві або більше граматичних основ"},
            {"question": "У реченні «Сонце зайшло, і місто стихло» основ:", "options": ["дві", "одна", "три"], "answer": "дві"},
            {"question": "Що треба знайти спочатку?", "options": ["підмет і присудок", "тільки прикметники", "усі коми"], "answer": "підмет і присудок"},
        ],
    },
    "history": {
        1: [
            {"question": "Хто запровадив християнство на Русі?", "options": ["Володимир Великий", "Ярослав Мудрий", "Олег"], "answer": "Володимир Великий"},
            {"question": "У якому році відбулося хрещення Русі?", "options": ["988", "1240", "1648"], "answer": "988"},
            {"question": "Для історії на НМТ важливо розуміти:", "options": ["причини й наслідки подій", "тільки портрети", "лише карти без дат"], "answer": "причини й наслідки подій"},
        ],
        2: [
            {"question": "1648 рік — це початок:", "options": ["Національно-визвольної війни", "Хрещення Русі", "Першої світової"], "answer": "Національно-визвольної війни"},
            {"question": "Богдан Хмельницький пов’язаний з:", "options": ["козацькою добою", "Київською Руссю", "ЗУНР"], "answer": "козацькою добою"},
            {"question": "Гетьманщина виникла внаслідок:", "options": ["козацьких подій", "індустріалізації", "перебудови"], "answer": "козацьких подій"},
        ],
        3: [
            {"question": "УНР проголосила:", "options": ["Центральна Рада", "Запорозька Січ", "Київська Русь"], "answer": "Центральна Рада"},
            {"question": "IV Універсал проголосив:", "options": ["незалежність УНР", "скасування мови", "утворення СРСР"], "answer": "незалежність УНР"},
            {"question": "У темі 1917–1921 важливо розрізняти:", "options": ["Центральну Раду, Гетьманат, Директорію", "тільки князів", "лише економіку"], "answer": "Центральну Раду, Гетьманат, Директорію"},
        ],
    },
    "english": {
        1: [
            {"question": "Present Simple використовують для:", "options": ["звичок і фактів", "дій зараз", "майбутнього в минулому"], "answer": "звичок і фактів", "explanation": "Present Simple використовують для звичок, фактів і регулярних дій: I play football every week. The Sun rises in the east."},
            {"question": "Правильний варіант:", "options": ["She studies every day", "She study every day", "She studying every day"], "answer": "She studies every day", "explanation": "Для he/she/it у Present Simple додаємо -s або -es до дієслова: study → studies."},
            {"question": "Для he/she/it додаємо:", "options": ["-s або -es", "-ing", "-ed"], "answer": "-s або -es", "explanation": "У Present Simple після he/she/it дієслово отримує закінчення -s або -es: he plays, she watches, it works."},
        ],
        2: [
            {"question": "Past Simple описує:", "options": ["дії в минулому", "дії прямо зараз", "факти без часу"], "answer": "дії в минулому"},
            {"question": "Правильний варіант:", "options": ["She went to school", "She go to school", "She going to school"], "answer": "She went to school"},
            {"question": "Для правильних дієслів часто додаємо:", "options": ["-ed", "-s", "will"], "answer": "-ed"},
        ],
        3: [
            {"question": "У Reading важливо шукати:", "options": ["ключові ідеї", "кожну кому", "тільки перше слово"], "answer": "ключові ідеї"},
            {"question": "job і work можуть бути:", "options": ["синонімами", "числівниками", "артиклями"], "answer": "синонімами"},
            {"question": "Не завжди треба:", "options": ["перекладати кожне слово", "читати питання", "шукати відповідь"], "answer": "перекладати кожне слово"},
        ],
    },
    "none": {
        1: [
            {"question": "Що робить EasyNMT?", "options": ["Будує навчальний маршрут", "Видаляє файли", "Замінює школу повністю"], "answer": "Будує навчальний маршрут"},
            {"question": "Після уроку буде:", "options": ["міні-тест", "нічого", "тільки картинка"], "answer": "міні-тест"},
            {"question": "Головна ідея першого уроку:", "options": ["зробити перший крок", "перевантажити учня", "пропустити практику"], "answer": "зробити перший крок"},
        ]
    },
}


EXTRA_QUIZ_QUESTIONS = {
    "math": {
        1: [
            {"question": "Якщо D > 0, то квадратне рівняння має:", "options": ["два корені", "один корінь", "жодного кореня"], "answer": "два корені"},
            {"question": "Що означає a у ax² + bx + c = 0?", "options": ["коефіцієнт біля x²", "вільний член", "відповідь"], "answer": "коефіцієнт біля x²"},
        ],
        2: [
            {"question": "У рівнянні x - 7 = 10 потрібно:", "options": ["додати 7 до обох частин", "поділити на 7", "помножити на x"], "answer": "додати 7 до обох частин"},
            {"question": "Рівняння 2x + 4 = 4 має розв’язок:", "options": ["x = 0", "x = 4", "x = 2"], "answer": "x = 0"},
        ],
        3: [
            {"question": "Нуль функції — це значення x, при якому:", "options": ["y = 0", "x = 0 завжди", "графік зникає"], "answer": "y = 0"},
            {"question": "Графік лінійної функції зазвичай є:", "options": ["прямою", "колом", "трикутником"], "answer": "прямою"},
        ],
    },
    "ukrainian": {
        1: [
            {"question": "Апостроф пишемо після префікса перед:", "options": ["я, ю, є, ї", "а, о, у", "б, п, в"], "answer": "я, ю, є, ї"},
            {"question": "Правопис допомагає уникати помилок у:", "options": ["написанні слів", "побудові графіка", "обчисленні коренів"], "answer": "написанні слів"},
        ],
        2: [
            {"question": "Правильний наголос у слові «завдання»:", "options": ["завдАння", "зАвдання", "завданнЯ"], "answer": "завдАння"},
            {"question": "Наголос треба тренувати:", "options": ["регулярно малими списками", "один раз на рік", "тільки перед сном"], "answer": "регулярно малими списками"},
        ],
        3: [
            {"question": "Граматична основа — це:", "options": ["підмет і присудок", "кома і тире", "іменник і прикметник завжди"], "answer": "підмет і присудок"},
            {"question": "Складне речення часто потребує:", "options": ["розділових знаків між частинами", "одного слова", "лише крапки на початку"], "answer": "розділових знаків між частинами"},
        ],
    },
    "history": {
        1: [
            {"question": "Ярослав Мудрий пов’язаний із:", "options": ["розквітом Київської Русі", "початком Другої світової", "утворенням ЗУНР"], "answer": "розквітом Київської Русі"},
            {"question": "Хрещення Русі посилило:", "options": ["міжнародні зв’язки", "заборону культури", "скасування держави"], "answer": "міжнародні зв’язки"},
        ],
        2: [
            {"question": "Запорозька Січ була пов’язана з:", "options": ["козацтвом", "Київською Руссю", "античністю"], "answer": "козацтвом"},
            {"question": "На НМТ з історії часто перевіряють:", "options": ["дати, діячів і наслідки", "тільки кольори прапорів", "лише погоду"], "answer": "дати, діячів і наслідки"},
        ],
        3: [
            {"question": "ЗУНР пов’язана насамперед із:", "options": ["Західною Україною", "Кримським ханством", "Київською Руссю"], "answer": "Західною Україною"},
            {"question": "Директорія прийшла після періоду:", "options": ["Гетьманату", "Хрещення Русі", "Козацької ради 1648"], "answer": "Гетьманату"},
        ],
    },
    "english": {
        1: [
            {"question": "Обери правильне заперечення:", "options": ["She does not play", "She do not play", "She not plays"], "answer": "She does not play", "explanation": "У запереченні з he/she/it використовуємо does not, а основне дієслово пишемо без -s: She does not play."},
            {"question": "Present Simple часто має маркери:", "options": ["usually, often, every day", "yesterday, last week", "now, at the moment"], "answer": "usually, often, every day", "explanation": "Маркери usually, often, every day часто показують регулярність, тому зазвичай потрібен Present Simple."},
        ],
        2: [
            {"question": "Маркер Past Simple:", "options": ["yesterday", "every day", "usually"], "answer": "yesterday"},
            {"question": "Правильне запитання:", "options": ["Did you watch it?", "Do you watched it?", "Watched you it?"], "answer": "Did you watch it?"},
        ],
        3: [
            {"question": "Skimming — це:", "options": ["швидке читання для загальної ідеї", "переклад кожного слова", "виписування всіх дат"], "answer": "швидке читання для загальної ідеї"},
            {"question": "Scanning — це:", "options": ["пошук конкретної інформації", "вивчення граматики", "читання вголос"], "answer": "пошук конкретної інформації"},
        ],
    },
    "none": {
        1: [
            {"question": "Що краще після теорії?", "options": ["коротка практика", "закрити сайт", "нічого не робити"], "answer": "коротка практика"},
            {"question": "EasyNMT зберігає:", "options": ["прогрес", "паролі у відкритому тексті", "випадкові картинки"], "answer": "прогрес"},
        ]
    },
}


def get_subject_key():
    subject_key = session.get("subject", "none")
    return subject_key if subject_key in VALID_SUBJECTS else "none"


def get_lessons_for_subject(subject_key=None):
    key = subject_key or get_subject_key()
    return LESSON_CATALOG.get(key, LESSON_CATALOG["none"])


def is_valid_lesson_id(lesson_id, subject_key=None):
    try:
        requested = int(lesson_id)
    except (TypeError, ValueError):
        return False
    return requested in {item["id"] for item in get_lessons_for_subject(subject_key)}


def normalize_lesson_id(lesson_id=None):
    lessons = get_lessons_for_subject()
    try:
        lesson_id = int(lesson_id or session.get("current_lesson_id", 1))
    except (TypeError, ValueError):
        lesson_id = 1

    valid_ids = [lesson["id"] for lesson in lessons]
    if lesson_id not in valid_ids:
        return lessons[0]["id"]
    return lesson_id


def get_lesson_content(lesson_id=None):
    lesson_id = normalize_lesson_id(lesson_id)
    for lesson in get_lessons_for_subject():
        if lesson["id"] == lesson_id:
            return lesson
    return get_lessons_for_subject()[0]


def get_lesson_details(lesson_id=None):
    lesson = get_lesson_content(lesson_id)
    subject_key = get_subject_key()
    lesson_id = lesson["id"]

    expanded = {
        "math": {
            1: {
                "simple_explanation": "Квадратне рівняння — це рівняння, де є x². Його можна уявити як задачу, у якій треба знайти такі значення x, щоб увесь вираз став нулем.",
                "nmt_relevance": "На НМТ квадратні рівняння трапляються в завданнях на корені, дискримінант, розкладання на множники, задачі з параметрами та графіки парабол.",
                "memory_tip": "Запам’ятай порядок: знайди a, b, c → порахуй D → визнач кількість коренів → підстав у формулу.",
                "formulas": ["D = b² - 4ac", "x₁,₂ = (-b ± √D) / 2a", "якщо D > 0 — два корені", "якщо D = 0 — один корінь", "якщо D < 0 — немає дійсних коренів"],
                "theory_points": [
                    "Квадратне рівняння має вигляд ax² + bx + c = 0, де a ≠ 0.",
                    "a — коефіцієнт біля x², b — біля x, c — вільний член.",
                    "Дискримінант показує, скільки коренів має рівняння.",
                    "Якщо D додатний, коренів два. Якщо D дорівнює нулю, корінь один. Якщо D від’ємний, дійсних коренів немає.",
                    "Іноді рівняння легше розв’язати без дискримінанта: винесенням спільного множника або формулами скороченого множення.",
                    "На тесті важливо не поспішати: одна помилка зі знаком може повністю змінити відповідь.",
                ],
                "extra_examples": [
                    "Легкий: x² - 9 = 0 → x² = 9 → x = 3 або x = -3.",
                    "Через дискримінант: x² - 5x + 6 = 0 → D = 25 - 24 = 1 → x₁ = 2, x₂ = 3.",
                    "Один корінь: x² + 4x + 4 = 0 → (x + 2)² = 0 → x = -2.",
                    "Без b: 2x² - 8 = 0 → 2x² = 8 → x² = 4 → x = ±2.",
                    "З винесенням: x² - 3x = 0 → x(x - 3) = 0 → x = 0 або x = 3.",
                    "Пастка: x² + 1 = 0 → x² = -1. Дійсних коренів немає.",
                ],
                "mistakes": ["Забути, що a не може дорівнювати нулю.", "Плутати знак b, особливо якщо b від’ємне.", "Забути два корені після ±.", "Взяти √D неправильно."],
                "summary_points": ["Впізнай ax² + bx + c = 0.", "Порахуй D.", "За D визнач кількість коренів.", "Підстав у формулу без поспіху."],
                "self_check": ["Чи правильно я визначив a, b, c?", "Чи не загубив мінус перед b?", "Чи перевірив кількість коренів за D?"],
            },
            2: {
                "simple_explanation": "Лінійне рівняння — це рівняння з x у першому степені. Головна мета — залишити x сам на одному боці.",
                "nmt_relevance": "Такі рівняння є базою для задач на відсотки, текстові задачі, нерівності та функції.",
                "memory_tip": "Думай про рівняння як про терези: що зробив зліва, те саме зроби справа.",
                "formulas": ["ax + b = 0", "ax = -b", "x = -b/a"],
                "theory_points": ["Перенось числа в один бік, вирази з x — в інший.", "Коли переносиш через знак рівності, дія змінюється на протилежну.", "Якщо перед x є множник, наприкінці діли на нього.", "Не пропускай проміжні кроки в складніших прикладах.", "Лінійні рівняння часто ховаються всередині текстових задач.", "Після розв’язання можна підставити відповідь назад і перевірити."],
                "extra_examples": ["x + 8 = 15 → x = 7.", "5x = 30 → x = 6.", "2x - 3 = 9 → 2x = 12 → x = 6.", "7 - x = 2 → -x = -5 → x = 5.", "3(x + 2) = 15 → x + 2 = 5 → x = 3.", "0,5x = 4 → x = 8."],
                "mistakes": ["Не змінити дію при перенесенні.", "Поділити тільки одну частину рівняння.", "Загубити мінус перед x.", "Розкрити дужки не для всіх доданків."],
                "summary_points": ["Прибери дужки.", "Збери x окремо.", "Збери числа окремо.", "Поділи на коефіцієнт біля x."],
                "self_check": ["Чи однаково я змінив обидві частини?", "Чи правильно розкрив дужки?", "Чи перевірив відповідь підстановкою?"],
            },
            3: {
                "simple_explanation": "Функція — це правило, яке кожному x ставить у відповідність певне y. Графік показує це правило на координатній площині.",
                "nmt_relevance": "На НМТ часто треба читати графік: знаходити значення функції, нулі, проміжки зростання та спадання.",
                "memory_tip": "Перша координата — x, друга — y. Спочатку рухайся по горизонталі, потім по вертикалі.",
                "formulas": ["y = f(x)", "нуль функції: f(x) = 0", "для y = kx + b графік — пряма"],
                "theory_points": ["Функція описує залежність між величинами.", "Значення x називають аргументом, значення y — значенням функції.", "Нуль функції — це x, при якому y = 0.", "Графік зростає, якщо при збільшенні x збільшується y.", "Графік спадає, якщо при збільшенні x значення y зменшується.", "У тестах часто достатньо уважно прочитати графік, а не рахувати складні формули."],
                "extra_examples": ["y = 2x + 1, x = 3 → y = 7.", "y = x - 4. Нуль: x - 4 = 0 → x = 4.", "Точка (3; 7): x = 3, y = 7.", "Якщо графік перетинає вісь Ox у x = -2, то -2 — нуль функції.", "y = -x + 5 спадає, бо коефіцієнт біля x від’ємний.", "Якщо на графіку при x = 2 значення y = 6, то f(2)=6."],
                "mistakes": ["Плутати x і y у точці.", "Шукати нуль функції на осі Oy.", "Не дивитися на масштаб клітинок.", "Вважати, що всі графіки — прямі."],
                "summary_points": ["Функція — правило залежності.", "Графік допомагає бачити значення.", "Нулі функції там, де y = 0.", "Завжди перевіряй масштаб."],
                "self_check": ["Чи правильно я читаю координати?", "Чи бачу, де графік перетинає Ox?", "Чи врахував масштаб?"],
            },
        },
        "ukrainian": {
            1: {
                "simple_explanation": "Орфографія — це правила правильного написання слів. На НМТ часто перевіряють не складну теорію, а уважність до типових пасток.",
                "nmt_relevance": "Тема потрібна для завдань на апостроф, м’який знак, подвоєння, префікси, спрощення та написання разом/окремо/через дефіс.",
                "memory_tip": "Вчи правило разом із 3 прикладами. Саме приклади закріплюють написання.",
                "formulas": ["після префікса перед я, ю, є, ї часто пишемо апостроф", "м’який знак позначає м’якість приголосного", "подвоєння залежить від будови слова"],
                "theory_points": ["Орфографія пояснює, як правильно писати слова.", "Апостроф не ставиться автоматично перед я, ю, є, ї — треба знати умову.", "М’який знак пишемо там, де потрібно позначити м’якість приголосного.", "Подвоєння часто залежить від збігу приголосних або походження слова.", "На НМТ завдання часто побудовані на схожих словах.", "Найкраща підготовка — короткі правила + багато прикладів."],
                "extra_examples": ["об’єкт — апостроф після префікса перед є.", "під’їзд — апостроф після префікса перед ї.", "буряк — без апострофа.", "свято — без апострофа.", "пів Європи — окремо, бо є власна назва.", "беззвучний — подвоєння через збіг приголосних."],
                "mistakes": ["Ставити апостроф у кожному слові перед я, ю, є, ї.", "Плутати вимову і написання.", "Не перевіряти будову слова.", "Вчити правило без прикладів."],
                "summary_points": ["Правило + приклад.", "Перевір префікс.", "Перевір, чи є власна назва.", "Не довіряй лише інтуїції."],
                "self_check": ["Чому тут є або немає апострофа?", "Яке правило це пояснює?", "Чи знаю я ще 2 схожі приклади?"],
            },
            2: {
                "simple_explanation": "Наголос — це склад, який вимовляється сильніше. У тестах часто дають слова, які в побуті вимовляють неправильно.",
                "nmt_relevance": "Завдання на наголос стабільно трапляються в тестах, тому їх варто тренувати окремими списками.",
                "memory_tip": "Створи власний список слів-пасток і повторюй його 3 хвилини щодня.",
                "formulas": ["наголос не завжди можна вивести правилом", "норма перевіряється словником", "краще вчити групами по 10–15 слів"],
                "theory_points": ["Наголос виділяє один склад у слові.", "Багато слів мають літературну норму, яка відрізняється від побутової вимови.", "У завданнях НМТ часто використовують найпоширеніші слова-пастки.", "Наголоси краще вчити через повторення, а не довгі пояснення.", "Слова можна групувати за темами або звучанням.", "Повторення вголос допомагає запам’ятати швидше."],
                "extra_examples": ["вИпадок", "завдАння", "чорнОзем", "каталОг", "фОльга", "одинАдцять"],
                "mistakes": ["Орієнтуватися лише на те, як говорять друзі.", "Вчити одразу 100 слів за раз.", "Не повторювати слова вголос.", "Плутати наголос у схожих словах."],
                "summary_points": ["Наголос — це норма.", "Вчи словами-пастками.", "Повторюй короткими блоками.", "Промовляй уголос."],
                "self_check": ["Чи можу я вимовити слово без підказки?", "Чи знаю я правильний склад?", "Чи повторював цей список сьогодні?"],
            },
            3: {
                "simple_explanation": "Складне речення — це речення з двома або більше граматичними основами. Основа — це підмет і присудок.",
                "nmt_relevance": "Тема потрібна для пунктуації, визначення типів речень і пошуку граматичних основ.",
                "memory_tip": "Перед тим як ставити кому, знайди всі підмети й присудки.",
                "formulas": ["граматична основа = підмет + присудок", "2 основи або більше = складне речення", "частини складного речення часто розділяються комою"],
                "theory_points": ["Складне речення має кілька частин.", "Кожна частина зазвичай має свою граматичну основу.", "Складносурядні речення мають рівноправні частини.", "Складнопідрядні мають головну і залежну частину.", "Безсполучникові поєднуються без сполучників.", "Пунктуація залежить від типу зв’язку між частинами."],
                "extra_examples": ["Сонце зайшло, і місто стихло.", "Я читаю, бо завтра тест.", "Коли прийшла весна, дерева зацвіли.", "Дощ ущух — діти вийшли надвір.", "Він знав, що відповідь правильна.", "Ми повторили тему, тому тест став легшим."],
                "mistakes": ["Рахувати коми замість граматичних основ.", "Не бачити присудок.", "Плутати просте речення з однорідними членами і складне.", "Ставити кому механічно."],
                "summary_points": ["Знайди основи.", "Визнач тип зв’язку.", "Постав розділовий знак за правилом.", "Перечитай речення повністю."],
                "self_check": ["Скільки тут граматичних основ?", "Який між ними зв’язок?", "Чому потрібна саме така кома?"],
            },
        },
        "history": {
            1: {
                "simple_explanation": "Київська Русь — це середньовічна держава зі столицею в Києві. У темі важливо знати князів, події та наслідки їхніх рішень.",
                "nmt_relevance": "На НМТ часто питають князів, дати, хрещення Русі, культуру, право і зовнішню політику.",
                "memory_tip": "До кожного князя прив’яжи 2–3 ключові дії. Так легше не плутати їх між собою.",
                "formulas": ["князь → дія → наслідок", "дата → подія → значення", "особа → реформа → вплив"],
                "theory_points": ["Київська Русь сформувалась навколо Києва як політичного центру.", "Володимир Великий пов’язаний із хрещенням Русі.", "Ярослав Мудрий — із розвитком культури, права та міжнародних зв’язків.", "Хрещення Русі посилило зв’язки з християнським світом.", "Русь активно контактувала з Візантією та Європою.", "Після роздробленості землі Русі поступово втрачали єдність."],
                "extra_examples": ["988 рік — хрещення Русі.", "Володимир Великий — християнізація держави.", "Ярослав Мудрий — Руська правда.", "Софія Київська — важлива культурна пам’ятка.", "Шлюбна дипломатія Ярослава посилила міжнародний авторитет.", "1240 рік — захоплення Києва монголами."],
                "mistakes": ["Плутати Володимира і Ярослава.", "Вчити дату без значення події.", "Не розуміти наслідки хрещення.", "Змішувати Русь і пізніші козацькі події."],
                "summary_points": ["Володимир — 988.", "Ярослав — право і культура.", "Київ — центр держави.", "Події вчи через наслідки."],
                "self_check": ["Який князь це зробив?", "Яка дата?", "Який наслідок для держави?"],
            },
            2: {
                "simple_explanation": "Козацька доба — це період, коли козацтво стало важливою військовою і політичною силою українських земель.",
                "nmt_relevance": "На НМТ часто питають Запорозьку Січ, Хмельницького, 1648 рік, Гетьманщину та договори.",
                "memory_tip": "До кожної події додавай три слова: хто, коли, наслідок.",
                "formulas": ["1648 → початок війни", "Хмельницький → Національно-визвольна війна", "Січ → центр козацтва"],
                "theory_points": ["Запорозька Січ була центром козацького життя.", "Козаки мали військову організацію і власні традиції.", "1648 рік став початком Національно-визвольної війни.", "Богдан Хмельницький очолив боротьбу проти Речі Посполитої.", "Гетьманщина стала формою української державності.", "Договори цієї доби важливо знати через їх наслідки."],
                "extra_examples": ["1648 — початок Національно-визвольної війни.", "Богдан Хмельницький — провідник війни.", "Запорозька Січ — військово-політичний центр.", "Зборівський договір — один із ключових договорів.", "Переяславська рада — важлива подія 1654 року.", "Гетьманщина — козацька держава."],
                "mistakes": ["Вчити тільки дати без договорів.", "Плутати причини і наслідки війни.", "Не розрізняти Січ і Гетьманщину.", "Змішувати різних гетьманів."],
                "summary_points": ["Січ — база козацтва.", "1648 — старт війни.", "Хмельницький — ключова постать.", "Гетьманщина — державність."],
                "self_check": ["Хто діяв?", "Яка дата?", "Що змінилось після події?"],
            },
            3: {
                "simple_explanation": "Українська революція 1917–1921 — це боротьба за українську державність після падіння Російської імперії.",
                "nmt_relevance": "На НМТ часто питають Центральну Раду, Універсали, Гетьманат, Директорію, ЗУНР та Акт Злуки.",
                "memory_tip": "Зроби ланцюжок: Центральна Рада → Гетьманат → Директорія → ЗУНР.",
                "formulas": ["Центральна Рада → УНР", "IV Універсал → незалежність", "22 січня 1919 → Акт Злуки"],
                "theory_points": ["Після 1917 року українці отримали шанс створити власну державу.", "Центральна Рада проголосила УНР.", "IV Універсал проголосив незалежність УНР.", "Гетьманат Павла Скоропадського мав інший політичний курс.", "Директорія відновила УНР після Гетьманату.", "ЗУНР виникла на західноукраїнських землях."],
                "extra_examples": ["Центральна Рада — Михайло Грушевський.", "IV Універсал — незалежність УНР.", "Павло Скоропадський — Гетьманат.", "Директорія — Винниченко, Петлюра.", "ЗУНР — Західна Україна.", "Акт Злуки — 22 січня 1919 року."],
                "mistakes": ["Плутати Універсали.", "Не розрізняти УНР і ЗУНР.", "Змішувати Центральну Раду і Директорію.", "Вчити події не в хронології."],
                "summary_points": ["Центральна Рада — початок УНР.", "IV Універсал — незалежність.", "Гетьманат — Скоропадський.", "Директорія — наступний етап."],
                "self_check": ["Який орган влади?", "Який документ?", "Який етап революції?"],
            },
        },
        "english": {
            1: {
                "simple_explanation": "Present Simple — це час для звичок, фактів і регулярних дій. Він відповідає на питання: що відбувається зазвичай?",
                "nmt_relevance": "На НМТ Present Simple потрібен у граматиці, читанні та виборі правильної форми дієслова.",
                "memory_tip": "Якщо бачиш usually, often, every day — часто потрібен Present Simple.",
                "formulas": ["I/you/we/they + V", "he/she/it + V-s", "do not + V", "does not + V"],
                "theory_points": ["Present Simple описує регулярні дії.", "Його використовують для фактів і загальних істин.", "У he/she/it додаємо -s або -es.", "У запереченнях використовуємо do not або does not.", "Після does дієслово йде без -s.", "У питаннях do/does ставимо перед підметом."],
                "extra_examples": ["I study every day.", "She studies every day.", "They do not play tennis.", "He does not like coffee.", "Do you speak English?", "Does she live here?"],
                "mistakes": ["She do замість She does.", "She does not plays замість She does not play.", "Забути -s у he/she/it.", "Використати Present Continuous для звички."],
                "summary_points": ["Звичка або факт — Present Simple.", "he/she/it отримує -s.", "Заперечення: do/does not.", "Після does без -s."],
                "self_check": ["Це звичка чи дія зараз?", "Підмет he/she/it?", "Чи є do або does?"],
            },
            2: {
                "simple_explanation": "Past Simple — це час для завершених дій у минулому. Він часто має слова yesterday, last week, ago.",
                "nmt_relevance": "На НМТ Past Simple часто перевіряють через неправильні дієслова, питання та заперечення.",
                "memory_tip": "Якщо є yesterday або last — думай про Past Simple.",
                "formulas": ["V-ed для правильних дієслів", "друга форма для неправильних", "did not + V", "Did + підмет + V?"],
                "theory_points": ["Past Simple описує завершену дію в минулому.", "Правильні дієслова отримують -ed.", "Неправильні дієслова мають другу форму.", "У запереченні використовуємо did not.", "Після did дієслово повертається у початкову форму.", "Питання починається з Did."],
                "extra_examples": ["I watched a film yesterday.", "She went to school last Monday.", "They did not play football.", "Did you see this movie?", "He visited his friend.", "We had breakfast at 8."],
                "mistakes": ["Did you went замість Did you go.", "Не знати другу форму неправильного дієслова.", "Плутати Past Simple і Present Perfect.", "Забути did у питанні."],
                "summary_points": ["Минуле завершене — Past Simple.", "Правильні: -ed.", "Неправильні: друга форма.", "Після did — початкова форма."],
                "self_check": ["Є маркер минулого?", "Дієслово правильне чи неправильне?", "Чи стоїть did у питанні?"],
            },
            3: {
                "simple_explanation": "Reading strategies — це способи читати текст швидше й точніше, не перекладаючи кожне слово.",
                "nmt_relevance": "На НМТ читання перевіряє головну думку, деталі, синоніми та логіку тексту.",
                "memory_tip": "Спочатку прочитай питання, потім шукай у тексті відповідну ідею, а не дослівне слово.",
                "formulas": ["skimming = швидко зрозуміти головну ідею", "scanning = знайти конкретну інформацію", "synonyms = слова з близьким значенням"],
                "theory_points": ["Не обов’язково перекладати весь текст.", "Skimming допомагає швидко зрозуміти тему.", "Scanning допомагає знайти конкретну інформацію.", "У тестах часто використовують синоніми.", "Відповідь має відповідати змісту, а не просто містити схоже слово.", "Перед вибором варіанта перечитай речення навколо потрібної інформації."],
                "extra_examples": ["job у питанні може бути work у тексті.", "important може бути essential.", "buy може бути purchase.", "Найкращий заголовок має передавати весь текст, а не одну деталь.", "Якщо питають про мету, шукай причину написання тексту.", "Якщо питають деталь, шукай конкретне речення."],
                "mistakes": ["Обирати відповідь лише через знайоме слово.", "Перекладати кожне слово і втрачати час.", "Не читати питання перед текстом.", "Ігнорувати синоніми."],
                "summary_points": ["Питання спочатку.", "Шукай ідею, не лише слово.", "Використовуй skimming і scanning.", "Перевір контекст."],
                "self_check": ["Що саме питають?", "Чи є синонім у тексті?", "Чи відповідь не суперечить контексту?"],
            },
        },
    }

    default_details = {
        "simple_explanation": lesson["theory"],
        "nmt_relevance": "Ця тема допомагає побудувати базу для наступних уроків і тестів.",
        "memory_tip": "Вчи тему маленькими частинами: спочатку ідея, потім приклад, потім тест.",
        "formulas": ["теорія → приклад → практика → перевірка"],
        "theory_points": [lesson["theory"], "Рухайся маленькими кроками.", "Після кожного блоку перевір себе коротким тестом."],
        "extra_examples": [lesson["example"], "Спробуй пояснити приклад своїми словами.", "Потім розв’яжи схоже завдання самостійно."],
        "mistakes": ["Поспішати і пропускати кроки.", "Читати теорію без практики.", "Не повертатися до помилок."],
        "summary_points": ["Зрозумій ідею.", "Розбери приклад.", "Пройди тест."],
        "self_check": ["Чи можу я пояснити тему своїми словами?", "Чи можу розв’язати схожий приклад?"],
    }

    return expanded.get(subject_key, {}).get(lesson_id, default_details)

def get_quiz_questions(lesson_id=None):
    subject_key = get_subject_key()
    lesson_id = normalize_lesson_id(lesson_id)
    subject_quizzes = QUIZ_BANK.get(subject_key, QUIZ_BANK["none"])
    base_questions = list(subject_quizzes.get(lesson_id, subject_quizzes[1]))
    extra_subject_questions = EXTRA_QUIZ_QUESTIONS.get(subject_key, EXTRA_QUIZ_QUESTIONS["none"])
    base_questions.extend(extra_subject_questions.get(lesson_id, extra_subject_questions[1]))
    return build_quiz(subject_key, lesson_id, base_questions)


def is_lesson_unlocked(lesson_id, subject_key=None):
    subject_key = subject_key or get_subject_key()
    lessons = get_lessons_for_subject(subject_key)
    lesson_ids = [item["id"] for item in lessons]
    if lesson_id not in lesson_ids:
        return False
    if lesson_id == lesson_ids[0]:
        return True
    previous_id = lesson_ids[lesson_ids.index(lesson_id) - 1]
    return previous_id in get_completed_lessons(subject_key)


def get_ai_usage_today(user_id):
    today = dt_date.today().isoformat()
    conn = get_db_connection()
    row = conn.execute(
        "SELECT request_count FROM ai_usage WHERE user_id = ? AND usage_date = ?",
        (user_id, today),
    ).fetchone()
    conn.close()
    return int(row["request_count"]) if row else 0


def increment_ai_usage(user_id):
    today = dt_date.today().isoformat()
    conn = get_db_connection()
    conn.execute(
        """
        INSERT INTO ai_usage (user_id, usage_date, request_count)
        VALUES (?, ?, 1)
        ON CONFLICT(user_id, usage_date) DO UPDATE SET
            request_count = request_count + 1
        """,
        (user_id, today),
    )
    conn.commit()
    conn.close()


def get_easy_answer(question, *, lesson_context=False, lesson=None):
    subject_key = get_subject_key()
    clean_question = (question or "").strip()

    if not lesson_context:
        subject_names = {
            "math": "математики",
            "ukrainian": "української мови",
            "history": "історії України",
            "english": "англійської мови",
            "none": "підготовки до НМТ",
        }
        subject_name = subject_names.get(subject_key, "підготовки до НМТ")
        if not clean_question:
            return f"Easy: Запитай будь-що про {subject_name}. Я поясню коротко, просто й без зайвих слів."
        lowered = clean_question.lower()
        if "приклад" in lowered:
            return "Easy: Напиши тему або саме завдання. Я підберу простий приклад і розберу кожен крок."
        if "прост" in lowered or "легш" in lowered:
            return "Easy: Скинь правило, речення або задачу. Я приберу складні слова й поясню все маленькими кроками."
        return f"Easy: Твоє питання: «{clean_question}». Почнемо з головної ідеї, а потім перевіримо її на прикладі."

    lesson = lesson or get_lesson_content()
    starters = {
        "math": "Easy: У математиці головне не зубрити формулу, а зрозуміти, що вона шукає. У темі «{title}» ми спочатку визначаємо дані, потім обираємо спосіб розв’язання і тільки після цього рахуємо.",
        "ukrainian": "Easy: В українській мові найкраще працює правило + приклад. У темі «{title}» спочатку знаходь підказку в слові, а потім перевіряй себе правилом.",
        "history": "Easy: В історії важливо не просто пам’ятати дату, а розуміти причину й наслідок. У темі «{title}» запитуй себе: що сталося, чому це сталося і до чого привело.",
        "english": "Easy: В англійській теми стають легшими, коли бачиш шаблон. У темі «{title}» дивись на ситуацію: це факт, звичка чи дія зараз? Тоді форма сама підказує себе.",
        "none": "Easy: Почнемо просто. Я поясню тему маленькими кроками, а потім дам приклад і перевірку.",
    }

    base = starters.get(subject_key, starters["none"]).format(title=lesson["title"])

    if not clean_question:
        return base + " Напиши, що саме тобі цікаво, і я поясню точніше."

    lowered = clean_question.lower()
    if "прост" in lowered or "легш" in lowered or "5 клас" in lowered:
        return base + " Якщо зовсім просто: уяви, що тема це двері. Правило це ключ. Спочатку знаходимо, який ключ потрібен, потім відкриваємо завдання крок за кроком."
    if "приклад" in lowered:
        return f"Easy: Ось приклад до теми «{lesson['title']}». {lesson['example']} Тепер спробуй пояснити собі, який був перший крок і чому саме він."
    if "чому" in lowered:
        return base + " Найчастіше відповідь на «чому» ховається в логіці правила: воно не вигадане просто так, а допомагає не плутатися в типових завданнях НМТ."
    return base + f" Твоє питання: «{clean_question}». Я б почав з цього: {lesson['goal'].capitalize()}."


@app.context_processor
def inject_global_state():
    return {
        "user_name": current_user_name(),
        "is_logged_in": is_logged_in(),
        "has_plan": onboarding_complete(),
        "csrf_token": csrf_token,
    }


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = (
            request.form.get("confirm_password")
            or request.form.get("password_confirm")
            or request.form.get("confirm")
            or ""
        )

        if not name or not email or not password or not confirm_password:
            flash("Заповни всі поля. Пароль потрібно ввести двічі.", "error")
            return render_template("register.html", name=name, email=email)

        if len(name) > 80 or len(email) > 254 or not EMAIL_PATTERN.fullmatch(email):
            flash("Перевір ім’я та введи коректну email-адресу.", "error")
            return render_template("register.html", name=name[:80], email=email[:254])

        if len(password) < 8 or len(password) > 128:
            flash("Пароль має містити від 8 до 128 символів.", "error")
            return render_template("register.html", name=name, email=email)

        if password != confirm_password:
            flash("Паролі не збігаються. Введи однаковий пароль у два поля.", "error")
            return render_template("register.html", name=name, email=email)

        conn = get_db_connection()
        existing_user = conn.execute("SELECT id FROM users WHERE lower(email) = ?", (email,)).fetchone()

        if existing_user:
            conn.close()
            flash("Користувач з таким email вже існує. Спробуй увійти.", "error")
            return render_template("register.html")

        password_hash = generate_password_hash(password)
        try:
            cursor = conn.execute(
                "INSERT INTO users (name, email, password_hash, provider) VALUES (?, ?, ?, ?)",
                (name, email, password_hash, "email"),
            )
            conn.commit()
            user = conn.execute("SELECT * FROM users WHERE id = ?", (cursor.lastrowid,)).fetchone()
        except sqlite3.IntegrityError:
            conn.rollback()
            flash("Користувач з таким email вже існує. Спробуй увійти.", "error")
            return render_template("register.html", name=name, email=email)
        finally:
            conn.close()

        login_user(user)
        clear_plan_session()
        session["progress"] = 0
        session["xp"] = 0
        flash("Акаунт створено. Тепер зберемо твій план.", "success")
        return redirect(url_for("goal"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        failure_key = login_failure_key(email)

        if login_is_blocked(failure_key):
            abort(429, description="Забагато невдалих спроб входу. Спробуй ще раз через 15 хвилин.")

        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE lower(email) = ?", (email,)).fetchone()
        conn.close()

        password_hash = user["password_hash"] if user is not None and user["password_hash"] else DUMMY_PASSWORD_HASH
        password_valid = check_password_hash(password_hash, password)
        if user is None or not user["password_hash"] or not password_valid:
            record_login_failure(failure_key)
            flash("Невірний email або пароль.", "error")
            return render_template("login.html", email=email)

        clear_login_failures(failure_key)
        login_user(user)
        session.permanent = request.form.get("remember") == "on"
        flash("Ти увійшов в акаунт.", "success")
        return redirect_after_auth()

    return render_template("login.html")


@app.route("/logout", methods=["POST"])
@require_login
def logout():
    session.clear()
    flash("Ти вийшов з акаунта.", "success")
    return redirect(url_for("home"))


@app.route("/auth/google/status")
def google_auth_status():
    """Safe diagnostics. It never returns credential values."""
    status = credentials_status()
    status.update(
        {
            "callback_url": google_callback_url(),
            "implementation": "oauth2_pkce_requests",
            "version": "v1.0 Beta",
        }
    )
    return status


def google_callback_url():
    configured = os.environ.get("GOOGLE_REDIRECT_URI", "").strip()
    if configured:
        return configured
    if app.config["TRUST_PROXY_HEADERS"]:
        return url_for("google_callback", _external=True, _scheme="https")
    return url_for("google_callback", _external=True)


@app.route("/login/google")
def google_login():
    status = credentials_status()
    if not status["google_client_ready"]:
        app.logger.warning(
            "Google OAuth unavailable: client_id_present=%s client_secret_present=%s",
            status["client_id_present"],
            status["client_secret_present"],
        )
        flash(
            "Вхід через Google зараз недоступний. Спробуй увійти за email або трохи пізніше.",
            "error",
        )
        return redirect(url_for("login"))

    callback_url = google_callback_url()
    try:
        return redirect(build_authorization_url(callback_url))
    except Exception:
        app.logger.exception("Could not start Google OAuth")
        flash("Не вдалося відкрити вхід через Google. Спробуй ще раз.", "error")
        return redirect(url_for("login"))


@app.route("/auth/google/callback")
def google_callback():
    if request.args.get("error"):
        app.logger.warning("Google OAuth was cancelled: %s", request.args.get("error"))
        flash("Вхід через Google скасовано.", "error")
        return redirect(url_for("login"))

    callback_url = google_callback_url()
    try:
        user_info = exchange_callback(
            code=request.args.get("code", ""),
            state=request.args.get("state", ""),
            callback_url=callback_url,
        )
    except Exception:
        app.logger.exception("Google OAuth callback failed")
        flash(
            "Не вдалося завершити вхід через Google. Спробуй ще раз через кілька секунд.",
            "error",
        )
        return redirect(url_for("login"))

    email = (user_info.get("email") or "").strip().lower()
    name = (user_info.get("name") or "").strip() or (email.split("@")[0] if email else "Учень")
    google_sub = (user_info.get("sub") or "").strip()
    avatar_url = (user_info.get("picture") or "").strip()
    email_verified = user_info.get("email_verified")

    if not email or not google_sub:
        flash("Google не передав потрібні дані акаунта. Спробуй інший акаунт.", "error")
        return redirect(url_for("login"))

    if email_verified is not True:
        flash("Спочатку підтвердь email у своєму Google-акаунті.", "error")
        return redirect(url_for("login"))

    conn = get_db_connection()
    try:
        user = conn.execute(
            "SELECT * FROM users WHERE google_sub = ? OR lower(email) = ?",
            (google_sub, email),
        ).fetchone()

        is_new_google_user = user is None

        if user is None:
            cursor = conn.execute(
                """
                INSERT INTO users
                    (name, email, password_hash, provider, google_sub, avatar_url)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (name, email, None, "google", google_sub, avatar_url),
            )
            conn.commit()
            user = conn.execute(
                "SELECT * FROM users WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
        else:
            conn.execute(
                """
                UPDATE users
                SET google_sub = COALESCE(google_sub, ?),
                    avatar_url = CASE WHEN ? <> '' THEN ? ELSE avatar_url END,
                    name = CASE WHEN name = '' THEN ? ELSE name END
                WHERE id = ?
                """,
                (google_sub, avatar_url, avatar_url, name, user["id"]),
            )
            conn.commit()
            user = conn.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
    except sqlite3.IntegrityError:
        conn.rollback()
        app.logger.exception("Could not link Google account")
        flash("Цей Google-акаунт уже прив’язаний до іншого профілю EasyNMT.", "error")
        return redirect(url_for("login"))
    finally:
        conn.close()

    if not is_new_google_user:
        ensure_legacy_google_plan(user["id"])

    login_user(user)
    session["user_avatar"] = avatar_url
    flash("Готово, ти увійшов через Google.", "success")
    return redirect_after_auth()


@app.route("/goal")
@require_login
def goal():
    return render_template("goal.html", step=1)


@app.route("/set-goal/<goal>", methods=["POST"])
@require_login
def set_goal(goal):
    if goal not in VALID_GOALS:
        abort(404)
    session["goal"] = goal
    session["progress"] = session.get("progress", 0)
    session["xp"] = session.get("xp", 0)
    save_plan_to_db()
    return redirect(url_for("subject"))


@app.route("/subject")
@require_login
def subject():
    return render_template("subject.html", step=2)


@app.route("/set-subject/<subject>", methods=["POST"])
@require_login
def set_subject(subject):
    if subject not in VALID_SUBJECTS:
        abort(404)
    previous_subject = session.get("subject")
    if previous_subject and previous_subject != subject:
        save_plan_to_db()
    session["subject"] = subject
    session["current_lesson_id"] = 1
    load_subject_progress_to_session(session["user_id"], subject)
    save_plan_to_db()
    return redirect(url_for("date"))


@app.route("/change-subject")
@require_login
def change_subject():
    if not onboarding_complete():
        return redirect(url_for("goal"))
    return render_template("change_subject.html", **get_user_data())


@app.route("/switch-subject/<subject>", methods=["POST"])
@require_login
def switch_subject(subject):
    if subject not in VALID_SUBJECTS:
        abort(404)
    save_plan_to_db()
    session["subject"] = subject
    requested_lesson = request.form.get("lesson", type=int)
    session["current_lesson_id"] = requested_lesson or 1
    load_subject_progress_to_session(session["user_id"], subject)
    if requested_lesson:
        session["current_lesson_id"] = normalize_lesson_id(requested_lesson)
    session.pop("last_score", None)
    session.pop("last_total", None)
    save_plan_to_db()
    flash("Предмет змінено. EasyNMT перебудував стартові уроки.", "success")
    if requested_lesson and is_lesson_unlocked(session["current_lesson_id"], subject):
        return redirect(url_for("lesson", lesson_id=session["current_lesson_id"]))
    return redirect(url_for("dashboard"))


@app.route("/date")
@require_login
def date():
    return render_template("date.html", step=3)


@app.route("/set-time/<time_left>", methods=["POST"])
@require_login
def set_time(time_left):
    if time_left not in VALID_TIME_LEFT:
        abort(404)
    session["time_left"] = time_left
    session["progress"] = session.get("progress", 0)
    session["xp"] = session.get("xp", 0)
    session["diagnostic_required"] = True
    save_plan_to_db()
    return redirect(url_for("loader"))


@app.route("/loader")
@require_login
def loader():
    if not onboarding_complete():
        return redirect(url_for("goal"))
    return render_template("loader.html")


DIAGNOSTIC_BANK = {
    "math": [
        ("Скільки буде 3 · 4?", ["7", "12", "14"], "12"),
        ("Яке число є розв’язком рівняння x + 5 = 9?", ["4", "5", "14"], "4"),
        ("Що означає x²?", ["x · 2", "x · x", "2 + x"], "x · x"),
        ("Скільки коренів може мати квадратне рівняння?", ["Тільки один", "Нуль, один або два", "Завжди два"], "Нуль, один або два"),
        ("Якщо y = 2x і x = 3, то y дорівнює...", ["5", "6", "9"], "6"),
    ],
    "ukrainian": [
        ("У якому слові потрібен апостроф?", ["буряк", "обєкт", "об’єкт"], "об’єкт"),
        ("Скільки граматичних основ у складному реченні?", ["Одна", "Дві або більше", "Жодної"], "Дві або більше"),
        ("Правильний наголос:", ["вИпадок", "випАдок", "випадОк"], "вИпадок"),
        ("Що таке підмет?", ["Головний член речення, що називає виконавця", "Розділовий знак", "Частина слова"], "Головний член речення, що називає виконавця"),
        ("Орфографія вивчає...", ["Правопис слів", "Будову тексту", "Тільки наголос"], "Правопис слів"),
    ],
    "history": [
        ("Хрещення Русі відбулося у...", ["988 році", "1240 році", "1648 році"], "988 році"),
        ("Хто очолив Національно-визвольну війну 1648 року?", ["Володимир Великий", "Богдан Хмельницький", "Михайло Грушевський"], "Богдан Хмельницький"),
        ("Що важливіше для НМТ з історії?", ["Лише дати", "Причини, події та наслідки", "Тільки портрети"], "Причини, події та наслідки"),
        ("IV Універсал проголосив...", ["Незалежність УНР", "Хрещення Русі", "Створення Січі"], "Незалежність УНР"),
        ("Київська Русь належить до...", ["Середньовіччя", "XX століття", "Сучасності"], "Середньовіччя"),
    ],
    "english": [
        ("Choose the correct sentence:", ["She play every day.", "She plays every day.", "She playing every day."], "She plays every day."),
        ("Past Simple of go:", ["goed", "went", "gone"], "went"),
        ("Present Simple is used for...", ["habits and facts", "actions happening now only", "future plans only"], "habits and facts"),
        ("Choose the correct negative:", ["He don't study.", "He doesn't study.", "He not study."], "He doesn't study."),
        ("A synonym for job is...", ["work", "sleep", "weather"], "work"),
    ],
}

@app.route("/diagnostic", methods=["GET", "POST"])
@require_login
def diagnostic():
    if not onboarding_complete():
        return redirect(url_for("goal"))
    subject_key = session.get("subject", "math")
    if request.method == "GET" and diagnostic_complete(subject_key) and not diagnostic_is_required():
        return redirect(url_for("dashboard"))
    questions = DIAGNOSTIC_BANK.get(subject_key, DIAGNOSTIC_BANK["math"])
    if request.method == "POST":
        score = sum(1 for index, q in enumerate(questions, 1) if request.form.get(f"q{index}") == q[2])
        level = "beginner" if score <= 2 else "foundation" if score <= 4 else "confident"
        conn = get_db_connection()
        conn.execute(
            """INSERT INTO diagnostic_results (user_id, subject, score, total, level)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(user_id, subject) DO UPDATE SET
                 score=excluded.score, total=excluded.total, level=excluded.level, completed_at=CURRENT_TIMESTAMP""",
            (session["user_id"], subject_key, score, len(questions), level),
        )
        conn.commit(); conn.close()
        session["diagnostic_required"] = False
        save_plan_to_db()
        flash("Перевірку завершено. Тепер маршрут підлаштовано під твій рівень.", "success")
        return redirect(url_for("welcome"))
    return render_template("diagnostic.html", **get_user_data(), questions=questions)

@app.route("/lesson/<int:lesson_id>/ready", methods=["POST"])
@require_login
def mark_lesson_ready(lesson_id):
    if not onboarding_complete():
        return redirect(url_for("goal"))
    if not is_valid_lesson_id(lesson_id):
        abort(404)
    lesson_id = normalize_lesson_id(lesson_id)
    if not is_lesson_unlocked(lesson_id):
        abort(403)
    conn = get_db_connection()
    conn.execute(
        "INSERT OR IGNORE INTO lesson_readiness (user_id, subject, lesson_id) VALUES (?, ?, ?)",
        (session["user_id"], session.get("subject", "none"), lesson_id),
    )
    conn.commit(); conn.close()
    flash("Пояснення пройдено. Тепер можна перевірити себе в тесті.", "success")
    return redirect(url_for("quiz", lesson_id=lesson_id))

@app.route("/about")
def about():
    return render_template("about.html", is_logged_in=is_logged_in())

@app.route("/pricing")
def pricing():
    return render_template("pricing.html", is_logged_in=is_logged_in())

@app.route("/privacy")
def privacy():
    return render_template("privacy.html", is_logged_in=is_logged_in())


WELCOME_EXPERIENCE = {
    "math": {
        "name": "Математика",
        "headline": "Кожна задача має розв’язання.",
        "messages": [
            "Сьогодні ще один крок до впевнених відповідей.",
            "Не поспішай. Точність починається з одного правильного кроку.",
            "Складне стає простішим, коли розібрати його по частинах.",
        ],
        "symbol": "∑",
    },
    "english": {
        "name": "English",
        "headline": "Let’s do it.",
        "messages": [
            "One lesson closer to your goal.",
            "Practice makes progress.",
            "Every word counts.",
        ],
        "symbol": "A",
    },
    "ukrainian": {
        "name": "Українська мова",
        "headline": "Мова відкриває можливості.",
        "messages": [
            "Одне правило сьогодні — більше впевненості на НМТ.",
            "Уважність до слова перетворюється на правильну відповідь.",
            "Рухайся крок за кроком. Ти вже ближче до своєї цілі.",
        ],
        "symbol": "Ї",
    },
    "history": {
        "name": "Історія України",
        "headline": "Минуле допомагає будувати майбутнє.",
        "messages": [
            "Сьогодні зв’яжемо події, причини та наслідки.",
            "Ще одна тема — і карта історії стає зрозумілішою.",
            "Не просто запам’ятовуй. Зрозумій, чому це сталося.",
        ],
        "symbol": "✦",
    },
}

@app.route("/welcome")
@require_login
def welcome():
    if not onboarding_complete():
        return redirect(url_for("goal"))
    if diagnostic_is_required() and not diagnostic_complete():
        return redirect(url_for("diagnostic"))

    subject_key = session.get("subject", "math")
    experience = WELCOME_EXPERIENCE.get(subject_key, WELCOME_EXPERIENCE["math"])
    message = random.choice(experience["messages"])
    return render_template(
        "welcome.html",
        subject_key=subject_key,
        subject_name=experience["name"],
        headline=experience["headline"],
        welcome_message=message,
        subject_symbol=experience["symbol"],
        user_name=session.get("user_name", "Учень"),
        is_logged_in=True,
        has_plan=True,
    )


@app.route("/dashboard")
@require_login
def dashboard():
    if not onboarding_complete():
        return redirect(url_for("goal"))
    if diagnostic_is_required() and not diagnostic_complete():
        return redirect(url_for("diagnostic"))

    return render_template("dashboard.html", **get_user_data())


@app.route("/today")
@require_login
def today():
    if not onboarding_complete():
        return redirect(url_for("goal"))

    return render_template("today.html", **get_user_data())


@app.route("/lesson")
@app.route("/lesson/<int:lesson_id>")
@require_login
def lesson(lesson_id=1):
    if not onboarding_complete():
        return redirect(url_for("goal"))

    if not is_valid_lesson_id(lesson_id):
        abort(404)
    lesson_id = normalize_lesson_id(lesson_id)
    if not is_lesson_unlocked(lesson_id):
        flash("Спочатку заверши попередній урок. Так нова тема не буде висіти в повітрі.", "error")
        return redirect(url_for("today"))

    session["current_lesson_id"] = lesson_id
    save_plan_to_db()
    lesson_content = get_lesson_content(lesson_id)
    return render_template(
        "lesson.html", **get_user_data(), lesson=lesson_content,
        details=get_lesson_details(lesson_id),
        lesson_ready=is_lesson_ready(lesson_id),
    )


def _save_solution_photo(file_storage, user_id, lesson_id, question_id):
    attachment = save_image_upload(
        file_storage,
        UPLOAD_DIR,
        max_bytes=app.config["AI_MAX_ATTACHMENT_BYTES"],
    )
    extension = os.path.splitext(attachment.stored_path)[1].lower()
    question_fragment = re.sub(r"[^A-Za-z0-9_-]", "", str(question_id))[:60] or "question"
    safe_name = f"u{user_id}_l{lesson_id}_{question_fragment}_{uuid.uuid4().hex}{extension}"
    path = os.path.join(UPLOAD_DIR, safe_name)
    os.replace(attachment.stored_path, path)
    return safe_name, path


@app.route("/solution-file/<path:filename>")
@require_login
def solution_file(filename):
    safe = secure_filename(filename)
    if safe != filename or not filename.startswith(f"u{session['user_id']}_"):
        abort(404)
    path = os.path.join(UPLOAD_DIR, safe)
    if not os.path.isfile(path):
        abort(404)
    return send_file(path)



@app.route("/api/quiz-draft/<int:lesson_id>", methods=["POST", "DELETE"])
@require_login
def quiz_draft_api(lesson_id):
    if not onboarding_complete():
        return {"ok": False, "error": "onboarding_required"}, 403
    if not is_valid_lesson_id(lesson_id):
        return {"ok": False, "error": "lesson_not_found"}, 404
    lesson_id = normalize_lesson_id(lesson_id)
    if not is_lesson_unlocked(lesson_id):
        return {"ok": False, "error": "lesson_locked"}, 403
    if request.method == "DELETE":
        delete_quiz_draft(lesson_id)
        return {"ok": True}
    payload = request.get_json(silent=True) or {}
    answers = payload.get("answers") if isinstance(payload, dict) else {}
    if not isinstance(answers, dict):
        return {"ok": False, "error": "invalid_answers"}, 400
    save_quiz_draft(lesson_id, answers)
    return {"ok": True}

@app.route("/quiz", methods=["GET", "POST"])
@app.route("/quiz/<int:lesson_id>", methods=["GET", "POST"])
@require_login
def quiz(lesson_id=None):
    if not onboarding_complete():
        return redirect(url_for("goal"))

    if lesson_id is not None and not is_valid_lesson_id(lesson_id):
        abort(404)
    lesson_id = normalize_lesson_id(lesson_id)
    if not is_lesson_unlocked(lesson_id):
        flash("Цей урок ще закритий. Заверши попередній, і він відкриється автоматично.", "error")
        return redirect(url_for("today"))
    if request.method == "GET" and not is_lesson_ready(lesson_id):
        flash("Спочатку пройди пояснення й познач, що готовий перевірити себе.", "error")
        return redirect(url_for("lesson", lesson_id=lesson_id))

    session["current_lesson_id"] = lesson_id
    save_plan_to_db()

    if request.method == "POST":
        attempt_token = (request.form.get("attempt_token") or "").strip()
        if not attempt_token:
            flash("Спроба тесту застаріла. Відкрий тест ще раз, відповіді збережено.", "error")
            return redirect(url_for("quiz", lesson_id=lesson_id))

        conn = get_db_connection()
        existing = conn.execute(
            """
            SELECT attempt_token, lesson_id, score, total, passed, xp_awarded, review_json, submitted_at
            FROM quiz_attempts
            WHERE attempt_token = ? AND user_id = ?
            """,
            (attempt_token, session["user_id"]),
        ).fetchone()
        conn.close()
        if existing:
            load_subject_progress_to_session(session["user_id"], get_subject_key())
            restore_attempt_to_session(dict(existing))
            flash("Цю спробу вже зараховано. Повторно XP не нараховується.", "info")
            return redirect(url_for("result"))

        conn = get_db_connection()
        quiz_session = conn.execute(
            """
            SELECT quiz_json FROM quiz_sessions
            WHERE attempt_token = ? AND user_id = ? AND subject = ? AND lesson_id = ?
              AND created_at >= datetime('now', '-1 day')
            """,
            (attempt_token, session["user_id"], get_subject_key(), lesson_id),
        ).fetchone()
        conn.close()
        if not quiz_session:
            flash("Сесія тесту оновилася. Текстові відповіді залишилися в чернетці.", "error")
            return redirect(url_for("quiz", lesson_id=lesson_id))
        try:
            active_quiz_map = json.loads(quiz_session["quiz_json"] or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            active_quiz_map = {}
        if not isinstance(active_quiz_map, dict) or not active_quiz_map:
            flash("Не вдалося відновити питання тесту. Відкрий його ще раз.", "error")
            return redirect(url_for("quiz", lesson_id=lesson_id))

        question_items = list(active_quiz_map.items())
        expected_total = sum(
            int(question.get("points", 0))
            for _qid, question in question_items
            if isinstance(question, dict)
        )
        if len(question_items) != 12 or expected_total != MAX_SCORE:
            app.logger.error(
                "Invalid stored quiz shape: user=%s subject=%s lesson=%s count=%s total=%s",
                session["user_id"], get_subject_key(), lesson_id, len(question_items), expected_total,
            )
            flash("Тест пошкоджено. Відкрий його ще раз, щоб створити нову спробу.", "error")
            return redirect(url_for("lesson", lesson_id=lesson_id))

        score = 0
        total = 0
        review = []

        for qid, question in question_items:
            points = int(question.get("points", 1))
            annotated_url = None
            photo_url = None
            if points == 3:
                user_answer = request.form.get(f"answer_{qid}", "").strip()
                photo = request.files.get(f"photo_{qid}")
                if photo and photo.filename:
                    try:
                        original_name, original_path = _save_solution_photo(photo, session["user_id"], lesson_id, qid)
                        photo_url = url_for("solution_file", filename=original_name)
                        if vision_grader.enabled:
                            analysis = vision_grader.grade(
                                image_path=original_path,
                                question=question.get("question", "Письмове завдання"),
                                correct_answer=question.get("answer", ""),
                                reference_solution=question.get("explanation", ""),
                            )
                            if analysis.get("mode") == "openai":
                                earned = max(0, min(points, int(analysis.get("score", 0))))
                                is_correct = earned == points
                                feedback = analysis.get("message", "Перевір позначений крок.")
                                annotated_name = f"u{session['user_id']}_annotated_{original_name.rsplit('.', 1)[0]}.jpg"
                                annotated_path = os.path.join(UPLOAD_DIR, annotated_name)
                                create_annotated_solution(original_path, annotated_path, analysis)
                                annotated_url = url_for("solution_file", filename=annotated_name)
                            else:
                                earned, is_correct, feedback = grade_question(question, user_answer)
                                feedback = "AI-перевірка фото недоступна. Оцінено текстовий розв’язок. " + feedback
                        else:
                            earned, is_correct, feedback = grade_question(question, user_answer)
                            feedback = "Оцінено текстовий розв’язок; фото збережено для перегляду. " + feedback
                    except (AttachmentError, ValueError) as exc:
                        earned, is_correct, fallback_feedback = grade_question(question, user_answer)
                        feedback = f"{exc} {fallback_feedback}"
                    except Exception:
                        app.logger.exception("Could not grade solution photo")
                        earned, is_correct, fallback_feedback = grade_question(question, user_answer)
                        feedback = "Не вдалося прочитати фото. Оцінено текстовий розв’язок. " + fallback_feedback
                else:
                    earned, is_correct, feedback = grade_question(question, user_answer)
            else:
                user_answer = request.form.get(f"answer_{qid}", "").strip()
                earned, is_correct, feedback = grade_question(question, user_answer)

            score += earned
            total += points
            review.append({
                "question": question.get("question", "Питання"),
                "user_answer": user_answer or ("Розв’язання на фото" if photo_url else "Відповіді немає"),
                "correct_answer": question.get("answer", "Переглянь матеріал уроку"),
                "is_correct": is_correct,
                "earned": earned,
                "points": points,
                "explanation": feedback,
                "type": question.get("type", "choice"),
                "photo_url": photo_url,
                "annotated_url": annotated_url,
            })

        passed = score >= PASS_SCORE
        finalization = finalize_quiz_attempt(
            attempt_token=attempt_token,
            lesson_id=lesson_id,
            score=score,
            total=total,
            passed=passed,
            review=review,
        )
        attempt = finalization["attempt"]
        if finalization["duplicate"]:
            load_subject_progress_to_session(session["user_id"], get_subject_key())
            flash("Цю спробу вже зараховано. Повторно XP не нараховується.", "info")
        else:
            session.update({
                "progress": finalization["progress"],
                "xp": finalization["xp"],
                "streak": finalization["streak"],
                "last_activity_date": finalization["last_activity_date"],
                "last_quiz_score": score,
                "last_quiz_total": total,
            })
        restore_attempt_to_session(attempt)
        session["new_achievements"] = finalization["new_achievements"]
        return redirect(url_for("result"))

    raw_questions = get_quiz_questions(lesson_id)
    prepared_questions = []
    active_quiz_map = {}
    for index, question in enumerate(raw_questions, start=1):
        prepared = dict(question)
        qid = f"{get_subject_key()}_{lesson_id}_{index}"
        prepared["id"] = qid
        if prepared.get("type") == "choice":
            options = list(prepared.get("options", []))
            random.shuffle(options)
            prepared["options"] = options
        prepared_questions.append(prepared)
        active_quiz_map[qid] = prepared

    attempt_token = uuid.uuid4().hex
    conn = get_db_connection()
    # Keep parallel browser tabs valid while pruning abandoned sessions.
    conn.execute(
        "DELETE FROM quiz_sessions WHERE user_id = ? AND created_at < datetime('now', '-1 day')",
        (session["user_id"],),
    )
    conn.execute(
        """
        INSERT INTO quiz_sessions (attempt_token, user_id, subject, lesson_id, quiz_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        (attempt_token, session["user_id"], get_subject_key(), lesson_id,
         json.dumps(active_quiz_map, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()
    draft_answers = get_quiz_draft(lesson_id)
    attempt_count = len(get_quiz_attempts(lesson_id))
    return render_template(
        "quiz.html", **get_user_data(), lesson=get_lesson_content(lesson_id),
        questions=prepared_questions, pass_score=PASS_SCORE, max_score=MAX_SCORE,
        attempt_token=attempt_token, draft_answers=draft_answers, attempt_count=attempt_count,
        vision_enabled=vision_grader.enabled,
    )


@app.route("/result")
@require_login
def result():
    if not onboarding_complete():
        return redirect(url_for("goal"))

    attempt = None
    token = session.get("last_attempt_token")
    conn = get_db_connection()
    if token:
        row = conn.execute(
            """SELECT attempt_token, lesson_id, score, total, passed, xp_awarded, review_json, submitted_at
               FROM quiz_attempts WHERE attempt_token = ? AND user_id = ?""",
            (token, session["user_id"]),
        ).fetchone()
        attempt = dict(row) if row else None
    if attempt is None:
        row = conn.execute(
            """SELECT attempt_token, lesson_id, score, total, passed, xp_awarded, review_json, submitted_at
               FROM quiz_attempts WHERE user_id = ? AND subject = ?
               ORDER BY submitted_at DESC, id DESC LIMIT 1""",
            (session["user_id"], session.get("subject", "none")),
        ).fetchone()
        attempt = dict(row) if row else None
    conn.close()

    if attempt:
        restore_attempt_to_session(attempt)
        try:
            review = json.loads(attempt.get("review_json") or "[]")
        except (TypeError, ValueError, json.JSONDecodeError):
            review = []
    elif "last_score" in session:
        review = session.get("last_review", [])
    else:
        return redirect(url_for("today"))

    lesson_id = normalize_lesson_id(session.get("last_lesson_id"))
    lessons = get_lessons_for_subject()
    valid_ids = [lesson["id"] for lesson in lessons]
    next_lesson_id = lesson_id + 1 if lesson_id + 1 in valid_ids else None

    return render_template(
        "result.html",
        **get_user_data(),
        lesson=get_lesson_content(lesson_id),
        next_lesson_id=next_lesson_id,
        has_next_lesson=next_lesson_id is not None,
        score=session.get("last_score", 0),
        total=session.get("last_total", 5),
        review=review,
        xp_gain=session.get("xp_gain", 0),
        new_achievements=session.get("new_achievements", []),
        passed=session.get("last_passed", False),
        pass_score=PASS_SCORE,
    )


@app.route("/theory/<int:lesson_id>")
@require_login
def theory_detail(lesson_id):
    if not onboarding_complete():
        return redirect(url_for("goal"))

    if not is_valid_lesson_id(lesson_id):
        abort(404)
    lesson_id = normalize_lesson_id(lesson_id)
    if not is_lesson_unlocked(lesson_id):
        abort(403)
    session["current_lesson_id"] = lesson_id

    return render_template(
        "theory_detail.html",
        **get_user_data(),
        lesson=get_lesson_content(lesson_id),
        details=get_lesson_details(lesson_id),
    )


@app.route("/example/<int:lesson_id>")
@require_login
def example_detail(lesson_id):
    if not onboarding_complete():
        return redirect(url_for("goal"))

    if not is_valid_lesson_id(lesson_id):
        abort(404)
    lesson_id = normalize_lesson_id(lesson_id)
    if not is_lesson_unlocked(lesson_id):
        abort(403)
    session["current_lesson_id"] = lesson_id

    lesson_data = get_lesson_content(lesson_id)
    details = get_lesson_details(lesson_id)
    return render_template(
        "example_detail.html",
        **get_user_data(),
        lesson=lesson_data,
        details=details,
        board=build_lesson_board(get_subject_key(), lesson_data, details),
    )



@app.route("/progress")
@require_login
def progress_page():
    if not onboarding_complete():
        return redirect(url_for("goal"))

    return render_template(
        "progress.html",
        **get_user_data(),
        completed_stats=get_completed_lesson_stats(),
        quiz_attempts=get_quiz_attempt_summary(),
    )


@app.route("/achievements")
@require_login
def achievements_page():
    if not onboarding_complete():
        return redirect(url_for("goal"))

    return render_template(
        "achievements.html",
        **get_user_data(),
        all_achievements=get_achievements(),
    )


@app.route("/tutor", methods=["GET", "POST"])
@require_login
def tutor():
    if not onboarding_complete():
        return redirect(url_for("goal"))

    question = ""
    answer = ""

    lesson_context = request.values.get("context") == "lesson"
    requested_lesson_id = request.values.get("lesson_id")
    lesson = None
    lesson_id = None
    if lesson_context:
        lesson_id = normalize_lesson_id(requested_lesson_id or session.get("current_lesson_id", 1))
        lesson = get_lesson_content(lesson_id)
        session["current_lesson_id"] = lesson_id

    user_id = session.get("user_id")
    daily_limit = app.config["OPENAI_DAILY_LIMIT"]
    used_today = get_ai_usage_today(user_id)
    ai_mode = "openai" if ai_service.enabled else "demo"
    ai_error = None

    if request.method == "POST":
        question = request.form.get("question", "").strip()
        max_chars = app.config["OPENAI_MAX_QUESTION_CHARS"]
        if not question:
            answer = "Напиши питання, і Easy допоможе розібратися."
        elif len(question) > max_chars:
            answer = f"Питання завелике. Скороти його до {max_chars} символів."
        elif ai_service.enabled and used_today >= daily_limit:
            answer = "Денний AI-ліміт вичерпано. Спробуй завтра або продовжуй у демо-режимі."
            ai_mode = "limit"
        else:
            fallback = get_easy_answer(
                question,
                lesson_context=lesson_context,
                lesson=lesson,
            )
            result = ai_service.answer(
                question=question,
                subject=session.get("subject", "НМТ"),
                lesson_title=lesson["title"] if lesson_context and lesson else "",
                lesson_goal=lesson.get("goal", "зрозуміти тему") if lesson_context and lesson else "",
                fallback=fallback,
                lesson_context=lesson_context,
            )
            answer = clean_tutor_answer_text(result.text)
            ai_mode = result.mode
            ai_error = result.error
            if result.mode == "openai":
                increment_ai_usage(user_id)
                used_today += 1

    return render_template(
        "tutor.html",
        **get_user_data(),
        lesson=lesson,
        lesson_context=lesson_context,
        lesson_id=lesson_id,
        question=question,
        answer=answer,
        ai_mode=ai_mode,
        ai_error=ai_error,
        ai_used=used_today,
        ai_limit=daily_limit,
        ai_model=app.config["OPENAI_MODEL"],
    )



def normalize_tutor_response_mode(value):
    """Keep the UI response mode small, predictable and prompt-safe."""
    normalized = str(value or "explain").strip().lower()
    if normalized not in {"explain", "concise", "practice"}:
        return "explain"
    return normalized


def clean_tutor_answer_text(value):
    """Avoid repeating the Easy name because the UI already labels assistant messages."""
    return ai_orchestrator.clean_text(value)


def shape_demo_tutor_answer(value, response_mode, *, lesson_context=False, lesson=None):
    """Make the three UI modes useful even before an OpenAI key is connected."""
    text = clean_tutor_answer_text(value)
    if response_mode == "practice":
        first_step = (
            f"Напиши одним реченням, що ти вже знаєш про тему «{lesson.get('title')}»."
            if lesson_context and lesson
            else "Напиши одним реченням, що ти вже знаєш про це."
        )
        return (
            f"Почнемо як на тренуванні. {first_step} "
            "Після твоєї відповіді я перевірю логіку й дам наступний крок."
        )
    if response_mode == "concise":
        sentences = re.split(r"(?<=[.!?…])\s+", text)
        return " ".join(sentences[:2]).strip()
    return text


def normalize_tutor_history(raw_history, limit=12):
    history = []
    if not isinstance(raw_history, list):
        return history
    for item in raw_history[-limit:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "")).strip().lower()
        text = str(item.get("text", "")).strip()
        if role in {"user", "assistant"} and text:
            history.append({"role": role, "text": text[:2400]})
    return history


def normalize_client_id(value, prefix):
    text = re.sub(r"[^A-Za-z0-9._:-]", "", str(value or "").strip())[:120]
    return text or f"{prefix}-{uuid.uuid4()}"


def build_tutor_learning_context(*, lesson_context, lesson, response_mode):
    data = get_user_data()
    return LearningContext(
        user_id=int(session.get("user_id")),
        user_name=str(session.get("user_name") or "Учень"),
        subject_key=str(session.get("subject") or "none"),
        subject_name=str(data.get("subject") or "Підготовка до НМТ"),
        goal=str(data.get("goal") or ""),
        time_left=str(data.get("time_left") or ""),
        progress=int(data.get("progress") or 0),
        xp=int(data.get("xp") or 0),
        streak=int(data.get("streak") or 1),
        lesson_id=int(lesson["id"]) if lesson_context and lesson else None,
        lesson_title=str(lesson.get("title", "")) if lesson_context and lesson else "",
        lesson_goal=str(lesson.get("goal", "зрозуміти тему")) if lesson_context and lesson else "",
        weak_topic=str(data.get("weak_topic") or ""),
        weak_count=int(data.get("weak_count") or 0),
        response_mode=response_mode,
        lesson_context=lesson_context,
    )


def build_tutor_ai_request(payload, *, question, lesson_context, lesson, response_mode, fallback):
    user_id = int(session.get("user_id"))
    conversation_id = normalize_client_id(payload.get("conversation_id"), "chat")
    user_message_id = normalize_client_id(payload.get("user_message_id"), "msg-user")
    assistant_message_id = normalize_client_id(payload.get("assistant_message_id"), "msg-easy")
    attachment_ids = normalize_attachment_ids(
        payload.get("attachment_ids", []),
        limit=app.config["AI_MAX_ATTACHMENTS"],
    )
    attachments = ai_repository.get_attachments(user_id=user_id, attachment_ids=attachment_ids)
    server_history = ai_repository.get_history(
        user_id=user_id,
        conversation_id=conversation_id,
        limit=12,
    )
    history = server_history or normalize_tutor_history(payload.get("history", []))
    context = build_tutor_learning_context(
        lesson_context=lesson_context,
        lesson=lesson,
        response_mode=response_mode,
    )
    return AIRequest(
        question=question,
        context=context,
        history=history,
        attachments=attachments,
        fallback=fallback,
        conversation_id=conversation_id,
        user_message_id=user_message_id,
        assistant_message_id=assistant_message_id,
    )


def tutor_sse_event(event_name, payload):
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event_name}\ndata: {encoded}\n\n"


def tutor_stream_chunks(text):
    """Readable fallback chunks; OpenAI mode uses native Responses API deltas."""
    tokens = re.findall(r"\S+\s*", str(text or ""))
    bucket = []
    bucket_length = 0
    for token in tokens:
        bucket.append(token)
        bucket_length += len(token)
        ends_sentence = bool(re.search(r"[.!?…][\"')\]]?\s*$", token))
        if bucket_length >= 28 or ends_sentence:
            yield "".join(bucket)
            bucket = []
            bucket_length = 0
    if bucket:
        yield "".join(bucket)


@app.route("/api/ai/status")
@require_login
def ai_status_api():
    used = get_ai_usage_today(session.get("user_id"))
    limit = app.config["OPENAI_DAILY_LIMIT"]
    return jsonify({
        "ok": True,
        "enabled": ai_orchestrator.enabled,
        "mode": "openai" if ai_orchestrator.enabled else "demo",
        "model": app.config["OPENAI_MODEL"],
        "vision_model": app.config["OPENAI_VISION_MODEL"],
        "used": used,
        "limit": limit,
        "streaming": True,
        "vision_ready": True,
        "vision_enabled": ai_orchestrator.enabled,
        "server_memory": True,
        "upload_limit": app.config["AI_DAILY_UPLOAD_LIMIT"],
    })


@app.route("/api/ai/attachments", methods=["POST"])
@require_login
def ai_attachment_upload_api():
    if not onboarding_complete():
        return jsonify({"ok": False, "error": "Спочатку заверши налаштування профілю."}), 403
    user_id = int(session.get("user_id"))
    today_start = f"{datetime.utcnow().date().isoformat()}T00:00:00+00:00"
    uploaded_today = ai_repository.count_attachments_since(user_id=user_id, since=today_start)
    if uploaded_today >= app.config["AI_DAILY_UPLOAD_LIMIT"]:
        return jsonify({
            "ok": False,
            "error": "Денний ліміт завантаження фото вичерпано. Спробуй завтра.",
        }), 429
    try:
        attachment = save_image_upload(
            request.files.get("file"),
            AI_UPLOAD_DIR,
            max_bytes=app.config["AI_MAX_ATTACHMENT_BYTES"],
        )
    except AttachmentError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    conversation_id = normalize_client_id(request.form.get("conversation_id"), "chat")
    ai_repository.save_attachment(
        user_id=user_id,
        attachment=attachment,
        conversation_id=conversation_id,
    )
    return jsonify({
        "ok": True,
        "attachment": {
            "id": attachment.id,
            "name": attachment.original_name,
            "mime_type": attachment.mime_type,
            "size_bytes": attachment.size_bytes,
            "kind": attachment.kind,
        },
    })


@app.route("/api/ai/conversations")
@require_login
def ai_conversations_api():
    return jsonify({
        "ok": True,
        "conversations": ai_repository.list_conversations(user_id=int(session.get("user_id"))),
    })


@app.route("/api/ai/conversations/<conversation_id>", methods=["PATCH", "DELETE"])
@require_login
def ai_conversation_api(conversation_id):
    conversation_id = normalize_client_id(conversation_id, "chat")
    user_id = int(session.get("user_id"))
    if request.method == "DELETE":
        ai_repository.delete_conversation(user_id=user_id, conversation_id=conversation_id)
        return jsonify({"ok": True})

    payload = request.get_json(silent=True) or {}
    title = payload.get("title") if "title" in payload else None
    pinned = bool(payload.get("pinned")) if "pinned" in payload else None
    ai_repository.update_conversation(
        user_id=user_id,
        conversation_id=conversation_id,
        title=title,
        pinned=pinned,
    )
    return jsonify({"ok": True})


@app.route("/api/ai/messages/<message_id>/feedback", methods=["POST"])
@require_login
def ai_message_feedback_api(message_id):
    payload = request.get_json(silent=True) or {}
    rating = str(payload.get("rating", "")).strip().lower()
    if rating not in {"up", "down"}:
        return jsonify({"ok": False, "error": "Невідома оцінка."}), 400
    saved = ai_repository.set_feedback(
        user_id=int(session.get("user_id")),
        message_id=normalize_client_id(message_id, "msg"),
        rating=rating,
    )
    if not saved:
        return jsonify({"ok": False, "error": "Повідомлення не знайдено."}), 404
    return jsonify({"ok": True})


@app.route("/api/tutor-chat", methods=["POST"])
@require_login
def tutor_chat_api():
    """Non-streaming fallback endpoint backed by the shared AI orchestrator."""
    if not onboarding_complete():
        return jsonify({"ok": False, "error": "Спочатку заверши налаштування профілю."}), 403

    payload = request.get_json(silent=True) or {}
    question = str(payload.get("question", "")).strip()
    lesson_context = str(payload.get("context", "")).lower() == "lesson"
    response_mode = normalize_tutor_response_mode(payload.get("response_mode"))

    max_chars = app.config["OPENAI_MAX_QUESTION_CHARS"]
    if not question:
        return jsonify({"ok": False, "error": "Напиши запитання для Easy."}), 400
    if len(question) > max_chars:
        return jsonify({"ok": False, "error": f"Скороти запитання до {max_chars} символів."}), 400

    lesson = None
    if lesson_context:
        lesson_id = normalize_lesson_id(payload.get("lesson_id") or session.get("current_lesson_id", 1))
        lesson = get_lesson_content(lesson_id)
        session["current_lesson_id"] = lesson_id

    user_id = int(session.get("user_id"))
    daily_limit = app.config["OPENAI_DAILY_LIMIT"]
    used_today = get_ai_usage_today(user_id)
    raw_fallback = get_easy_answer(question, lesson_context=lesson_context, lesson=lesson)
    fallback = shape_demo_tutor_answer(
        raw_fallback,
        response_mode,
        lesson_context=lesson_context,
        lesson=lesson,
    )
    ai_request = build_tutor_ai_request(
        payload,
        question=question,
        lesson_context=lesson_context,
        lesson=lesson,
        response_mode=response_mode,
        fallback=fallback,
    )

    if ai_orchestrator.enabled and used_today >= daily_limit:
        answer = "Денний AI-ліміт вичерпано. Продовжимо завтра, а зараз відкрий попередню відповідь або повтори урок."
        ai_orchestrator.prepare(ai_request)
        ai_repository.add_message(
            message_id=ai_request.assistant_message_id,
            conversation_id=ai_request.conversation_id,
            user_id=user_id,
            role="assistant",
            content=answer,
            provider_mode="limit",
        )
        mode = "limit"
        error = None
        response_id = None
    else:
        result = ai_orchestrator.complete(ai_request)
        answer = clean_tutor_answer_text(result.text)
        mode = result.mode
        error = result.error
        response_id = result.response_id
        if mode == "openai":
            increment_ai_usage(user_id)
            used_today += 1

    response = {
        "ok": True,
        "answer": answer,
        "mode": mode,
        "used": used_today,
        "limit": daily_limit,
        "response_mode": response_mode,
        "conversation_id": ai_request.conversation_id,
        "user_message_id": ai_request.user_message_id,
        "assistant_message_id": ai_request.assistant_message_id,
        "response_id": response_id,
        "attachments": [item.id for item in ai_request.attachments],
    }
    if app.debug and error:
        response["debug_error"] = error
    return jsonify(response)


@app.route("/api/tutor-chat/stream", methods=["POST"])
@require_login
def tutor_chat_stream_api():
    """SSE endpoint with native OpenAI Responses API deltas and demo fallback."""
    if not onboarding_complete():
        return jsonify({"ok": False, "error": "Спочатку заверши налаштування профілю."}), 403

    payload = request.get_json(silent=True) or {}
    question = str(payload.get("question", "")).strip()
    lesson_context = str(payload.get("context", "")).lower() == "lesson"
    response_mode = normalize_tutor_response_mode(payload.get("response_mode"))

    max_chars = app.config["OPENAI_MAX_QUESTION_CHARS"]
    if not question:
        return jsonify({"ok": False, "error": "Напиши запитання для Easy."}), 400
    if len(question) > max_chars:
        return jsonify({"ok": False, "error": f"Скороти запитання до {max_chars} символів."}), 400

    lesson = None
    if lesson_context:
        lesson_id = normalize_lesson_id(payload.get("lesson_id") or session.get("current_lesson_id", 1))
        lesson = get_lesson_content(lesson_id)
        session["current_lesson_id"] = lesson_id

    user_id = int(session.get("user_id"))
    daily_limit = app.config["OPENAI_DAILY_LIMIT"]
    used_today = get_ai_usage_today(user_id)
    raw_fallback = get_easy_answer(question, lesson_context=lesson_context, lesson=lesson)
    fallback = shape_demo_tutor_answer(
        raw_fallback,
        response_mode,
        lesson_context=lesson_context,
        lesson=lesson,
    )
    ai_request = build_tutor_ai_request(
        payload,
        question=question,
        lesson_context=lesson_context,
        lesson=lesson,
        response_mode=response_mode,
        fallback=fallback,
    )

    @stream_with_context
    def generate():
        nonlocal used_today
        yield tutor_sse_event("status", {"message": "Збираю навчальний контекст"})

        if ai_orchestrator.enabled and used_today >= daily_limit:
            answer_text = "Денний AI-ліміт вичерпано. Продовжимо завтра, а зараз відкрий попередню відповідь або повтори урок."
            ai_orchestrator.prepare(ai_request)
            ai_repository.add_message(
                message_id=ai_request.assistant_message_id,
                conversation_id=ai_request.conversation_id,
                user_id=user_id,
                role="assistant",
                content=answer_text,
                provider_mode="limit",
            )
            yield tutor_sse_event("meta", {
                "mode": "limit",
                "used": used_today,
                "limit": daily_limit,
                "response_mode": response_mode,
            })
            for chunk in tutor_stream_chunks(answer_text):
                yield tutor_sse_event("delta", {"text": chunk})
            yield tutor_sse_event("done", {
                "ok": True,
                "answer": answer_text,
                "mode": "limit",
                "used": used_today,
                "limit": daily_limit,
                "response_mode": response_mode,
                "conversation_id": ai_request.conversation_id,
                "user_message_id": ai_request.user_message_id,
                "assistant_message_id": ai_request.assistant_message_id,
            })
            return

        yield tutor_sse_event("status", {
            "message": "Аналізую фото й умову" if ai_request.attachments else "Будую зрозуміле пояснення"
        })
        final = None
        for event in ai_orchestrator.stream(ai_request):
            if event.type == "delta":
                yield tutor_sse_event("delta", {"text": event.data.get("text", "")})
            elif event.type == "fallback":
                yield tutor_sse_event("status", {"message": "Працюю у безпечному демо-режимі"})
                for chunk in tutor_stream_chunks(event.data.get("text", fallback)):
                    yield tutor_sse_event("delta", {"text": chunk})
            elif event.type == "done":
                final = event.data

        final = final or {"text": fallback, "mode": "demo"}
        mode = str(final.get("mode", "demo"))
        if mode == "openai":
            increment_ai_usage(user_id)
            used_today += 1
        yield tutor_sse_event("meta", {
            "mode": mode,
            "used": used_today,
            "limit": daily_limit,
            "response_mode": response_mode,
        })
        done_payload = {
            "ok": True,
            "answer": clean_tutor_answer_text(final.get("text", fallback)),
            "mode": mode,
            "used": used_today,
            "limit": daily_limit,
            "response_mode": response_mode,
            "conversation_id": ai_request.conversation_id,
            "user_message_id": ai_request.user_message_id,
            "assistant_message_id": ai_request.assistant_message_id,
            "response_id": final.get("response_id"),
            "attachments": [item.id for item in ai_request.attachments],
        }
        if app.debug and final.get("error"):
            done_payload["debug_error"] = final.get("error")
        yield tutor_sse_event("done", done_payload)

    response = Response(generate(), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache, no-transform"
    response.headers["X-Accel-Buffering"] = "no"
    response.headers["Connection"] = "keep-alive"
    return response



@app.route("/api/lesson-chat", methods=["POST"])
@require_login
def lesson_chat_api():
    """Return a contextual Easy answer without leaving the lesson page."""
    if not onboarding_complete():
        return jsonify({"ok": False, "error": "Спочатку заверши налаштування профілю."}), 403

    payload = request.get_json(silent=True) or request.form
    question = str(payload.get("question", "")).strip()
    lesson_id = normalize_lesson_id(payload.get("lesson_id") or session.get("current_lesson_id", 1))
    lesson = get_lesson_content(lesson_id)
    session["current_lesson_id"] = lesson_id

    max_chars = app.config["OPENAI_MAX_QUESTION_CHARS"]
    if not question:
        return jsonify({"ok": False, "error": "Напиши запитання для Easy."}), 400
    if len(question) > max_chars:
        return jsonify({"ok": False, "error": f"Скороти запитання до {max_chars} символів."}), 400

    user_id = session.get("user_id")
    daily_limit = app.config["OPENAI_DAILY_LIMIT"]
    used_today = get_ai_usage_today(user_id)

    if ai_service.enabled and used_today >= daily_limit:
        return jsonify({
            "ok": True,
            "answer": "Денний AI-ліміт вичерпано. Продовжимо завтра, а зараз можеш повторити матеріал уроку.",
            "mode": "limit",
            "used": used_today,
            "limit": daily_limit,
        })

    fallback = get_easy_answer(question, lesson_context=True, lesson=lesson)
    result = ai_service.answer(
        question=question,
        subject=session.get("subject", "НМТ"),
        lesson_title=lesson["title"],
        lesson_goal=lesson.get("goal", "зрозуміти тему"),
        fallback=fallback,
        lesson_context=True,
    )

    if result.mode == "openai":
        increment_ai_usage(user_id)
        used_today += 1

    return jsonify({
        "ok": True,
        "answer": result.text,
        "mode": result.mode,
        "used": used_today,
        "limit": daily_limit,
    })


@app.route("/library")
@require_login
def library():
    if not onboarding_complete():
        return redirect(url_for("goal"))

    subject_names = {
        "math": "📐 Математика",
        "ukrainian": "🇺🇦 Українська мова",
        "history": "📜 Історія України",
        "english": "🇬🇧 Англійська мова",
    }
    catalog_view = []
    for key, lessons in LESSON_CATALOG.items():
        if key == "none":
            continue
        completed = get_completed_lessons(key)
        catalog_view.append({
            "key": key,
            "name": subject_names.get(key, key),
            "lessons": lessons,
            "completed": completed,
            "progress": round((len(completed) / max(1, len(lessons))) * 100),
        })

    return render_template("library.html", **get_user_data(), catalog_view=catalog_view)


@app.route("/planner")
@require_login
def planner():
    if not onboarding_complete():
        return redirect(url_for("goal"))

    lessons = get_lessons_for_subject()
    completed = get_completed_lessons()
    plan_rows = []
    for index, item in enumerate(lessons, start=1):
        plan_rows.append({
            "week": index,
            "lesson": item,
            "status": "Завершено" if item["id"] in completed else ("Сьогодні" if item["id"] == get_next_unfinished_lesson_id() else "Заплановано"),
            "tasks": ["Теорія", "Приклади", "Smart-тест", "Повторення помилок"],
        })

    return render_template("planner.html", **get_user_data(), plan_rows=plan_rows)


@app.route("/mistakes")
@require_login
def mistakes():
    if not onboarding_complete():
        return redirect(url_for("goal"))

    conn = get_db_connection()
    rows = conn.execute(
        """SELECT question, user_answer, correct_answer, explanation, lesson_id, created_at
        FROM mistakes
        WHERE user_id = ? AND subject = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 100""",
        (session["user_id"], session.get("subject", "none")),
    ).fetchall()
    conn.close()

    mistakes_only = [
        {
            "question": row["question"],
            "user_answer": row["user_answer"] or "Ще не вибрано",
            "correct_answer": row["correct_answer"],
            "explanation": row["explanation"],
            "lesson_id": row["lesson_id"],
            "created_at": row["created_at"],
            "is_correct": False,
        }
        for row in rows
    ]
    return render_template("mistakes.html", **get_user_data(), mistakes=mistakes_only, review=mistakes_only)


@app.route("/profile")
@require_login
def profile():
    if not onboarding_complete():
        return redirect(url_for("goal"))

    return render_template(
        "profile.html",
        **get_user_data(),
        user_email=session.get("user_email"),
        completed_stats=get_completed_lesson_stats(),
        all_achievements=get_achievements(),
    )


@app.route("/settings", methods=["GET", "POST"])
@require_login
def settings():
    if request.method == "POST":
        goal_value = request.form.get("goal")
        subject_value = request.form.get("subject")
        time_value = request.form.get("time_left")

        if goal_value not in VALID_GOALS or subject_value not in VALID_SUBJECTS or time_value not in VALID_TIME_LEFT:
            abort(400, description="Невідоме значення налаштувань.")

        if goal_value:
            session["goal"] = goal_value
        if subject_value and subject_value != session.get("subject"):
            save_plan_to_db()
            session["subject"] = subject_value
            session["current_lesson_id"] = 1
            load_subject_progress_to_session(session["user_id"], subject_value)
        if time_value:
            session["time_left"] = time_value

        save_plan_to_db()
        flash("Налаштування оновлено.", "success")
        return redirect(url_for("settings"))

    return render_template("settings.html", **get_user_data())


@app.route("/beta-check")
@require_login
def beta_check():
    if not onboarding_complete():
        return redirect(url_for("goal"))

    checks = [
        {"icon": "✅", "title": "Онбординг", "desc": "Реєстрація, ціль, предмет і час працюють."},
        {"icon": "✅", "title": "Уроки", "desc": "Є теорія, приклади, тести й результат."},
        {"icon": "✅", "title": "Прогрес", "desc": "XP, серія, уроки та досягнення зберігаються."},
        {"icon": "✅", "title": "AI Викладач", "desc": "Готові Responses API, streaming, серверна пам’ять, фото та навчальний контекст."},
        {"icon": "✅", "title": "Публікація", "desc": "Збірка підготовлена до Railway: Gunicorn, health-check і постійна база даних."},
    ]
    return render_template("beta_check.html", **get_user_data(), checks=checks)


@app.route("/robots.txt")
def robots_txt():
    base_url = request.url_root.rstrip("/")
    content = f"User-agent: *\nAllow: /\n\nSitemap: {base_url}/sitemap.xml\n"
    return Response(content, mimetype="text/plain")


@app.route("/sitemap.xml")
def sitemap_xml():
    base_url = request.url_root.rstrip("/")
    content = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>{base_url}/</loc>
    <changefreq>weekly</changefreq>
    <priority>1.0</priority>
  </url>
</urlset>
"""
    return Response(content, mimetype="application/xml")




@app.route("/api/v1-beta/curriculum", methods=["GET", "POST"])
@require_login
def v1_beta_curriculum_api():
    try:
        uid=int(session["user_id"])
        if request.method=="GET":
            cid=request.args.get("id",type=int); data=learning_repository.curriculum_bundle(cid,uid) if cid else None
            return ({"ok":True,"curriculum":data} if data else ({"ok":False,"error":"not_found"},404))
        p=request.get_json(silent=True) or {}; data=learning_service.generate_curriculum(uid,str(p.get("subject") or session.get("subject") or "Математика"),str(p.get("goal") or session.get("goal") or "Підготовка до НМТ"),str(p.get("level") or "basic"),bool(p.get("force")))
        return {"ok":True,"curriculum":data,"version":"v1.0 Beta"}
    except Exception as exc:
        app.logger.exception("curriculum generation failed"); return {"ok":False,"error":str(exc)},500

@app.route("/api/v1-beta/topic/<int:topic_id>/lesson", methods=["GET","POST"])
@require_login
def v1_beta_lesson_api(topic_id):
    try:
        p=request.get_json(silent=True) or {}; data=learning_service.generate_lesson(int(session["user_id"]),topic_id,bool(p.get("force")))
        return {"ok":True,"lesson":data,"version":"v1.0 Beta"}
    except Exception as exc:
        app.logger.exception("lesson generation failed"); return {"ok":False,"error":str(exc)},500

@app.route("/api/v1-beta/topic/<int:topic_id>/quiz", methods=["GET","POST"])
@require_login
def v1_beta_quiz_api(topic_id):
    try:
        p=request.get_json(silent=True) or {}; data=learning_service.generate_quiz(int(session["user_id"]),topic_id,bool(p.get("force")))
        safe=dict(data); out=[]
        for item in safe.get("questions",[]):
            x=dict(item)
            for k in ("answer","correct_answer","solution_steps","rubric"): x.pop(k,None)
            out.append(x)
        safe["questions"]=out; return {"ok":True,"quiz":safe,"version":"v1.0 Beta"}
    except Exception as exc:
        app.logger.exception("quiz generation failed"); return {"ok":False,"error":str(exc)},500

@app.route("/api/v1-beta/quiz/<int:quiz_id>/grade", methods=["POST"])
@require_login
def v1_beta_grade_api(quiz_id):
    try:
        p=request.get_json(silent=True) or {}; answers=p.get("answers")
        if not isinstance(answers,(dict,list)): return {"ok":False,"error":"invalid_answers"},400
        return {"ok":True,"result":learning_service.grade_quiz(int(session["user_id"]),quiz_id,answers),"version":"v1.0 Beta"}
    except Exception as exc:
        app.logger.exception("grading failed"); return {"ok":False,"error":str(exc)},500

@app.route("/v1-beta")
@require_login
def v1_beta_hub():
    return render_template("v1_beta.html", **get_user_data(), version="v1.0 Beta")

if __name__ == "__main__":
    app.run(debug=app.config["DEBUG"])

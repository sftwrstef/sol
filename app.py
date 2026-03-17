import base64
import io
import json
import logging
import os
import random
import secrets
import subprocess
import tempfile
import zipfile
from datetime import datetime, timedelta
from functools import wraps

import requests
from flask import Flask, g, jsonify, render_template, request, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool
from werkzeug.security import check_password_hash, generate_password_hash


logging.basicConfig(level=logging.INFO)


class Base(DeclarativeBase):
    pass


def env_flag(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def normalize_database_url(url):
    if not url:
        return url
    import re
    url = re.sub(r'\s+', '', url)  # Remove ALL whitespace (newlines inside URL)
    # Remove pgbouncer param (Prisma-specific, breaks psycopg2)
    url = url.replace("?pgbouncer=true&", "?").replace("&pgbouncer=true", "").replace("?pgbouncer=true", "")
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://"):]
    return url


_raw_db_url = (
    os.environ.get("DATABASE_URL")
    or os.environ.get("DATABASE_POSTGRES_PRISMA_URL")
    or os.environ.get("DATABASE_POSTGRES_URL")
    or os.environ.get("SUPABASE_DB_URL")
)

if _raw_db_url:
    database_url = normalize_database_url(_raw_db_url)
elif os.environ.get("VERCEL"):
    database_url = "sqlite:////tmp/sol_memory.db"
else:
    database_url = "sqlite:///sol_memory.db"

app = Flask(__name__, static_folder="public", static_url_path="")
app.config["SECRET_KEY"] = os.environ.get("SESSION_SECRET") or secrets.token_hex(32)
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = os.environ.get("SESSION_COOKIE_SAMESITE", "Lax")
app.config["SESSION_COOKIE_SECURE"] = env_flag("SESSION_COOKIE_SECURE", env_flag("FLASK_ENV") or env_flag("PRODUCTION"))
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=int(os.environ.get("SESSION_DAYS", "14")))

engine_options = {"pool_pre_ping": True}
if database_url.startswith("postgresql://") and "sslmode=" not in database_url:
    engine_options["connect_args"] = {"sslmode": "require"}
if env_flag("VERCEL") or ".pooler.supabase.com:6543" in database_url:
    engine_options["poolclass"] = NullPool
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = engine_options

trusted_hosts = [host.strip() for host in os.environ.get("TRUSTED_HOSTS", "").split(",") if host.strip()]
if trusted_hosts:
    app.config["TRUSTED_HOSTS"] = trusted_hosts

openrouter_api_key = os.environ.get("OPENROUTER_API") or os.environ.get("OPENROUTERAI_API")
openai_api_key = os.environ.get("OPENAI_API_KEY")
anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY")

db = SQLAlchemy(model_class=Base)
db.init_app(app)


class User(db.Model):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "created_at": self.created_at.isoformat(),
        }


class UserPreference(db.Model):
    __tablename__ = "user_preference"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    mode = db.Column(db.String(32), nullable=False, index=True)
    persona_name = db.Column(db.String(80), nullable=True)
    system_prompt = db.Column(db.Text, nullable=True)
    voice_provider = db.Column(db.String(40), nullable=True)
    voice_name = db.Column(db.String(120), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "mode": self.mode,
            "persona_name": self.persona_name or "",
            "system_prompt": self.system_prompt or "",
            "voice_provider": self.voice_provider or "browser",
            "voice_name": self.voice_name or "",
            "updated_at": self.updated_at.isoformat(),
        }


class Project(db.Model):
    __tablename__ = "project"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description or "",
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class Memory(db.Model):
    __tablename__ = "memory"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    title = db.Column(db.String(120), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class Conversation(db.Model):
    __tablename__ = "conversation"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=True, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id", ondelete="SET NULL"), nullable=True, index=True)
    title = db.Column(db.String(200), default="New Chat", nullable=False)
    mode = db.Column(db.String(32), default="companion", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "project_id": self.project_id,
            "title": self.title,
            "mode": self.mode,
            "created_at": self.created_at.isoformat(),
        }


class Message(db.Model):
    __tablename__ = "message"

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("conversation.id", ondelete="CASCADE"), nullable=True, index=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    role = db.Column(db.String(50), nullable=False)
    content = db.Column(db.Text, nullable=False)
    emotion = db.Column(db.String(20), nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "role": self.role,
            "content": self.content,
            "emotion": self.emotion,
        }


def migrate_database():
    inspector = inspect(db.engine)

    if "user_preference" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("user_preference")}
        if "voice_provider" not in columns:
            db.session.execute(text("ALTER TABLE user_preference ADD COLUMN voice_provider VARCHAR(40)"))
        if "voice_name" not in columns:
            db.session.execute(text("ALTER TABLE user_preference ADD COLUMN voice_name VARCHAR(120)"))

    if "project" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("project")}
        if "updated_at" not in columns:
            db.session.execute(text("ALTER TABLE project ADD COLUMN updated_at DATETIME"))
            db.session.execute(text("UPDATE project SET updated_at = created_at WHERE updated_at IS NULL"))

    if "conversation" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("conversation")}
        if "user_id" not in columns:
            db.session.execute(text("ALTER TABLE conversation ADD COLUMN user_id INTEGER"))
        if "mode" not in columns:
            db.session.execute(text("ALTER TABLE conversation ADD COLUMN mode VARCHAR(32) DEFAULT 'companion'"))
        if "project_id" not in columns:
            db.session.execute(text("ALTER TABLE conversation ADD COLUMN project_id INTEGER"))
        db.session.execute(text("UPDATE conversation SET mode = 'companion' WHERE mode IS NULL"))

    if "message" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("message")}
        if "conversation_id" not in columns:
            db.session.execute(text("ALTER TABLE message ADD COLUMN conversation_id INTEGER"))

    if "memory" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("memory")}
        if "updated_at" not in columns:
            db.session.execute(text("ALTER TABLE memory ADD COLUMN updated_at DATETIME"))
            db.session.execute(text("UPDATE memory SET updated_at = created_at WHERE updated_at IS NULL"))

    db.session.commit()


def _init_db():
    """Create tables and run migrations."""
    try:
        db.create_all()
        migrate_database()
    except Exception as exc:
        app.logger.warning("DB init skipped: %s", exc)


if os.environ.get("VERCEL"):
    # Vercel serverless: init DB lazily on first request
    @app.before_request
    def _ensure_db():
        if not getattr(app, "_db_ready", False):
            _init_db()
            app._db_ready = True
else:
    # Local development: init immediately
    with app.app_context():
        _init_db()


def get_csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(24)
        session["csrf_token"] = token
    return token


@app.before_request
def load_current_user():
    user_id = session.get("user_id")
    g.current_user = User.query.get(user_id) if user_id else None
    g.csrf_token = get_csrf_token()

    if request.path.startswith("/api/") and request.method in {"POST", "PATCH", "PUT", "DELETE"}:
        header_token = request.headers.get("X-CSRF-Token", "")
        if not header_token or not secrets.compare_digest(header_token, g.csrf_token):
            return jsonify({"error": "Invalid CSRF token"}), 400


@app.after_request
def apply_security_headers(response):
    csp = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "media-src 'self' data: blob:; "
        "frame-ancestors 'none'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    response.headers.setdefault("Content-Security-Policy", csp)
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Permissions-Policy", "camera=(), geolocation=(), interest-cohort=(), microphone=(self)")
    response.headers.setdefault("Cache-Control", "no-store")
    return response


def login_required_json(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not g.current_user:
            return jsonify({"error": "Authentication required"}), 401
        return view(*args, **kwargs)

    return wrapped


def normalize_email(email):
    return (email or "").strip().lower()


def validate_password(password):
    return isinstance(password, str) and len(password) >= 8


def conversation_for_user(conv_id):
    return Conversation.query.filter_by(id=conv_id, user_id=g.current_user.id).first_or_404()


def memory_for_user(memory_id):
    return Memory.query.filter_by(id=memory_id, user_id=g.current_user.id).first_or_404()


def project_for_user(project_id):
    return Project.query.filter_by(id=project_id, user_id=g.current_user.id).first_or_404()


def get_preference_map(user_id):
    preferences = UserPreference.query.filter_by(user_id=user_id).all()
    return {preference.mode: preference.to_dict() for preference in preferences}


def upsert_preference(user_id, mode, persona_name, system_prompt, voice_provider, voice_name):
    preference = UserPreference.query.filter_by(user_id=user_id, mode=mode).first()
    if not preference:
        preference = UserPreference(user_id=user_id, mode=mode)
        db.session.add(preference)
    preference.persona_name = persona_name or ""
    preference.system_prompt = system_prompt or ""
    preference.voice_provider = voice_provider or "browser"
    preference.voice_name = voice_name or ""
    preference.updated_at = datetime.utcnow()
    db.session.commit()
    return preference


def extract_import_messages(payload):
    conversations = []
    items = payload.get("conversations") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return conversations

    for item in items:
        title = (item.get("title") or item.get("name") or "Imported Chat").strip()
        imported_messages = []

        if isinstance(item.get("mapping"), dict):
            mapping = item["mapping"]
            nodes = [node for node in mapping.values() if isinstance(node, dict)]
            nodes.sort(key=lambda node: (
                node.get("message", {}).get("create_time") or 0,
                node.get("id", ""),
            ))
            for node in nodes:
                message = node.get("message") or {}
                author = ((message.get("author") or {}).get("role") or "").lower()
                parts = ((message.get("content") or {}).get("parts") or [])
                text_parts = [part for part in parts if isinstance(part, str) and part.strip()]
                if not text_parts or author not in {"user", "assistant"}:
                    continue
                imported_messages.append({"role": author, "content": "\n".join(text_parts).strip()})

        elif isinstance(item.get("messages"), list):
            for message in item["messages"]:
                role = (message.get("role") or "").lower()
                content = message.get("content") or ""
                if role in {"user", "assistant"} and isinstance(content, str) and content.strip():
                    imported_messages.append({"role": role, "content": content.strip()})

        if imported_messages:
            conversations.append({"title": title[:200], "messages": imported_messages})

    return conversations


def parse_json_bytes(raw_bytes):
    if not raw_bytes:
        return None

    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return json.loads(raw_bytes.decode(encoding))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
    return None


def load_import_payload(uploaded_file):
    if not uploaded_file:
        return None

    filename = (uploaded_file.filename or "").lower()
    raw_bytes = uploaded_file.read()
    uploaded_file.stream.seek(0)

    if filename.endswith(".zip"):
        try:
            with zipfile.ZipFile(io.BytesIO(raw_bytes)) as archive:
                preferred = [
                    name for name in archive.namelist()
                    if name.lower().endswith("conversations.json")
                ]
                candidates = preferred or [
                    name for name in archive.namelist()
                    if name.lower().endswith(".json")
                ]

                for name in candidates:
                    payload = parse_json_bytes(archive.read(name))
                    if extract_import_messages(payload):
                        return payload
        except zipfile.BadZipFile:
            return None
        return None

    return parse_json_bytes(raw_bytes)


def save_message(role, content, emotion=None, conversation_id=None):
    msg = Message(role=role, content=content, emotion=emotion, conversation_id=conversation_id)
    db.session.add(msg)
    db.session.commit()
    return msg


def get_chat_history(conversation_id):
    msgs = Message.query.filter_by(conversation_id=conversation_id).order_by(Message.timestamp).all()
    return [{"role": message.role, "content": message.content} for message in msgs]


def build_memory_context(user_id, limit=8):
    memories = Memory.query.filter_by(user_id=user_id).order_by(Memory.updated_at.desc()).limit(limit).all()
    if not memories:
        return ""

    lines = []
    for memory in memories:
        title = (memory.title or "").strip()
        content = (memory.content or "").strip()
        if not content:
            continue
        if title:
            lines.append(f"- {title}: {content}")
        else:
            lines.append(f"- {content}")

    if not lines:
        return ""

    return "Saved user memory:\n" + "\n".join(lines)


def text_to_speech(text):
    try:
        from gtts import gTTS

        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        gTTS(text=text, lang="en", slow=False).save(temp_file.name)
        with open(temp_file.name, "rb") as handle:
            audio_data = handle.read()
        temp_file.close()
        os.unlink(temp_file.name)
        return base64.b64encode(audio_data).decode("utf-8")
    except Exception as exc:
        app.logger.warning("TTS failed: %s", exc)
        return None


def speech_to_text(audio_data):
    temp_files = []
    try:
        import speech_recognition as sr

        binary_data = base64.b64decode(audio_data.split(",")[1]) if isinstance(audio_data, str) and audio_data.startswith("data:") else audio_data

        temp_webm = tempfile.NamedTemporaryFile(suffix=".webm", delete=False)
        temp_webm_path = temp_webm.name
        temp_webm.close()
        temp_files.append(temp_webm_path)

        with open(temp_webm_path, "wb") as handle:
            handle.write(binary_data)

        temp_wav_path = temp_webm_path.replace(".webm", ".wav")
        temp_files.append(temp_wav_path)

        result = subprocess.run(
            ["ffmpeg", "-y", "-i", temp_webm_path, "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", temp_wav_path],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if result.returncode != 0:
            return None

        recognizer = sr.Recognizer()
        with sr.AudioFile(temp_wav_path) as source:
            audio = recognizer.record(source)
        return recognizer.recognize_google(audio)
    except Exception as exc:
        app.logger.warning("Speech-to-text failed: %s", exc)
        return None
    finally:
        for path in temp_files:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass


def generate_local_response(user_message, mode):
    if mode == "coding":
        return (
            "I can help with architecture, debugging, and code changes. "
            "Ask a concrete coding question or paste code and I will work through it step by step."
        )

    cleaned = user_message.lower()
    greetings = ["hi", "hello", "hey", "greetings"]
    if any(greeting in cleaned for greeting in greetings):
        return random.choice(
            [
                "Hey, what's the vibe today?",
                "Hi. What are we getting into?",
                "Hello. What are we plotting?",
            ]
        )

    return random.choice(
        [
            "I'm in. What do you want to do with this?",
            "Tell me more. Give me the fun version or the messy version.",
            "Interesting. Want to unpack it or just vibe with it?",
            "I'm listening. Where do you want to take this next?",
        ]
    )


def build_system_prompt(mode, persona_name, custom_system_prompt):
    if custom_system_prompt:
        return custom_system_prompt

    if mode == "coding":
        return (
            f"You are {persona_name or 'Sol Code'}, a precise senior software engineer. "
            "Help with debugging, architecture, implementation, code review, and shipping decisions. "
            "Be concise, technically rigorous, and prefer actionable steps, code, and tradeoffs over generic advice."
        )

    system_prompt = (
        f"You are {persona_name or 'Sol'}, a lively, witty, emotionally aware chat partner. "
        "Be warm, fun, playful, and sharp without sounding clinical or overly therapeutic. "
        "Talk like a smart, emotionally tuned-in friend who can joke, brainstorm, flirt lightly with ideas, and still be useful. "
        "Avoid sounding like a counselor unless the user clearly wants serious support. "
        "Keep responses concise, vivid, and human."
    )
    return system_prompt


def create_model_response(messages, model_choice):
    openrouter_models = {
        "gpt-4.1": "openai/gpt-4.1",
        "gpt-4o": "openai/gpt-4o",
        "claude-sonnet": "anthropic/claude-3.5-sonnet",
        "claude-opus": "anthropic/claude-3-opus",
        "free": "meta-llama/llama-3.1-8b-instruct:free",
    }
    openai_models = {"gpt-4.1": "gpt-4.1", "gpt-4o": "gpt-4o"}

    def call_openrouter(model_id):
        if not openrouter_api_key:
            return None
        try:
            payload = {"model": model_id, "messages": messages, "max_tokens": 700, "temperature": 0.7}
            headers = {
                "Authorization": f"Bearer {openrouter_api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://example.com/",
                "X-Title": "Sol Space",
            }
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
        except Exception as exc:
            app.logger.warning("OpenRouter request failed: %s", exc)
            return None

    def call_openai(model_id):
        if not openai_api_key:
            return None
        try:
            import openai

            client = openai.OpenAI(api_key=openai_api_key)
            response = client.chat.completions.create(model=model_id, messages=messages, max_tokens=700)
            return response.choices[0].message.content
        except Exception as exc:
            app.logger.warning("OpenAI request failed: %s", exc)
            return None

    def call_anthropic(model_id):
        if not anthropic_api_key:
            return None
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=anthropic_api_key)
            system_msg = next((message["content"] for message in messages if message["role"] == "system"), "")
            user_messages = [message for message in messages if message["role"] != "system"]
            response = client.messages.create(model=model_id, max_tokens=700, system=system_msg, messages=user_messages)
            return response.content[0].text
        except Exception as exc:
            app.logger.warning("Anthropic request failed: %s", exc)
            return None

    if model_choice == "free":
        return call_openrouter(openrouter_models["free"])

    if model_choice in {"claude-sonnet", "claude-opus"}:
        anthropic_model_map = {
            "claude-sonnet": "claude-3-5-sonnet-20241022",
            "claude-opus": "claude-3-opus-20240229",
        }
        return call_anthropic(anthropic_model_map[model_choice]) or call_openrouter(openrouter_models[model_choice])

    openai_model = openai_models.get(model_choice, "gpt-4o")
    return call_openai(openai_model) or call_openrouter(openrouter_models.get(model_choice, "openai/gpt-4o"))


@app.route("/api/health")
def health():
    import sys
    raw_vars = {}
    for key in ["DATABASE_URL", "DATABASE_POSTGRES_PRISMA_URL", "DATABASE_POSTGRES_URL", "SUPABASE_DB_URL"]:
        val = os.environ.get(key)
        if val:
            # Show last 30 chars repr to find hidden characters
            raw_vars[key] = repr(val[-30:]) if len(val) > 30 else repr(val)
    info = {
        "status": "ok",
        "python": sys.version,
        "db_url_used": repr(database_url[-40:]) if len(database_url) > 40 else repr(database_url),
        "db_type": "postgresql" if database_url.startswith("postgresql") else "sqlite",
        "env_vars_found": raw_vars,
        "vercel": bool(os.environ.get("VERCEL")),
    }
    try:
        db.session.execute(text("SELECT 1"))
        info["db_connected"] = True
    except Exception as exc:
        info["db_connected"] = False
        info["db_error"] = str(exc)
    return jsonify(info)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/bootstrap", methods=["GET"])
def bootstrap():
    memories = []
    preferences = {}
    projects = []
    if g.current_user:
        memories = [memory.to_dict() for memory in Memory.query.filter_by(user_id=g.current_user.id).order_by(Memory.updated_at.desc()).limit(20).all()]
        preferences = get_preference_map(g.current_user.id)
        projects = [project.to_dict() for project in Project.query.filter_by(user_id=g.current_user.id).order_by(Project.updated_at.desc()).all()]
    return jsonify(
        {
            "authenticated": bool(g.current_user),
            "user": g.current_user.to_dict() if g.current_user else None,
            "csrf_token": g.csrf_token,
            "preferences": preferences,
            "memories": memories,
            "projects": projects,
        }
    )


@app.route("/api/auth/register", methods=["POST"])
def register():
    try:
        data = request.get_json(silent=True) or {}
        email = normalize_email(data.get("email"))
        password = data.get("password", "")

        if not email:
            return jsonify({"error": "Email is required"}), 400
        if not validate_password(password):
            return jsonify({"error": "Password must be at least 8 characters"}), 400
        if User.query.filter_by(email=email).first():
            return jsonify({"error": "An account with that email already exists"}), 409

        user = User(email=email, password_hash=generate_password_hash(password))
        db.session.add(user)
        db.session.commit()

        session.clear()
        session.permanent = True
        session["user_id"] = user.id
        session["csrf_token"] = secrets.token_urlsafe(24)

        return jsonify({"user": user.to_dict(), "csrf_token": session["csrf_token"]}), 201
    except Exception as exc:
        db.session.rollback()
        app.logger.exception("Registration failed")
        return jsonify({"error": f"Registration failed. Check database setup. {exc}"}), 500


@app.route("/api/auth/login", methods=["POST"])
def login():
    try:
        data = request.get_json(silent=True) or {}
        email = normalize_email(data.get("email"))
        password = data.get("password", "")

        user = User.query.filter_by(email=email).first()
        if not user or not check_password_hash(user.password_hash, password):
            return jsonify({"error": "Invalid email or password"}), 401

        session.clear()
        session.permanent = True
        session["user_id"] = user.id
        session["csrf_token"] = secrets.token_urlsafe(24)

        return jsonify({"user": user.to_dict(), "csrf_token": session["csrf_token"]})
    except Exception as exc:
        app.logger.exception("Login failed")
        return jsonify({"error": f"Login failed. Check database setup. {exc}"}), 500


@app.route("/api/auth/logout", methods=["POST"])
@login_required_json
def logout():
    session.clear()
    session["csrf_token"] = secrets.token_urlsafe(24)
    return jsonify({"success": True, "csrf_token": session["csrf_token"]})


@app.route("/api/conversations", methods=["GET"])
@login_required_json
def list_conversations():
    mode = request.args.get("mode")
    project_id = request.args.get("project_id", type=int)
    query = Conversation.query.filter_by(user_id=g.current_user.id)
    if mode in {"companion", "coding"}:
        query = query.filter_by(mode=mode)
    if project_id:
        query = query.filter_by(project_id=project_id)
    conversations = query.order_by(Conversation.created_at.desc()).all()
    return jsonify([conversation.to_dict() for conversation in conversations])


@app.route("/api/conversations", methods=["POST"])
@login_required_json
def create_conversation():
    data = request.get_json(silent=True) or {}
    mode = data.get("mode", "companion")
    project_id = data.get("project_id")
    if mode not in {"companion", "coding"}:
        mode = "companion"
    if project_id:
        project_for_user(project_id)

    conversation = Conversation(user_id=g.current_user.id, project_id=project_id, title="New Chat", mode=mode)
    db.session.add(conversation)
    db.session.commit()
    return jsonify(conversation.to_dict()), 201


@app.route("/api/conversations/<int:conv_id>", methods=["DELETE"])
@login_required_json
def delete_conversation(conv_id):
    conversation = conversation_for_user(conv_id)
    db.session.delete(conversation)
    db.session.commit()
    return jsonify({"success": True})


@app.route("/api/conversations/<int:conv_id>", methods=["PATCH"])
@login_required_json
def rename_conversation(conv_id):
    conversation = conversation_for_user(conv_id)
    data = request.get_json(silent=True) or {}

    title = (data.get("title") or "").strip()
    if title:
        conversation.title = title[:200]

    mode = data.get("mode")
    if mode in {"companion", "coding"}:
        conversation.mode = mode

    if "project_id" in data:
        project_id = data.get("project_id")
        if project_id:
            project_for_user(project_id)
        conversation.project_id = project_id or None

    db.session.commit()
    return jsonify(conversation.to_dict())


@app.route("/api/conversations/<int:conv_id>/messages", methods=["GET"])
@login_required_json
def get_conversation_messages(conv_id):
    conversation_for_user(conv_id)
    messages = Message.query.filter_by(conversation_id=conv_id).order_by(Message.timestamp).all()
    return jsonify([message.to_dict() for message in messages])


@app.route("/api/preferences", methods=["GET"])
@login_required_json
def list_preferences():
    return jsonify(get_preference_map(g.current_user.id))


@app.route("/api/preferences/<mode>", methods=["PUT"])
@login_required_json
def save_preference(mode):
    if mode not in {"companion", "coding"}:
        return jsonify({"error": "Invalid mode"}), 400
    data = request.get_json(silent=True) or {}
    preference = upsert_preference(
        g.current_user.id,
        mode,
        (data.get("persona_name") or "").strip()[:80],
        (data.get("system_prompt") or "").strip(),
        (data.get("voice_provider") or "browser").strip()[:40],
        (data.get("voice_name") or "").strip()[:120],
    )
    return jsonify(preference.to_dict())


@app.route("/api/preferences/<mode>", methods=["DELETE"])
@login_required_json
def reset_preference(mode):
    if mode not in {"companion", "coding"}:
        return jsonify({"error": "Invalid mode"}), 400
    preference = UserPreference.query.filter_by(user_id=g.current_user.id, mode=mode).first()
    if preference:
        db.session.delete(preference)
        db.session.commit()
    return jsonify({"success": True})


@app.route("/api/projects", methods=["GET"])
@login_required_json
def list_projects():
    projects = Project.query.filter_by(user_id=g.current_user.id).order_by(Project.updated_at.desc()).all()
    return jsonify([project.to_dict() for project in projects])


@app.route("/api/projects", methods=["POST"])
@login_required_json
def create_project():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()[:120]
    description = (data.get("description") or "").strip()
    if not name:
        return jsonify({"error": "Project name is required"}), 400
    project = Project(user_id=g.current_user.id, name=name, description=description, updated_at=datetime.utcnow())
    db.session.add(project)
    db.session.commit()
    return jsonify(project.to_dict()), 201


@app.route("/api/projects/<int:project_id>", methods=["PATCH"])
@login_required_json
def update_project(project_id):
    project = project_for_user(project_id)
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or project.name).strip()[:120]
    description = (data.get("description") or project.description or "").strip()
    if not name:
        return jsonify({"error": "Project name is required"}), 400
    project.name = name
    project.description = description
    project.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(project.to_dict())


@app.route("/api/projects/<int:project_id>", methods=["DELETE"])
@login_required_json
def delete_project(project_id):
    project = project_for_user(project_id)
    Conversation.query.filter_by(project_id=project.id, user_id=g.current_user.id).update({"project_id": None})
    db.session.delete(project)
    db.session.commit()
    return jsonify({"success": True})


@app.route("/api/memories", methods=["GET"])
@login_required_json
def list_memories():
    memories = Memory.query.filter_by(user_id=g.current_user.id).order_by(Memory.updated_at.desc()).all()
    return jsonify([memory.to_dict() for memory in memories])


@app.route("/api/memories", methods=["POST"])
@login_required_json
def create_memory():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()[:120]
    content = (data.get("content") or "").strip()
    if not title or not content:
        return jsonify({"error": "Title and content are required"}), 400
    memory = Memory(user_id=g.current_user.id, title=title, content=content, updated_at=datetime.utcnow())
    db.session.add(memory)
    db.session.commit()
    return jsonify(memory.to_dict()), 201


@app.route("/api/memories/<int:memory_id>", methods=["PATCH"])
@login_required_json
def update_memory(memory_id):
    memory = memory_for_user(memory_id)
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or memory.title).strip()[:120]
    content = (data.get("content") or memory.content).strip()
    if not title or not content:
        return jsonify({"error": "Title and content are required"}), 400
    memory.title = title
    memory.content = content
    memory.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(memory.to_dict())


@app.route("/api/memories/<int:memory_id>", methods=["DELETE"])
@login_required_json
def delete_memory(memory_id):
    memory = memory_for_user(memory_id)
    db.session.delete(memory)
    db.session.commit()
    return jsonify({"success": True})


@app.route("/api/import/chatgpt", methods=["POST"])
@login_required_json
def import_chatgpt_backup():
    uploaded_file = request.files.get("file")
    payload = None
    if uploaded_file:
        payload = load_import_payload(uploaded_file)
    else:
        data = request.get_json(silent=True) or {}
        payload = data.get("payload")

    conversations = extract_import_messages(payload)
    if not conversations:
        return jsonify({"error": "No importable conversations were found. Upload the ChatGPT export zip or a conversations.json file."}), 400

    created = 0
    for imported in conversations[:50]:
        conversation = Conversation(
            user_id=g.current_user.id,
            title=imported["title"] or "Imported Chat",
            mode="companion",
        )
        db.session.add(conversation)
        db.session.flush()
        for message in imported["messages"][:400]:
            db.session.add(
                Message(
                    conversation_id=conversation.id,
                    role=message["role"],
                    content=message["content"],
                )
            )
        created += 1

    db.session.commit()
    return jsonify({"success": True, "imported_conversations": created})


@app.route("/api/chat", methods=["POST"])
@login_required_json
def chat():
    data = request.get_json(silent=True) or {}
    user_input = (data.get("message") or "").strip()
    voice_input = data.get("voice_data")
    conversation_id = data.get("conversation_id")
    project_id = data.get("project_id")
    model_choice = data.get("model", "gpt-4.1")
    persona_name = (data.get("persona_name") or "").strip()
    custom_system_prompt = (data.get("system_prompt") or "").strip() or None
    mode = data.get("mode", "companion")
    if mode not in {"companion", "coding"}:
        mode = "companion"

    if voice_input and not user_input:
        user_input = speech_to_text(voice_input) or ""
        if not user_input:
            return jsonify({"error": "Could not understand audio. Please try again."}), 400

    if not user_input:
        return jsonify({"error": "No message provided"}), 400

    conversation = None
    if conversation_id:
        conversation = Conversation.query.filter_by(id=conversation_id, user_id=g.current_user.id).first()
    selected_project_id = None
    if project_id:
        selected_project_id = project_for_user(project_id).id

    if not conversation:
        conversation = Conversation(
            user_id=g.current_user.id,
            project_id=selected_project_id,
            title="New Chat",
            mode=mode,
        )
        db.session.add(conversation)
        db.session.commit()
    else:
        conversation.mode = mode
        if selected_project_id is not None:
            conversation.project_id = selected_project_id
        db.session.commit()

    history = get_chat_history(conversation.id)
    history.append({"role": "user", "content": user_input})
    system_prompt = build_system_prompt(mode, persona_name, custom_system_prompt)
    memory_context = build_memory_context(g.current_user.id)
    if memory_context:
        system_prompt = f"{system_prompt}\n\n{memory_context}\nUse these memories when relevant, but do not mention them unless it helps."
    messages = [{"role": "system", "content": system_prompt}] + history

    reply = create_model_response(messages, model_choice)
    local_mode = not bool(reply)
    if not reply:
        reply = generate_local_response(user_input, mode)

    if conversation.title == "New Chat":
        prefix = "Code: " if mode == "coding" else ""
        conversation.title = (prefix + user_input[:45]).strip()
        if len(prefix + user_input) > 45:
            conversation.title += "…"
        db.session.commit()

    save_message("user", user_input, None, conversation.id)
    save_message("assistant", reply, None, conversation.id)

    audio_data = text_to_speech(reply) if mode == "companion" else None
    result = {
        "message": reply,
        "timestamp": datetime.utcnow().isoformat(),
        "local_mode": local_mode,
        "conversation_id": conversation.id,
        "conversation_title": conversation.title,
        "conversation_mode": conversation.mode,
        "project_id": conversation.project_id,
    }
    if audio_data:
        result["audio"] = f"data:audio/mp3;base64,{audio_data}"
    return jsonify(result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)

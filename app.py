import base64
import logging
import os
import random
import secrets
import subprocess
import tempfile
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
    url = url.strip().replace("\\n", "").replace("\n", "").replace("\r", "")
    # Remove pgbouncer param (Prisma-specific, breaks psycopg2)
    url = url.replace("?pgbouncer=true&", "?").replace("&pgbouncer=true", "").replace("?pgbouncer=true", "")
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://"):]
    return url


_raw_db_url = (
    os.environ.get("DATABASE_URL")
    or os.environ.get("DATABASE_POSTGRES_URL")
    or os.environ.get("DATABASE_POSTGRES_PRISMA_URL")
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
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024
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


class Conversation(db.Model):
    __tablename__ = "conversation"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=True, index=True)
    title = db.Column(db.String(200), default="New Chat", nullable=False)
    mode = db.Column(db.String(32), default="companion", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
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

    if "conversation" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("conversation")}
        if "user_id" not in columns:
            db.session.execute(text("ALTER TABLE conversation ADD COLUMN user_id INTEGER"))
        if "mode" not in columns:
            db.session.execute(text("ALTER TABLE conversation ADD COLUMN mode VARCHAR(32) DEFAULT 'companion'"))
        db.session.execute(text("UPDATE conversation SET mode = 'companion' WHERE mode IS NULL"))

    if "message" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("message")}
        if "conversation_id" not in columns:
            db.session.execute(text("ALTER TABLE message ADD COLUMN conversation_id INTEGER"))

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


def save_message(role, content, emotion=None, conversation_id=None):
    msg = Message(role=role, content=content, emotion=emotion, conversation_id=conversation_id)
    db.session.add(msg)
    db.session.commit()
    return msg


def get_chat_history(conversation_id):
    msgs = Message.query.filter_by(conversation_id=conversation_id).order_by(Message.timestamp).all()
    return [{"role": message.role, "content": message.content} for message in msgs]

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
                "Hey, I'm here. How are you doing?",
                "Hello! What's on your mind today?",
                "Hi there. I'm listening.",
            ]
        )

    return random.choice(
        [
            "I'm here with you. What would you like to explore?",
            "Tell me more. I'm listening.",
            "That's interesting. How are you feeling about it?",
            "I appreciate you sharing that. What matters most to you right now?",
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
        f"You are {persona_name or 'Sol'}, a warm and emotionally intelligent AI companion. "
        "You help people feel heard, safe, and understood. "
        "Be conversational, compassionate, and genuine. "
        "When someone shares something difficult, validate it before offering thoughts. "
        "Keep responses concise but meaningful."
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
    return jsonify(
        {
            "authenticated": bool(g.current_user),
            "user": g.current_user.to_dict() if g.current_user else None,
            "csrf_token": g.csrf_token,
        }
    )


@app.route("/api/auth/register", methods=["POST"])
def register():
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


@app.route("/api/auth/login", methods=["POST"])
def login():
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
    query = Conversation.query.filter_by(user_id=g.current_user.id)
    if mode in {"companion", "coding"}:
        query = query.filter_by(mode=mode)
    conversations = query.order_by(Conversation.created_at.desc()).all()
    return jsonify([conversation.to_dict() for conversation in conversations])


@app.route("/api/conversations", methods=["POST"])
@login_required_json
def create_conversation():
    data = request.get_json(silent=True) or {}
    mode = data.get("mode", "companion")
    if mode not in {"companion", "coding"}:
        mode = "companion"

    conversation = Conversation(user_id=g.current_user.id, title="New Chat", mode=mode)
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

    db.session.commit()
    return jsonify(conversation.to_dict())


@app.route("/api/conversations/<int:conv_id>/messages", methods=["GET"])
@login_required_json
def get_conversation_messages(conv_id):
    conversation_for_user(conv_id)
    messages = Message.query.filter_by(conversation_id=conv_id).order_by(Message.timestamp).all()
    return jsonify([message.to_dict() for message in messages])


@app.route("/api/chat", methods=["POST"])
@login_required_json
def chat():
    data = request.get_json(silent=True) or {}
    user_input = (data.get("message") or "").strip()
    voice_input = data.get("voice_data")
    conversation_id = data.get("conversation_id")
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

    if not conversation:
        conversation = Conversation(user_id=g.current_user.id, title="New Chat", mode=mode)
        db.session.add(conversation)
        db.session.commit()
    else:
        conversation.mode = mode
        db.session.commit()

    history = get_chat_history(conversation.id)
    history.append({"role": "user", "content": user_input})
    system_prompt = build_system_prompt(mode, persona_name, custom_system_prompt)
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
    }
    if audio_data:
        result["audio"] = f"data:audio/mp3;base64,{audio_data}"
    return jsonify(result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)

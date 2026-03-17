import os
import requests
import logging
import random
import re
import json
import base64
import tempfile
import io
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
import openai
from gtts import gTTS
import speech_recognition as sr
import pyttsx3
import text2emotion as te

logging.basicConfig(level=logging.DEBUG)

class Base(DeclarativeBase):
    pass

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "sol_space_secret")

openrouter_api_key = os.environ.get("OPENROUTER_API") or os.environ.get("OPENROUTERAI_API")
openai_api_key = os.environ.get("OPENAI_API_KEY")
anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY")

app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///sol_memory.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(model_class=Base)
db.init_app(app)

# ─── Models ─────────────────────────────────────────────────────────
class Conversation(db.Model):
    __tablename__ = 'conversation'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), default='New Chat')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {'id': self.id, 'title': self.title, 'created_at': self.created_at.isoformat()}

class Message(db.Model):
    __tablename__ = 'message'
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversation.id', ondelete='CASCADE'), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    role = db.Column(db.String(50), nullable=False)
    content = db.Column(db.Text, nullable=False)
    emotion = db.Column(db.String(20), nullable=True)
    audio_file = db.Column(db.Text, nullable=True)

    def to_dict(self):
        return {
            'id': self.id, 'timestamp': self.timestamp.isoformat(),
            'role': self.role, 'content': self.content,
            'emotion': self.emotion, 'has_audio': bool(self.audio_file)
        }

with app.app_context():
    db.create_all()
    # Add conversation_id column to existing message table if not present
    try:
        db.session.execute(db.text(
            "ALTER TABLE message ADD COLUMN IF NOT EXISTS conversation_id INTEGER REFERENCES conversation(id) ON DELETE CASCADE"
        ))
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        app.logger.debug(f"Migration note: {e}")

# ─── Helpers ─────────────────────────────────────────────────────────
def save_message(role, content, emotion=None, conversation_id=None):
    try:
        msg = Message(role=role, content=content, emotion=emotion, conversation_id=conversation_id)
        db.session.add(msg)
        db.session.commit()
        return msg
    except Exception as e:
        app.logger.error(f"Error saving message: {e}")
        db.session.rollback()
        return None

def get_chat_history(conversation_id):
    try:
        msgs = Message.query.filter_by(conversation_id=conversation_id).order_by(Message.timestamp).all()
        return [{"role": m.role, "content": m.content} for m in msgs]
    except Exception as e:
        app.logger.error(f"Error retrieving conversation: {e}")
        return []

def detect_emotion(text):
    try:
        emotions = te.get_emotion(text)
        if not emotions:
            return "neutral"
        dominant = max(emotions.items(), key=lambda x: x[1])
        emotion_map = {"Happy": "happy", "Sad": "sad", "Angry": "angry", "Fear": "fearful", "Surprise": "surprised"}
        return emotion_map.get(dominant[0], "neutral") if dominant[1] > 0 else "neutral"
    except Exception as e:
        app.logger.error(f"Emotion detection error: {e}")
        return "neutral"

def text_to_speech(text):
    try:
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')
        tts = gTTS(text=text, lang='en', slow=False)
        tts.save(temp_file.name)
        with open(temp_file.name, 'rb') as f:
            audio_data = f.read()
        temp_file.close()
        os.unlink(temp_file.name)
        return base64.b64encode(audio_data).decode('utf-8')
    except Exception as e:
        app.logger.error(f"TTS error: {e}")
        return None

def speech_to_text(audio_data):
    temp_files = []
    try:
        if isinstance(audio_data, str) and audio_data.startswith('data:'):
            binary_data = base64.b64decode(audio_data.split(',')[1])
        else:
            binary_data = audio_data

        temp_webm = tempfile.NamedTemporaryFile(suffix='.webm', delete=False)
        temp_webm_path = temp_webm.name
        temp_files.append(temp_webm_path)
        temp_webm.close()
        with open(temp_webm_path, 'wb') as f:
            f.write(binary_data)

        temp_wav_path = temp_webm_path.replace('.webm', '.wav')
        temp_files.append(temp_wav_path)

        import subprocess
        result = subprocess.run(
            ['ffmpeg', '-y', '-i', temp_webm_path, '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1', temp_wav_path],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            return None

        recognizer = sr.Recognizer()
        with sr.AudioFile(temp_wav_path) as source:
            audio = recognizer.record(source)
            return recognizer.recognize_google(audio)
    except Exception as e:
        app.logger.error(f"STT error: {e}")
        return None
    finally:
        for path in temp_files:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except:
                pass

def generate_local_response(user_message, emotion):
    cleaned = user_message.lower()
    greetings = ["hi", "hello", "hey", "greetings"]
    if any(g in cleaned for g in greetings):
        return random.choice(["Hey, I'm here. How are you doing?", "Hello! What's on your mind today?", "Hi there. I'm listening."])
    emotion_responses = {
        "happy": "That's wonderful to hear. What's bringing you joy right now?",
        "sad": "I hear that you're going through something hard. Would you like to talk about it?",
        "angry": "That sounds really frustrating. What happened?",
        "fearful": "It sounds like something has you worried. I'm here — what's going on?",
    }
    if emotion in emotion_responses:
        return emotion_responses[emotion]
    return random.choice([
        "I'm here with you. What would you like to explore?",
        "Tell me more — I'm listening.",
        "That's interesting. How are you feeling about it?",
        "I appreciate you sharing that. What matters most to you right now?"
    ])

# ─── Routes ──────────────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/conversations', methods=['GET'])
def list_conversations():
    convs = Conversation.query.order_by(Conversation.created_at.desc()).all()
    return jsonify([c.to_dict() for c in convs])

@app.route('/api/conversations', methods=['POST'])
def create_conversation():
    conv = Conversation(title='New Chat')
    db.session.add(conv)
    db.session.commit()
    return jsonify(conv.to_dict())

@app.route('/api/conversations/<int:conv_id>', methods=['DELETE'])
def delete_conversation(conv_id):
    conv = Conversation.query.get_or_404(conv_id)
    db.session.delete(conv)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/conversations/<int:conv_id>', methods=['PATCH'])
def rename_conversation(conv_id):
    conv = Conversation.query.get_or_404(conv_id)
    conv.title = request.json.get('title', 'New Chat')
    db.session.commit()
    return jsonify(conv.to_dict())

@app.route('/api/conversations/<int:conv_id>/messages', methods=['GET'])
def get_conversation_messages(conv_id):
    msgs = Message.query.filter_by(conversation_id=conv_id).order_by(Message.timestamp).all()
    return jsonify([{'id': m.id, 'role': m.role, 'content': m.content, 'emotion': m.emotion, 'timestamp': m.timestamp.isoformat()} for m in msgs])

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.json
    user_input = data.get('message', '')
    voice_input = data.get('voice_data', None)
    conversation_id = data.get('conversation_id', None)
    model_choice = data.get('model', 'gpt-4.1')
    persona_name = data.get('persona_name', 'Sol')
    custom_system_prompt = data.get('system_prompt', None)

    # Handle voice
    if voice_input and not user_input:
        user_input = speech_to_text(voice_input)
        if not user_input:
            return jsonify({"error": "Could not understand audio. Please try again."}), 400

    if not user_input:
        return jsonify({"error": "No message provided"}), 400

    # Get or create conversation
    conv = None
    if conversation_id:
        conv = Conversation.query.get(conversation_id)
    if not conv:
        conv = Conversation(title='New Chat')
        db.session.add(conv)
        db.session.commit()
        conversation_id = conv.id

    emotion = detect_emotion(user_input)
    history = get_chat_history(conversation_id)
    history.append({"role": "user", "content": user_input})

    if custom_system_prompt:
        system_prompt = custom_system_prompt
    else:
        system_prompt = (
            f"You are {persona_name}, a warm and emotionally intelligent AI companion. "
            "You help people feel heard, safe, and understood. "
            "Be conversational, compassionate, and genuine. "
            "When someone shares how they feel, validate their emotions before offering thoughts. "
            "Keep responses concise but meaningful."
        )
    if emotion and emotion != "neutral":
        emotion_map = {
            "happy": "The user seems happy. Match their energy.",
            "sad": "The user seems sad. Be especially gentle and empathetic.",
            "angry": "The user seems frustrated. Be calm and understanding.",
            "fearful": "The user seems anxious. Be reassuring.",
        }
        system_prompt += " " + emotion_map.get(emotion, "")

    messages = [{"role": "system", "content": system_prompt}] + history

    got_real_response = False
    sol_reply = generate_local_response(user_input, emotion)
    using_local_mode = False

    # OpenRouter model IDs
    OPENROUTER_MODELS = {
        'gpt-4.1':         'openai/gpt-4.1',
        'gpt-4o':          'openai/gpt-4o',
        'claude-sonnet':   'anthropic/claude-3.5-sonnet',
        'claude-opus':     'anthropic/claude-3-opus',
        'free':            'meta-llama/llama-3.1-8b-instruct:free',
    }
    # Direct OpenAI model IDs
    OPENAI_MODELS = {'gpt-4.1': 'gpt-4.1', 'gpt-4o': 'gpt-4o'}

    def call_openrouter(model_id):
        if not openrouter_api_key:
            return None
        try:
            payload = {"model": model_id, "messages": messages, "max_tokens": 600, "temperature": 0.7}
            headers = {
                "Authorization": f"Bearer {openrouter_api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://replit.com/",
                "X-Title": "Sol Space"
            }
            resp = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=30)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            app.logger.error(f"OpenRouter error ({model_id}): {e}")
            return None

    def call_openai(model_id):
        if not openai_api_key:
            return None
        try:
            client = openai.OpenAI(api_key=openai_api_key)
            resp = client.chat.completions.create(model=model_id, messages=messages, max_tokens=600)
            return resp.choices[0].message.content
        except Exception as e:
            app.logger.error(f"OpenAI error ({model_id}): {e}")
            return None

    def call_anthropic_direct(model_id):
        if not anthropic_api_key:
            return None
        try:
            import anthropic as ant
            client = ant.Anthropic(api_key=anthropic_api_key)
            system_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
            user_msgs = [m for m in messages if m["role"] != "system"]
            resp = client.messages.create(model=model_id, max_tokens=600, system=system_msg, messages=user_msgs)
            return resp.content[0].text
        except Exception as e:
            app.logger.error(f"Anthropic direct error: {e}")
            return None

    # Model routing logic
    if model_choice == 'free':
        result = call_openrouter(OPENROUTER_MODELS['free'])
        if result:
            sol_reply = result
            got_real_response = True

    elif model_choice in ('claude-sonnet', 'claude-opus'):
        anthropic_model_map = {'claude-sonnet': 'claude-3-5-sonnet-20241022', 'claude-opus': 'claude-3-opus-20240229'}
        result = call_anthropic_direct(anthropic_model_map[model_choice])
        if not result:
            result = call_openrouter(OPENROUTER_MODELS[model_choice])
        if result:
            sol_reply = result
            got_real_response = True

    else:
        # GPT-4.1 or GPT-4o: try OpenAI direct first, fall back to OpenRouter
        openai_model = OPENAI_MODELS.get(model_choice, 'gpt-4o')
        result = call_openai(openai_model)
        if not result:
            result = call_openrouter(OPENROUTER_MODELS.get(model_choice, 'openai/gpt-4o'))
        if result:
            sol_reply = result
            got_real_response = True

    if not got_real_response:
        using_local_mode = True

    # Auto-title conversation from first user message
    if conv.title == 'New Chat':
        conv.title = user_input[:45] + ('…' if len(user_input) > 45 else '')
        db.session.commit()

    # Save messages
    save_message("user", user_input, emotion, conversation_id)
    save_message("assistant", sol_reply, None, conversation_id)

    # TTS
    audio_data = None
    try:
        audio_data = text_to_speech(sol_reply)
    except Exception as e:
        app.logger.error(f"TTS error: {e}")

    result = {
        "message": sol_reply,
        "timestamp": datetime.now().isoformat(),
        "emotion": emotion,
        "local_mode": using_local_mode,
        "conversation_id": conversation_id,
        "conversation_title": conv.title
    }
    if audio_data:
        result["audio"] = f"data:audio/mp3;base64,{audio_data}"
    return jsonify(result)

@app.route('/api/create_audio_dir', methods=['POST'])
def create_audio_dir():
    os.makedirs(os.path.join('static', 'audio'), exist_ok=True)
    return jsonify({"success": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

import os
import io
import json
import time
import hashlib
import threading
from datetime import datetime
from flask import Flask, request, Response, send_from_directory, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
import requests
import re

try:
    from PIL import Image
    import pytesseract
    OCR_AVAILABLE = True
except Exception:
    OCR_AVAILABLE = False

from fuzzywuzzy import fuzz

# ------------------------ Config ------------------------
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXT = {'png','jpg','jpeg','gif','webp','pdf'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__, static_folder='.', static_url_path='/')
CORS(app)

OLLAMA_URL = os.environ.get('OLLAMA_URL', 'http://localhost:11434/api/generate')
OLLAMA_MODEL = os.environ.get('OLLAMA_MODEL', 'llama3:8b')

# Local DB paths
LOCAL_DB_PATH = 'local_db'
CARDIO_FAQ = os.path.join(LOCAL_DB_PATH, 'cardio_faq.json')
CARDIO_TIPS = os.path.join(LOCAL_DB_PATH, 'cardio_tips.json')
CLINICS = os.path.join(LOCAL_DB_PATH, 'clinics.json')
SYMPTOM_MAP = os.path.join(LOCAL_DB_PATH, 'symptom_disease_map.json')

# WHO / verified cardiology data
WHO_DATA = os.path.join('data_sources', 'who_cardiology_data.json')

# Simple cache path
CACHE_PATH = os.path.join('local_db', 'ai_cache.json')
SESSION_MEM = os.path.join('local_db', 'session_memory.json')

# Mandatory ethics disclaimer (WHO-inspired: Educational only, no diagnosis)
ETHICS_DISCLAIMER = """
⚠️ IMPORTANT ETHICS NOTICE: 
I am DoctorAI, an AI tool for educational guidance based on AHA/WHO data. 
I am NOT a doctor and cannot diagnose, treat, or provide medical advice. 
Always consult a certified cardiologist for your health. 
Your data is anonymous and not stored without consent. 
If in doubt, seek immediate professional help.
"""

CONSENT_KEY = 'user_consent'

# Ensure files exist
os.makedirs(LOCAL_DB_PATH, exist_ok=True)

if not os.path.exists(SESSION_MEM):
    with open(SESSION_MEM, 'w', encoding='utf-8') as f:
        json.dump({"previous_questions": [], "user_consent": False, "audit_logs": []}, f)

if not os.path.exists(CACHE_PATH):
    with open(CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump({}, f)

# ------------------------ Helpers ------------------------

def allowed_file(filename):
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    return ext in ALLOWED_EXT


def load_json(path):
    try:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        return {}
    return {}


def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def inject_ethics(response_text):
    return f"{response_text}\n\n{ETHICS_DISCLAIMER}"


# ------------------------ Medical Utilities ------------------------

def match_symptoms(question):
    mapping = load_json(SYMPTOM_MAP)
    q_lower = question.lower()
    matches = []
    for symptom, conditions in mapping.items():
        if symptom in q_lower:
            matches.append((symptom, conditions))
    if matches:
        lines = []
        for s, cond in matches:
            lines.append(f"'{s}': possible -> {', '.join(cond)}")
        return "; ".join(lines)
    return None


def check_local_db(question):
    faq = load_json(CARDIO_FAQ)
    tips = load_json(CARDIO_TIPS)
    clinics = load_json(CLINICS)
    q_lower = question.lower()

    # FAQs with fuzzy confidence
    best = None
    best_score = 0
    for key, answer in faq.items():
        score = fuzz.ratio(key, q_lower)
        if score > best_score:
            best_score = score
            best = (answer, score)
    if best and best_score > 60:
        ans, sc = best
        return {"answer": ans, "confidence": round(sc/100, 2)}

    # Tips keywords (exact)
    for key, tip in tips.items():
        if key in q_lower:
            return {"answer": tip, "confidence": 0.8}

    # Clinics
    if 'clinic' in q_lower or 'hospital' in q_lower:
        clinics_list = [c.get('name') + " ("+c.get('phone','N/A')+")" for c in clinics]
        return {"answer": "Here are some local cardiology clinics: " + ", ".join(clinics_list), "confidence": 0.7}

    return None


def check_who_data(question):
    who_data = load_json(WHO_DATA)
    q_lower = question.lower()
    # simple key lookup
    for key, info in who_data.items():
        if key in q_lower:
            return {"answer": info, "confidence": 0.85}
    return None


# ------------------------ Session Memory ------------------------

def remember_question(question):
    data = load_json(SESSION_MEM)
    if not data.get('user_consent', False):
        return
    history = data.get('previous_questions', [])
    history.append({'q': question, 't': datetime.utcnow().isoformat()})
    history = history[-5:]
    save_json(SESSION_MEM, {'previous_questions': history, **{k: v for k, v in data.items() if k != 'previous_questions'}})


def recall_user_context():
    data = load_json(SESSION_MEM)
    if not data.get('user_consent', False):
        return ""
    prev = data.get('previous_questions', [])
    if prev:
        return f"Earlier you asked: '{prev[-1]['q']}'"
    return ""


# ------------------------ Simple Cache ------------------------

def cache_get(key):
    cache = load_json(CACHE_PATH)
    return cache.get(key)


def cache_set(key, value):
    cache = load_json(CACHE_PATH)
    cache[key] = {'v': value, 't': time.time()}
    save_json(CACHE_PATH, cache)


# ------------------------ Logging ------------------------

def log_interaction(message, response, level=3):
    log_data = load_json(SESSION_MEM)
    logs = log_data.get('audit_logs', [])
    anon_msg = re.sub(r'\b\w{5,}\b', '[REDACTED]', message)  # Simple anonymize names/places
    logs.append({'timestamp': datetime.utcnow().isoformat(), 'anon_query': anon_msg, 'response_level': level})
    logs = logs[-100:]  # Keep last 100
    save_json(SESSION_MEM, {**log_data, 'audit_logs': logs})


# ------------------------ Prompt Builder ------------------------

def build_prompt(message, additional_info=None, urgency_info=None):
    context = recall_user_context()
    prompt = f"""
You are DoctorAI, a virtual cardiologist. Follow WHO 2025 AI Ethics: Be transparent, empathetic, equitable. Use simple English. NEVER diagnose—say 'possible' or 'suggest consulting'.
If emergent, prioritize safety over advice.
End EVERY response with the following disclaimer: {ETHICS_DISCLAIMER}

{context}
User: {message}
"""
    if urgency_info:
        prompt += f"\nURGENCY ALERT: {urgency_info}\nInclude this prominently at the beginning of your response to ensure user safety."
    if additional_info:
        prompt += f"\nRELEVANT DATA FROM LOCAL DB/WHO/SYMPTOM MATCHES:\n{chr(10).join(additional_info)}\nIncorporate this information accurately into your response to provide comprehensive guidance."
    return prompt


# ------------------------ LLM / Ollama Interaction (streaming safe) ------------------------

def classify_urgency(message):
    urgency_prompt = f"""
    Based on AHA 2025 Cardiac Emergency Guidelines, classify this symptom as:
    - Level 1: IMMEDIATE EMERGENCY (e.g., persistent chest pain >5 mins, SOB with sweating → Call 108/ER NOW).
    - Level 2: URGENT (e.g., new palpitations → See doctor within 24h).
    - Level 3: NON-URGENT (general advice).
    
    Symptoms: {message}
    
    Output ONLY: LEVEL [1|2|3]: Brief reason (1 sentence). Confidence: HIGH/MED/LOW.
    """
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": urgency_prompt,
        "stream": False,
        "options": {"temperature": 0.1} 
    }
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=10)
        if resp.ok:
            result = resp.json().get('response', '').strip()
            if 'LEVEL 1' in result.upper():
                return {"level": 1, "action": "🚨 EMERGENCY! Call 108 or go to nearest hospital IMMEDIATELY. Do not wait.", "confidence": 1.0, "reason": result}
            elif 'LEVEL 2' in result.upper():
                return {"level": 2, "action": "⚠️ URGENT: Contact a doctor or clinic within 24 hours.", "confidence": 0.8, "reason": result}
    except:
        pass
    return {"level": 3, "action": "General advice follows.", "confidence": 0.5, "reason": ""}

EMERGENCY_PATTERNS = [
    # Core Cardiac Symptoms (AHA 2025 ACS, ESC 2024)
    r"chest pain|chest discomfort|angina|pressure in chest|tightness in chest|burning in chest|heavy chest|squeezing chest",
    r"shortness of breath|difficulty breathing|sob|breathless|can\'?t breathe|gasping for air|trouble breathing",
    r"heart attack|myocardial infarction|mi|cardiac arrest",
    r"severe pain|unbearable pain|excruciating pain|radiating to arm|radiating to jaw|radiating to neck|radiating to back|pain in shoulder blade|arm numbness",

    # Associated Symptoms (Neurological/GI/Autonomic, AHA 2025)
    r"nausea|vomiting|vomit|cold sweat|clammy sweat|excessive sweating|lightheaded|dizzy|faint|fainting|confusion|disorientation|extreme fatigue|severe tiredness",
    r"irregular heartbeat|palpitations severe|fast heartbeat|racing heart|heart skipping beats|passing out|loss of consciousness|syncope|blackout",

    # Urgency and Duration Modifiers
    r"sudden(ly)?|acute|worsening fast|rapid worsening|for ([0-9]+ )?(minutes|minuts?|hours?)|lasting long|persistent|ongoing for a while",

    # Atypical Presentations (Women/Elderly, AHA 2025)
    r"unusual fatigue|extreme tiredness|jaw pain|upper back pain|stomach pain|epigastric pain|indigestion|heartburn feeling|mid-back pain|shoulder discomfort",

    # Other Critical Conditions (Aortic Dissection, Pulmonary Embolism, Tamponade)
    r"sudden severe back pain|ripping pain|tearing pain|chest and back pain|sharp chest pain sudden|pulmonary embolism|lung clot|blood clot in lung",
    r"swelling in legs|edema|leg swelling|ankle swelling|blue lips|cyanosis|bluish skin|rapid breathing|tachypnea",

    # Stroke-like or Neurological Overlap (ESC 2024)
    r"sudden weakness|arm weakness|face drooping|slurred speech|difficulty speaking|stroke symptoms|sudden numbness",

    # Heart Failure and Other Signs (ESC 2024, WHO)
    r"swollen ankles|feet swelling|difficulty breathing lying down|orthopnea|waking up breathless|paroxysmal nocturnal dyspnea|coughing at night|pink frothy sputum"
]

def is_potential_emergency(message):
    msg_lower = message.lower()
    return any(re.search(pattern, msg_lower) for pattern in EMERGENCY_PATTERNS)


def ask_ai_stream(message, additional_info=None, urgency_info=None, stream=True, timeout=60):
    full_prompt = build_prompt(message, additional_info, urgency_info)
    # simple cache key
    cache_key = hashlib.sha256(full_prompt.encode('utf-8')).hexdigest()
    cached = cache_get(cache_key)
    if cached and (time.time() - cached.get('t', 0) < 60*60):  # 1 hour cache
        full_text = cached['v']
        if not stream:
            return full_text
        else:
            for i in range(0, len(full_text), 200):
                yield json.dumps({"reply": full_text[i:i+200]}) + "\n"
            return

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": full_prompt,
        "stream": stream,
        "options": {"temperature": 0.2, "top_p": 0.9}
    }
    headers = {"Content-Type": "application/json"}

    try:
        with requests.post(OLLAMA_URL, data=json.dumps(payload), headers=headers, stream=stream, timeout=timeout) as resp:
            if not resp.ok:
                text = f"Ollama error: HTTP {resp.status_code}\n\n{ETHICS_DISCLAIMER}"
                if not stream:
                    cache_set(cache_key, text)
                    return text
                yield json.dumps({"reply": text}) + "\n"
                return

            if stream:
                full_text = ""
                for line in resp.iter_lines():
                    if line:
                        try:
                            data = json.loads(line.decode('utf-8'))
                            chunk = data.get('response') or data.get('output') or data.get('text') or ""
                            if data.get('done', False):
                                break
                            if chunk:
                                full_text += chunk
                                yield json.dumps({"reply": chunk}) + "\n"
                        except Exception:
                            text = line.decode('utf-8', errors='ignore')
                            if text.strip():
                                full_text += text
                                yield json.dumps({"reply": text}) + "\n"
                if full_text:
                    cache_set(cache_key, full_text)
                return
            else:
                # non-stream
                result = resp.json()
                text = result.get('response', '') + "\n\n" + ETHICS_DISCLAIMER
                cache_set(cache_key, text)
                return text

    except Exception as e:
        msg = f"Error connecting to Ollama: {str(e)}\n\n{ETHICS_DISCLAIMER}"
        if stream:
            yield json.dumps({"reply": msg}) + "\n"
        else:
            return msg


# ------------------------ Routes ------------------------

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')


@app.route('/health')
def health():
    return jsonify({"status": "ok", "ollama": OLLAMA_URL, "model": OLLAMA_MODEL})


@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json(force=True)
    message = data.get('message','')

    if not message.strip():
        return jsonify({"reply":"Please enter a message.\n\n" + ETHICS_DISCLAIMER})

    session_data = load_json(SESSION_MEM)
    consent = session_data.get(CONSENT_KEY, False)

    if not consent:
        if message.lower() in ['yes', 'y', 'consent', 'consent granted']:
            save_json(SESSION_MEM, {**session_data, CONSENT_KEY: True})
            return jsonify({"answer": "Consent noted. How can I help with your heart health today?\n\n" + ETHICS_DISCLAIMER})
        else:
            consent_msg = "Welcome! Before we start, do you consent to anonymous chat history for better context? (Yes/No) This helps me remember symptoms safely. Reply 'Yes' to proceed.\n\n" + ETHICS_DISCLAIMER
            save_json(SESSION_MEM, {**session_data, CONSENT_KEY: False})
            return jsonify({"answer": consent_msg, "requires_consent": True})

    # Collect additional info
    additional_info = []
    symptom_str = match_symptoms(message)
    if symptom_str:
        additional_info.append(f"Symptom matcher: {symptom_str}")

    local = check_local_db(message)
    if local:
        additional_info.append(f"Local DB info: {local['answer']}")

    who = check_who_data(message)
    if who:
        additional_info.append(f"WHO data: {who['answer']}")

    # Emergency detector
    urgency_info = None
    urgency_level = 3
    if is_potential_emergency(message):
        urgency = classify_urgency(message)
        urgency_level = urgency['level']
        if urgency['level'] in [1, 2]:
            urgency_info = f"{urgency['action']}\nReason: {urgency['reason']}"

    # Always proceed to AI with combined info
    remember_question(message)
    log_interaction(message, "AI response with combined data", urgency_level)

    return Response(
        ask_ai_stream(message, additional_info if additional_info else None, urgency_info),
        mimetype='text/plain'
    )

@app.route('/upload-image', methods=['POST'])
def upload_image():
    if 'image' not in request.files:
        return jsonify({'error':'No image uploaded'}), 400
    f = request.files['image']
    if f.filename == '':
        return jsonify({'error':'Empty filename'}), 400
    if not allowed_file(f.filename):
        return jsonify({'error':'File type not allowed'}), 400

    fname = secure_filename(f.filename)
    timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S%f')
    saved_name = f"{os.path.splitext(fname)[0]}_{timestamp}{os.path.splitext(fname)[1]}"
    path = os.path.join(UPLOAD_FOLDER, saved_name)
    f.save(path)

    file_url = f"/{UPLOAD_FOLDER}/{saved_name}"

    # If OCR available and filename suggests a report, attempt extraction
    analysis = None
    if OCR_AVAILABLE and any(k in fname.lower() for k in ['ecg', 'report', 'blood', 'cholesterol']):
        try:
            img = Image.open(path)
            text = pytesseract.image_to_string(img)
            analysis = {'extracted_text': text[:2000]}
        except Exception as e:
            analysis = {'error': str(e)}

    return jsonify({'url': file_url, 'analysis': analysis})


@app.route(f'/{UPLOAD_FOLDER}/<path:filename>')
def uploaded_file(filename):
    full = os.path.join(UPLOAD_FOLDER)
    if os.path.exists(os.path.join(full, filename)):
        return send_from_directory(full, filename)
    return ("Not found",404)


@app.route('/<path:filename>')
def static_proxy(filename):
    if os.path.exists(filename):
        return send_from_directory('.', filename)
    return ("Not found",404)


# ------------------------ Run ------------------------
if __name__ == '__main__':
    print("Starting DoctorAI v2.0 on http://localhost:5000")
    print(f"Ollama endpoint: {OLLAMA_URL} | Model: {OLLAMA_MODEL}")
    # don't auto-ngrok in production - keep optional
    if os.environ.get('ENABLE_NGROK','1') == '1':
        try:
            from pyngrok import ngrok
            public_url = ngrok.connect(5000)
            print(f"🔥 Public URL (Ngrok): {public_url}")
        except Exception as e:
            print(f"Ngrok startup failed: {e}")
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)
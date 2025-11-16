# 🩺 DoctorAI — Advanced AI Cardiologist (WHO + AHA Guided)

DoctorAI is a **clinical‑grade cardiology support system** powered by LLMs (Ollama / Llama 3), WHO 2025 guidelines, medical symptom mapping, OCR analysis, and intelligent emergency classification.

This is **NOT** a simple chatbot — it is a full medical AI framework with:

* Emergency detection (AHA/WHO compliant)
* Local medical database fusion
* WHO cardiology data integration
* Symptom-to-disease reasoning
* OCR support for ECG / reports
* Session memory + anonymized logging
* Streaming responses (ChatGPT-style)

It is designed for **educational + research purposes only**.

---

## 🚀 Features

### **1. 🔥 Real-time Emergency Detection (AI Triage System)**

DoctorAI classifies user symptoms into:

* **LEVEL 1 — EMERGENCY** → “Call 108 / go to hospital NOW”
* **LEVEL 2 — URGENT** → Consult doctor within 24 hours
* **LEVEL 3 — NON-URGENT** → General guidance

Uses AHA 2025 + ESC 2024 approved symptom patterns.

---

### **2. 🧠 Symptom Matching Engine**

Maps symptoms to possible diseases using `symptom_disease_map.json`.

Example:

```
'chest pain' → possible: Angina, MI, GERD
```

---

### **3. 🗂 Multi-source Medical Knowledge Fusion**

DoctorAI pulls data from:

* `cardio_faq.json` (common questions)
* `cardio_tips.json` (verified health tips)
* `clinics.json` (local cardiology centers)
* `who_cardiology_data.json` (WHO medical data)

All relevant information is automatically merged into the LLM prompt.

---

### **4. 🧾 OCR Support for Medical Reports**

If user uploads files like:

* ECG
* Cholesterol report
* Blood test
* Medical scan

DoctorAI extracts text using **Tesseract OCR** and includes it in analysis.

---

### **5. 💬 LLM Streaming (ChatGPT-like)**

Responses are streamed chunk-by-chunk for smooth real-time conversation.

---

### **6. 🔐 Safety + Ethics Layer**

WHO 2025 AI Ethics built-in:

* No diagnosis
* No prescriptions
* Transparency
* User consent system
* Anonymized audit logs (HIPAA-like)

Every response ends with a mandatory disclaimer.

---

### **7. 🧠 Session Memory + Caching**

* Remembers last 5 user questions (only if consented)
* Full anonymized logs
* Smart caching for repeated queries

---

## 📁 Project Structure

```
DoctorAI/
│── app.py                  # Main Flask server
│── uploads/                # User uploaded medical files
│── local_db/
│     ├── cardio_faq.json
│     ├── cardio_tips.json
│     ├── clinics.json
│     ├── symptom_disease_map.json
│     ├── ai_cache.json
│     └── session_memory.json
│
├── data_sources/
│     └── who_cardiology_data.json
│
└── index.html              # Optional frontend UI
```

---

## 💻 How It Works (Core Flow)

1. User sends message → `/chat` endpoint
2. System checks:

   * Local DB matches
   * WHO data
   * Symptom patterns
   * Emergency triggers
3. Builds a **smart medical prompt**
4. Passes to Ollama → streams response
5. Adds ethics disclaimer
6. Logs anonymized query

---

## 🔧 Setup Instructions

### **1. Install Requirements**

```
pip install flask flask-cors requests fuzzywuzzy python-Levenshtein pytesseract pillow
```

### **2. Install Tesseract OCR**

* Windows: [https://github.com/UB-Mannheim/tesseract/wiki](https://github.com/UB-Mannheim/tesseract/wiki)
* Linux: `sudo apt install tesseract-ocr`

### **3. Install & Run Ollama**

```
ollama pull llama3:8b
ollama serve
```

### **4. Run DoctorAI**

```
python app.py
```

Server runs at:

```
http://localhost:5000
```

---

## 🔌 API Endpoints

### **POST /chat**

Chat with DoctorAI.

```
{
  "message": "I have chest pain radiating to my left arm"
}
```

### **POST /upload-image**

Upload ECG / medical reports.

### **GET /health**

Health check.

---

## 🛑 Ethics Disclaimer (Auto-injected)

DoctorAI is **NOT** a doctor.
It provides educational guidance only.
Always consult a certified cardiologist.

---

## 🌟 Why This Project Is Special

This is not just an LLM frontend.
It is a **complete medical intelligence pipeline**:

* Risk classification
* Symptom inference
* WHO-level knowledge
* Real-time triage
* OCR medical analysis
* AI context merging

This puts the project in **research + startup level** domain.

---

## 🧑‍💻 Built By

**Sanu Sharma** — AI Engineer & Innovator

If you use this project, give credit to the original creator.

---

## 📬 Contact

* Email: *sanusharma0045.v@gmail.com*


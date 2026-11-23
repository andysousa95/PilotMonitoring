# ✈️ Pilot Monitoring FBW A2NX version

**Pilot Monitoring** is a 100% offline virtual voice assistant for the **FlyByWire A320neo** in Microsoft Flight Simulator (MSFS). The project combines local speech recognition, audio synthesis, and real-time telemetry via SimConnect, monitored through a responsive Flask web dashboard.

---

## 🚀 Features

- **100% Offline Speech Recognition:** Powered by the **Vosk Engine** (`vosk-model-small-pt-0.3`) for fast, local voice processing without third-party API dependencies.
- **Embedded Web Dashboard:** Responsive interface built with Flask and Bootstrap 5 featuring auto-adjusting **Light / Dark Mode**.
- **Telemetry & Cockpit Interaction:** Direct integration with MSFS using the **SimConnect** API.
- **Automated Windows Build:** CI/CD pipeline via **GitHub Actions** that compiles the project into a portable `.exe` package ready for deployment.

---

## 🛠️ Tech Stack

- **Language:** Python 3.10+
- **Web Interface:** Flask, HTML5, Bootstrap 5
- **Speech-to-Text (STT):** Vosk (`vosk-model-small-pt-0.3`)
- **Text-to-Speech (TTS):** `pyttsx3`
- **Simulator Integration:** SimConnect API (`SimConnect` Python wrapper)
- **Compilation & Packaging:** PyInstaller + GitHub Actions

---

## 📂 Repository Structure

```text
PilotMonitoring/
├── .github/
│   └── workflows/
│       └── build.yml      # CI/CD pipeline for Windows executable compilation
├── templates/
│   └── index.html         # Responsive HTML/Bootstrap dashboard
├── app.py                 # Core application (Flask routes & copilot logic)
├── requirements.txt       # Project dependencies
└── README.md              # Project documentation

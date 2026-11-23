# ✈️ PilotMonitoring — Voice-Activated A320neo Co-Pilot (MSFS / FBW A32NX)

**PilotMonitoring** is a lightweight, offline voice-activated cockpit assistant designed for **Microsoft Flight Simulator (MSFS)** and the **FlyByWire A32NX**. Built with Python, it acts as a Pilot Monitoring (PM) / First Officer, executing official A320neo checklists, reading real-time aircraft telemetry, and automating cockpit callouts and controls via voice commands.

---

## ✨ Key Features

* **100% Offline Voice Recognition:** Powered by `faster-whisper` (`base.en` with `int8` CPU quantization) for low-latency, high-accuracy aviation phraseology recognition without relying on cloud APIs or internet connectivity.
* **Official FlyByWire A32NX Checklists:** Complete Challenge & Response checklists synchronized with custom First Officer `.wav` audio callouts and dynamic timing.
* **Real-Time Telemetry via SimConnect:** Reads live aircraft data (such as fuel quantity in tons, altitude, speed, and flight phase) directly from MSFS and injects dynamic values into checklist readouts.
* **Cockpit Automation & Callouts:** Supports voice-triggered flap settings, pack control, landing lights, and cabin crew announcements.
* **ECAM-Style Dark GUI:** High-contrast cockpit communication log with real-time progress tracking, audio input/output device selectors, and status indicators.

---

## 📋 Supported Checklists (FBW A32NX Standard)

* **Cockpit Preparation** *(with dynamic SimConnect fuel readout)*
* **Before Start**
* **After Start**
* **Taxi**
* **Line-Up**
* **Approach**
* **Landing**
* **After Landing**
* **Parking**
* **Securing the Aircraft**

---

## 🛠️ Tech Stack

* **Speech-to-Text:** [Faster-Whisper](https://github.com/SYSTRAN/faster-whisper) (`base.en`, `int8`)
* **Simulator Integration:** `SimConnect` (Python-SimConnect)
* **Audio I/O & Playback:** `sounddevice`, `numpy`, `scipy` / `wave`
* **Cockpit Keybind Automation:** `pyautogui`
* **GUI:** `tkinter` / `ttk` (Custom ECAM Dark Theme)

---

## 🚀 Getting Started

### Prerequisites
* Windows 10/11
* Microsoft Flight Simulator (with FlyByWire A32NX)
* Python 3.10+ (if running from source)

### Installation (From Source)
1. Clone the repository:
   Not allowed until the initial tests confirm the correctly functionalities of the app.



Standalone Executable
If you are using the compiled .exe release, simply keep the audio/ folder in the same directory as PilotMonitoring.exe and launch it once MSFS is running.

🎙️ Usage Tips
Select your Microphone (Input) and Headset/Speakers (Output) in the top audio bar.

Load into the cockpit in MSFS.

Speak clearly using standard checklist triggers (e.g., "After start checklist", "Taxi checklist", "Line-up checklist", "Approach checklist").

Monitor the Cockpit Comm Log for real-time Challenge & Response verification.

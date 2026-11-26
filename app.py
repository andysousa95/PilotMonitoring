import os
import queue
import re
import struct
import sys
import threading
import time
import pyttsx3
import tkinter as tk
from tkinter import scrolledtext, ttk, messagebox
from SimConnect import AircraftEvents, AircraftRequests, SimConnect
import numpy as np
import sounddevice as sd

#VARIÁVEIS GLOBAIS#
sm = None
aq = None
ae = None

if "DISPLAY" not in os.environ:
  os.environ["DISPLAY"] = ":0"

if getattr(sys, "frozen", False):
  exe_dir = os.path.dirname(os.path.abspath(sys.executable))
  log_file = open(
      os.path.join(exe_dir, "erro_log.txt"), "w", encoding="utf-8", buffering=1
  )
  sys.stdout = log_file
  sys.stderr = log_file

try:
  from faster_whisper import WhisperModel
  import pyautogui
  from SimConnect import AircraftRequests, SimConnect
except Exception as e:
  root_err = tk.Tk()
  root_err.withdraw()
  messagebox.showerror("Erro de Dependência", f"Falha ao importar módulos:\n{e}")
  sys.exit(1)

SAMPLE_RATE = 16000

if getattr(sys, "frozen", False):
  meipass_path = getattr(
      sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable))
  )
  exe_dir = os.path.dirname(os.path.abspath(sys.executable))

  WHISPER_DIR = (
      os.path.join(meipass_path, "whisper-model")
      if os.path.exists(os.path.join(meipass_path, "whisper-model"))
      else os.path.join(exe_dir, "whisper-model")
  )
  AUDIO_PATH = (
      os.path.join(meipass_path, "audio")
      if os.path.exists(os.path.join(meipass_path, "audio"))
      else os.path.join(exe_dir, "audio")
  )
else:
  base_path = os.path.dirname(os.path.abspath(__file__))
  WHISPER_DIR = os.path.join(base_path, "whisper-model")
  AUDIO_PATH = os.path.join(base_path, "audio")

# Localiza a pasta real onde o model.bin foi extraído
caminho_modelo_real = WHISPER_DIR
for root_dir, _, files in os.walk(WHISPER_DIR):
  if "model.bin" in files:
    caminho_modelo_real = root_dir
    break

try:
  whisper_model = WhisperModel(
      caminho_modelo_real,
      device="cpu",
      compute_type="int8",
      local_files_only=True,
  )
except Exception as e:
  root_err = tk.Tk()
  root_err.withdraw()
  messagebox.showerror(
      "Erro ao Iniciar Whisper",
      f"Não foi possível carregar o modelo:\n{e}\n\nCaminho: {caminho_modelo_real}",
  )
  sys.exit(1)

AVIATION_PROMPT = (
    "Airbus A320 cockpit preparation checklist, before start checklist, after"
    " start checklist, taxi checklist, line-up checklist, approach checklist, landing checklist"
    " after landing checklist, parking checklist, flaps, spoilers, push and"
    " start."
)

audio_queue = queue.Queue()
estado_checklist = {"ativa": False, "checklist_nome": None, "indice_atual": 0, "aguardando_resposta": False}
estado_voo = {
    "thrust_set_disparado": False,
    "anunciou_100knots": False,
    "tripulacao_dec_disparada": False,
    "tripulacao_pouso_disparada": False,
}

config_volumes = {
    "mic_gain": 1.0,
    "app_volume": 1.0,
    "input_device": None,
    "output_device": None,
    "mic_mutado": False,
}

DIGITOS = {
    "zero": 0,
    "oh": 0,
    "one": 1,
    "two": 2,
    "to": 2,
    "too": 2,
    "three": 3,
    "tree": 3,
    "four": 4,
    "for": 4,
    "five": 5,
    "fife": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "niner": 9,
}

# FUNÇÃO PARA EXECUTAR COMANDOS DE HEADING & ALTITUDE#

def extrair_numero_fcu(texto):
  """Extrai qualquer número falado ('278', 'two seven eight', 'five thousand')."""
  limpo = re.sub(r"[^\w\s]", "", texto.lower())

  # Caso 1: Dígitos diretos ("278", "5000", "350")
  junto = re.sub(r"(?<=\d)\s+(?=\d)", "", limpo)
  match = re.search(r"\d+", junto)
  if match:
    return int(match.group())

  # Caso 2: Por extenso com milhar ("five thousand", "twelve thousand five hundred")
  palavras = limpo.split()
  if "thousand" in palavras:
    idx = palavras.index("thousand")
    milhar = DIGITOS.get(palavras[idx - 1], 0) if idx > 0 else 0
    centena = (
        DIGITOS.get(palavras[idx + 1], 0) * 100
        if idx + 1 < len(palavras) and palavras[idx + 1] in DIGITOS
        else 0
    )
    if milhar > 0:
      return (milhar * 1000) + centena

  # Caso 3: Dígito a dígito por extenso ("zero four five" -> 45, "three four zero" -> 340)
  sequencia = "".join(str(DIGITOS[p]) for p in palavras if p in DIGITOS)
  return int(sequencia) if sequencia else None


def setar_heading(hdg):
  if not (0 <= hdg <= 360):
    atualizar_gui_logs(
        f"⚠️ Heading inválido: {hdg} (use 000 a 360)\n", "#ff5252"
    )
    return

  hdg_formatado = f"{hdg:03d}"
  try:
    if ae:
      evento_hdg = ae.find("HEADING_BUG_SET")
      evento_hdg(hdg)
    atualizar_gui_logs(
        f"✈️ Copiloto: Heading {hdg_formatado} set.\n", "#00e5ff"
    )
  except Exception as e:
    atualizar_gui_logs(f"❌ Erro SimConnect (HDG): {e}\n", "#ff5252")


def setar_altitude_ou_fl(valor, eh_fl=True):
  if eh_fl:
    if not (1 <= valor <= 450):
      atualizar_gui_logs(f"⚠️ Flight Level inválido: FL{valor}\n", "#ff5252")
      return
    altitude_pes = valor * 100
    label = f"FL{valor:03d} ({altitude_pes} ft)"
  else:
    if not (100 <= valor <= 45000):
      atualizar_gui_logs(f"⚠️ Altitude inválida: {valor} ft\n", "#ff5252")
      return
    altitude_pes = valor
    label = f"{altitude_pes} ft"

  try:
    if ae:
      evento_alt = ae.find("AP_ALT_VAR_SET_ENGLISH")
      evento_alt(altitude_pes)
    atualizar_gui_logs(f"✈️ Copiloto: Altitude {label} set.\n", "#00e5ff")
  except Exception as e:
    atualizar_gui_logs(f"❌ Erro SimConnect (ALT): {e}\n", "#ff5252")



# REPRODUÇÃO DE ÁUDIO & CHECKLIST AUTOMÁTICA

def ler_wav_pcm(caminho_arquivo):
  with open(caminho_arquivo, "rb") as f:
    data = f.read()

  pos = 12
  channels = 1
  sample_rate = 44100
  bits_per_sample = 16
  audio_format = 1

  while pos < len(data) - 8:
    chunk_id = data[pos : pos + 4]
    chunk_size = struct.unpack("<I", data[pos + 4 : pos + 8])[0]
    chunk_data = data[pos + 8 : pos + 8 + chunk_size]

    if chunk_id == b"fmt ":
      audio_format, channels, sample_rate, _, _, bits_per_sample = (
          struct.unpack("<HHIIHH", chunk_data[:16])
      )
    elif chunk_id == b"data":
      if audio_format == 3 and bits_per_sample == 32:
        samples = np.frombuffer(chunk_data, dtype=np.float32)
      elif bits_per_sample == 16:
        samples = (
            np.frombuffer(chunk_data, dtype=np.int16).astype(np.float32) / 32768.0
        )
      elif bits_per_sample == 32:
        samples = (
            np.frombuffer(chunk_data, dtype=np.int32).astype(np.float32)
            / 2147483648.0
        )
      else:
        samples = (
            np.frombuffer(chunk_data, dtype=np.int16).astype(np.float32) / 32768.0
        )

      if channels > 1:
        samples = samples.reshape(-1, channels)

      duracao = len(samples) / float(sample_rate)
      return samples, sample_rate, duracao

    pos += 8 + chunk_size + (chunk_size % 2)

  return None, 44100, 6.0


def obter_duracao_wav(nome_arquivo):
  caminho = os.path.join(AUDIO_PATH, f"{nome_arquivo}.wav")
  if os.path.exists(caminho):
    try:
      _, _, duracao = ler_wav_pcm(caminho)
      return duracao
    except Exception:
      pass
  return 6.0


def tocar_audio(nome_arquivo):
  caminho_arquivo = os.path.join(AUDIO_PATH, f"{nome_arquivo}.wav")
  if not os.path.exists(caminho_arquivo):
    atualizar_gui_logs(
        f"⚠️ Áudio não encontrado: {nome_arquivo}.wav\n", "#ffab00"
    )
    return

  def _play():
    try:
      samples, sr, _ = ler_wav_pcm(caminho_arquivo)
      if samples is not None:
        audio_ajustado = samples * config_volumes["app_volume"]
        out_dev = config_volumes["output_device"]
        sd.play(audio_ajustado, samplerate=sr, device=out_dev)
        sd.wait()
    except Exception as e:
      atualizar_gui_logs(f"⚠️ Erro ao reproduzir áudio: {e}\n", "#ff5252")

  threading.Thread(target=_play, daemon=True).start()


def log_e_falar(texto_log, arquivo_audio=None):
  atualizar_gui_logs(f"👨‍✈️ Copiloto: {texto_log}\n", "#00e5ff")
  if arquivo_audio:
    tocar_audio(arquivo_audio)


def falar_tts(texto):
  def _falar():
    try:
      engine = pyttsx3.init()
      engine.setProperty("rate", 175)
      engine.setProperty("volume", min(1.0, config_volumes["app_volume"]))
      for voz in engine.getProperty("voices"):
        if "en-US" in voz.id or "en_US" in voz.id or "English" in voz.name:
          engine.setProperty("voice", voz.id)
          break
      engine.say(texto)
      engine.runAndWait()
    except Exception as e:
      atualizar_gui_logs(f"⚠️ Erro TTS: {e}\n", "#ffab00")

  threading.Thread(target=_falar, daemon=True).start()


def parar_checklist():
  global estado_checklist
  if estado_checklist["ativa"]:
    estado_checklist["ativa"] = False
    estado_checklist["checklist_nome"] = None
    sd.stop()
    progress_bar["value"] = 0
    lbl_progresso_status.config(
        text="⏹️ CHECKLIST INTERROMPIDA PELO COMANDANTE.", fg="#ffab00"
    )
    atualizar_gui_logs("⏹️ Checklist cancelada.\n", "#ffab00")


def executar_checklist_automaticamente(nome):
  global estado_checklist
  itens = CHECKLISTS[nome]
  total_itens = len(itens)

  progress_bar["maximum"] = total_itens
  progress_bar["value"] = 0

  nome_arquivo_audio = f"{nome.capitalize()} checklist"
  duracao_total = obter_duracao_wav(nome_arquivo_audio)

  delay_titulo = min(2.2, duracao_total * 0.20)
  tempo_final = min(1.5, duracao_total * 0.12)
  tempo_util = max(1.0, duracao_total - delay_titulo - tempo_final)
  intervalo_item = tempo_util / total_itens

  lbl_progresso_status.config(
      text=f"🔊 EXECUTANDO: {nome.upper()} ({duracao_total:.1f}s)...",
      fg="#00e5ff",
  )
  inicio_audio = time.monotonic()
  tocar_audio(nome_arquivo_audio)

  for i, (item, resposta) in enumerate(itens, start=1):
    if not estado_checklist["ativa"]:
      break

    momento_alvo = delay_titulo + ((i - 1) * intervalo_item)
    espera = momento_alvo - (time.monotonic() - inicio_audio)
    if espera > 0:
      time.sleep(espera)

    if not estado_checklist["ativa"]:
      break

    resposta_final = resposta
    if item.upper() == "FUEL QUANTITY" and telemetria.get("fuel_tons", 0) > 0:
      resposta_final = f"{telemetria['fuel_tons']} TONS"

    lbl_progresso_status.config(
        text=f"[{i}/{total_itens}] {nome.upper()} ➔ {item} [{resposta_final}]",
        fg="#00e676",
    )
    atualizar_gui_logs(
        f"   ✓ {item.ljust(24, '.')} {resposta_final}\n", "#a8dadc"
    )

    progress_bar["value"] = i
    root.update_idletasks()

  if estado_checklist["ativa"]:
    restante = duracao_total - (time.monotonic() - inicio_audio)
    if restante > 0:
      time.sleep(restante)

    lbl_progresso_status.config(
        text=f"✅ {nome.upper()} CHECKLIST COMPLETED", fg="#00e676"
    )
    atualizar_gui_logs(
        f"✔️ {nome.capitalize()} checklist concluída.\n", "#00e676"
    )

    time.sleep(1.5)
    while not audio_queue.empty():
      try:
        audio_queue.get_nowait()
      except queue.Empty:
        break

    estado_checklist["ativa"] = False
    estado_checklist["checklist_nome"] = None


def iniciar_checklist(nome):
  global estado_checklist
  if nome not in CHECKLISTS:
    log_e_falar(f"Checklist {nome} not found.")
    return

  if estado_checklist["ativa"]:
    return

  estado_checklist["ativa"] = True
  estado_checklist["checklist_nome"] = nome

  log_e_falar(f"Running {nome} checklist.")
  threading.Thread(
      target=executar_checklist_automaticamente, args=(nome,), daemon=True
  ).start()


# ==========================================
# SIMULADOR & MONITORAMENTO
# ==========================================
telemetria = {
    "altitude": 0,
    "airspeed": 0,
    "vertical_speed": 0,
    "on_ground": True,
    "landing_lights": False,
    "gear_handle": 1,
    "gear_anterior": 1,
    "fuel_tons": 0.0,
}


def monitorar_simulador():
  global sm, aq, ae
  while True:
    try:
      sm = SimConnect()
      aq = AircraftRequests(sm)
      atualizar_status_sim(True)
      while True:
        telemetria["altitude"] = aq.get("PLANE_ALTITUDE") or 0
        telemetria["airspeed"] = aq.get("AIRSPEED_INDICATED") or 0
        telemetria["vertical_speed"] = aq.get("VERTICAL_SPEED") or 0
        telemetria["on_ground"] = bool(aq.get("SIM_ON_GROUND"))
        telemetria["landing_lights"] = bool(aq.get("LIGHT_LANDING"))
        telemetria["gear_handle"] = int(aq.get("GEAR_HANDLE_POSITION") or 0)
        peso_lbs = aq.get("FUEL_TOTAL_QUANTITY_WEIGHT") or 0
        telemetria["fuel_tons"] = round(peso_lbs * 0.000453592, 1)
        executar_logica_automatica()
        time.sleep(0.2)
    except Exception:
      atualizar_status_sim(False)
      time.sleep(4)


def executar_logica_automatica():
  global estado_voo
  as_nos = telemetria["airspeed"] * 0.592484
  on_ground = telemetria["on_ground"]
  landing_lights = telemetria["landing_lights"]
  gear_atual = telemetria["gear_handle"]
  gear_ant = telemetria["gear_anterior"]

  if not on_ground:
    estado_voo["thrust_set_disparado"] = False
    estado_voo["anunciou_100knots"] = False
    estado_voo["tripulacao_dec_disparada"] = False
  else:
    estado_voo["tripulacao_pouso_disparada"] = False

  if on_ground and landing_lights and not estado_voo["tripulacao_dec_disparada"]:
    log_e_falar("Cabin crew, takeoff.", "Tripulação decolagem")
    pyautogui.hotkey("ctrl", "shift", "a")
    estado_voo["tripulacao_dec_disparada"] = True

  if (
      not on_ground
      and gear_ant == 0
      and gear_atual == 1
      and not estado_voo["tripulacao_pouso_disparada"]
  ):
    log_e_falar("Cabin crew, landing.", "Tripulação pouso")
    pyautogui.hotkey("ctrl", "shift", "a")
    estado_voo["tripulacao_pouso_disparada"] = True

  telemetria["gear_anterior"] = gear_atual

  if on_ground and as_nos >= 80 and not estado_voo["thrust_set_disparado"]:
    log_e_falar("80 knots, thrust set.", "80 knots")
    estado_voo["thrust_set_disparado"] = True

  if on_ground and as_nos >= 100 and not estado_voo["anunciou_100knots"]:
    log_e_falar("100 knots, crosscheck.", "100 knots")
    estado_voo["anunciou_100knots"] = True


# ==========================================
# CHECKLISTS & COMANDOS DE VOZ
# ==========================================
CHECKLISTS = {
    "cockpit preparation": [
        ("GEAR PINS and COVERS", "REMOVED"),
        ("FUEL QUANTITY", "(KG/LB)"),
        ("SEAT BELTS", "ON"),
        ("ADIRS", "NAV"),
        ("BARO REF", "SET (BOTH)"),
    ],
    "before start": [
        ("PARKING BRAKE", "SET / RELEASED"),
        ("T.O SPEEDS & THRUST", "(BOTH)"),
        ("WINDOWS", "CLOSED(BOTH)")
        ("BEACON", "ON"),
    ],
    "after start": [
        ("ANTI ICE", "OFF / AS RQRD"),
        ("ECAM STATUS", "CHECKED"),
        ("PITCH TRIM", "___%"),
    ],
    "taxi": [
        ("FLIGHT CONTROLS", "CHECKED (BOTH)"),
        ("FLAPS SETTINGS", "CONF___(BOTH)"),
        ("RADAR & PRED W/SH", "ON & AUTO"),
        ("ENG MODE SEL", "___"),
        ("ECAM MEMO", "TO NO BLUE"),
        ("CABIN", "READY")
    ],
    "line-up": [
        ("T.O. RWY", "CONFIRMED (BOTH)"),
        ("TCAS", "___"),
        ("PACKS 1 & 2", "___"),
    ],
    "approach": [
        ("BARO REF", "SET (BOTH)"),
        ("SEAT BELTS", "ON"),
        ("MINIMUM", "___"),
        ("AUTO BREAK", "___"),
        ("ENG MODE SEL", "AS RQRD"),
    ],
    "landing": [
        ("ECAM MEMO", "LDG NO BLUE"),
        ("CABIN", "READY"),
    ],
    "after landing": [
        ("RADAR & PRED W/S", "OFF"),
    ],
    "parking": [
        ("PARK BRK or CHOCKS", "SET"),
        ("ENGINES", "OFF"),
        ("WINGS LIGHT", "OFF"),
        ("FUEL PUMPS", "OFF"),
        ("YELLOW ELEC PUMP", "OFF"),
    ],
}


def tratar_comando_voz(texto):
  global estado_checklist, estado_voo
  texto_limpo = re.sub(r"[^\w\s\.]", "", texto.lower()).strip()
  if not texto_limpo:
    return

  atualizar_gui_logs(f"🎙️ Comandante: {texto_limpo}\n", "#f1f5f9")

  # --- COMANDOS FCU (HEADING / FLIGHT LEVEL / ALTITUDE) ---
  if "heading" in texto_limpo:
    hdg = extrair_numero_fcu(texto_limpo)
    if hdg is not None:
      setar_heading(hdg)
      return

  if "flight level" in texto_limpo or re.search(r"\bfl\b", texto_limpo):
    fl = extrair_numero_fcu(texto_limpo)
    if fl is not None:
      setar_altitude_ou_fl(fl, eh_fl=True)
      return

  if "altitude" in texto_limpo:
    alt = extrair_numero_fcu(texto_limpo)
    if alt is not None:
      setar_altitude_ou_fl(alt, eh_fl=(alt < 500))
      return

  # --- COMANDOS DE OPERAÇÃO & CHECKLISTS ---
  if "push and start" in texto_limpo or "push start" in texto_limpo:
    log_e_falar("Push and start authorized.")
  elif (
      any(
          p in texto_limpo
          for p in [
              "cockpit preparation",
              "cock beach preparation",
              "cock bit preparation",
              "cook pit preparation",
              "preparation checklist",
          ]
      )
      and "checklist" in texto_limpo
  ):
    iniciar_checklist("cockpit preparation")
  elif "before start" in texto_limpo and "checklist" in texto_limpo:
    iniciar_checklist("before start")
  elif "after start" in texto_limpo and "checklist" in texto_limpo:
    iniciar_checklist("after start")
  elif "taxi" in texto_limpo and "checklist" in texto_limpo:
    iniciar_checklist("taxi")
  elif (
      "line up" in texto_limpo or "lineup" in texto_limpo
  ) and "checklist" in texto_limpo:
    iniciar_checklist("line-up")
  elif "approach" in texto_limpo and "checklist" in texto_limpo:
    iniciar_checklist("approach")
  elif (
      "landing" in texto_limpo
      and "after" not in texto_limpo
      and "checklist" in texto_limpo
  ):
    iniciar_checklist("landing")
  elif "after landing" in texto_limpo and "checklist" in texto_limpo:
    iniciar_checklist("after landing")
  elif "parking" in texto_limpo and "checklist" in texto_limpo:
    iniciar_checklist("parking")
  elif "pack one on" in texto_limpo or "pack 1 on" in texto_limpo:
    log_e_falar("Pack one on, check.")
  elif "pack two on" in texto_limpo or "pack 2 on" in texto_limpo:
    log_e_falar("Pack two on, check.")
  elif "flaps one" in texto_limpo or "flaps 1" in texto_limpo:
    log_e_falar("Speed check, flaps 1.", "Flaps 1")
    pyautogui.press("f7")
  elif "flaps two" in texto_limpo or "flaps 2" in texto_limpo:
    log_e_falar("Speed check, flaps 2.", "Flaps 2")
    pyautogui.press("f7")
    pyautogui.press("f7")
  elif "flaps three" in texto_limpo or "flaps 3" in texto_limpo:
    log_e_falar("Speed check, flaps 3.", "Flaps 3")
    pyautogui.press("f7")
    pyautogui.press("f7")
    pyautogui.press("f7")
  elif "flaps full" in texto_limpo:
    log_e_falar("Speed check, flaps full.", "Flaps full")
    pyautogui.press("f8")
  elif "arm spoilers" in texto_limpo or "armar spoilers" in texto_limpo:
    pyautogui.hotkey("shift", "/")
  elif "cabin crew takeoff" in texto_limpo or "crew takeoff" in texto_limpo:
    log_e_falar("Cabin crew, takeoff.", "Tripulação decolagem")
    pyautogui.hotkey("ctrl", "shift", "a")
    estado_voo["tripulacao_dec_disparada"] = True
  elif "cabin crew landing" in texto_limpo or "crew landing" in texto_limpo:
    log_e_falar("Cabin crew, landing.", "Tripulação pouso")
    pyautogui.hotkey("ctrl", "shift", "a")
    estado_voo["tripulacao_pouso_disparada"] = True


# ==========================================
# CAPTURA DE ÁUDIO & MEDIDOR VU
# ==========================================
def callback_audio(indata, frames, time_info, status):
  if estado_checklist["ativa"] or config_volumes["mic_mutado"]:
    return
  audio_modificado = indata * config_volumes["mic_gain"]
  audio_queue.put(audio_modificado.copy())


def loop_escuta():
  LIMIAR_VOLUME = 0.035
  BLOCOS_SILENCIO_FIM = 8

  gravando = False
  buffer_fala = []
  blocos_silencio = 0

  while True:
    try:
      in_dev = config_volumes["input_device"]
      with sd.InputStream(
          device=in_dev,
          samplerate=SAMPLE_RATE,
          blocksize=1600,
          dtype="float32",
          channels=1,
          callback=callback_audio,
      ):
        while True:
          if config_volumes["input_device"] != in_dev:
            break

          bloco = audio_queue.get().flatten()
          if estado_checklist["ativa"] or config_volumes["mic_mutado"]:
            gravando = False
            buffer_fala = []
            blocos_silencio = 0
            atualizar_vu_meter(0.0)
            continue

          volume_rms = float(np.sqrt(np.mean(bloco**2)))
          atualizar_vu_meter(volume_rms)

          if volume_rms > LIMIAR_VOLUME:
            if not gravando:
              gravando = True
              buffer_fala = []
            buffer_fala.append(bloco)
            blocos_silencio = 0
          elif gravando:
            buffer_fala.append(bloco)
            blocos_silencio += 1

            if blocos_silencio >= BLOCOS_SILENCIO_FIM:
              gravando = False
              audio_completo = np.concatenate(buffer_fala)
              buffer_fala = []

              if len(audio_completo) > SAMPLE_RATE * 0.8:
                segments, _ = whisper_model.transcribe(
                    audio_completo,
                    language="en",
                    initial_prompt=AVIATION_PROMPT,
                    beam_size=1,
                )
                texto_final = " ".join([seg.text for seg in segments]).strip()
                if texto_final:
                  tratar_comando_voz(texto_final)
    except Exception:
      time.sleep(2)


# ==========================================
# INTERFACE GRÁFICA MODERNA (AIRBUS ECAM STYLE)
# ==========================================
root = tk.Tk()
root.title("PilotMonitoring FBW — A320neo Copilot")
root.geometry("680x760")
root.configure(bg="#0b0e14")

COR_BG = "#0b0e14"
COR_CARD = "#131822"
COR_BORDA = "#1f2937"
COR_TEXTO = "#f1f5f9"
COR_SUBTEXTO = "#94a3b8"
COR_ECAM_VERDE = "#00e676"
COR_ECAM_CIANO = "#00e5ff"
COR_ECAM_AMBAR = "#ffab00"
COR_ECAM_VERMELHO = "#ff5252"

style = ttk.Style()
style.theme_use("clam")
style.configure(
    "ECAM.TCombobox",
    fieldbackground="#161b22",
    background="#21262d",
    foreground="#00e5ff",
    arrowcolor="#00e5ff",
    bordercolor="#30363d",
    lightcolor="#161b22",
    darkcolor="#161b22",
)

style.map(
  "ECAM.TCombobox",
    fieldbackground=[("readonly", "#161b22"), ("disabled", "#0d1117")],
    foreground=[("readonly", "#00e5ff"), ("disabled", "#484f58")],
    selectbackground=[("readonly", "#161b22")],
    selectforeground=[("readonly", "#00e5ff")],  
)

root.option_add("*TCombobox*Listbox.background", "#161b22")
root.option_add("*TCombobox*Listbox.foreground", "#e6edf3")
root.option_add("*TCombobox*Listbox.selectBackground", "#00e5ff")
root.option_add("*TCombobox*Listbox.selectForeground", "#0d1117")

style.configure(
    "Airbus.Horizontal.TProgressbar",
    troughcolor="#1e293b",
    background=COR_ECAM_CIANO,
    bordercolor="#1e293b",
    lightcolor=COR_ECAM_CIANO,
    darkcolor=COR_ECAM_CIANO,
)
style.configure(
    "VU.Horizontal.TProgressbar",
    troughcolor="#1e293b",
    background=COR_ECAM_VERDE,
    bordercolor="#1e293b",
)

# --- HEADER ---
frame_top = tk.Frame(
    root, bg=COR_CARD, highlightbackground=COR_BORDA, highlightthickness=1
)
frame_top.pack(fill="x", padx=14, pady=(12, 6))

lbl_title = tk.Label(
    frame_top,
    text="✈ A320NEO FLIGHT DECK ASSISTANT",
    bg=COR_CARD,
    fg=COR_ECAM_CIANO,
    font=("Consolas", 12, "bold"),
)
lbl_title.pack(side="left", padx=12, pady=10)

lbl_status = tk.Label(
    frame_top,
    text="● SEARCHING MSFS...",
    bg="#2a1c15",
    fg=COR_ECAM_AMBAR,
    font=("Consolas", 9, "bold"),
    padx=10,
    pady=4,
)
lbl_status.pack(side="right", padx=12, pady=8)

# --- PAINEL DE ÁUDIO E TELEMETRIA DE VOZ ---
frame_audio = tk.LabelFrame(
    root,
    text=" AUDIO & VOICE CONTROL (ACP) ",
    bg=COR_CARD,
    fg=COR_SUBTEXTO,
    font=("Consolas", 9, "bold"),
    bd=1,
    relief="solid",
    highlightbackground=COR_BORDA,
)
frame_audio.pack(fill="x", padx=14, pady=6)

try:
  all_devices = sd.query_devices()
  mic_list = [
      (d["name"], i)
      for i, d in enumerate(all_devices)
      if d["max_input_channels"] > 0
  ]
  out_list = [
      (d["name"], i)
      for i, d in enumerate(all_devices)
      if d["max_output_channels"] > 0
  ]
except Exception:
  mic_list = [("Default Microphone", None)]
  out_list = [("Default Speaker", None)]

mic_names = [m[0] for m in mic_list]
out_names = [o[0] for o in out_list]


def selecionar_mic(event):
  idx_sel = combo_mic.current()
  if idx_sel >= 0:
    config_volumes["input_device"] = mic_list[idx_sel][1]


def selecionar_out(event):
  idx_sel = combo_out.current()
  if idx_sel >= 0:
    config_volumes["output_device"] = out_list[idx_sel][1]


def atualizar_vol_mic(val):
  config_volumes["mic_gain"] = float(val)


def atualizar_vol_app(val):
  config_volumes["app_volume"] = float(val)


def alternar_mute_mic():
  config_volumes["mic_mutado"] = not config_volumes["mic_mutado"]
  if config_volumes["mic_mutado"]:
    btn_mute.config(
        text="🔇 MIC MUTED (CLICK TO UNMUTE)",
        bg="#3b1818",
        fg=COR_ECAM_VERMELHO,
    )
    vu_bar["value"] = 0
  else:
    btn_mute.config(
        text="🎙️ MIC ACTIVE (LISTENING)", bg="#132e22", fg=COR_ECAM_VERDE
    )


tk.Label(
    frame_audio,
    text="MIC INPUT:",
    bg=COR_CARD,
    fg=COR_TEXTO,
    font=("Consolas", 9),
).grid(row=0, column=0, sticky="w", padx=10, pady=5)
combo_mic = ttk.Combobox(
    frame_audio, values=mic_names, state="readonly", font=("Segoe UI", 9), style="ECAM.TCombobox"
)
if mic_names:
  combo_mic.current(0)
  config_volumes["input_device"] = mic_list[0][1]
combo_mic.grid(row=0, column=1, columnspan=2, padx=10, pady=5, sticky="ew")
combo_mic.bind("<<ComboboxSelected>>", selecionar_mic)

tk.Label(
    frame_audio,
    text="AUDIO OUT:",
    bg=COR_CARD,
    fg=COR_TEXTO,
    font=("Consolas", 9),
).grid(row=1, column=0, sticky="w", padx=10, pady=5)
combo_out = ttk.Combobox(
    frame_audio, values=out_names, state="readonly", font=("Segoe UI", 9), style="ECAM.TCombobox",
)
if out_names:
  combo_out.current(0)
  config_volumes["output_device"] = out_list[0][1]
combo_out.grid(row=1, column=1, columnspan=2, padx=10, pady=5, sticky="ew")
combo_out.bind("<<ComboboxSelected>>", selecionar_out)

tk.Label(
    frame_audio,
    text="MIC GAIN:",
    bg=COR_CARD,
    fg=COR_TEXTO,
    font=("Consolas", 9),
).grid(row=2, column=0, sticky="w", padx=10, pady=4)
slider_mic = tk.Scale(
    frame_audio,
    from_=0.2,
    to=3.0,
    resolution=0.1,
    orient="horizontal",
    bg=COR_CARD,
    fg=COR_TEXTO,
    highlightthickness=0,
    troughcolor="#1e293b",
    activebackground=COR_ECAM_CIANO,
    command=atualizar_vol_mic,
)
slider_mic.set(1.0)
slider_mic.grid(row=2, column=1, columnspan=2, padx=10, pady=2, sticky="ew")

tk.Label(
    frame_audio,
    text="COPILOT VOL:",
    bg=COR_CARD,
    fg=COR_TEXTO,
    font=("Consolas", 9),
).grid(row=3, column=0, sticky="w", padx=10, pady=4)
slider_app = tk.Scale(
    frame_audio,
    from_=0.0,
    to=2.0,
    resolution=0.1,
    orient="horizontal",
    bg=COR_CARD,
    fg=COR_TEXTO,
    highlightthickness=0,
    troughcolor="#1e293b",
    activebackground=COR_ECAM_CIANO,
    command=atualizar_vol_app,
)
slider_app.set(1.0)
slider_app.grid(row=3, column=1, columnspan=2, padx=10, pady=2, sticky="ew")

tk.Label(
    frame_audio,
    text="MIC LEVEL:",
    bg=COR_CARD,
    fg=COR_SUBTEXTO,
    font=("Consolas", 8),
).grid(row=4, column=0, sticky="w", padx=10, pady=(4, 8))
vu_bar = ttk.Progressbar(
    frame_audio,
    orient="horizontal",
    maximum=100,
    mode="determinate",
    style="VU.Horizontal.TProgressbar",
)
vu_bar.grid(row=4, column=1, padx=10, pady=(4, 8), sticky="ew")

btn_mute = tk.Button(
    frame_audio,
    text="🎙️ MIC ACTIVE (LISTENING)",
    bg="#132e22",
    fg=COR_ECAM_VERDE,
    font=("Consolas", 8, "bold"),
    bd=0,
    padx=10,
    pady=4,
    cursor="hand2",
    command=alternar_mute_mic,
)
btn_mute.grid(row=4, column=2, padx=10, pady=(4, 8), sticky="e")

frame_audio.columnconfigure(1, weight=1)

# --- ACIONAMENTO RÁPIDO DE CHECKLISTS ---
frame_botoes = tk.LabelFrame(
    root,
    text=" ECAM CHECKLISTS (VOICE OR CLICK) ",
    bg=COR_CARD,
    fg=COR_SUBTEXTO,
    font=("Consolas", 9, "bold"),
    bd=1,
    relief="solid",
)
frame_botoes.pack(fill="x", padx=14, pady=6)

nomes_botoes = [
    ("COCKPIT PREP", "cockpit preparation"),
    ("BEFORE START", "before start"),
    ("AFTER START", "after start"),
    ("TAXI", "taxi"),
    ("LINE-UP", "line-up"),
    ("APPROACH", "approach"),
    ("LANDING", "landing"),
    ("AFTER LANDING", "after landing"),
    ("PARKING", "parking"),
]

for idx, (label_btn, chave_chk) in enumerate(nomes_botoes):
  r, c = divmod(idx, 4)
  btn = tk.Button(
      frame_botoes,
      text=label_btn,
      bg="#1e293b",
      fg=COR_TEXTO,
      activebackground="#334155",
      activeforeground=COR_ECAM_CIANO,
      font=("Consolas", 8, "bold"),
      bd=0,
      pady=6,
      cursor="hand2",
      command=lambda k=chave_chk: iniciar_checklist(k),
  )
  btn.grid(row=r, column=c, padx=5, pady=5, sticky="ew")
  frame_botoes.columnconfigure(c, weight=1)

# --- PROGRESSO DA CHECKLIST ATUAL ---
frame_checklist_visual = tk.Frame(
    root, bg=COR_CARD, highlightbackground=COR_BORDA, highlightthickness=1
)
frame_checklist_visual.pack(fill="x", padx=14, pady=6)

top_prog = tk.Frame(frame_checklist_visual, bg=COR_CARD)
top_prog.pack(fill="x", padx=10, pady=(6, 2))

lbl_progresso_status = tk.Label(
    top_prog,
    text="STANDBY — AGUARDANDO COMANDO...",
    bg=COR_CARD,
    fg=COR_ECAM_CIANO,
    font=("Consolas", 9, "bold"),
    anchor="w",
)
lbl_progresso_status.pack(side="left", fill="x", expand=True)

btn_stop = tk.Button(
    top_prog,
    text="⏹ CANCELAR",
    bg="#3b1818",
    fg=COR_ECAM_VERMELHO,
    font=("Consolas", 8, "bold"),
    bd=0,
    padx=8,
    pady=2,
    cursor="hand2",
    command=parar_checklist,
)
btn_stop.pack(side="right")

progress_bar = ttk.Progressbar(
    frame_checklist_visual,
    orient="horizontal",
    mode="determinate",
    style="Airbus.Horizontal.TProgressbar",
)
progress_bar.pack(fill="x", padx=10, pady=(4, 10))

# --- TERMINAL DE COMUNICAÇÃO INTEGRADO ---
frame_terminal = tk.LabelFrame(
    root,
    text=" COCKPIT COM LOG ",
    bg=COR_CARD,
    fg=COR_SUBTEXTO,
    font=("Consolas", 9, "bold"),
    bd=1,
    relief="solid",
)
frame_terminal.pack(fill="both", expand=True, padx=14, pady=(6, 12))

txt_logs = scrolledtext.ScrolledText(
    frame_terminal,
    bg="#07090d",
    fg=COR_ECAM_VERDE,
    insertbackground="white",
    font=("Consolas", 9),
    bd=0,
    highlightthickness=0,
)
txt_logs.pack(fill="both", expand=True, padx=8, pady=8)


def atualizar_gui_logs(texto, cor="#00e676"):
  def _insert():
    tag_name = f"cor_{cor}"
    txt_logs.tag_config(tag_name, foreground=cor)
    txt_logs.insert(tk.END, texto, tag_name)
    txt_logs.see(tk.END)

  root.after(0, _insert)


def atualizar_vu_meter(rms):
  nivel = min(100, int((rms / 0.12) * 100))
  root.after(0, lambda: vu_bar.configure(value=nivel))


def atualizar_status_sim(conectado):
  def _status():
    if conectado:
      lbl_status.config(
          text="● MSFS CONNECTED", bg="#132e22", fg=COR_ECAM_VERDE
      )
    else:
      lbl_status.config(
          text="● SEARCHING MSFS...", bg="#2a1c15", fg=COR_ECAM_AMBAR
      )

  root.after(0, _status)


if __name__ == "__main__":
  atualizar_gui_logs(
      "System initialized. Ready for flight operations.\n", COR_ECAM_CIANO
  )
  threading.Thread(target=loop_escuta, daemon=True).start()
  threading.Thread(target=monitorar_simulador, daemon=True).start()
  root.mainloop()
import streamlit as st
import datetime
import json
import base64
import io as pyio
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Boolean, DateTime, Text, inspect, text
)
from sqlalchemy.orm import declarative_base, sessionmaker, scoped_session
from sqlalchemy.exc import IntegrityError

try:
    from streamlit_autorefresh import st_autorefresh
    AUTOREFRESH_AVAILABLE = True
except ImportError:
    AUTOREFRESH_AVAILABLE = False

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

try:
    from fpdf import FPDF
    FPDF_AVAILABLE = True
except ImportError:
    FPDF_AVAILABLE = False

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import openpyxl  # noqa: F401  (nur für pandas ExcelWriter benötigt)
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False

# ---------------------------------------------------------------------------
# GRUNDKONFIGURATION
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Bienen-Logbuch",
    page_icon="🐝",
    layout="centered",
    initial_sidebar_state="expanded",
)

DEFAULT_IMKER = ["Niklas", "Gina", "Leander", "Oliver"]

VORGANG_ZAEHLUNG = "Volk zählen"
VORGANG_DURCHSICHT = "Durchsicht (Stockkarte)"
VORGANG_BEHANDLUNG = "Behandlung (Stockkarte)"
VORGANG_ERNTE = "Ernte / Schleuderung (Stockkarte)"
VORGANG_SCHWARMKONTROLLE = "Schwarmkontrolle"
GESCHUETZTE_VORGAENGE = {VORGANG_ZAEHLUNG, VORGANG_DURCHSICHT, VORGANG_BEHANDLUNG, VORGANG_ERNTE, VORGANG_SCHWARMKONTROLLE}

DEFAULT_VORGAENGE = [
    VORGANG_SCHWARMKONTROLLE, "Honigraum aufgesetzt", "Honigraum entnommen",
    "Königin gesichtet", "Königin markiert", "Varroa-Behandlung",
    "Fütterung", "Ablegerbildung", "Waben erneuert", "Allgemeine Durchsicht",
    "Winterbehandlung", "Erstfrühjahrskontrolle", "Sonstiges",
    VORGANG_ZAEHLUNG, VORGANG_DURCHSICHT, VORGANG_BEHANDLUNG, VORGANG_ERNTE,
]
STATUS_OPTIONS = ["🟢 Alles top", "🟡 Beobachten", "🔴 Kritisch"]

WEATTER_CODES = {
    0: "Klarer Himmel", 1: "Überwiegend klar", 2: "Teilweise bewölkt", 3: "Bedeckt",
    45: "Nebel", 48: "Reifnebel",
    51: "Leichter Nieselregen", 53: "Nieselregen", 55: "Starker Nieselregen",
    61: "Leichter Regen", 63: "Regen", 65: "Starker Regen",
    71: "Leichter Schneefall", 73: "Schneefall", 75: "Starker Schneefall",
    80: "Leichte Regenschauer", 81: "Regenschauer", 82: "Heftige Regenschauer",
    95: "Gewitter", 96: "Gewitter mit Hagel", 99: "Starkes Gewitter mit Hagel",
}
STURM_CODES = {95, 96, 99}
REGEN_CODES = {51, 53, 55, 61, 63, 65, 71, 73, 75, 80, 81, 82, 95, 96, 99}
TSIS_URL = "https://tsis.fli.de/"

NAV_ITEMS = [
    (":material/dashboard:", "Dashboard"),
    (":material/edit_note:", "Logbuch"),
    (":material/inventory_2:", "Material"),
    (":material/task_alt:", "Aufgaben"),
    (":material/calendar_month:", "Kalender"),
    (":material/settings:", "Verwaltung"),
    (":material/payments:", "Imker-Kasse"),
]

# ---------------------------------------------------------------------------
# ZUSATZ-CSS: Bienenwaben-Hintergrund, goldener Glanz beim aktiven Reiter
# (Grundfarben kommen aus .streamlit/config.toml)
# ---------------------------------------------------------------------------
CUSTOM_CSS = """
<style>
    .stApp {
        background-color: #16211B;
        background-image: url("data:image/svg+xml,%3Csvg%20xmlns='http://www.w3.org/2000/svg'%20width='52'%20height='90'%20viewBox='0%200%2052%2090'%3E%3Cg%20fill='none'%20stroke='%23D9A441'%20stroke-opacity='0.16'%20stroke-width='1.5'%3E%3Cpolygon%20points='0,-30%2026,-15%2026,15%200,30%20-26,15%20-26,-15'/%3E%3Cpolygon%20points='26,15%2052,30%2052,60%2026,75%200,60%200,30'/%3E%3C/g%3E%3C/svg%3E");
        background-repeat: repeat;
        background-attachment: fixed;
    }
    section[data-testid="stSidebar"] {
        background-color: #182620;
        background-image: url("data:image/svg+xml,%3Csvg%20xmlns='http://www.w3.org/2000/svg'%20width='52'%20height='90'%20viewBox='0%200%2052%2090'%3E%3Cg%20fill='none'%20stroke='%23D9A441'%20stroke-opacity='0.16'%20stroke-width='1.5'%3E%3Cpolygon%20points='0,-30%2026,-15%2026,15%200,30%20-26,15%20-26,-15'/%3E%3Cpolygon%20points='26,15%2052,30%2052,60%2026,75%200,60%200,30'/%3E%3C/g%3E%3C/svg%3E");
        background-repeat: repeat;
        border-right: 1px solid rgba(217,164,65,0.15);
    }

    h1, h2, h3 { letter-spacing: 0.2px; }
    section[data-testid="stSidebar"] .sidebar-tagline {
        color: #8A8F9C !important; font-size: 0.8em; margin-top: -8px; margin-bottom: 14px;
    }

    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 14px !important;
        border: 1px solid rgba(217, 164, 65, 0.25) !important;
        background-color: rgba(22, 33, 27, 0.55) !important;
        transition: border-color 0.15s ease;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:hover {
        border-color: rgba(217, 164, 65, 0.55) !important;
    }
    div[data-testid="stForm"] {
        border-radius: 14px !important;
        border: 1px solid rgba(217, 164, 65, 0.25) !important;
        background-color: rgba(22, 33, 27, 0.55) !important;
    }

    .stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"],
    .stDownloadButton > button[kind="primary"], .stLinkButton > a[kind="primary"] {
        background-color: #D9A441 !important; color: #12151C !important;
        font-weight: 600 !important; border: none !important; border-radius: 8px !important;
    }
    .stButton > button[kind="primary"]:hover, .stFormSubmitButton > button[kind="primary"]:hover,
    .stDownloadButton > button[kind="primary"]:hover { background-color: #C08F35 !important; }
    .stButton > button[kind="primary"] *, .stFormSubmitButton > button[kind="primary"] *,
    .stDownloadButton > button[kind="primary"] * { color: #12151C !important; }

    .stButton > button[kind="secondary"] { border-radius: 8px !important; }

    section[data-testid="stSidebar"] .stButton > button {
        background-color: transparent !important; border: none !important; box-shadow: none !important;
        text-align: left !important; justify-content: flex-start !important;
        font-weight: 500 !important; border-radius: 10px !important; padding: 0.65rem 1rem !important;
        margin-bottom: 2px;
        transition: background-color 0.15s ease, box-shadow 0.15s ease;
    }
    section[data-testid="stSidebar"] .stButton > button:hover { background-color: rgba(217,164,65,0.10) !important; }
    section[data-testid="stSidebar"] button[kind="primary"] {
        background-color: rgba(217,164,65,0.22) !important; color: #D9A441 !important; font-weight: 700 !important;
        box-shadow: 0 0 16px rgba(217,164,65,0.30), inset 0 0 0 1px rgba(217,164,65,0.45) !important;
    }
    section[data-testid="stSidebar"] button[kind="primary"] * { color: #D9A441 !important; }

    .stTabs [aria-selected="true"] { color: #D9A441 !important; }

    .badge-nachtrag {
        background-color: rgba(239, 68, 68, 0.85); color: #FFFFFF !important;
        padding: 2px 8px; border-radius: 6px; font-size: 0.75em; font-weight: 700;
    }
    .badge-stockkarte {
        background-color: rgba(217, 164, 65, 0.20); color: #D9A441 !important;
        padding: 2px 8px; border-radius: 6px; font-size: 0.72em; font-weight: 600;
        border: 1px solid rgba(217,164,65,0.4);
    }
    .badge-auto {
        background-color: rgba(96, 165, 250, 0.20); color: #93C5FD !important;
        padding: 2px 8px; border-radius: 6px; font-size: 0.72em; font-weight: 600;
        border: 1px solid rgba(96,165,250,0.4);
    }
    .flug-card {
        border-radius: 10px; border: 1px solid rgba(217,164,65,0.28);
        padding: 10px 14px; text-align: center;
    }

    .fixed-footer {
        position: fixed; left: 0; bottom: 0; width: 100%;
        background-color: #1B1F2A; color: #D9A441 !important; text-align: center;
        padding: 8px 0; font-weight: 600; font-size: 0.85em; letter-spacing: 0.3px;
        border-top: 1px solid rgba(217,164,65,0.30); z-index: 999;
        text-shadow: 0 0 8px rgba(217,164,65,0.65), 0 0 18px rgba(217,164,65,0.25);
    }
    .fixed-footer span[data-testid="stIconMaterial"] {
        vertical-align: middle; font-size: 1.1em;
        filter: drop-shadow(0 0 6px rgba(217,164,65,0.7));
    }
    .block-container { padding-bottom: 60px; }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# DATENBANK-MODELLE
# ---------------------------------------------------------------------------
Base = declarative_base()


class Imker(Base):
    __tablename__ = "imker"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)


class Standort(Base):
    __tablename__ = "standorte"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    lat = Column(Float)
    lon = Column(Float)


class Volk(Base):
    __tablename__ = "voelker"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    status = Column(String, default="🟢 Alles top")
    archiviert = Column(Boolean, default=False)
    standort_id = Column(Integer, nullable=True)
    mutter_volk = Column(String, nullable=True)
    koenigin_jahr = Column(Integer, nullable=True)
    koenigin_herkunft = Column(String, nullable=True)
    koenigin_gezeichnet = Column(Boolean, default=False)
    koenigin_fluegel_beschnitten = Column(Boolean, default=False)
    beutenart = Column(String, nullable=True)
    raehmchenmass = Column(String, nullable=True)


class Vorgang(Base):
    __tablename__ = "vorgaenge"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)


class LogEintrag(Base):
    __tablename__ = "log_eintraege"
    id = Column(Integer, primary_key=True)
    imker = Column(String)
    volk = Column(String)
    vorgang = Column(String)
    status = Column(String)
    notiz = Column(Text)
    zeitpunkt = Column(DateTime)
    is_nachtrag = Column(Boolean, default=False)
    wetter_temp = Column(Float, nullable=True)
    wetter_text = Column(String, nullable=True)
    foto_data = Column(Text, nullable=True)
    foto_dateiname = Column(String, nullable=True)
    bienenzahl = Column(Integer, nullable=True)
    wabengassen_besetzt = Column(Integer, nullable=True)
    sanftmut = Column(String, nullable=True)
    stifte_gesichtet = Column(Boolean, nullable=True)
    brut_offen = Column(Boolean, nullable=True)
    brut_verdeckelt = Column(Boolean, nullable=True)
    anzahl_brutwaben = Column(Integer, nullable=True)
    schwarmzellen = Column(String, nullable=True)
    schwarm_massnahme = Column(String, nullable=True)
    baurahmen = Column(Boolean, nullable=True)
    honigraum_aufgesetzt = Column(Boolean, nullable=True)
    varroa_milbenfall = Column(Float, nullable=True)
    behandlung_mittel = Column(String, nullable=True)
    behandlung_menge = Column(String, nullable=True)
    behandlung_charge = Column(String, nullable=True)
    behandlung_wartezeit = Column(String, nullable=True)
    fuetterung_futterart = Column(String, nullable=True)
    fuetterung_menge = Column(Float, nullable=True)
    ernte_kg = Column(Float, nullable=True)
    ernte_trachtart = Column(String, nullable=True)
    ernte_wassergehalt = Column(Float, nullable=True)


class Aufgabe(Base):
    __tablename__ = "aufgaben"
    id = Column(Integer, primary_key=True)
    titel = Column(String)
    zugewiesen_an = Column(String)
    faellig_am = Column(String)
    erledigt = Column(Boolean, default=False)
    volk = Column(String, nullable=True)
    vorgang = Column(String, nullable=True)
    quelle = Column(String, default="manuell")


class KassenEintrag(Base):
    __tablename__ = "kasse"
    id = Column(Integer, primary_key=True)
    typ = Column(String)
    betrag = Column(Float)
    person = Column(String)
    beschreibung = Column(Text)
    zeitpunkt = Column(DateTime)
    is_nachtrag = Column(Boolean, default=False)


class InventarItem(Base):
    __tablename__ = "inventar"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    menge = Column(Float, default=0)
    einheit = Column(String, default="Stück")


class Reservierung(Base):
    __tablename__ = "reservierungen"
    id = Column(Integer, primary_key=True)
    kunde_name = Column(String)
    glaeser = Column(Integer)
    sorte = Column(String, nullable=True)
    status = Column(String, default="Reserviert")
    notiz = Column(Text, nullable=True)
    erstellt_am = Column(DateTime)


class Abwesenheit(Base):
    __tablename__ = "abwesenheiten"
    id = Column(Integer, primary_key=True)
    person = Column(String)
    von_datum = Column(DateTime)
    bis_datum = Column(DateTime)
    notiz = Column(Text, nullable=True)


class Einstellung(Base):
    __tablename__ = "einstellungen"
    id = Column(Integer, primary_key=True)
    schluessel = Column(String, unique=True)
    wert = Column(String)


def run_migrations(engine):
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.tables.values():
            if not inspector.has_table(table.name):
                continue
            existing_cols = {c["name"] for c in inspector.get_columns(table.name)}
            for col in table.columns:
                if col.name not in existing_cols:
                    try:
                        col_type = col.type.compile(dialect=engine.dialect)
                        conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN {col.name} {col_type}'))
                    except Exception:
                        pass


@st.cache_resource
def get_engine():
    db_url = st.secrets.get("DB_URL", "sqlite:///bienen.db")
    connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}
    engine = create_engine(db_url, connect_args=connect_args, pool_pre_ping=True)
    Base.metadata.create_all(engine)
    run_migrations(engine)
    return engine


def ist_dauerhafte_datenbank():
    """True, wenn eine echte Cloud-Datenbank (z.B. Supabase) konfiguriert ist.
    False, wenn auf die lokale, bei jedem Neustart geleerte SQLite-Datei zurückgefallen wird."""
    db_url = st.secrets.get("DB_URL", None)
    return bool(db_url) and not db_url.startswith("sqlite")


def get_db():
    engine = get_engine()
    Session = scoped_session(sessionmaker(bind=engine))
    return Session()


def get_setting(schluessel, default=None):
    db = get_db()
    try:
        e = db.query(Einstellung).filter(Einstellung.schluessel == schluessel).first()
        return e.wert if e else default
    finally:
        db.close()


def set_setting(schluessel, wert):
    db = get_db()
    try:
        e = db.query(Einstellung).filter(Einstellung.schluessel == schluessel).first()
        if e:
            e.wert = str(wert)
        else:
            db.add(Einstellung(schluessel=schluessel, wert=str(wert)))
        db.commit()
    finally:
        db.close()


def seed_defaults():
    db = get_db()
    try:
        if db.query(Imker).count() == 0:
            for name in DEFAULT_IMKER:
                db.add(Imker(name=name))
            try:
                db.commit()
            except IntegrityError:
                db.rollback()

        if db.query(Vorgang).count() == 0:
            for name in DEFAULT_VORGAENGE:
                db.add(Vorgang(name=name))
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
        else:
            vorhandene = {v.name for v in db.query(Vorgang).all()}
            for name in [VORGANG_ZAEHLUNG, VORGANG_DURCHSICHT, VORGANG_BEHANDLUNG, VORGANG_ERNTE]:
                if name not in vorhandene:
                    db.add(Vorgang(name=name))
            try:
                db.commit()
            except IntegrityError:
                db.rollback()

        if db.query(Standort).count() == 0:
            db.add(Standort(name="Hauptstandort", lat=50.9375, lon=6.9603))
            try:
                db.commit()
            except IntegrityError:
                db.rollback()

        if db.query(Volk).count() == 0:
            db.add(Volk(name="Volk 1"))
            db.add(Volk(name="Volk 2"))
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
    finally:
        db.close()


seed_defaults()

# ---------------------------------------------------------------------------
# HELFER
# ---------------------------------------------------------------------------
def format_ts(dt):
    if dt is None:
        return "-"
    return dt.strftime("%d.%m.%Y %H:%M")


def parse_datum(s):
    if not s:
        return None
    try:
        return datetime.datetime.strptime(s, "%d.%m.%Y").date()
    except Exception:
        return None


def strip_emoji_prefix(status):
    if not status:
        return status
    teile = status.split(" ", 1)
    return teile[1] if len(teile) > 1 else status


def zeichnungsfarbe(jahr):
    if not jahr:
        return "-"
    rest = jahr % 5
    mapping = {1: "Weiß", 2: "Gelb", 3: "Rot", 4: "Grün", 0: "Blau"}
    return mapping.get(rest, "-")


def pdf_safe(txt, max_word_len=40):
    if txt is None:
        return ""
    txt = str(txt).encode("latin-1", "ignore").decode("latin-1")
    txt = " ".join(txt.split())
    woerter = txt.split(" ")
    neue_woerter = []
    for w in woerter:
        while len(w) > max_word_len:
            neue_woerter.append(w[:max_word_len])
            w = w[max_word_len:]
        neue_woerter.append(w)
    return " ".join(neue_woerter)


def verarbeite_foto(uploaded_file, max_size=1200, quality=80):
    if uploaded_file is None or not PIL_AVAILABLE:
        return None, None
    try:
        img = Image.open(uploaded_file)
        img = img.convert("RGB")
        img.thumbnail((max_size, max_size))
        buf = pyio.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        return b64, uploaded_file.name
    except Exception:
        return None, None


def hole_wetter_fuer_volk(volk_obj):
    if not REQUESTS_AVAILABLE:
        return None, None
    lat, lon = None, None
    db = get_db()
    try:
        if volk_obj and volk_obj.standort_id:
            s = db.query(Standort).get(volk_obj.standort_id)
            if s:
                lat, lon = s.lat, s.lon
        if lat is None or lon is None:
            erster = db.query(Standort).order_by(Standort.id).first()
            if erster:
                lat, lon = erster.lat, erster.lon
    finally:
        db.close()
    if lat is None or lon is None:
        lat, lon = 50.9375, 6.9603
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
        r = requests.get(url, timeout=5)
        data = r.json()
        cw = data.get("current_weather", {})
        temp = cw.get("temperature")
        code = cw.get("weathercode")
        return temp, WEATTER_CODES.get(code, "Unbekannt")
    except Exception:
        return None, None


def pruefe_unwetter(lat, lon):
    if not REQUESTS_AVAILABLE:
        return False
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=weathercode,windspeed_10m&forecast_days=2"
        r = requests.get(url, timeout=5)
        data = r.json()
        codes = data.get("hourly", {}).get("weathercode", [])[:24]
        winde = data.get("hourly", {}).get("windspeed_10m", [])[:24]
        if any(c in STURM_CODES for c in codes):
            return True
        if any((w or 0) > 60 for w in winde):
            return True
    except Exception:
        pass
    return False


@st.cache_data(ttl=1800)
def pruefe_unwetter_cached(standort_id, lat, lon):
    return pruefe_unwetter(lat, lon)


def hole_flugwetter(lat, lon):
    if not REQUESTS_AVAILABLE:
        return None
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
        r = requests.get(url, timeout=5)
        data = r.json()
        cw = data.get("current_weather", {})
        return cw.get("temperature"), cw.get("windspeed"), cw.get("weathercode")
    except Exception:
        return None


@st.cache_data(ttl=1800)
def hole_flugwetter_cached(standort_id, lat, lon):
    return hole_flugwetter(lat, lon)


def bewerte_flugwetter(temp, wind, code):
    if temp is None:
        return "–", "Keine Daten"
    if code in REGEN_CODES:
        return "❌", "Niederschlag"
    if temp < 10:
        return "❌", "Zu kalt"
    if temp < 14 or (wind or 0) > 25:
        return "⚠️", "Grenzwertig"
    return "✅", "Gutes Flugwetter"


def stammbaum_vorfahren(volk_name, alle_dict, max_tiefe=12):
    kette = [volk_name]
    aktuelle = volk_name
    for _ in range(max_tiefe):
        v = alle_dict.get(aktuelle)
        if v and v.mutter_volk and v.mutter_volk in alle_dict and v.mutter_volk not in kette:
            kette.append(v.mutter_volk)
            aktuelle = v.mutter_volk
        else:
            break
    return list(reversed(kette))


def stammbaum_nachkommen(volk_name, alle_voelker):
    return [v.name for v in alle_voelker if v.mutter_volk == volk_name]


def safe_pdf_line(pdf, line_text, size=10, style=""):
    if not line_text:
        return
    try:
        pdf.set_font("Helvetica", style, size)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(0, 6, pdf_safe(line_text))
    except Exception:
        try:
            pdf.set_x(pdf.l_margin)
            pdf.ln(6)
        except Exception:
            pass


def erstelle_stockkarte_pdf(volk, standort_name, eintraege):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    safe_pdf_line(pdf, f"Stockkarte - {volk.name}", size=16, style="B")
    safe_pdf_line(pdf, f"Erstellt am {datetime.datetime.now().strftime('%d.%m.%Y %H:%M')}", size=9)
    pdf.ln(2)

    safe_pdf_line(pdf, "1. Stammdaten", size=13, style="B")
    zeichnung = zeichnungsfarbe(volk.koenigin_jahr)
    stammdaten_zeilen = [
        f"Volk: {volk.name}",
        f"Standort: {standort_name or '-'}",
        f"Muttervolk: {volk.mutter_volk or '-'}",
        f"Koenigin Geburtsjahr: {volk.koenigin_jahr or '-'} (Zeichnungsfarbe: {zeichnung})",
        f"Herkunft / Rasse: {volk.koenigin_herkunft or '-'}",
        f"Gezeichnet: {'Ja' if volk.koenigin_gezeichnet else 'Nein'}   Fluegel beschnitten: {'Ja' if volk.koenigin_fluegel_beschnitten else 'Nein'}",
        f"Beutenart: {volk.beutenart or '-'}   Raehmchenmass: {volk.raehmchenmass or '-'}",
    ]
    for zeile in stammdaten_zeilen:
        safe_pdf_line(pdf, zeile, size=10)
    pdf.ln(3)

    durchsicht = [e for e in eintraege if e.vorgang == VORGANG_DURCHSICHT]
    behandlung = [e for e in eintraege if e.vorgang == VORGANG_BEHANDLUNG]
    ernte = [e for e in eintraege if e.vorgang == VORGANG_ERNTE]
    sonstige = [e for e in eintraege if e.vorgang not in (VORGANG_DURCHSICHT, VORGANG_BEHANDLUNG, VORGANG_ERNTE)]

    safe_pdf_line(pdf, "2. Laufende Durchsichten", size=13, style="B")
    if not durchsicht:
        safe_pdf_line(pdf, "Keine Durchsichten erfasst.", size=10, style="I")
    for e in durchsicht:
        safe_pdf_line(pdf, f"{format_ts(e.zeitpunkt)} | {e.imker}", size=10, style="B")
        details = []
        if e.wetter_temp is not None:
            details.append(f"Wetter: {e.wetter_temp:.0f} Grad C, {e.wetter_text}")
        if e.wabengassen_besetzt is not None:
            details.append(f"Besetzte Wabengassen: {e.wabengassen_besetzt}")
        if e.sanftmut:
            details.append(f"Sanftmut: {e.sanftmut}")
        if e.stifte_gesichtet is not None:
            details.append(f"Stifte gesichtet: {'Ja' if e.stifte_gesichtet else 'Nein'}")
        if e.brut_offen is not None or e.brut_verdeckelt is not None:
            details.append(f"Brut: offen={'Ja' if e.brut_offen else 'Nein'}, verdeckelt={'Ja' if e.brut_verdeckelt else 'Nein'}")
        if e.anzahl_brutwaben is not None:
            details.append(f"Anzahl Brutwaben: {e.anzahl_brutwaben}")
        if e.schwarmzellen:
            details.append(f"Schwarmzellen: {e.schwarmzellen}")
        if e.schwarm_massnahme:
            details.append(f"Massnahme: {e.schwarm_massnahme}")
        if e.baurahmen is not None:
            details.append(f"Baurahmen gegeben: {'Ja' if e.baurahmen else 'Nein'}")
        if e.honigraum_aufgesetzt is not None:
            details.append(f"Honigraum aufgesetzt: {'Ja' if e.honigraum_aufgesetzt else 'Nein'}")
        if e.notiz:
            details.append(f"Notiz: {e.notiz}")
        for d in details:
            safe_pdf_line(pdf, "  - " + d, size=9)
        pdf.ln(1)
    pdf.ln(2)

    safe_pdf_line(pdf, "3. Gesundheit & Behandlungen", size=13, style="B")
    if not behandlung:
        safe_pdf_line(pdf, "Keine Behandlungen erfasst.", size=10, style="I")
    for e in behandlung:
        safe_pdf_line(pdf, f"{format_ts(e.zeitpunkt)} | Behandler: {e.imker}", size=10, style="B")
        details = []
        if e.varroa_milbenfall is not None:
            details.append(f"Natuerlicher Milbenfall: {e.varroa_milbenfall} pro Tag")
        if e.behandlung_mittel:
            details.append(f"Mittel: {e.behandlung_mittel}")
        if e.behandlung_menge:
            details.append(f"Menge/Dosierung: {e.behandlung_menge}")
        if e.behandlung_charge:
            details.append(f"Chargennummer: {e.behandlung_charge}")
        if e.behandlung_wartezeit:
            details.append(f"Wartezeit: {e.behandlung_wartezeit}")
        if e.fuetterung_futterart:
            details.append(f"Fuetterung: {e.fuetterung_futterart}, {e.fuetterung_menge or 0} kg/l")
        if e.notiz:
            details.append(f"Notiz: {e.notiz}")
        for d in details:
            safe_pdf_line(pdf, "  - " + d, size=9)
        pdf.ln(1)
    pdf.ln(2)

    safe_pdf_line(pdf, "4. Ertrag & Schleuderung", size=13, style="B")
    if not ernte:
        safe_pdf_line(pdf, "Keine Ernte erfasst.", size=10, style="I")
    for e in ernte:
        safe_pdf_line(pdf, f"{format_ts(e.zeitpunkt)} | {e.imker}", size=10, style="B")
        details = []
        if e.ernte_kg is not None:
            details.append(f"Ertrag: {e.ernte_kg} kg")
        if e.ernte_trachtart:
            details.append(f"Trachtart: {e.ernte_trachtart}")
        if e.ernte_wassergehalt is not None:
            details.append(f"Wassergehalt: {e.ernte_wassergehalt} %")
        if e.notiz:
            details.append(f"Notiz: {e.notiz}")
        for d in details:
            safe_pdf_line(pdf, "  - " + d, size=9)
        pdf.ln(1)
    pdf.ln(2)

    if sonstige:
        safe_pdf_line(pdf, "5. Weitere Logbuch-Eintraege", size=13, style="B")
        for e in sonstige:
            status_text = strip_emoji_prefix(e.status)
            kopf = f"{format_ts(e.zeitpunkt)} | {e.imker} | {e.vorgang} | Status: {status_text}"
            safe_pdf_line(pdf, kopf, size=9)
            if e.notiz:
                safe_pdf_line(pdf, "  Notiz: " + e.notiz, size=9)

    return bytes(pdf.output())


def alle_daten_als_dict(inkl_fotos=True):
    db = get_db()
    try:
        log_columns = [c.name for c in LogEintrag.__table__.columns if inkl_fotos or c.name != "foto_data"]
        data = {
            "imker": [{"name": i.name} for i in db.query(Imker).all()],
            "standorte": [{"name": s.name, "lat": s.lat, "lon": s.lon} for s in db.query(Standort).all()],
            "voelker": [{c.name: getattr(v, c.name) for c in Volk.__table__.columns} for v in db.query(Volk).all()],
            "vorgaenge": [{"name": v.name} for v in db.query(Vorgang).all()],
            "log_eintraege": [
                {c: getattr(e, c) for c in log_columns}
                for e in db.query(LogEintrag).all()
            ],
            "aufgaben": [{c.name: getattr(a, c.name) for c in Aufgabe.__table__.columns} for a in db.query(Aufgabe).all()],
            "kasse": [{c.name: getattr(k, c.name) for c in KassenEintrag.__table__.columns} for k in db.query(KassenEintrag).all()],
            "inventar": [{c.name: getattr(m, c.name) for c in InventarItem.__table__.columns} for m in db.query(InventarItem).all()],
            "reservierungen": [{c.name: getattr(r, c.name) for c in Reservierung.__table__.columns} for r in db.query(Reservierung).all()],
            "abwesenheiten": [{c.name: getattr(a, c.name) for c in Abwesenheit.__table__.columns} for a in db.query(Abwesenheit).all()],
            "einstellungen": [{"schluessel": e.schluessel, "wert": e.wert} for e in db.query(Einstellung).all()],
        }
    finally:
        db.close()
    return data


def erstelle_excel_export():
    if not PANDAS_AVAILABLE or not OPENPYXL_AVAILABLE:
        return None
    daten = alle_daten_als_dict(inkl_fotos=False)
    buffer = pyio.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for key, rows in daten.items():
            df = pd.DataFrame(rows) if rows else pd.DataFrame()
            sheet_name = key[:31]
            df.to_excel(writer, sheet_name=sheet_name, index=False)
    buffer.seek(0)
    return buffer.getvalue()


def _parse_iso_datetime(wert):
    if not wert:
        return None
    try:
        return datetime.datetime.fromisoformat(str(wert))
    except Exception:
        return None


def stelle_backup_wieder_her(daten):
    """Löscht alle bestehenden Daten und spielt den Inhalt eines JSON-Backups ein."""
    db = get_db()
    try:
        for modell in [LogEintrag, KassenEintrag, Aufgabe, InventarItem, Reservierung,
                       Abwesenheit, Volk, Imker, Vorgang, Standort, Einstellung]:
            db.query(modell).delete()
        db.commit()

        for row in daten.get("imker", []):
            db.add(Imker(name=row["name"]))
        for row in daten.get("standorte", []):
            db.add(Standort(name=row["name"], lat=row.get("lat"), lon=row.get("lon")))
        for row in daten.get("vorgaenge", []):
            db.add(Vorgang(name=row["name"]))
        db.commit()

        volk_felder = set(Volk.__table__.columns.keys())
        for row in daten.get("voelker", []):
            db.add(Volk(**{k: v for k, v in row.items() if k in volk_felder}))
        db.commit()

        log_felder = set(LogEintrag.__table__.columns.keys())
        for row in daten.get("log_eintraege", []):
            kwargs = {k: v for k, v in row.items() if k in log_felder}
            if "zeitpunkt" in kwargs:
                kwargs["zeitpunkt"] = _parse_iso_datetime(kwargs["zeitpunkt"])
            db.add(LogEintrag(**kwargs))
        db.commit()

        aufgaben_felder = set(Aufgabe.__table__.columns.keys())
        for row in daten.get("aufgaben", []):
            db.add(Aufgabe(**{k: v for k, v in row.items() if k in aufgaben_felder}))
        db.commit()

        kasse_felder = set(KassenEintrag.__table__.columns.keys())
        for row in daten.get("kasse", []):
            kwargs = {k: v for k, v in row.items() if k in kasse_felder}
            if "zeitpunkt" in kwargs:
                kwargs["zeitpunkt"] = _parse_iso_datetime(kwargs["zeitpunkt"])
            db.add(KassenEintrag(**kwargs))
        db.commit()

        inv_felder = set(InventarItem.__table__.columns.keys())
        for row in daten.get("inventar", []):
            db.add(InventarItem(**{k: v for k, v in row.items() if k in inv_felder}))
        db.commit()

        res_felder = set(Reservierung.__table__.columns.keys())
        for row in daten.get("reservierungen", []):
            kwargs = {k: v for k, v in row.items() if k in res_felder}
            if "erstellt_am" in kwargs:
                kwargs["erstellt_am"] = _parse_iso_datetime(kwargs["erstellt_am"])
            db.add(Reservierung(**kwargs))
        db.commit()

        abw_felder = set(Abwesenheit.__table__.columns.keys())
        for row in daten.get("abwesenheiten", []):
            kwargs = {k: v for k, v in row.items() if k in abw_felder}
            for feld in ("von_datum", "bis_datum"):
                if feld in kwargs:
                    kwargs[feld] = _parse_iso_datetime(kwargs[feld])
            db.add(Abwesenheit(**kwargs))
        db.commit()

        for row in daten.get("einstellungen", []):
            db.add(Einstellung(schluessel=row["schluessel"], wert=row["wert"]))
        db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# DYNAMISCHE ZUSATZFELDER JE NACH VORGANG (für Stockkarte)
# ---------------------------------------------------------------------------
def render_stockkarte_felder(vorgang, keyprefix, defaults=None):
    defaults = defaults or {}
    extra = {}
    if vorgang == VORGANG_ZAEHLUNG:
        st.markdown("##### Zählung")
        extra["bienenzahl"] = st.number_input(
            "Anzahl gezählte Bienen", min_value=0, step=10,
            value=int(defaults.get("bienenzahl") or 0), key=f"{keyprefix}_bienenzahl",
        )
    elif vorgang == VORGANG_DURCHSICHT:
        st.markdown("##### Durchsicht-Details")
        c1, c2 = st.columns(2)
        extra["wabengassen_besetzt"] = c1.number_input(
            "Besetzte Wabengassen", min_value=0, max_value=30, step=1,
            value=int(defaults.get("wabengassen_besetzt") or 0), key=f"{keyprefix}_wabengassen",
        )
        sanftmut_opts = ["Ruhig", "Normal", "Nervös", "Stechlustig"]
        sm_default = defaults.get("sanftmut")
        extra["sanftmut"] = c2.selectbox(
            "Sanftmut / Wabenstetigkeit", sanftmut_opts,
            index=sanftmut_opts.index(sm_default) if sm_default in sanftmut_opts else 0,
            key=f"{keyprefix}_sanftmut",
        )
        c3, c4, c5 = st.columns(3)
        extra["stifte_gesichtet"] = c3.checkbox("Stifte gesichtet", value=bool(defaults.get("stifte_gesichtet")), key=f"{keyprefix}_stifte")
        extra["brut_offen"] = c4.checkbox("Offene Brut", value=bool(defaults.get("brut_offen")), key=f"{keyprefix}_brutoffen")
        extra["brut_verdeckelt"] = c5.checkbox("Verdeckelte Brut", value=bool(defaults.get("brut_verdeckelt")), key=f"{keyprefix}_brutverd")
        extra["anzahl_brutwaben"] = st.number_input(
            "Anzahl Brutwaben", min_value=0, step=1,
            value=int(defaults.get("anzahl_brutwaben") or 0), key=f"{keyprefix}_brutwaben",
        )
        schwarm_opts = ["Keine", "Spielnäpfchen", "Bestiftete Schwarmzellen", "Verdeckelte Schwarmzellen"]
        sz_default = defaults.get("schwarmzellen")
        extra["schwarmzellen"] = st.selectbox(
            "Schwarmzellen", schwarm_opts,
            index=schwarm_opts.index(sz_default) if sz_default in schwarm_opts else 0,
            key=f"{keyprefix}_schwarmzellen",
        )
        extra["schwarm_massnahme"] = st.text_input(
            "Maßnahme (z. B. Zellen gebrochen, Ableger gebildet)",
            value=defaults.get("schwarm_massnahme") or "", key=f"{keyprefix}_massnahme",
        )
        c6, c7 = st.columns(2)
        extra["baurahmen"] = c6.checkbox("Baurahmen/Drohnenrahmen gegeben", value=bool(defaults.get("baurahmen")), key=f"{keyprefix}_baurahmen")
        extra["honigraum_aufgesetzt"] = c7.checkbox("Honigraum aufgesetzt/erweitert", value=bool(defaults.get("honigraum_aufgesetzt")), key=f"{keyprefix}_honigraum")
    elif vorgang == VORGANG_BEHANDLUNG:
        st.markdown("##### Gesundheit & Behandlung")
        extra["varroa_milbenfall"] = st.number_input(
            "Natürlicher Milbenfall (Milben pro Tag)", min_value=0.0, step=0.5,
            value=float(defaults.get("varroa_milbenfall") or 0.0), key=f"{keyprefix}_milbenfall",
        )
        c1, c2 = st.columns(2)
        extra["behandlung_mittel"] = c1.text_input(
            "Verwendetes Mittel (z. B. Ameisensäure 60%)",
            value=defaults.get("behandlung_mittel") or "", key=f"{keyprefix}_mittel",
        )
        extra["behandlung_menge"] = c2.text_input(
            "Menge / Dosierung (z. B. 50 ml)",
            value=defaults.get("behandlung_menge") or "", key=f"{keyprefix}_menge",
        )
        c3, c4 = st.columns(2)
        extra["behandlung_charge"] = c3.text_input(
            "Chargennummer", value=defaults.get("behandlung_charge") or "", key=f"{keyprefix}_charge",
        )
        extra["behandlung_wartezeit"] = c4.text_input(
            "Wartezeit", value=defaults.get("behandlung_wartezeit") or "", key=f"{keyprefix}_wartezeit",
        )
        st.caption("Name des Behandlers wird automatisch aus dem Feld 'Wer bist du?' übernommen.")
        st.markdown("**Fütterung (optional)**")
        c5, c6 = st.columns(2)
        extra["fuetterung_futterart"] = c5.text_input(
            "Futterart (Sirup/Futterteig)", value=defaults.get("fuetterung_futterart") or "", key=f"{keyprefix}_futterart",
        )
        extra["fuetterung_menge"] = c6.number_input(
            "Menge (kg/l)", min_value=0.0, step=0.5,
            value=float(defaults.get("fuetterung_menge") or 0.0), key=f"{keyprefix}_futtermenge",
        )
    elif vorgang == VORGANG_ERNTE:
        st.markdown("##### Ertrag & Schleuderung")
        c1, c2 = st.columns(2)
        extra["ernte_kg"] = c1.number_input(
            "Ertrag (kg)", min_value=0.0, step=0.5,
            value=float(defaults.get("ernte_kg") or 0.0), key=f"{keyprefix}_ernte_kg",
        )
        extra["ernte_trachtart"] = c2.text_input(
            "Trachtart (z. B. Frühtracht/Raps)", value=defaults.get("ernte_trachtart") or "", key=f"{keyprefix}_trachtart",
        )
        extra["ernte_wassergehalt"] = st.number_input(
            "Wassergehalt (%)", min_value=0.0, max_value=30.0, step=0.1,
            value=float(defaults.get("ernte_wassergehalt") or 0.0), key=f"{keyprefix}_wassergehalt",
        )
    return extra


def erstelle_schwarm_timer(volk_name, wer):
    tage = int(get_setting("schwarm_timer_tage", "7") or 7)
    db = get_db()
    try:
        alte = db.query(Aufgabe).filter(
            Aufgabe.volk == volk_name, Aufgabe.quelle == "schwarm_timer", Aufgabe.erledigt == False
        ).all()
        for a in alte:
            a.erledigt = True
        faellig = (datetime.date.today() + datetime.timedelta(days=tage)).strftime("%d.%m.%Y")
        db.add(Aufgabe(
            titel=f"Schwarmkontrolle fällig: {volk_name}", zugewiesen_an=wer,
            faellig_am=faellig, volk=volk_name, vorgang=VORGANG_SCHWARMKONTROLLE, quelle="schwarm_timer",
        ))
        db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# SESSION-STATE GRUNDWERTE
# ---------------------------------------------------------------------------
st.session_state.setdefault("view", "main")
st.session_state.setdefault("detail_volk_id", None)
st.session_state.setdefault("editing_id", None)
st.session_state.setdefault("log_form_version", 0)
st.session_state.setdefault("kasse_form_version", 0)
st.session_state.setdefault("current_page", "Dashboard")

# ---------------------------------------------------------------------------
# SIDEBAR: LOGO & NAVIGATION IM LISTEN-STIL
# ---------------------------------------------------------------------------
st.sidebar.markdown("## :material/hive: Bienen-Logbuch")
st.sidebar.markdown('<div class="sidebar-tagline">Gemeinsames Imker-Logbuch</div>', unsafe_allow_html=True)

for icon, name in NAV_ITEMS:
    aktiv = (st.session_state.view == "main") and (st.session_state.current_page == name)
    if st.sidebar.button(
        name, key=f"nav_{name}", use_container_width=True, icon=icon,
        type="primary" if aktiv else "secondary",
    ):
        st.session_state.current_page = name
        st.session_state.view = "main"
        st.session_state.editing_id = None
        st.rerun()
page = st.session_state.current_page

if not ist_dauerhafte_datenbank():
    st.error(
        "Keine dauerhafte Datenbank-Verbindung gefunden (DB_URL fehlt oder ist falsch). "
        "Alle Eingaben gehen beim nächsten Neustart der App verloren! Bitte in Streamlit "
        "Cloud unter 'Settings → Secrets' prüfen, ob DB_URL korrekt hinterlegt ist.",
        icon=":material/warning:",
    )

# ---------------------------------------------------------------------------
# LIVE-AKTUALISIERUNG
# ---------------------------------------------------------------------------
if AUTOREFRESH_AVAILABLE:
    st_autorefresh(interval=6000, key="auto_refresh")


def check_new_entries():
    db = get_db()
    try:
        last_log = db.query(LogEintrag).order_by(LogEintrag.id.desc()).first()
        last_kasse = db.query(KassenEintrag).order_by(KassenEintrag.id.desc()).first()
    finally:
        db.close()

    current_log_id = last_log.id if last_log else 0
    current_kasse_id = last_kasse.id if last_kasse else 0

    st.session_state.setdefault("seen_log_id", current_log_id)
    st.session_state.setdefault("seen_kasse_id", current_kasse_id)

    if current_log_id > st.session_state.seen_log_id:
        st.toast(f"Neuer Logbuch-Eintrag von {last_log.imker}!", icon=":material/edit_note:")
        st.session_state.seen_log_id = current_log_id
    if current_kasse_id > st.session_state.seen_kasse_id:
        st.toast(f"Neue Kassen-Buchung von {last_kasse.person}!", icon=":material/payments:")
        st.session_state.seen_kasse_id = current_kasse_id


check_new_entries()

# ---------------------------------------------------------------------------
# WIEDERVERWENDBARE BEARBEITBARE LOGBUCH-EINTRAGS-ANSICHT
# ---------------------------------------------------------------------------
def render_editable_log_entry(e, imker_liste, volk_liste, vorgang_liste, show_volk=False):
    if st.session_state.editing_id == e.id:
        with st.container(border=True):
            st.markdown("**Eintrag bearbeiten**")
            neu_imker = st.selectbox("Wer", imker_liste, index=imker_liste.index(e.imker) if e.imker in imker_liste else 0, key=f"edit_wer_{e.id}")
            neu_volk = st.selectbox("Volk", volk_liste, index=volk_liste.index(e.volk) if e.volk in volk_liste else 0, key=f"edit_volk_{e.id}")
            neu_vorgang = st.pills(
                "Vorgang", vorgang_liste,
                default=e.vorgang if e.vorgang in vorgang_liste else vorgang_liste[0],
                key=f"edit_vorgang_{e.id}",
            )
            if neu_vorgang is None:
                neu_vorgang = e.vorgang if e.vorgang in vorgang_liste else vorgang_liste[0]
            neu_status = st.selectbox("Status", STATUS_OPTIONS, index=STATUS_OPTIONS.index(e.status) if e.status in STATUS_OPTIONS else 0, key=f"edit_status_{e.id}")
            neu_notiz = st.text_area("Notizen", value=e.notiz or "", key=f"edit_notiz_{e.id}")
            c1, c2 = st.columns(2)
            neu_datum = c1.date_input("Datum", value=e.zeitpunkt.date() if e.zeitpunkt else datetime.date.today(), format="DD.MM.YYYY", key=f"edit_datum_{e.id}")
            neu_zeit = c2.time_input("Uhrzeit", value=e.zeitpunkt.time() if e.zeitpunkt else datetime.datetime.now().time(), key=f"edit_zeit_{e.id}")

            if e.foto_data:
                st.image(base64.b64decode(e.foto_data), caption=e.foto_dateiname or "Foto", width=220)
                foto_entfernen = st.checkbox("Foto entfernen", key=f"edit_foto_entfernen_{e.id}")
            else:
                foto_entfernen = False
            neues_foto = st.file_uploader("Neues Foto hochladen (ersetzt vorhandenes)", type=["jpg", "jpeg", "png"], key=f"edit_foto_{e.id}")

            defaults = {c.name: getattr(e, c.name) for c in LogEintrag.__table__.columns}
            extra = render_stockkarte_felder(neu_vorgang, f"edit_{e.id}", defaults)

            b1, b2, b3 = st.columns(3)
            if b1.button("Speichern", key=f"save_{e.id}", type="primary", icon=":material/save:"):
                db = get_db()
                try:
                    obj = db.query(LogEintrag).get(e.id)
                    obj.imker = neu_imker
                    obj.volk = neu_volk
                    obj.vorgang = neu_vorgang
                    obj.status = neu_status
                    obj.notiz = neu_notiz
                    obj.zeitpunkt = datetime.datetime.combine(neu_datum, neu_zeit)
                    for feld, wert in extra.items():
                        setattr(obj, feld, wert)
                    if neues_foto is not None:
                        foto_b64, foto_name = verarbeite_foto(neues_foto)
                        obj.foto_data = foto_b64
                        obj.foto_dateiname = foto_name
                    elif foto_entfernen:
                        obj.foto_data = None
                        obj.foto_dateiname = None
                    db.commit()
                finally:
                    db.close()
                if neu_vorgang == VORGANG_SCHWARMKONTROLLE:
                    erstelle_schwarm_timer(neu_volk, neu_imker)
                st.session_state.editing_id = None
                st.success("Eintrag aktualisiert.")
                st.rerun()
            if b2.button("Abbrechen", key=f"cancel_{e.id}", icon=":material/close:"):
                st.session_state.editing_id = None
                st.rerun()
            if b3.button("Löschen", key=f"delete_{e.id}", icon=":material/delete:"):
                db = get_db()
                try:
                    obj = db.query(LogEintrag).get(e.id)
                    db.delete(obj)
                    db.commit()
                finally:
                    db.close()
                st.session_state.editing_id = None
                st.success("Eintrag gelöscht.")
                st.rerun()
    else:
        with st.container(border=True):
            tag = ' <span class="badge-nachtrag">NACHTRAG</span>' if e.is_nachtrag else ""
            stk = ' <span class="badge-stockkarte">Stockkarte</span>' if e.vorgang in (VORGANG_DURCHSICHT, VORGANG_BEHANDLUNG, VORGANG_ERNTE) else ""
            volk_praefix = f"{e.volk} — " if show_volk else ""
            wetter_info = f" · {e.wetter_temp:.0f}°C, {e.wetter_text}" if e.wetter_temp is not None else ""
            st.markdown(
                f"**{format_ts(e.zeitpunkt)}** — {volk_praefix}**{e.imker}**: {e.vorgang} ({e.status}){wetter_info}{tag}{stk}",
                unsafe_allow_html=True,
            )
            if e.notiz:
                st.caption(e.notiz)
            if e.foto_data:
                st.image(base64.b64decode(e.foto_data), width=260)
            extra_bits = []
            if e.bienenzahl is not None:
                extra_bits.append(f"{e.bienenzahl} Bienen gezählt")
            if e.ernte_kg is not None:
                extra_bits.append(f"{e.ernte_kg:g} kg geerntet")
            if e.varroa_milbenfall is not None:
                extra_bits.append(f"Milbenfall: {e.varroa_milbenfall:g}/Tag")
            if extra_bits:
                st.caption(" · ".join(extra_bits))
            if st.button("Bearbeiten", key=f"edit_btn_{e.id}", icon=":material/edit:"):
                st.session_state.editing_id = e.id
                st.rerun()


# ---------------------------------------------------------------------------
# VOLK-DETAILANSICHT
# ---------------------------------------------------------------------------
def render_volk_detail(volk_id):
    db = get_db()
    try:
        volk = db.query(Volk).get(volk_id)
        imker_liste = [i.name for i in db.query(Imker).order_by(Imker.name).all()]
        volk_liste = [v.name for v in db.query(Volk).filter(Volk.archiviert == False).order_by(Volk.name).all()]
        vorgang_liste = [v.name for v in db.query(Vorgang).order_by(Vorgang.name).all()]
        standorte = db.query(Standort).order_by(Standort.name).all()
        alle_voelker = db.query(Volk).all()
    finally:
        db.close()

    if volk is None:
        st.warning("Dieses Volk existiert nicht mehr.")
        if st.button("Zurück zum Dashboard", icon=":material/arrow_back:"):
            st.session_state.view = "main"
            st.rerun()
        return

    if st.button("Zurück zum Dashboard", icon=":material/arrow_back:"):
        st.session_state.view = "main"
        st.session_state.editing_id = None
        st.rerun()

    st.header(volk.name, icon=":material/hive:", divider="orange")

    with st.expander("Stammdaten (für Stockkarte)", icon=":material/badge:"):
        neuer_name = st.text_input("Name des Volkes", value=volk.name, key=f"detail_rename_{volk.id}")
        standort_namen = ["- kein Standort -"] + [s.name for s in standorte]
        aktueller_index = 0
        if volk.standort_id:
            for idx, s in enumerate(standorte):
                if s.id == volk.standort_id:
                    aktueller_index = idx + 1
        gewaehlter_standort = st.selectbox("Standort", standort_namen, index=aktueller_index, key=f"detail_standort_{volk.id}")

        mutter_optionen = ["- kein Muttervolk / Ursprungsvolk -"] + [v.name for v in alle_voelker if v.name != volk.name]
        mutter_index = 0
        if volk.mutter_volk and volk.mutter_volk in mutter_optionen:
            mutter_index = mutter_optionen.index(volk.mutter_volk)
        gewaehlte_mutter = st.selectbox("Muttervolk (falls Ableger)", mutter_optionen, index=mutter_index, key=f"detail_mutter_{volk.id}")

        c1, c2 = st.columns(2)
        koenigin_jahr = c1.number_input("Königin Geburtsjahr", min_value=2015, max_value=2040, step=1,
                                          value=volk.koenigin_jahr or datetime.date.today().year, key=f"detail_jahr_{volk.id}")
        c2.text_input("Zeichnungsfarbe (automatisch)", value=zeichnungsfarbe(koenigin_jahr), disabled=True, key=f"detail_farbe_{volk.id}")

        koenigin_herkunft = st.text_input("Herkunft / Rasse (z. B. Carnica, Buckfast, Standbegattet)", value=volk.koenigin_herkunft or "", key=f"detail_herkunft_{volk.id}")

        c3, c4 = st.columns(2)
        koenigin_gezeichnet = c3.checkbox("Königin gezeichnet", value=bool(volk.koenigin_gezeichnet), key=f"detail_gezeichnet_{volk.id}")
        koenigin_fluegel = c4.checkbox("Flügel beschnitten", value=bool(volk.koenigin_fluegel_beschnitten), key=f"detail_fluegel_{volk.id}")

        c5, c6 = st.columns(2)
        beutenart = c5.text_input("Beutenart (z. B. Zander, DNM, Dadant)", value=volk.beutenart or "", key=f"detail_beute_{volk.id}")
        raehmchenmass = c6.text_input("Rähmchenmaß", value=volk.raehmchenmass or "", key=f"detail_raehmchen_{volk.id}")

        if st.button("Stammdaten speichern", key=f"detail_save_{volk.id}", type="primary", icon=":material/save:"):
            db = get_db()
            try:
                v = db.query(Volk).get(volk_id)
                alter_name = v.name
                if neuer_name and neuer_name != alter_name:
                    v.name = neuer_name
                    for e in db.query(LogEintrag).filter(LogEintrag.volk == alter_name).all():
                        e.volk = neuer_name
                    for kind in db.query(Volk).filter(Volk.mutter_volk == alter_name).all():
                        kind.mutter_volk = neuer_name
                if gewaehlter_standort == "- kein Standort -":
                    v.standort_id = None
                else:
                    passender = next((s for s in standorte if s.name == gewaehlter_standort), None)
                    v.standort_id = passender.id if passender else None
                v.mutter_volk = None if gewaehlte_mutter.startswith("- kein") else gewaehlte_mutter
                v.koenigin_jahr = int(koenigin_jahr)
                v.koenigin_herkunft = koenigin_herkunft
                v.koenigin_gezeichnet = koenigin_gezeichnet
                v.koenigin_fluegel_beschnitten = koenigin_fluegel
                v.beutenart = beutenart
                v.raehmchenmass = raehmchenmass
                db.commit()
            finally:
                db.close()
            st.success("Stammdaten gespeichert.")
            st.rerun()

    neuer_status = st.selectbox(
        "Status dieses Volkes", STATUS_OPTIONS,
        index=STATUS_OPTIONS.index(volk.status) if volk.status in STATUS_OPTIONS else 0,
    )
    if neuer_status != volk.status:
        db = get_db()
        try:
            v = db.query(Volk).get(volk_id)
            v.status = neuer_status
            db.commit()
        finally:
            db.close()
        st.rerun()

    tab1, tab2, tab3 = st.tabs([":material/menu_book: Komplettes Logbuch", ":material/picture_as_pdf: Stockkarte (PDF)", ":material/account_tree: Stammbaum"])

    with tab1:
        db = get_db()
        try:
            eintraege = (
                db.query(LogEintrag)
                .filter(LogEintrag.volk == volk.name)
                .order_by(LogEintrag.zeitpunkt.desc())
                .all()
            )
        finally:
            db.close()

        suchtext = st.text_input(
            "Suche in diesem Volk", placeholder="Notizen durchsuchen…",
            key=f"volk_suche_{volk.id}", label_visibility="collapsed",
            icon=":material/search:",
        )
        with st.expander("Erweiterte Suche", icon=":material/tune:"):
            c1, c2 = st.columns(2)
            f_vorgang = c1.selectbox("Vorgang", ["Alle"] + vorgang_liste, key=f"volk_suche_vorgang_{volk.id}")
            f_imker = c2.selectbox("Person", ["Alle"] + imker_liste, key=f"volk_suche_imker_{volk.id}")
            c3, c4 = st.columns(2)
            f_von = c3.date_input("Von", value=None, format="DD.MM.YYYY", key=f"volk_suche_von_{volk.id}")
            f_bis = c4.date_input("Bis", value=None, format="DD.MM.YYYY", key=f"volk_suche_bis_{volk.id}")

        gefiltert = eintraege
        if suchtext:
            gefiltert = [e for e in gefiltert if suchtext.lower() in (e.notiz or "").lower()]
        if f_vorgang != "Alle":
            gefiltert = [e for e in gefiltert if e.vorgang == f_vorgang]
        if f_imker != "Alle":
            gefiltert = [e for e in gefiltert if e.imker == f_imker]
        if f_von:
            gefiltert = [e for e in gefiltert if e.zeitpunkt and e.zeitpunkt.date() >= f_von]
        if f_bis:
            gefiltert = [e for e in gefiltert if e.zeitpunkt and e.zeitpunkt.date() <= f_bis]

        st.caption(f"{len(gefiltert)} von {len(eintraege)} Einträgen")
        if not eintraege:
            st.info("Für dieses Volk gibt es noch keine Einträge.")
        for e in gefiltert:
            render_editable_log_entry(e, imker_liste, volk_liste, vorgang_liste, show_volk=False)

    with tab2:
        st.markdown("Erstellt die gesetzlich vorgeschriebene Stockkarte inkl. Stammdaten, Durchsichten, Behandlungen und Ernte.")
        if not FPDF_AVAILABLE:
            st.warning("Das PDF-Modul (fpdf2) ist nicht installiert. Bitte requirements.txt aktualisieren.")
        else:
            db = get_db()
            try:
                eintraege_chrono = (
                    db.query(LogEintrag)
                    .filter(LogEintrag.volk == volk.name)
                    .order_by(LogEintrag.zeitpunkt.asc())
                    .all()
                )
                standort_name = None
                if volk.standort_id:
                    s = db.query(Standort).get(volk.standort_id)
                    standort_name = s.name if s else None
            finally:
                db.close()
            try:
                pdf_bytes = erstelle_stockkarte_pdf(volk, standort_name, eintraege_chrono)
                st.download_button(
                    "Stockkarte als PDF herunterladen",
                    data=pdf_bytes,
                    file_name=f"Stockkarte_{volk.name.replace(' ', '_')}.pdf",
                    mime="application/pdf",
                    type="primary",
                    icon=":material/picture_as_pdf:",
                )
            except Exception:
                st.error("Die PDF-Erstellung ist fehlgeschlagen. Bitte versuch es erneut oder melde dich beim Support.")

    with tab3:
        alle_dict = {v.name: v for v in alle_voelker}
        vorfahren = stammbaum_vorfahren(volk.name, alle_dict)
        st.markdown("**Abstammungslinie:**")
        st.markdown(" → ".join(vorfahren))
        nachkommen = stammbaum_nachkommen(volk.name, alle_voelker)
        if nachkommen:
            st.markdown("**Direkte Ableger:**")
            for n in nachkommen:
                st.write("- " + n)
        else:
            st.caption("Bisher keine Ableger von diesem Volk erfasst.")


# ---------------------------------------------------------------------------
# ROUTING
# ---------------------------------------------------------------------------
if st.session_state.view == "volk_detail":
    render_volk_detail(st.session_state.detail_volk_id)

elif page == "Dashboard":
    st.header("Dashboard", icon=":material/dashboard:", divider="orange")

    db = get_db()
    try:
        alle_standorte_check = db.query(Standort).order_by(Standort.name).all()
    finally:
        db.close()

    for s in alle_standorte_check:
        if s.lat is not None and s.lon is not None and pruefe_unwetter_cached(s.id, s.lat, s.lon):
            st.error(f"Unwetter an Standort '{s.name}' droht in den nächsten 24 Stunden!", icon=":material/warning:")

    if alle_standorte_check:
        st.markdown("###### :material/air: Flugwetter")
        cols = st.columns(len(alle_standorte_check))
        for col, s in zip(cols, alle_standorte_check):
            ergebnis = hole_flugwetter_cached(s.id, s.lat, s.lon) if s.lat is not None and s.lon is not None else None
            with col:
                if ergebnis:
                    temp, wind, code = ergebnis
                    symbol, hinweis = bewerte_flugwetter(temp, wind, code)
                    temp_text = f"{temp:.0f}°C" if temp is not None else "-"
                    st.markdown(
                        f'<div class="flug-card"><div style="font-size:1.4em">{symbol}</div>'
                        f'<div style="font-weight:600">{s.name}</div>'
                        f'<div>{temp_text}</div><div style="font-size:0.8em;color:#8A8F9C">{hinweis}</div></div>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.caption(f"{s.name}: keine Wetterdaten")

    tab_uebersicht, tab_zaehlung, tab_statistik = st.tabs([":material/hive: Völker-Übersicht", ":material/bar_chart: Zählungen", ":material/insights: Statistik"])

    with tab_uebersicht:
        db = get_db()
        try:
            voelker = db.query(Volk).filter(Volk.archiviert == False).order_by(Volk.name).all()
            if not voelker:
                st.info("Noch keine Völker angelegt. Geh zu 'Verwaltung'.")
            for volk in voelker:
                with st.container(border=True):
                    col1, col2 = st.columns([2, 1])
                    with col1:
                        if st.button(volk.name, key=f"open_{volk.id}", use_container_width=True, icon=":material/hive:"):
                            st.session_state.view = "volk_detail"
                            st.session_state.detail_volk_id = volk.id
                            st.session_state.editing_id = None
                            st.rerun()
                    with col2:
                        neuer_status = st.selectbox(
                            "Status",
                            STATUS_OPTIONS,
                            index=STATUS_OPTIONS.index(volk.status) if volk.status in STATUS_OPTIONS else 0,
                            key=f"status_{volk.id}",
                            label_visibility="collapsed",
                        )
                        if neuer_status != volk.status:
                            volk.status = neuer_status
                            db.commit()
                            st.rerun()

                    letzte = (
                        db.query(LogEintrag)
                        .filter(LogEintrag.volk == volk.name)
                        .order_by(LogEintrag.zeitpunkt.desc())
                        .limit(3)
                        .all()
                    )
                    if letzte:
                        st.caption("Letzte Einträge — zum Bearbeiten auf den Volksnamen oben klicken")
                        for e in letzte:
                            tag = ' <span class="badge-nachtrag">NACHTRAG</span>' if e.is_nachtrag else ""
                            st.markdown(
                                f"- {format_ts(e.zeitpunkt)} — **{e.imker}**: {e.vorgang}{tag}",
                                unsafe_allow_html=True,
                            )
                            if e.notiz:
                                st.caption(e.notiz)
                    else:
                        st.caption("Noch keine Einträge für dieses Volk.")
        finally:
            db.close()

    with tab_zaehlung:
        if not PANDAS_AVAILABLE:
            st.warning("Für Diagramme wird das Paket 'pandas' benötigt. Bitte requirements.txt aktualisieren.")
        else:
            db = get_db()
            try:
                zaehlungen = (
                    db.query(LogEintrag)
                    .filter(LogEintrag.vorgang == VORGANG_ZAEHLUNG)
                    .order_by(LogEintrag.zeitpunkt.asc())
                    .all()
                )
            finally:
                db.close()

            if not zaehlungen:
                st.info("Noch keine Zählungen erfasst. Wähle im Logbuch den Vorgang 'Volk zählen'.")
            else:
                df = pd.DataFrame([
                    {"Datum": z.zeitpunkt, "Volk": z.volk, "Anzahl": z.bienenzahl}
                    for z in zaehlungen if z.bienenzahl is not None
                ])
                if df.empty:
                    st.info("Es gibt Einträge mit dem Vorgang 'Volk zählen', aber noch keine erfasste Anzahl.")
                else:
                    alle_voelker_namen = sorted(df["Volk"].unique())
                    ausgewaehlt = st.multiselect("Völker auswählen", alle_voelker_namen, default=alle_voelker_namen)
                    df_f = df[df["Volk"].isin(ausgewaehlt)]
                    if not df_f.empty:
                        pivot = df_f.pivot_table(index="Datum", columns="Volk", values="Anzahl", aggfunc="mean")
                        st.line_chart(pivot)
                        st.dataframe(
                            df_f.sort_values("Datum", ascending=False).rename(columns={"Anzahl": "Gezählte Bienen"}),
                            use_container_width=True, hide_index=True,
                        )

    with tab_statistik:
        if not PANDAS_AVAILABLE:
            st.warning("Für Statistiken wird das Paket 'pandas' benötigt.")
        else:
            db = get_db()
            try:
                ernte_eintraege = db.query(LogEintrag).filter(LogEintrag.vorgang == VORGANG_ERNTE, LogEintrag.ernte_kg.isnot(None)).all()
                varroa_eintraege = db.query(LogEintrag).filter(LogEintrag.vorgang == VORGANG_BEHANDLUNG, LogEintrag.varroa_milbenfall.isnot(None)).all()
                alle_voelker_stat = db.query(Volk).all()
            finally:
                db.close()

            st.markdown("###### :material/bar_chart: Honigertrag pro Jahr")
            if not ernte_eintraege:
                st.caption("Noch keine Ernte-Einträge erfasst.")
            else:
                df_ernte = pd.DataFrame([{"Jahr": e.zeitpunkt.year, "Volk": e.volk, "kg": e.ernte_kg} for e in ernte_eintraege])
                jahres_summe = df_ernte.groupby("Jahr")["kg"].sum()
                st.bar_chart(jahres_summe)

            st.markdown("###### :material/bug_report: Varroa-Milbenfall im Verlauf")
            if not varroa_eintraege:
                st.caption("Noch keine Behandlungs-Einträge mit Milbenfall erfasst.")
            else:
                df_varroa = pd.DataFrame([{"Datum": e.zeitpunkt, "Volk": e.volk, "Milbenfall": e.varroa_milbenfall} for e in varroa_eintraege])
                voelker_opts = sorted(df_varroa["Volk"].unique())
                gewaehlt = st.multiselect("Völker", voelker_opts, default=voelker_opts, key="stat_varroa_voelker")
                df_vf = df_varroa[df_varroa["Volk"].isin(gewaehlt)]
                if not df_vf.empty:
                    pivot_v = df_vf.pivot_table(index="Datum", columns="Volk", values="Milbenfall", aggfunc="mean")
                    st.line_chart(pivot_v)

            st.markdown("###### :material/account_tree: Ertrag nach Abstammungslinie")
            if not ernte_eintraege:
                st.caption("Noch keine Daten für einen Linienvergleich.")
            else:
                alle_dict_stat = {v.name: v for v in alle_voelker_stat}

                def _wurzel(volk_name):
                    kette = stammbaum_vorfahren(volk_name, alle_dict_stat)
                    return kette[0] if kette else volk_name

                df_ernte["Linie"] = df_ernte["Volk"].apply(_wurzel)
                linien_summe = df_ernte.groupby("Linie")["kg"].sum().sort_values(ascending=False)
                st.bar_chart(linien_summe)

elif page == "Logbuch":
    st.header("Logbuch", icon=":material/edit_note:", divider="orange")
    tab1, tab2 = st.tabs([":material/edit_square: Neuer Eintrag", ":material/history: Historie & Suche"])

    with tab1:
        db = get_db()
        try:
            imker_liste = [i.name for i in db.query(Imker).order_by(Imker.name).all()]
            volk_liste = [
                v.name for v in db.query(Volk).filter(Volk.archiviert == False).order_by(Volk.name).all()
            ]
            vorgang_liste = [v.name for v in db.query(Vorgang).order_by(Vorgang.name).all()]
        finally:
            db.close()

        if not volk_liste or not imker_liste:
            st.warning("Bitte zuerst unter 'Verwaltung' ein Volk bzw. eine Person anlegen.")
        else:
            v = st.session_state.log_form_version

            st.markdown("##### :material/person: Imker & Volk")
            c1, c2 = st.columns(2)
            wer = c1.selectbox("Wer bist du?", imker_liste, key=f"log_wer_{v}")
            volk = c2.selectbox("Welches Volk?", volk_liste, key=f"log_volk_{v}")

            st.markdown("##### :material/build: Vorgang & Zustand")
            vorgang = st.pills(
                "Vorgang/Aktion", vorgang_liste, default=vorgang_liste[0], key=f"log_vorgang_{v}"
            )
            if vorgang is None:
                vorgang = vorgang_liste[0]
            status = st.selectbox("Status-Update", STATUS_OPTIONS, key=f"log_status_{v}")

            if vorgang == VORGANG_SCHWARMKONTROLLE:
                tage = int(get_setting("schwarm_timer_tage", "7") or 7)
                st.caption(f"Beim Speichern wird automatisch eine Erinnerung für die nächste Schwarmkontrolle in {tage} Tagen angelegt.")

            extra = render_stockkarte_felder(vorgang, f"log_{v}")

            st.markdown("##### :material/edit_note: Notizen")
            notiz = st.text_area("Beobachtungen", placeholder="z. B. 3 Brutwaben gesehen, Volk sehr ruhig, Stifte vorhanden", key=f"log_notiz_{v}", label_visibility="collapsed")

            foto = st.file_uploader("Foto (optional)", type=["jpg", "jpeg", "png"], key=f"log_foto_{v}")

            st.markdown("##### :material/schedule: Zeitpunkt")
            ist_nachtrag = st.toggle("Ist das ein Nachtrag?", key=f"log_nachtrag_{v}")
            nachtrag_datum, nachtrag_zeit = None, None
            if ist_nachtrag:
                c5, c6 = st.columns(2)
                nachtrag_datum = c5.date_input("Datum", format="DD.MM.YYYY", key=f"log_datum_{v}")
                nachtrag_zeit = c6.time_input("Uhrzeit", key=f"log_zeit_{v}")
            else:
                st.caption("Es wird automatisch der aktuelle Zeitpunkt gespeichert.")

            if st.button("Eintrag speichern", use_container_width=True, key=f"log_save_{v}", type="primary", icon=":material/save:"):
                db = get_db()
                try:
                    volk_obj = db.query(Volk).filter(Volk.name == volk).first()

                    if ist_nachtrag and nachtrag_datum and nachtrag_zeit:
                        zeitpunkt = datetime.datetime.combine(nachtrag_datum, nachtrag_zeit)
                        wetter_temp, wetter_text = None, None
                    else:
                        zeitpunkt = datetime.datetime.now()
                        wetter_temp, wetter_text = hole_wetter_fuer_volk(volk_obj)

                    foto_b64, foto_name = verarbeite_foto(foto)

                    neuer_eintrag = LogEintrag(
                        imker=wer, volk=volk, vorgang=vorgang, status=status,
                        notiz=notiz, zeitpunkt=zeitpunkt, is_nachtrag=ist_nachtrag,
                        wetter_temp=wetter_temp, wetter_text=wetter_text,
                        foto_data=foto_b64, foto_dateiname=foto_name,
                    )
                    for feld, wert in extra.items():
                        setattr(neuer_eintrag, feld, wert)
                    db.add(neuer_eintrag)
                    if volk_obj:
                        volk_obj.status = status
                    db.commit()
                finally:
                    db.close()
                if vorgang == VORGANG_SCHWARMKONTROLLE:
                    erstelle_schwarm_timer(volk, wer)
                st.session_state.log_form_version += 1
                st.success("Eintrag erfolgreich gespeichert!")
                st.rerun()

    with tab2:
        db = get_db()
        try:
            alle = db.query(LogEintrag).order_by(LogEintrag.zeitpunkt.desc()).all()
            imker_liste = [i.name for i in db.query(Imker).order_by(Imker.name).all()]
            volk_liste = [v.name for v in db.query(Volk).order_by(Volk.name).all()]
            vorgang_liste = [v.name for v in db.query(Vorgang).order_by(Vorgang.name).all()]
        finally:
            db.close()

        imker_opts = ["Alle"] + sorted({e.imker for e in alle})
        volk_opts = ["Alle"] + sorted({e.volk for e in alle})
        vorgang_opts = ["Alle"] + sorted({e.vorgang for e in alle})

        c1, c2, c3 = st.columns(3)
        f_imker = c1.selectbox("Imker", imker_opts)
        f_volk = c2.selectbox("Volk", volk_opts)
        f_vorgang = c3.selectbox("Vorgang", vorgang_opts)
        suchtext = st.text_input("Freitextsuche (Notizen)")

        gefiltert = alle
        if f_imker != "Alle":
            gefiltert = [e for e in gefiltert if e.imker == f_imker]
        if f_volk != "Alle":
            gefiltert = [e for e in gefiltert if e.volk == f_volk]
        if f_vorgang != "Alle":
            gefiltert = [e for e in gefiltert if e.vorgang == f_vorgang]
        if suchtext:
            gefiltert = [e for e in gefiltert if suchtext.lower() in (e.notiz or "").lower()]

        st.caption(f"{len(gefiltert)} Einträge gefunden")
        for e in gefiltert:
            render_editable_log_entry(e, imker_liste, volk_liste, vorgang_liste, show_volk=True)

elif page == "Material":
    st.header("Material & Inventar", icon=":material/inventory_2:", divider="orange")
    st.markdown("Behalte den Überblick über euer Material, damit niemand versehentlich doppelt einkauft.")
    db = get_db()
    try:
        c1, c2, c3 = st.columns([2, 1, 1])
        neu_name = c1.text_input("Artikel", key="inv_neu_name")
        neu_menge = c2.number_input("Menge", min_value=0.0, step=1.0, key="inv_neu_menge")
        neu_einheit = c3.text_input("Einheit", value="Stück", key="inv_neu_einheit")
        if st.button("Artikel hinzufügen", type="primary", icon=":material/add:") and neu_name:
            if not db.query(InventarItem).filter(InventarItem.name == neu_name).first():
                db.add(InventarItem(name=neu_name, menge=neu_menge, einheit=neu_einheit))
                db.commit()
                st.success(f"'{neu_name}' hinzugefügt.")
                st.rerun()
            else:
                st.warning("Dieser Artikel existiert schon, bitte unten die Menge anpassen.")

        st.divider()
        items = db.query(InventarItem).order_by(InventarItem.name).all()
        if not items:
            st.caption("Noch kein Material erfasst.")
        for item in items:
            with st.container(border=True):
                c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 1, 1])
                c1.write(f"**{item.name}**")
                c2.write(f"{item.menge:g} {item.einheit}")
                if c3.button("", key=f"minus_{item.id}", icon=":material/remove:"):
                    item.menge = max(0, item.menge - 1)
                    db.commit()
                    st.rerun()
                if c4.button("", key=f"plus_{item.id}", icon=":material/add:"):
                    item.menge += 1
                    db.commit()
                    st.rerun()
                if c5.button("", key=f"del_inv_{item.id}", icon=":material/delete:"):
                    db.delete(item)
                    db.commit()
                    st.rerun()
    finally:
        db.close()

elif page == "Aufgaben":
    st.header("Aufgaben", icon=":material/task_alt:", divider="orange")
    db = get_db()
    try:
        imker_liste = [i.name for i in db.query(Imker).order_by(Imker.name).all()]
        volk_liste = [v.name for v in db.query(Volk).filter(Volk.archiviert == False).order_by(Volk.name).all()]
        vorgang_liste = [v.name for v in db.query(Vorgang).order_by(Vorgang.name).all()]
    finally:
        db.close()

    with st.form("neue_aufgabe_top", clear_on_submit=True):
        titel = st.text_input("Aufgabe")
        c1, c2 = st.columns(2)
        zugewiesen = c1.selectbox("Zugewiesen an", imker_liste) if imker_liste else None
        faellig = c2.date_input("Fällig am", format="DD.MM.YYYY")
        c3, c4 = st.columns(2)
        gewaehltes_volk = c3.selectbox("Volk (optional)", ["- Allgemein -"] + volk_liste)
        gewaehlter_vorgang = c4.selectbox("Vorgang/Aktion (optional)", ["- keiner -"] + vorgang_liste)
        if st.form_submit_button("Aufgabe anlegen", type="primary", icon=":material/add:") and titel:
            db = get_db()
            try:
                db.add(Aufgabe(
                    titel=titel, zugewiesen_an=zugewiesen,
                    faellig_am=faellig.strftime("%d.%m.%Y"),
                    volk=None if gewaehltes_volk == "- Allgemein -" else gewaehltes_volk,
                    vorgang=None if gewaehlter_vorgang == "- keiner -" else gewaehlter_vorgang,
                    quelle="manuell",
                ))
                db.commit()
            finally:
                db.close()
            st.success("Aufgabe angelegt.")
            st.rerun()

    st.divider()
    db = get_db()
    try:
        offene = db.query(Aufgabe).filter(Aufgabe.erledigt == False).all()
        offene_sortiert = sorted(offene, key=lambda x: parse_datum(x.faellig_am) or datetime.date.max)
        erledigte = db.query(Aufgabe).order_by(Aufgabe.id.desc()).filter(Aufgabe.erledigt == True).limit(30).all()

        st.subheader("Offene Aufgaben")
        if not offene_sortiert:
            st.caption("Keine offenen Aufgaben.")
        for a in offene_sortiert:
            with st.container(border=True):
                zusatz = []
                if a.volk:
                    zusatz.append(f"Volk: {a.volk}")
                if a.vorgang:
                    zusatz.append(f"Vorgang: {a.vorgang}")
                auto_badge = ' <span class="badge-auto">Automatisch</span>' if a.quelle == "schwarm_timer" else ""
                c1, c2 = st.columns([4, 1])
                textzeile = f"**{a.titel}** — {a.zugewiesen_an} — fällig {a.faellig_am}"
                if zusatz:
                    textzeile += "  \n_" + " · ".join(zusatz) + "_"
                c1.markdown(textzeile + auto_badge, unsafe_allow_html=True)
                if c2.button("", key=f"done_top_{a.id}", icon=":material/check_circle:"):
                    db2 = get_db()
                    try:
                        obj = db2.query(Aufgabe).get(a.id)
                        obj.erledigt = True
                        if obj.volk:
                            db2.add(LogEintrag(
                                imker=obj.zugewiesen_an or "Unbekannt", volk=obj.volk,
                                vorgang=obj.vorgang or "Sonstiges", status="🟢 Alles top",
                                notiz=f"Aufgabe erledigt: {obj.titel}", zeitpunkt=datetime.datetime.now(),
                                is_nachtrag=False,
                            ))
                        db2.commit()
                    finally:
                        db2.close()
                    st.success("Erledigt!")
                    st.rerun()

        with st.expander(f"Erledigte Aufgaben ({len(erledigte)})", icon=":material/history:"):
            for a in erledigte:
                c1, c2 = st.columns([4, 1])
                c1.write(f"~~{a.titel}~~ — {a.zugewiesen_an}")
                if c2.button("", key=f"undo_top_{a.id}", icon=":material/undo:"):
                    a.erledigt = False
                    db.commit()
                    st.rerun()
    finally:
        db.close()

elif page == "Kalender":
    st.header("Kalender", icon=":material/calendar_month:", divider="orange")
    tab1, tab2 = st.tabs([":material/event: Übersicht", ":material/beach_access: Abwesenheiten"])

    with tab1:
        heute = datetime.date.today()
        diese_woche_montag = heute - datetime.timedelta(days=heute.weekday())
        bereich_start = diese_woche_montag - datetime.timedelta(days=7)
        bereich_ende = diese_woche_montag + datetime.timedelta(days=21) - datetime.timedelta(days=1)

        db = get_db()
        try:
            offene_aufgaben = db.query(Aufgabe).filter(Aufgabe.erledigt == False).all()
            log_eintraege = db.query(LogEintrag).filter(
                LogEintrag.zeitpunkt >= datetime.datetime.combine(bereich_start, datetime.time.min),
                LogEintrag.zeitpunkt <= datetime.datetime.combine(bereich_ende, datetime.time.max),
            ).all()
            abwesenheiten = db.query(Abwesenheit).all()
        finally:
            db.close()

        ereignisse_pro_tag = {}

        def _add_event(d, typ, text):
            if d is not None and bereich_start <= d <= bereich_ende:
                ereignisse_pro_tag.setdefault(d, []).append((typ, text))

        for a in offene_aufgaben:
            d = parse_datum(a.faellig_am)
            praefix = "⏱ " if a.quelle == "schwarm_timer" else ""
            _add_event(d, "aufgabe", praefix + a.titel + (f" ({a.volk})" if a.volk else ""))
        for e in log_eintraege:
            _add_event(e.zeitpunkt.date(), "log", f"{e.volk}: {e.vorgang}")
        for ab in abwesenheiten:
            if ab.von_datum and ab.bis_datum:
                cur = max(ab.von_datum.date(), bereich_start)
                end = min(ab.bis_datum.date(), bereich_ende)
                while cur <= end:
                    _add_event(cur, "abwesend", f"{ab.person} abwesend")
                    cur += datetime.timedelta(days=1)

        FARBEN = {"aufgabe": "#93C5FD", "log": "#D9A441", "abwesend": "#F0ABFC"}
        st.caption(":material/task_alt: Aufgaben · :material/edit_note: Logbuch · :material/beach_access: Abwesenheit")

        wochentag_namen = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
        wochen_labels = ["Vorherige Woche", "Diese Woche", "Nächste Woche", "Übernächste Woche"]

        for woche_idx in range(4):
            woche_start = bereich_start + datetime.timedelta(weeks=woche_idx)
            woche_ende = woche_start + datetime.timedelta(days=6)
            hervorhebung = " :material/arrow_back:" if woche_idx == 1 else ""
            st.markdown(
                f"**{wochen_labels[woche_idx]}**{hervorhebung}  \n"
                f"<span style='color:#8A8F9C;font-size:0.85em'>{woche_start.strftime('%d.%m.')} – {woche_ende.strftime('%d.%m.%Y')}</span>",
                unsafe_allow_html=True,
            )
            cols = st.columns(7)
            for i in range(7):
                tag = woche_start + datetime.timedelta(days=i)
                ist_heute = tag == heute
                with cols[i]:
                    box_style = (
                        "background-color:rgba(217,164,65,0.22);border:1px solid rgba(217,164,65,0.6);"
                        if ist_heute else "border:1px solid rgba(217,164,65,0.15);"
                    )
                    st.markdown(
                        f"<div style='{box_style}border-radius:8px;padding:5px;min-height:70px;'>"
                        f"<div style='font-size:0.68em;color:#8A8F9C'>{wochentag_namen[i]}</div>"
                        f"<div style='font-weight:700;font-size:0.9em'>{tag.day}.{tag.month}.</div>"
                        + "".join(
                            f"<div style='font-size:0.62em;color:{FARBEN.get(typ, '#EDEDED')};"
                            f"white-space:nowrap;overflow:hidden;text-overflow:ellipsis' title='{text}'>• {text}</div>"
                            for typ, text in ereignisse_pro_tag.get(tag, [])[:3]
                        )
                        + (
                            f"<div style='font-size:0.6em;color:#8A8F9C'>+{len(ereignisse_pro_tag.get(tag, [])) - 3} mehr</div>"
                            if len(ereignisse_pro_tag.get(tag, [])) > 3 else ""
                        )
                        + "</div>",
                        unsafe_allow_html=True,
                    )
            st.write("")

    with tab2:
        db = get_db()
        try:
            imker_liste = [i.name for i in db.query(Imker).order_by(Imker.name).all()]
        finally:
            db.close()

        with st.form("neue_abwesenheit", clear_on_submit=True):
            person = st.selectbox("Wer ist abwesend?", imker_liste) if imker_liste else None
            c1, c2 = st.columns(2)
            von = c1.date_input("Von", format="DD.MM.YYYY")
            bis = c2.date_input("Bis", format="DD.MM.YYYY")
            notiz = st.text_input("Notiz (optional, z. B. 'Urlaub in Italien')")
            if st.form_submit_button("Abwesenheit eintragen", type="primary", icon=":material/add:") and person:
                db = get_db()
                try:
                    db.add(Abwesenheit(
                        person=person,
                        von_datum=datetime.datetime.combine(von, datetime.time.min),
                        bis_datum=datetime.datetime.combine(bis, datetime.time.min),
                        notiz=notiz,
                    ))
                    db.commit()
                finally:
                    db.close()
                st.success("Abwesenheit eingetragen.")
                st.rerun()

        st.divider()
        db = get_db()
        try:
            heute_dt = datetime.datetime.now()
            alle_abw = db.query(Abwesenheit).order_by(Abwesenheit.von_datum).all()
            if not alle_abw:
                st.caption("Noch keine Abwesenheiten eingetragen.")
            for ab in alle_abw:
                aktiv = ab.von_datum and ab.bis_datum and ab.von_datum.date() <= heute_dt.date() <= ab.bis_datum.date()
                with st.container(border=True):
                    c1, c2 = st.columns([4, 1])
                    status_txt = " (gerade abwesend)" if aktiv else ""
                    zeitraum = f"{ab.von_datum.strftime('%d.%m.%Y')} – {ab.bis_datum.strftime('%d.%m.%Y')}" if ab.von_datum and ab.bis_datum else "-"
                    text = f"**{ab.person}**: {zeitraum}{status_txt}"
                    if ab.notiz:
                        text += f"  \n_{ab.notiz}_"
                    c1.markdown(text)
                    if c2.button("", key=f"del_abw_{ab.id}", icon=":material/delete:"):
                        db.delete(ab)
                        db.commit()
                        st.rerun()
        finally:
            db.close()

elif page == "Verwaltung":
    st.header("Verwaltung", icon=":material/settings:", divider="orange")
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
        [
            ":material/hive: Völker", ":material/build: Vorgänge", ":material/group: Imker",
            ":material/location_on: Standorte", ":material/tune: Einstellungen", ":material/backup: Sicherung",
        ]
    )

    with tab1:
        db = get_db()
        try:
            standorte = db.query(Standort).order_by(Standort.name).all()
            c1, c2 = st.columns([2, 2])
            neu = c1.text_input("Neues Volk anlegen (Name)")
            standort_namen = ["- kein Standort -"] + [s.name for s in standorte]
            neuer_standort = c2.selectbox("Standort", standort_namen, key="neu_volk_standort")
            if st.button("Volk hinzufügen", icon=":material/add:") and neu:
                if not db.query(Volk).filter(Volk.name == neu).first():
                    passender = next((s for s in standorte if s.name == neuer_standort), None)
                    db.add(Volk(name=neu, standort_id=passender.id if passender else None))
                    db.commit()
                    st.success(f"Volk '{neu}' angelegt.")
                    st.rerun()
                else:
                    st.warning("Ein Volk mit diesem Namen existiert schon.")

            st.divider()
            st.markdown("**Bestehende Völker umbenennen oder archivieren**")
            voelker = db.query(Volk).order_by(Volk.archiviert, Volk.name).all()
            for v in voelker:
                c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
                c1.write(("🗄 " if v.archiviert else "") + v.name)
                neuer_name = c2.text_input(
                    "Umbenennen", value=v.name, key=f"rename_{v.id}", label_visibility="collapsed"
                )
                if c3.button("", key=f"btn_rename_{v.id}", icon=":material/edit:") and neuer_name and neuer_name != v.name:
                    alter_name = v.name
                    v.name = neuer_name
                    for e in db.query(LogEintrag).filter(LogEintrag.volk == alter_name).all():
                        e.volk = neuer_name
                    for kind in db.query(Volk).filter(Volk.mutter_volk == alter_name).all():
                        kind.mutter_volk = neuer_name
                    db.commit()
                    st.rerun()
                icon_arch = ":material/unarchive:" if v.archiviert else ":material/archive:"
                if c4.button("", key=f"btn_arch_{v.id}", icon=icon_arch):
                    v.archiviert = not v.archiviert
                    db.commit()
                    st.rerun()
            st.caption("Tipp: Standort, Muttervolk und weitere Stammdaten kannst du direkt in der Volk-Ansicht (Dashboard → Volk anklicken) bearbeiten.")
        finally:
            db.close()

    with tab2:
        db = get_db()
        try:
            neu = st.text_input("Neuen Vorgang/Aktion hinzufügen")
            if st.button("Vorgang hinzufügen", icon=":material/add:") and neu:
                if not db.query(Vorgang).filter(Vorgang.name == neu).first():
                    db.add(Vorgang(name=neu))
                    db.commit()
                    st.success(f"Vorgang '{neu}' hinzugefügt.")
                    st.rerun()
                else:
                    st.warning("Dieser Vorgang existiert schon.")
            st.divider()
            st.caption("Die grau hinterlegten Vorgänge sind für die Stockkarte bzw. den Schwarm-Timer reserviert und können nicht geändert werden. Löschen entfernt einen Vorgang nur aus der Auswahlliste — bereits gespeicherte Einträge bleiben unverändert erhalten.")
            for v in db.query(Vorgang).order_by(Vorgang.name).all():
                if v.name in GESCHUETZTE_VORGAENGE:
                    st.markdown(f":material/lock: {v.name}")
                    continue
                c1, c2, c3 = st.columns([3, 1, 1])
                neuer_vname = c1.text_input(
                    "Umbenennen", value=v.name, key=f"rename_vorgang_{v.id}", label_visibility="collapsed"
                )
                if c2.button("", key=f"btn_rename_vorgang_{v.id}", icon=":material/edit:") and neuer_vname and neuer_vname != v.name:
                    alter_vname = v.name
                    v.name = neuer_vname
                    for e in db.query(LogEintrag).filter(LogEintrag.vorgang == alter_vname).all():
                        e.vorgang = neuer_vname
                    db.commit()
                    st.rerun()
                if c3.button("", key=f"btn_del_vorgang_{v.id}", icon=":material/delete:"):
                    db.delete(v)
                    db.commit()
                    st.rerun()
        finally:
            db.close()

    with tab3:
        db = get_db()
        try:
            neu = st.text_input("Neue Person hinzufügen")
            if st.button("Person hinzufügen", icon=":material/add:") and neu:
                if not db.query(Imker).filter(Imker.name == neu).first():
                    db.add(Imker(name=neu))
                    db.commit()
                    st.success(f"'{neu}' wurde hinzugefügt.")
                    st.rerun()
                else:
                    st.warning("Diese Person existiert schon.")

            st.divider()
            st.markdown("**Bestehende Personen umbenennen oder löschen**")
            st.caption("Löschen entfernt eine Person nur aus der Auswahlliste — bereits gespeicherte Einträge behalten den bisherigen Namen.")
            for i in db.query(Imker).order_by(Imker.name).all():
                c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
                c1.write("• " + i.name)
                neuer_name = c2.text_input(
                    "Umbenennen", value=i.name, key=f"rename_imker_{i.id}", label_visibility="collapsed"
                )
                if c3.button("", key=f"btn_rename_imker_{i.id}", icon=":material/edit:") and neuer_name and neuer_name != i.name:
                    alter_name = i.name
                    i.name = neuer_name
                    for e in db.query(LogEintrag).filter(LogEintrag.imker == alter_name).all():
                        e.imker = neuer_name
                    for k in db.query(KassenEintrag).filter(KassenEintrag.person == alter_name).all():
                        k.person = neuer_name
                    for a in db.query(Aufgabe).filter(Aufgabe.zugewiesen_an == alter_name).all():
                        a.zugewiesen_an = neuer_name
                    db.commit()
                    st.success(f"'{alter_name}' wurde zu '{neuer_name}' umbenannt.")
                    st.rerun()
                if c4.button("", key=f"btn_del_imker_{i.id}", icon=":material/delete:"):
                    db.delete(i)
                    db.commit()
                    st.rerun()
        finally:
            db.close()

    with tab4:
        subtab1, subtab2 = st.tabs([":material/edit_location: Verwaltung", ":material/map: AFB-Sperrbezirk-Check"])

        with subtab1:
            st.markdown("Legt eure Bienenstandorte an (z. B. Hauptstandort, Rapsfeld). Jedes Volk kann in seinen Stammdaten einem Standort zugeordnet werden — die App holt dann automatisch das passende Wetter für diesen Ort.")
            db = get_db()
            try:
                c1, c2, c3 = st.columns([2, 1, 1])
                neu_name = c1.text_input("Name des Standorts", key="neu_standort_name")
                neu_lat = c2.number_input("Breitengrad (Latitude)", value=50.9375, format="%.4f", key="neu_standort_lat")
                neu_lon = c3.number_input("Längengrad (Longitude)", value=6.9603, format="%.4f", key="neu_standort_lon")
                st.caption("Tipp: Adresse bei Google Maps eingeben, Rechtsklick auf den Punkt → Koordinaten werden angezeigt.")
                if st.button("Standort hinzufügen", type="primary", icon=":material/add_location:") and neu_name:
                    if not db.query(Standort).filter(Standort.name == neu_name).first():
                        db.add(Standort(name=neu_name, lat=neu_lat, lon=neu_lon))
                        db.commit()
                        st.success(f"Standort '{neu_name}' angelegt.")
                        st.rerun()
                    else:
                        st.warning("Dieser Standort existiert schon.")

                st.divider()
                for s in db.query(Standort).order_by(Standort.name).all():
                    with st.container(border=True):
                        c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
                        neuer_sname = c1.text_input("Name", value=s.name, key=f"standort_name_{s.id}", label_visibility="collapsed")
                        neuer_slat = c2.number_input("Lat", value=s.lat, format="%.4f", key=f"standort_lat_{s.id}", label_visibility="collapsed")
                        neuer_slon = c3.number_input("Lon", value=s.lon, format="%.4f", key=f"standort_lon_{s.id}", label_visibility="collapsed")
                        if c4.button("", key=f"standort_save_{s.id}", icon=":material/save:"):
                            s.name = neuer_sname
                            s.lat = neuer_slat
                            s.lon = neuer_slon
                            db.commit()
                            st.success("Gespeichert.")
                            st.rerun()
                        if st.button("Standort löschen", key=f"standort_del_{s.id}", icon=":material/delete:"):
                            betroffene = db.query(Volk).filter(Volk.standort_id == s.id).all()
                            for v in betroffene:
                                v.standort_id = None
                            db.delete(s)
                            db.commit()
                            st.rerun()
            finally:
                db.close()

        with subtab2:
            st.markdown("Prüft, ob eure Bienenstandorte in einem aktuellen Sperrbezirk wegen Amerikanischer Faulbrut (AFB) liegen könnten.")
            db = get_db()
            try:
                standorte = db.query(Standort).order_by(Standort.name).all()
            finally:
                db.close()
            if not standorte:
                st.caption("Noch keine Standorte angelegt.")
            for s in standorte:
                with st.container(border=True):
                    st.markdown(f"**{s.name}** ({s.lat:.4f}, {s.lon:.4f})")
                    st.link_button("Zur TSIS-Seuchenkarte (Friedrich-Loeffler-Institut)", TSIS_URL, type="primary", icon=":material/map:")
            st.caption(
                "Die TSIS-Karte (TierSeuchenInformationsSystem) des Friedrich-Loeffler-Instituts ist die "
                "bundesweite amtliche Quelle für gemeldete Sperrbezirke, auch für Baden-Württemberg. Für "
                "verbindliche Auskünfte zu eurem konkreten Standort wendet euch zusätzlich an euer "
                "zuständiges Veterinäramt."
            )

    with tab5:
        st.markdown("Stelle hier ein, nach wie vielen Tagen die App automatisch an die nächste Schwarmkontrolle erinnern soll.")
        aktuell = int(get_setting("schwarm_timer_tage", "7") or 7)
        neu = st.number_input("Schwarmkontroll-Intervall (Tage)", min_value=1, max_value=30, value=aktuell)
        if st.button("Speichern", type="primary", icon=":material/save:"):
            set_setting("schwarm_timer_tage", neu)
            st.success("Gespeichert.")

    with tab6:
        if ist_dauerhafte_datenbank():
            st.success("Datenbankverbindung aktiv: Daten werden dauerhaft extern gespeichert (Supabase).", icon=":material/cloud_done:")
        else:
            st.error("Achtung: Aktuell keine dauerhafte Datenbank verbunden — Daten gehen beim nächsten Neustart verloren!", icon=":material/cloud_off:")
        st.markdown(
            "Eure Daten liegen bereits dauerhaft und kostenlos in einer Cloud-Datenbank (Supabase) — "
            "unabhängig von Streamlit. Auch wenn du den App-Code komplett neu schreibst, bleiben die "
            "Daten erhalten, solange die Datenbank-Verbindung (DB_URL) gleich bleibt. Hier kannst du "
            "zusätzlich jederzeit eine vollständige Sicherung herunterladen."
        )
        daten = alle_daten_als_dict()
        anzahl_log = len(daten["log_eintraege"])
        anzahl_kasse = len(daten["kasse"])
        st.caption(f"Aktuell gespeichert: {anzahl_log} Logbuch-Einträge, {anzahl_kasse} Kassen-Buchungen.")

        c1, c2 = st.columns(2)
        json_bytes = json.dumps(daten, default=str, ensure_ascii=False, indent=2).encode("utf-8")
        c1.download_button(
            "Backup als JSON",
            data=json_bytes,
            file_name=f"bienen_backup_{datetime.date.today()}.json",
            mime="application/json",
            type="primary",
            icon=":material/download:",
            use_container_width=True,
        )
        if PANDAS_AVAILABLE and OPENPYXL_AVAILABLE:
            excel_bytes = erstelle_excel_export()
            c2.download_button(
                "Backup als Excel",
                data=excel_bytes,
                file_name=f"bienen_backup_{datetime.date.today()}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                icon=":material/table_view:",
                use_container_width=True,
            )
        else:
            c2.caption("Für Excel-Export werden 'pandas' und 'openpyxl' benötigt.")

        st.divider()
        st.markdown("###### :material/upload_file: Backup wiederherstellen")
        st.warning(
            "Das Hochladen eines Backups überschreibt ALLE aktuellen Daten unwiderruflich mit dem Inhalt der Datei!",
            icon=":material/warning:",
        )
        hochgeladene_datei = st.file_uploader("JSON-Backup-Datei auswählen", type=["json"], key="backup_upload")
        if hochgeladene_datei is not None:
            bestaetigt = st.checkbox(
                "Ich verstehe, dass alle aktuellen Daten überschrieben werden.",
                key="backup_restore_confirm",
            )
            if st.button(
                "Backup jetzt wiederherstellen", type="primary",
                icon=":material/restore:", disabled=not bestaetigt,
            ):
                try:
                    inhalt = json.load(hochgeladene_datei)
                    stelle_backup_wieder_her(inhalt)
                    st.success("Backup erfolgreich wiederhergestellt.")
                    st.rerun()
                except Exception as ex:
                    st.error(f"Wiederherstellung fehlgeschlagen: {ex}")

elif page == "Imker-Kasse":
    st.header("Imker-Kasse", icon=":material/payments:", divider="orange")
    db = get_db()
    try:
        imker_liste = [i.name for i in db.query(Imker).order_by(Imker.name).all()]
    finally:
        db.close()

    tab1, tab2, tab3 = st.tabs([":material/receipt_long: Buchung erfassen", ":material/account_balance_wallet: Kassensturz", ":material/local_florist: Reservierungen"])

    with tab1:
        v = st.session_state.kasse_form_version
        typ = st.radio("Art", ["Ausgabe (Material)", "Einnahme (Honigverkauf)"], horizontal=True, key=f"kasse_typ_{v}")
        betrag = st.number_input("Betrag (€)", min_value=0.0, step=0.5, format="%.2f", key=f"kasse_betrag_{v}")
        person = st.selectbox("Wer hat bezahlt / Geld entgegengenommen?", imker_liste, key=f"kasse_person_{v}")
        beschreibung = st.text_input("Beschreibung", key=f"kasse_beschreibung_{v}")

        ist_nachtrag = st.toggle("Ist das ein Nachtrag?", key=f"kasse_nachtrag_{v}")
        nachtrag_datum, nachtrag_zeit = None, None
        if ist_nachtrag:
            c1, c2 = st.columns(2)
            nachtrag_datum = c1.date_input("Datum", format="DD.MM.YYYY", key=f"kasse_datum_{v}")
            nachtrag_zeit = c2.time_input("Uhrzeit", key=f"kasse_zeit_{v}")

        if st.button("Buchung speichern", use_container_width=True, key=f"kasse_save_{v}", type="primary", icon=":material/save:"):
            zeitpunkt = (
                datetime.datetime.combine(nachtrag_datum, nachtrag_zeit)
                if ist_nachtrag and nachtrag_datum and nachtrag_zeit
                else datetime.datetime.now()
            )
            db = get_db()
            try:
                db.add(KassenEintrag(
                    typ="Ausgabe" if "Ausgabe" in typ else "Einnahme",
                    betrag=betrag, person=person, beschreibung=beschreibung,
                    zeitpunkt=zeitpunkt, is_nachtrag=ist_nachtrag,
                ))
                db.commit()
            finally:
                db.close()
            st.session_state.kasse_form_version += 1
            st.success("Buchung gespeichert.")
            st.rerun()

    with tab2:
        db = get_db()
        try:
            alle = db.query(KassenEintrag).order_by(KassenEintrag.zeitpunkt.desc()).all()
        finally:
            db.close()

        gesamt_einnahmen = sum(e.betrag for e in alle if e.typ == "Einnahme")
        gesamt_ausgaben = sum(e.betrag for e in alle if e.typ == "Ausgabe")
        kontostand = gesamt_einnahmen - gesamt_ausgaben

        c1, c2, c3 = st.columns(3)
        c1.metric("Einnahmen", f"{gesamt_einnahmen:.2f} €")
        c2.metric("Ausgaben", f"{gesamt_ausgaben:.2f} €")
        c3.metric("Kontostand", f"{kontostand:.2f} €")

        if PANDAS_AVAILABLE and alle:
            st.markdown("###### :material/trending_up: Vermögensentwicklung")
            df_kasse = pd.DataFrame([
                {"Datum": e.zeitpunkt, "Betrag": e.betrag if e.typ == "Einnahme" else -e.betrag}
                for e in sorted(alle, key=lambda x: x.zeitpunkt)
            ])
            df_kasse["Kontostand"] = df_kasse["Betrag"].cumsum()
            st.line_chart(df_kasse.set_index("Datum")["Kontostand"])

        st.divider()
        st.subheader("Wer schuldet wem? (Ausgaben-Ausgleich)")
        personen = sorted({e.person for e in alle})
        if personen and gesamt_ausgaben > 0:
            anteil_pro_person = gesamt_ausgaben / len(personen)
            bezahlt_pro_person = {
                p: sum(e.betrag for e in alle if e.typ == "Ausgabe" and e.person == p) for p in personen
            }
            saldo = {p: bezahlt_pro_person.get(p, 0) - anteil_pro_person for p in personen}

            glaeubiger = [[p, saldo[p]] for p in saldo if saldo[p] > 0.01]
            schuldner = [[p, -saldo[p]] for p in saldo if saldo[p] < -0.01]
            glaeubiger.sort(key=lambda x: -x[1])
            schuldner.sort(key=lambda x: -x[1])

            ausgleich = []
            i, j = 0, 0
            while i < len(schuldner) and j < len(glaeubiger):
                name_s, betrag_s = schuldner[i]
                name_g, betrag_g = glaeubiger[j]
                zahlung = min(betrag_s, betrag_g)
                ausgleich.append(f"**{name_s}** schuldet **{name_g}**: {zahlung:.2f} €")
                schuldner[i][1] -= zahlung
                glaeubiger[j][1] -= zahlung
                if schuldner[i][1] < 0.01:
                    i += 1
                if glaeubiger[j][1] < 0.01:
                    j += 1

            if ausgleich:
                for line in ausgleich:
                    st.markdown("- " + line)
            else:
                st.caption("Alles ausgeglichen.")
        else:
            st.caption("Noch keine Ausgaben erfasst.")

        st.divider()
        st.subheader("Alle Buchungen")
        for e in alle:
            tag = ' <span class="badge-nachtrag">NACHTRAG</span>' if e.is_nachtrag else ""
            with st.container(border=True):
                st.markdown(
                    f"**{format_ts(e.zeitpunkt)}** — {e.person} — {e.betrag:.2f} € — {e.beschreibung} ({e.typ}){tag}",
                    unsafe_allow_html=True,
                )

    with tab3:
        st.markdown("Behalte den Überblick, welcher Honig schon reserviert oder verkauft ist.")
        with st.form("neue_reservierung", clear_on_submit=True):
            kunde = st.text_input("Kunde")
            c1, c2 = st.columns(2)
            glaeser = c1.number_input("Anzahl Gläser", min_value=1, step=1)
            sorte = c2.text_input("Sorte (z. B. Frühtracht)")
            status_res = st.selectbox("Status", ["Reserviert", "Bezahlt", "Abgeholt"])
            notiz_res = st.text_input("Notiz (optional)")
            if st.form_submit_button("Reservierung anlegen", type="primary", icon=":material/add:") and kunde:
                db = get_db()
                try:
                    db.add(Reservierung(
                        kunde_name=kunde, glaeser=glaeser, sorte=sorte, status=status_res,
                        notiz=notiz_res, erstellt_am=datetime.datetime.now(),
                    ))
                    db.commit()
                finally:
                    db.close()
                st.success("Reservierung angelegt.")
                st.rerun()

        st.divider()
        db = get_db()
        try:
            res = db.query(Reservierung).order_by(Reservierung.erstellt_am.desc()).all()
            gesamt = sum(r.glaeser for r in res)
            st.caption(f"Insgesamt vergeben: {gesamt} Gläser")
            for r in res:
                with st.container(border=True):
                    c1, c2, c3 = st.columns([3, 2, 1])
                    text = f"**{r.kunde_name}** — {r.glaeser} Gläser" + (f" {r.sorte}" if r.sorte else "")
                    if r.notiz:
                        text += f"  \n_{r.notiz}_"
                    c1.markdown(text)
                    status_opts = ["Reserviert", "Bezahlt", "Abgeholt"]
                    neuer_status_res = c2.selectbox(
                        "Status", status_opts,
                        index=status_opts.index(r.status) if r.status in status_opts else 0,
                        key=f"res_status_{r.id}", label_visibility="collapsed",
                    )
                    if neuer_status_res != r.status:
                        r.status = neuer_status_res
                        db.commit()
                        st.rerun()
                    if c3.button("", key=f"res_del_{r.id}", icon=":material/delete:"):
                        db.delete(r)
                        db.commit()
                        st.rerun()
        finally:
            db.close()

# ---------------------------------------------------------------------------
# FOOTER
# ---------------------------------------------------------------------------
st.markdown(
    '<div class="fixed-footer">:material/hive: Rettet die Bienen, scheißt auf die Bäume :material/hive:</div>',
    unsafe_allow_html=True,
)

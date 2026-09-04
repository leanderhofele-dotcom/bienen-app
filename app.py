import streamlit as st
import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Boolean, DateTime, Text
)
from sqlalchemy.orm import declarative_base, sessionmaker, scoped_session

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

# ---------------------------------------------------------------------------
# GRUNDKONFIGURATION
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="🐝 Bienen-Logbuch",
    page_icon="🐝",
    layout="centered",
    initial_sidebar_state="expanded",
)

DEFAULT_IMKER = ["Anna", "Lukas", "Ben", "Mia"]
DEFAULT_VORGAENGE = [
    "Schwarmkontrolle", "Honigraum aufgesetzt", "Honigraum entnommen",
    "Königin gesichtet", "Königin markiert", "Varroa-Behandlung",
    "Fütterung", "Ablegerbildung", "Waben erneuert", "Allgemeine Durchsicht",
    "Winterbehandlung", "Erstfrühjahrskontrolle", "Sonstiges",
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

# ---------------------------------------------------------------------------
# DATENBANK-MODELLE
# ---------------------------------------------------------------------------
Base = declarative_base()


class Imker(Base):
    __tablename__ = "imker"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)


class Volk(Base):
    __tablename__ = "voelker"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    status = Column(String, default="🟢 Alles top")
    archiviert = Column(Boolean, default=False)


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


class Aufgabe(Base):
    __tablename__ = "aufgaben"
    id = Column(Integer, primary_key=True)
    titel = Column(String)
    zugewiesen_an = Column(String)
    faellig_am = Column(String)
    erledigt = Column(Boolean, default=False)


class KassenEintrag(Base):
    __tablename__ = "kasse"
    id = Column(Integer, primary_key=True)
    typ = Column(String)  # "Ausgabe" oder "Einnahme"
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


class Einstellung(Base):
    __tablename__ = "einstellungen"
    id = Column(Integer, primary_key=True)
    schluessel = Column(String, unique=True)
    wert = Column(String)


@st.cache_resource
def get_engine():
    db_url = st.secrets.get("DB_URL", "sqlite:///bienen.db")
    connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}
    engine = create_engine(db_url, connect_args=connect_args, pool_pre_ping=True)
    Base.metadata.create_all(engine)
    return engine


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
        if db.query(Vorgang).count() == 0:
            for name in DEFAULT_VORGAENGE:
                db.add(Vorgang(name=name))
        if db.query(Volk).count() == 0:
            db.add(Volk(name="Volk 1"))
            db.add(Volk(name="Volk 2"))
        db.commit()
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


def strip_emoji_prefix(status):
    if not status:
        return status
    teile = status.split(" ", 1)
    return teile[1] if len(teile) > 1 else status


def pdf_safe(text):
    if text is None:
        return ""
    return text.encode("latin-1", "ignore").decode("latin-1")


def hole_wetter():
    if not REQUESTS_AVAILABLE:
        return None, None
    try:
        lat = float(get_setting("standort_lat", "50.9375"))
        lon = float(get_setting("standort_lon", "6.9603"))
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
        r = requests.get(url, timeout=5)
        data = r.json()
        cw = data.get("current_weather", {})
        temp = cw.get("temperature")
        code = cw.get("weathercode")
        beschreibung = WEATTER_CODES.get(code, "Unbekannt")
        return temp, beschreibung
    except Exception:
        return None, None


def erstelle_stockkarte_pdf(volk_name, eintraege):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, pdf_safe(f"Stockkarte - {volk_name}"), ln=1)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 8, pdf_safe(f"Erstellt am {datetime.datetime.now().strftime('%d.%m.%Y %H:%M')}"), ln=1)
    pdf.ln(4)
    if not eintraege:
        pdf.set_font("Helvetica", "I", 11)
        pdf.cell(0, 8, "Keine Einträge vorhanden.", ln=1)
    for e in eintraege:
        pdf.set_font("Helvetica", "B", 11)
        status_text = strip_emoji_prefix(e.status)
        kopf = f"{format_ts(e.zeitpunkt)} | {e.imker} | {e.vorgang} | Status: {status_text}"
        if e.is_nachtrag:
            kopf += " (NACHTRAG)"
        pdf.multi_cell(0, 6, pdf_safe(kopf))
        pdf.set_font("Helvetica", "", 10)
        if e.notiz:
            pdf.multi_cell(0, 6, pdf_safe(f"Notiz: {e.notiz}"))
        if e.wetter_temp is not None:
            pdf.multi_cell(0, 6, pdf_safe(f"Wetter: {e.wetter_temp:.0f} Grad C, {e.wetter_text}"))
        pdf.ln(2)
    return bytes(pdf.output())


# ---------------------------------------------------------------------------
# SESSION-STATE GRUNDWERTE
# ---------------------------------------------------------------------------
st.session_state.setdefault("theme", "dark")
st.session_state.setdefault("view", "main")
st.session_state.setdefault("detail_volk_id", None)
st.session_state.setdefault("editing_id", None)
st.session_state.setdefault("log_form_version", 0)
st.session_state.setdefault("kasse_form_version", 0)

# ---------------------------------------------------------------------------
# SIDEBAR: LOGO, DARSTELLUNG, NAVIGATION
# ---------------------------------------------------------------------------
st.sidebar.markdown("## 🐝 Bienen-Logbuch")
theme_choice = st.sidebar.radio(
    "Darstellung", ["🌙 Dunkel", "☀️ Hell"],
    horizontal=True,
    index=0 if st.session_state.theme == "dark" else 1,
)
st.session_state.theme = "dark" if theme_choice == "🌙 Dunkel" else "light"

if st.session_state.view == "main":
    page = st.sidebar.radio(
        "Bereich wählen",
        ["📊 Dashboard", "📖 Logbuch", "⚙️ Verwaltung & Aufgaben", "💰 Imker-Kasse"],
        label_visibility="collapsed",
    )
else:
    page = None

# ---------------------------------------------------------------------------
# CSS: STARKER KONTRAST, DARK & LIGHT MODE
# ---------------------------------------------------------------------------
DARK_CSS = """
<style>
    .stApp { background-color: #0E1117; }
    h1, h2, h3, h4, h5, h6, p, span, label, li, div, .stMarkdown { color: #FFFFFF !important; }
    h1 { text-shadow: 0 0 10px #FFD700; border-bottom: 2px solid #F59E0B; padding-bottom: 8px; }
    section[data-testid="stSidebar"] { background-color: #000000; border-right: 2px solid #F59E0B; }
    div[data-testid="stForm"], div[data-testid="stVerticalBlockBorderWrapper"] {
        background-color: #1F2937; border: 1px solid #F59E0B; border-radius: 10px; padding: 10px;
    }
    .stButton > button, .stFormSubmitButton > button, .stDownloadButton > button {
        background-color: #FFD700; color: #000000 !important; font-weight: 700;
        border: none; border-radius: 8px; box-shadow: 0 0 8px #F59E0B;
    }
    .stButton > button:hover, .stFormSubmitButton > button:hover, .stDownloadButton > button:hover {
        background-color: #F59E0B; color: #000000 !important; box-shadow: 0 0 14px #FFD700;
    }
    .stButton > button *, .stFormSubmitButton > button *, .stDownloadButton > button * { color: #000000 !important; }
    div[data-baseweb="select"] > div, .stTextInput input, .stTextArea textarea,
    .stNumberInput input, .stDateInput input, .stTimeInput input {
        background-color: #1A1D25 !important; color: #FFFFFF !important; border: 1px solid #F59E0B !important;
    }
    div[data-baseweb="popover"] li, ul[data-baseweb="menu"] li, ul[role="listbox"] li {
        background-color: #1A1D25 !important; color: #FFFFFF !important;
    }
    .stTabs [data-baseweb="tab"] { color: #FFD700 !important; }
    .stTabs [aria-selected="true"] { color: #000000 !important; background-color: #FFD700; border-radius: 6px 6px 0 0; }
    .stTabs [aria-selected="true"] * { color: #000000 !important; }
    div[data-testid="stMetric"] { background-color: #1F2937; border: 1px solid #F59E0B; border-radius: 10px; padding: 10px; }
    .badge-nachtrag { background-color: #EF4444; color: #FFFFFF !important; padding: 2px 8px; border-radius: 6px; font-size: 0.75em; font-weight: 700; }
    .volk-link button { text-align: left !important; }
    .fixed-footer {
        position: fixed; left: 0; bottom: 0; width: 100%; background-color: #000000; color: #FFD700 !important;
        text-align: center; padding: 8px 0; font-weight: 700; border-top: 1px solid #F59E0B; z-index: 999;
    }
    .block-container { padding-bottom: 70px; }
</style>
"""

LIGHT_CSS = """
<style>
    .stApp { background-color: #FFFBEB; }
    h1, h2, h3, h4, h5, h6, p, span, label, li, div, .stMarkdown { color: #1E293B !important; }
    h1 { border-bottom: 2px solid #D97706; padding-bottom: 8px; }
    section[data-testid="stSidebar"] { background-color: #FFF3D6; border-right: 2px solid #D97706; }
    div[data-testid="stForm"], div[data-testid="stVerticalBlockBorderWrapper"] {
        background-color: #FFFFFF; border: 1px solid #D97706; border-radius: 10px; padding: 10px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.08);
    }
    .stButton > button, .stFormSubmitButton > button, .stDownloadButton > button {
        background-color: #D97706; color: #FFFFFF !important; font-weight: 700; border: none; border-radius: 8px;
    }
    .stButton > button:hover, .stFormSubmitButton > button:hover, .stDownloadButton > button:hover {
        background-color: #B45309; color: #FFFFFF !important;
    }
    .stButton > button *, .stFormSubmitButton > button *, .stDownloadButton > button * { color: #FFFFFF !important; }
    div[data-baseweb="select"] > div, .stTextInput input, .stTextArea textarea,
    .stNumberInput input, .stDateInput input, .stTimeInput input {
        background-color: #F3F4F6 !important; color: #1E293B !important; border: 1px solid #D97706 !important;
    }
    div[data-baseweb="popover"] li, ul[data-baseweb="menu"] li, ul[role="listbox"] li {
        background-color: #FFFFFF !important; color: #1E293B !important;
    }
    .stTabs [data-baseweb="tab"] { color: #B45309 !important; }
    .stTabs [aria-selected="true"] { color: #FFFFFF !important; background-color: #D97706; border-radius: 6px 6px 0 0; }
    .stTabs [aria-selected="true"] * { color: #FFFFFF !important; }
    div[data-testid="stMetric"] { background-color: #FFFFFF; border: 1px solid #D97706; border-radius: 10px; padding: 10px; }
    .badge-nachtrag { background-color: #FCA5A5; color: #7F1D1D !important; padding: 2px 8px; border-radius: 6px; font-size: 0.75em; font-weight: 700; }
    .volk-link button { text-align: left !important; }
    .fixed-footer {
        position: fixed; left: 0; bottom: 0; width: 100%; background-color: #D97706; color: #000000 !important;
        text-align: center; padding: 8px 0; font-weight: 700; border-top: 1px solid #B45309; z-index: 999;
    }
    .block-container { padding-bottom: 70px; }
</style>
"""

st.markdown(DARK_CSS if st.session_state.theme == "dark" else LIGHT_CSS, unsafe_allow_html=True)

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
        st.toast(f"🐝 Neuer Logbuch-Eintrag von {last_log.imker}!", icon="🆕")
        st.session_state.seen_log_id = current_log_id
    if current_kasse_id > st.session_state.seen_kasse_id:
        st.toast(f"💰 Neue Kassen-Buchung von {last_kasse.person}!", icon="🆕")
        st.session_state.seen_kasse_id = current_kasse_id


check_new_entries()

# ---------------------------------------------------------------------------
# WIEDERVERWENDBARE BEARBEITBARE LOGBUCH-EINTRAGS-ANSICHT
# ---------------------------------------------------------------------------
def render_editable_log_entry(e, imker_liste, volk_liste, vorgang_liste, show_volk=False):
    if st.session_state.editing_id == e.id:
        with st.container(border=True):
            st.markdown("**✏️ Eintrag bearbeiten**")
            neu_imker = st.selectbox("Wer", imker_liste, index=imker_liste.index(e.imker) if e.imker in imker_liste else 0, key=f"edit_wer_{e.id}")
            neu_volk = st.selectbox("Volk", volk_liste, index=volk_liste.index(e.volk) if e.volk in volk_liste else 0, key=f"edit_volk_{e.id}")
            neu_vorgang = st.selectbox("Vorgang", vorgang_liste, index=vorgang_liste.index(e.vorgang) if e.vorgang in vorgang_liste else 0, key=f"edit_vorgang_{e.id}")
            neu_status = st.selectbox("Status", STATUS_OPTIONS, index=STATUS_OPTIONS.index(e.status) if e.status in STATUS_OPTIONS else 0, key=f"edit_status_{e.id}")
            neu_notiz = st.text_area("Notizen", value=e.notiz or "", key=f"edit_notiz_{e.id}")
            c1, c2 = st.columns(2)
            neu_datum = c1.date_input("Datum", value=e.zeitpunkt.date() if e.zeitpunkt else datetime.date.today(), format="DD.MM.YYYY", key=f"edit_datum_{e.id}")
            neu_zeit = c2.time_input("Uhrzeit", value=e.zeitpunkt.time() if e.zeitpunkt else datetime.datetime.now().time(), key=f"edit_zeit_{e.id}")

            b1, b2, b3 = st.columns(3)
            if b1.button("💾 Speichern", key=f"save_{e.id}"):
                db = get_db()
                try:
                    obj = db.query(LogEintrag).get(e.id)
                    obj.imker = neu_imker
                    obj.volk = neu_volk
                    obj.vorgang = neu_vorgang
                    obj.status = neu_status
                    obj.notiz = neu_notiz
                    obj.zeitpunkt = datetime.datetime.combine(neu_datum, neu_zeit)
                    db.commit()
                finally:
                    db.close()
                st.session_state.editing_id = None
                st.success("Eintrag aktualisiert.")
                st.rerun()
            if b2.button("❌ Abbrechen", key=f"cancel_{e.id}"):
                st.session_state.editing_id = None
                st.rerun()
            if b3.button("🗑️ Löschen", key=f"delete_{e.id}"):
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
            volk_praefix = f"{e.volk} — " if show_volk else ""
            wetter_info = f" · {e.wetter_temp:.0f}°C, {e.wetter_text}" if e.wetter_temp is not None else ""
            st.markdown(
                f"**{format_ts(e.zeitpunkt)}** — {volk_praefix}**{e.imker}**: {e.vorgang} ({e.status}){wetter_info}{tag}",
                unsafe_allow_html=True,
            )
            if e.notiz:
                st.caption(e.notiz)
            if st.button("✏️ Bearbeiten", key=f"edit_btn_{e.id}"):
                st.session_state.editing_id = e.id
                st.rerun()


# ---------------------------------------------------------------------------
# VOLK-DETAILANSICHT (übers Dashboard erreichbar)
# ---------------------------------------------------------------------------
def render_volk_detail(volk_id):
    db = get_db()
    try:
        volk = db.query(Volk).get(volk_id)
        imker_liste = [i.name for i in db.query(Imker).order_by(Imker.name).all()]
        volk_liste = [v.name for v in db.query(Volk).filter(Volk.archiviert == False).order_by(Volk.name).all()]
        vorgang_liste = [v.name for v in db.query(Vorgang).order_by(Vorgang.name).all()]
    finally:
        db.close()

    if volk is None:
        st.warning("Dieses Volk existiert nicht mehr.")
        if st.button("⬅ Zurück zum Dashboard"):
            st.session_state.view = "main"
            st.rerun()
        return

    if st.button("⬅ Zurück zum Dashboard"):
        st.session_state.view = "main"
        st.session_state.editing_id = None
        st.rerun()

    st.title(f"🐝 {volk.name}")
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

    tab1, tab2 = st.tabs(["📜 Komplettes Logbuch", "📄 Stockkarte (PDF)"])

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
        st.caption(f"{len(eintraege)} Einträge für dieses Volk")
        if not eintraege:
            st.info("Für dieses Volk gibt es noch keine Einträge.")
        for e in eintraege:
            render_editable_log_entry(e, imker_liste, volk_liste, vorgang_liste, show_volk=False)

    with tab2:
        st.markdown("Hier kannst du die gesetzlich vorgeschriebene Stockkarte als PDF herunterladen (z. B. für das Veterinäramt).")
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
            finally:
                db.close()
            pdf_bytes = erstelle_stockkarte_pdf(volk.name, eintraege_chrono)
            st.download_button(
                "📄 Stockkarte als PDF herunterladen",
                data=pdf_bytes,
                file_name=f"Stockkarte_{volk.name.replace(' ', '_')}.pdf",
                mime="application/pdf",
            )


# ---------------------------------------------------------------------------
# ROUTING
# ---------------------------------------------------------------------------
if st.session_state.view == "volk_detail":
    render_volk_detail(st.session_state.detail_volk_id)

# ---------------------------------------------------------------------------
# SEITE: DASHBOARD
# ---------------------------------------------------------------------------
elif page == "📊 Dashboard":
    st.title("📊 Völker-Dashboard")
    db = get_db()
    try:
        voelker = db.query(Volk).filter(Volk.archiviert == False).order_by(Volk.name).all()
        if not voelker:
            st.info("Noch keine Völker angelegt. Geh zu '⚙️ Verwaltung & Aufgaben'.")
        for volk in voelker:
            with st.container(border=True):
                col1, col2 = st.columns([2, 1])
                with col1:
                    st.markdown('<div class="volk-link">', unsafe_allow_html=True)
                    if st.button(f"🐝 {volk.name}  ➜", key=f"open_{volk.id}", use_container_width=True):
                        st.session_state.view = "volk_detail"
                        st.session_state.detail_volk_id = volk.id
                        st.session_state.editing_id = None
                        st.rerun()
                    st.markdown('</div>', unsafe_allow_html=True)
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
                    st.markdown("**Letzte Einträge:** _(zum Bearbeiten auf den Volksnamen oben klicken)_")
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

# ---------------------------------------------------------------------------
# SEITE: LOGBUCH
# ---------------------------------------------------------------------------
elif page == "📖 Logbuch":
    st.title("📖 Logbuch")
    tab1, tab2 = st.tabs(["✍️ Neuer Eintrag", "🔍 Historie & Suche"])

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
            st.warning("Bitte zuerst unter '⚙️ Verwaltung & Aufgaben' ein Volk bzw. eine Person anlegen.")
        else:
            v = st.session_state.log_form_version

            st.markdown("##### 👤 Imker & Volk")
            c1, c2 = st.columns(2)
            wer = c1.selectbox("Wer bist du?", imker_liste, key=f"log_wer_{v}")
            volk = c2.selectbox("Welches Volk?", volk_liste, key=f"log_volk_{v}")

            st.markdown("##### 🛠️ Vorgang & Zustand")
            c3, c4 = st.columns(2)
            vorgang = c3.selectbox("Vorgang/Aktion", vorgang_liste, key=f"log_vorgang_{v}")
            status = c4.selectbox("Status-Update", STATUS_OPTIONS, key=f"log_status_{v}")

            st.markdown("##### 📝 Notizen")
            notiz = st.text_area("Beobachtungen", placeholder="z. B. 3 Brutwaben gesehen, Volk sehr ruhig, Stifte vorhanden", key=f"log_notiz_{v}", label_visibility="collapsed")

            st.markdown("##### 🕘 Zeitpunkt")
            ist_nachtrag = st.toggle("Ist das ein Nachtrag?", key=f"log_nachtrag_{v}")
            nachtrag_datum, nachtrag_zeit = None, None
            if ist_nachtrag:
                c5, c6 = st.columns(2)
                nachtrag_datum = c5.date_input("Datum", format="DD.MM.YYYY", key=f"log_datum_{v}")
                nachtrag_zeit = c6.time_input("Uhrzeit", key=f"log_zeit_{v}")
            else:
                st.caption("Es wird automatisch der aktuelle Zeitpunkt gespeichert.")

            if st.button("💾 Eintrag speichern", use_container_width=True, key=f"log_save_{v}"):
                if ist_nachtrag and nachtrag_datum and nachtrag_zeit:
                    zeitpunkt = datetime.datetime.combine(nachtrag_datum, nachtrag_zeit)
                    wetter_temp, wetter_text = None, None
                else:
                    zeitpunkt = datetime.datetime.now()
                    wetter_temp, wetter_text = hole_wetter()

                db = get_db()
                try:
                    db.add(LogEintrag(
                        imker=wer, volk=volk, vorgang=vorgang, status=status,
                        notiz=notiz, zeitpunkt=zeitpunkt, is_nachtrag=ist_nachtrag,
                        wetter_temp=wetter_temp, wetter_text=wetter_text,
                    ))
                    volk_obj = db.query(Volk).filter(Volk.name == volk).first()
                    if volk_obj:
                        volk_obj.status = status
                    db.commit()
                finally:
                    db.close()
                st.session_state.log_form_version += 1
                st.success("Eintrag erfolgreich gespeichert! 🐝")
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
        suchtext = st.text_input("🔍 Freitextsuche (Notizen)")

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

# ---------------------------------------------------------------------------
# SEITE: VERWALTUNG & AUFGABEN
# ---------------------------------------------------------------------------
elif page == "⚙️ Verwaltung & Aufgaben":
    st.title("⚙️ Verwaltung & Aufgaben")
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
        ["🐝 Völker", "🛠️ Vorgänge", "👥 Imker", "✅ Aufgaben", "📦 Material", "📍 Standort"]
    )

    with tab1:
        db = get_db()
        try:
            neu = st.text_input("Neues Volk anlegen (Name)")
            if st.button("➕ Volk hinzufügen") and neu:
                if not db.query(Volk).filter(Volk.name == neu).first():
                    db.add(Volk(name=neu))
                    db.commit()
                    st.success(f"Volk '{neu}' angelegt.")
                    st.rerun()
                else:
                    st.warning("Ein Volk mit diesem Namen existiert schon.")

            st.divider()
            voelker = db.query(Volk).order_by(Volk.archiviert, Volk.name).all()
            for v in voelker:
                c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
                c1.write(("🗄️ " if v.archiviert else "🟢 ") + v.name)
                neuer_name = c2.text_input(
                    "Umbenennen", value=v.name, key=f"rename_{v.id}", label_visibility="collapsed"
                )
                if c3.button("✏️", key=f"btn_rename_{v.id}"):
                    v.name = neuer_name
                    db.commit()
                    st.rerun()
                label = "📤" if v.archiviert else "📥"
                if c4.button(label, key=f"btn_arch_{v.id}"):
                    v.archiviert = not v.archiviert
                    db.commit()
                    st.rerun()
        finally:
            db.close()

    with tab2:
        db = get_db()
        try:
            neu = st.text_input("Neuen Vorgang/Aktion hinzufügen")
            if st.button("➕ Vorgang hinzufügen") and neu:
                if not db.query(Vorgang).filter(Vorgang.name == neu).first():
                    db.add(Vorgang(name=neu))
                    db.commit()
                    st.success(f"Vorgang '{neu}' hinzugefügt.")
                    st.rerun()
                else:
                    st.warning("Dieser Vorgang existiert schon.")
            st.divider()
            for v in db.query(Vorgang).order_by(Vorgang.name).all():
                st.write("• " + v.name)
        finally:
            db.close()

    with tab3:
        db = get_db()
        try:
            neu = st.text_input("Neue Person hinzufügen")
            if st.button("➕ Person hinzufügen") and neu:
                if not db.query(Imker).filter(Imker.name == neu).first():
                    db.add(Imker(name=neu))
                    db.commit()
                    st.success(f"'{neu}' wurde hinzugefügt.")
                    st.rerun()
                else:
                    st.warning("Diese Person existiert schon.")
            st.divider()
            for i in db.query(Imker).order_by(Imker.name).all():
                st.write("• " + i.name)
        finally:
            db.close()

    with tab4:
        db = get_db()
        try:
            imker_liste = [i.name for i in db.query(Imker).order_by(Imker.name).all()]
        finally:
            db.close()

        with st.form("neue_aufgabe", clear_on_submit=True):
            titel = st.text_input("Aufgabe")
            zugewiesen = st.selectbox("Zugewiesen an", imker_liste) if imker_liste else None
            faellig = st.date_input("Fällig am", format="DD.MM.YYYY")
            if st.form_submit_button("➕ Aufgabe anlegen") and titel:
                db = get_db()
                try:
                    db.add(Aufgabe(
                        titel=titel, zugewiesen_an=zugewiesen,
                        faellig_am=faellig.strftime("%d.%m.%Y"),
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
            erledigte = db.query(Aufgabe).filter(Aufgabe.erledigt == True).all()

            st.subheader("Offene Aufgaben")
            if not offene:
                st.caption("Keine offenen Aufgaben. 🎉")
            for a in offene:
                c1, c2 = st.columns([4, 1])
                c1.write(f"**{a.titel}** — {a.zugewiesen_an} — fällig {a.faellig_am}")
                if c2.button("✅", key=f"done_{a.id}"):
                    a.erledigt = True
                    db.commit()
                    st.rerun()

            with st.expander(f"Erledigte Aufgaben ({len(erledigte)})"):
                for a in erledigte:
                    c1, c2 = st.columns([4, 1])
                    c1.write(f"~~{a.titel}~~ — {a.zugewiesen_an}")
                    if c2.button("↩️", key=f"undo_{a.id}"):
                        a.erledigt = False
                        db.commit()
                        st.rerun()
        finally:
            db.close()

    with tab5:
        st.markdown("Behalte den Überblick über euer Material, damit niemand versehentlich doppelt einkauft.")
        db = get_db()
        try:
            c1, c2, c3 = st.columns([2, 1, 1])
            neu_name = c1.text_input("Artikel", key="inv_neu_name")
            neu_menge = c2.number_input("Menge", min_value=0.0, step=1.0, key="inv_neu_menge")
            neu_einheit = c3.text_input("Einheit", value="Stück", key="inv_neu_einheit")
            if st.button("➕ Artikel hinzufügen") and neu_name:
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
                c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 1, 1])
                c1.write(f"**{item.name}**")
                c2.write(f"{item.menge:g} {item.einheit}")
                if c3.button("➖", key=f"minus_{item.id}"):
                    item.menge = max(0, item.menge - 1)
                    db.commit()
                    st.rerun()
                if c4.button("➕", key=f"plus_{item.id}"):
                    item.menge += 1
                    db.commit()
                    st.rerun()
                if c5.button("🗑️", key=f"del_inv_{item.id}"):
                    db.delete(item)
                    db.commit()
                    st.rerun()
        finally:
            db.close()

    with tab6:
        st.markdown("Trag hier die Koordinaten eures Bienenstands ein, damit die App beim Speichern automatisch das aktuelle Wetter mit abspeichert.")
        lat_default = float(get_setting("standort_lat", "50.9375"))
        lon_default = float(get_setting("standort_lon", "6.9603"))
        c1, c2 = st.columns(2)
        neu_lat = c1.number_input("Breitengrad (Latitude)", value=lat_default, format="%.4f")
        neu_lon = c2.number_input("Längengrad (Longitude)", value=lon_default, format="%.4f")
        st.caption("Tipp: Adresse bei Google Maps eingeben, Rechtsklick auf den Punkt → Koordinaten werden angezeigt.")
        if st.button("💾 Standort speichern"):
            set_setting("standort_lat", neu_lat)
            set_setting("standort_lon", neu_lon)
            st.success("Standort gespeichert.")

# ---------------------------------------------------------------------------
# SEITE: IMKER-KASSE
# ---------------------------------------------------------------------------
elif page == "💰 Imker-Kasse":
    st.title("💰 Imker-Kasse")
    db = get_db()
    try:
        imker_liste = [i.name for i in db.query(Imker).order_by(Imker.name).all()]
    finally:
        db.close()

    tab1, tab2 = st.tabs(["✍️ Buchung erfassen", "📈 Kassensturz"])

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

        if st.button("💾 Buchung speichern", use_container_width=True, key=f"kasse_save_{v}"):
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
                st.caption("Alles ausgeglichen. ⚖️")
        else:
            st.caption("Noch keine Ausgaben erfasst.")

        st.divider()
        st.subheader("Alle Buchungen")
        for e in alle:
            tag = ' <span class="badge-nachtrag">NACHTRAG</span>' if e.is_nachtrag else ""
            symbol = "🔴" if e.typ == "Ausgabe" else "🟢"
            with st.container(border=True):
                st.markdown(
                    f"{symbol} **{format_ts(e.zeitpunkt)}** — {e.person} — {e.betrag:.2f} € — {e.beschreibung}{tag}",
                    unsafe_allow_html=True,
                )

# ---------------------------------------------------------------------------
# FOOTER
# ---------------------------------------------------------------------------
st.markdown(
    '<div class="fixed-footer">🐝 Rettet die Bienen, scheißt auf die Bäume 🐝</div>',
    unsafe_allow_html=True,
)

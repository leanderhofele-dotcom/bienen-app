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

# ---------------------------------------------------------------------------
# CYBERPUNK-DESIGN
# ---------------------------------------------------------------------------
CYBERPUNK_CSS = """
<style>
    .stApp {
        background-color: #0E1117;
        color: #FFFFFF;
    }
    h1, h2, h3, h4, h5, h6, p, span, label, div {
        color: #FFFFFF;
    }
    h1 {
        text-shadow: 0 0 10px #FFD700;
        border-bottom: 2px solid #F59E0B;
        padding-bottom: 8px;
    }
    section[data-testid="stSidebar"] {
        background-color: #000000;
        border-right: 2px solid #F59E0B;
    }
    div[data-testid="stForm"], div[data-testid="stVerticalBlockBorderWrapper"] {
        background-color: #14161C;
        border: 1px solid #F59E0B;
        border-radius: 10px;
        padding: 10px;
    }
    .stButton > button, .stFormSubmitButton > button {
        background-color: #FFD700;
        color: #000000;
        font-weight: 700;
        border: none;
        border-radius: 8px;
        box-shadow: 0 0 8px #F59E0B;
    }
    .stButton > button:hover, .stFormSubmitButton > button:hover {
        background-color: #F59E0B;
        color: #000000;
        box-shadow: 0 0 14px #FFD700;
    }
    div[data-baseweb="select"] > div, .stTextInput input, .stTextArea textarea,
    .stNumberInput input, .stDateInput input, .stTimeInput input {
        background-color: #1A1D25 !important;
        color: #FFFFFF !important;
        border: 1px solid #F59E0B !important;
    }
    .stTabs [data-baseweb="tab"] {
        color: #FFD700;
    }
    .stTabs [aria-selected="true"] {
        color: #000000;
        background-color: #FFD700;
        border-radius: 6px 6px 0 0;
    }
    div[data-testid="stMetric"] {
        background-color: #14161C;
        border: 1px solid #F59E0B;
        border-radius: 10px;
        padding: 10px;
    }
    .fixed-footer {
        position: fixed;
        left: 0;
        bottom: 0;
        width: 100%;
        background-color: #000000;
        color: #FFD700;
        text-align: center;
        padding: 8px 0;
        font-weight: 600;
        border-top: 1px solid #F59E0B;
        z-index: 999;
    }
    .block-container {
        padding-bottom: 70px;
    }
</style>
"""
st.markdown(CYBERPUNK_CSS, unsafe_allow_html=True)

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


def format_ts(dt):
    if dt is None:
        return "-"
    return dt.strftime("%d.%m.%Y %H:%M")


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

    if "seen_log_id" not in st.session_state:
        st.session_state.seen_log_id = current_log_id
    if "seen_kasse_id" not in st.session_state:
        st.session_state.seen_kasse_id = current_kasse_id

    if current_log_id > st.session_state.seen_log_id:
        st.toast(f"🐝 Neuer Logbuch-Eintrag von {last_log.imker}!", icon="🆕")
        st.session_state.seen_log_id = current_log_id
    if current_kasse_id > st.session_state.seen_kasse_id:
        st.toast(f"💰 Neue Kassen-Buchung von {last_kasse.person}!", icon="🆕")
        st.session_state.seen_kasse_id = current_kasse_id


check_new_entries()

# ---------------------------------------------------------------------------
# NAVIGATION
# ---------------------------------------------------------------------------
st.sidebar.markdown("## 🐝 Bienen-Logbuch")
page = st.sidebar.radio(
    "Bereich wählen",
    ["📊 Dashboard", "📖 Logbuch", "⚙️ Verwaltung & Aufgaben", "💰 Imker-Kasse"],
    label_visibility="collapsed",
)

# ---------------------------------------------------------------------------
# SEITE: DASHBOARD
# ---------------------------------------------------------------------------
if page == "📊 Dashboard":
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
                    st.subheader(volk.name)
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
                    st.markdown("**Letzte Einträge:**")
                    for e in letzte:
                        tag = " `[NACHTRAG]`" if e.is_nachtrag else ""
                        st.markdown(
                            f"- {format_ts(e.zeitpunkt)} — **{e.imker}**: {e.vorgang}{tag}"
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
            with st.form("neuer_log_eintrag", clear_on_submit=True):
                wer = st.selectbox("Wer", imker_liste)
                volk = st.selectbox("Volk", volk_liste)
                vorgang = st.selectbox("Vorgang/Aktion", vorgang_liste)
                status = st.selectbox("Status-Update", STATUS_OPTIONS)
                notiz = st.text_area("Notizen")

                ist_nachtrag = st.checkbox("Ist das ein Nachtrag?")
                nachtrag_datum, nachtrag_zeit = None, None
                if ist_nachtrag:
                    c1, c2 = st.columns(2)
                    with c1:
                        nachtrag_datum = st.date_input("Datum", format="DD.MM.YYYY")
                    with c2:
                        nachtrag_zeit = st.time_input("Uhrzeit")

                submitted = st.form_submit_button("💾 Eintrag speichern")
                if submitted:
                    if ist_nachtrag and nachtrag_datum and nachtrag_zeit:
                        zeitpunkt = datetime.datetime.combine(nachtrag_datum, nachtrag_zeit)
                    else:
                        zeitpunkt = datetime.datetime.now()

                    db = get_db()
                    try:
                        db.add(LogEintrag(
                            imker=wer, volk=volk, vorgang=vorgang, status=status,
                            notiz=notiz, zeitpunkt=zeitpunkt, is_nachtrag=ist_nachtrag,
                        ))
                        v = db.query(Volk).filter(Volk.name == volk).first()
                        if v:
                            v.status = status
                        db.commit()
                    finally:
                        db.close()
                    st.success("Eintrag gespeichert! 🐝")
                    st.rerun()

    with tab2:
        db = get_db()
        try:
            alle = db.query(LogEintrag).order_by(LogEintrag.zeitpunkt.desc()).all()
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
            tag = " 🏷️ `[NACHTRAG]`" if e.is_nachtrag else ""
            with st.container(border=True):
                st.markdown(f"**{format_ts(e.zeitpunkt)}** — {e.volk} — **{e.imker}**: {e.vorgang} ({e.status}){tag}")
                if e.notiz:
                    st.caption(e.notiz)

# ---------------------------------------------------------------------------
# SEITE: VERWALTUNG & AUFGABEN
# ---------------------------------------------------------------------------
elif page == "⚙️ Verwaltung & Aufgaben":
    st.title("⚙️ Verwaltung & Aufgaben")
    tab1, tab2, tab3, tab4 = st.tabs(["🐝 Völker", "🛠️ Vorgänge", "👥 Imker", "✅ Aufgaben"])

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
        with st.form("neue_buchung", clear_on_submit=True):
            typ = st.radio("Art", ["Ausgabe (Material)", "Einnahme (Honigverkauf)"], horizontal=True)
            betrag = st.number_input("Betrag (€)", min_value=0.0, step=0.5, format="%.2f")
            person = st.selectbox("Wer hat bezahlt / Geld entgegengenommen?", imker_liste)
            beschreibung = st.text_input("Beschreibung")

            ist_nachtrag = st.checkbox("Ist das ein Nachtrag?")
            nachtrag_datum, nachtrag_zeit = None, None
            if ist_nachtrag:
                c1, c2 = st.columns(2)
                nachtrag_datum = c1.date_input("Datum", format="DD.MM.YYYY")
                nachtrag_zeit = c2.time_input("Uhrzeit")

            if st.form_submit_button("💾 Buchung speichern"):
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
            tag = " 🏷️ `[NACHTRAG]`" if e.is_nachtrag else ""
            symbol = "🔴" if e.typ == "Ausgabe" else "🟢"
            with st.container(border=True):
                st.markdown(
                    f"{symbol} **{format_ts(e.zeitpunkt)}** — {e.person} — {e.betrag:.2f} € — {e.beschreibung}{tag}"
                )

# ---------------------------------------------------------------------------
# FOOTER
# ---------------------------------------------------------------------------
st.markdown(
    '<div class="fixed-footer">🐝 Rettet die Bienen, scheißt auf die Bäume 🐝</div>',
    unsafe_allow_html=True,
)

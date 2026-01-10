import streamlit as st
import pandas as pd
from datetime import date, timedelta
import pyodbc
from dotenv import load_dotenv
import os

# Laden der Umgebungsvariablen (SERVER, DATABASE, UID, PWD) aus der .env-Datei
load_dotenv()

########################################################################################################################

# --- 1. Konfiguration und Initialisierung ---

st.set_page_config(layout="wide", page_title="Dashboard Filter Demo")

# Standardwerte für Datumsfelder
DEFAULT_START_DATE = date(2025, 1, 1)
DEFAULT_END_DATE = date.today()

# Initialisiere alle Filter-Keys im Session State
# UI State Keys (von Widgets gelesen)
if 'zeitraum_input' not in st.session_state: st.session_state['zeitraum_input'] = 'Gesamt'
if 'start_date_input' not in st.session_state: st.session_state['start_date_input'] = DEFAULT_START_DATE
if 'end_date_input' not in st.session_state: st.session_state['end_date_input'] = DEFAULT_END_DATE
if 'produkt_filter_exklusiv' not in st.session_state: st.session_state['produkt_filter_exklusiv'] = False
if 'kunde_input' not in st.session_state: st.session_state['kunde_input'] = []
if 'produkt_input' not in st.session_state: st.session_state['produkt_input'] = []

# Steuert, ob die angewendeten Filter die DB-Abfrage triggern sollen (Muss beim Start FALSE sein)
if 'data_applied' not in st.session_state: st.session_state['data_applied'] = False

# Applied State Keys (von DB-Funktion gelesen) - Initialisierung auf Standardwerte
# HINWEIS: Die Funktion _init_applied_state() wurde entfernt, da sie data_applied = True gesetzt hat.
if 'applied_zeitraum' not in st.session_state: st.session_state['applied_zeitraum'] = 'Gesamt'
if 'applied_start_date' not in st.session_state: st.session_state['applied_start_date'] = DEFAULT_START_DATE
if 'applied_end_date' not in st.session_state: st.session_state['applied_end_date'] = DEFAULT_END_DATE
if 'applied_kunde_input' not in st.session_state: st.session_state['applied_kunde_input'] = []
if 'applied_produkt_input' not in st.session_state: st.session_state['applied_produkt_input'] = []
if 'applied_produkt_filter_exklusiv' not in st.session_state: st.session_state[
    'applied_produkt_filter_exklusiv'] = False

# Security Level
if "security_level" not in st.session_state:
    st.session_state["security_level"] = 3  # Default für Studenten (Admin Rechte)
st.set_page_config(layout="wide", page_title="Dashboard Filter Demo")

def apply_filters():
    """Kopiert alle aktuellen UI-Filterwerte in die 'applied'-Keys und setzt den Trigger."""
    st.session_state['applied_zeitraum'] = st.session_state['zeitraum_input']
    st.session_state['applied_start_date'] = st.session_state['start_date_input']
    st.session_state['applied_end_date'] = st.session_state['end_date_input']
    st.session_state['applied_kunde_input'] = st.session_state['kunde_input']
    st.session_state['applied_produkt_input'] = st.session_state['produkt_input']
    st.session_state['applied_produkt_filter_exklusiv'] = st.session_state['produkt_filter_exklusiv']
    # Wichtig: Setze den Trigger, damit die DB-Abfrage beim nächsten Rerun ausgeführt wird
    st.session_state.data_applied = True

    # NEU: Erzwinge sofortigen Rerun, damit die gecachten Funktionen den neuen State sehen
    st.rerun()


def reset_filters():
    """Setzt alle Filter im Session State auf ihre Standardwerte zurück und wendet sie an."""
    # 1. UI Keys zurücksetzen
    st.session_state['zeitraum_input'] = 'Gesamt'
    st.session_state['start_date_input'] = DEFAULT_START_DATE
    st.session_state['end_date_input'] = DEFAULT_END_DATE
    st.session_state['kunde_input'] = []
    st.session_state['produkt_input'] = []
    st.session_state['produkt_filter_exklusiv'] = False

    # 2. Applied Keys sofort aktualisieren, um die Datenabfrage zu triggern
    apply_filters()


def update_dates_on_period_change():
    """
    Callback-Funktion, die die Start- und Enddaten im Session State
    aktualisiert, sobald die Zeitraum-Selectbox geändert wird.
    """
    zeitraum = st.session_state.get('zeitraum_input', 'Gesamt')
    current_end_date = date.today()

    # Holen Sie sich das min_data_date aus dem Session State, falls es gesetzt wurde (nach Datenladung)
    # Ansonsten Fallback auf den initialen Wert.
    min_data_date_fallback = st.session_state.get('min_data_date', DEFAULT_START_DATE)

    target_start_date = None
    target_end_date = current_end_date

    if zeitraum == 'Letzte 7 Tage':
        target_start_date = current_end_date - timedelta(days=7)
    elif zeitraum == 'Letzte 30 Tage':
        target_start_date = current_end_date - timedelta(days=30)
    elif zeitraum == 'Gesamt':
        # Bei 'Gesamt' die tatsächliche Min-Range verwenden
        target_start_date = min_data_date_fallback
        target_end_date = current_end_date

        # Nur aktualisieren, wenn ein vordefinierter Zeitraum gewählt wurde
    if target_start_date is not None and zeitraum != 'Benutzerdefiniert':
        st.session_state['start_date_input'] = target_start_date
        st.session_state['end_date_input'] = target_end_date


########################################################################################################################
# SQL

#######################################################################################################################
# --- HILFSFUNKTIONEN ZUM LADEN VON DATEN MIT EXPLIZITEM CACHING ---

def _get_db_connection():
    """Stellt die Datenbankverbindung her (wird NICHT gecached)."""
    server = os.environ.get('SERVER')
    database = os.environ.get('DATABASE')
    uid = os.environ.get('UID')
    pwd = os.environ.get('PWD')

    if not all([server, database, uid, pwd]):
        st.error(
            "Datenbank-Konfiguration fehlt! Bitte stellen Sie sicher, dass SERVER, DATABASE, UID und PWD in der .env-Datei gesetzt sind.")
        return None
    try:
        connection_string = (
            "Driver={ODBC Driver 17 for SQL Server};"
            f"Server={server};"
            f"Database={database};"
            f"UID={uid};"
            f"PWD={pwd}"
        )
        return connection_string
    except Exception as e:
        st.error(f"Fehler beim Erstellen des Connection Strings: {e}")
        return None


@st.cache_data(ttl=600)
def load_eventlog_data(customer_ids, start_date, end_date, material_ids, is_strict_inclusion):
    """Lädt die Eventlog-Daten, Cache-Key ist die Liste der Argumente."""
    connection_string = _get_db_connection()
    if not connection_string:
        return pd.DataFrame()

    # --- Parameter formatieren (liest direkt von den Funktionsargumenten) ---
    customer_id_param = f"'{','.join(map(str, customer_ids))}'" if customer_ids else "NULL"
    start_date_param = f"'{start_date.strftime('%Y-%m-%d')}'"
    end_date_param = f"'{end_date.strftime('%Y-%m-%d')}'"
    material_ids_list = [str(p).replace("'", "''") for p in material_ids]
    material_ids_param = f"'{','.join(material_ids_list)}'" if material_ids_list else "NULL"
    material_filter_mode_param = 1 if is_strict_inclusion else 0

    SQL_QUERY = f"""
    EXEC stored_proc.sp_process_analyzer_orchestrator
        @output = 'eventlog',
        @customer_id = {customer_id_param},
        @start_date = {start_date_param},
        @end_date = {end_date_param},
        @material_ids = {material_ids_param},
        @material_filter_mode = {material_filter_mode_param};
    """
    try:
        with pyodbc.connect(connection_string) as connection:
            df = pd.read_sql(SQL_QUERY, connection)
        if 'Datum' in df.columns:
            df['Datum'] = pd.to_datetime(df['Datum'])
        return df
    except pyodbc.Error as ex:
        st.error(f"Fehler bei der Eventlog-Datenbankabfrage: {ex}")
        return pd.DataFrame()

@st.cache_data(ttl=300)
def load_sollwerte():
    sql = """
        SELECT ATTRIBUTE_NAME, TARGET_VALUE
        FROM dbo.T_PROCESS_TO_BE_TIME
    """
    with pyodbc.connect(_get_db_connection()) as conn:
        df = pd.read_sql(sql, conn)

    return dict(zip(df["ATTRIBUTE_NAME"], df["TARGET_VALUE"]))

@st.cache_data(ttl=600)
def load_kpi_data(customer_ids, start_date, end_date, material_ids, is_strict_inclusion):
    """Lädt die KPI-Daten, Cache-Key ist die Liste der Argumente."""
    connection_string = _get_db_connection()
    if not connection_string:
        return pd.DataFrame()

    # --- Parameter formatieren (liest direkt von den Funktionsargumenten) ---
    customer_id_param = f"'{','.join(map(str, customer_ids))}'" if customer_ids else "NULL"
    start_date_param = f"'{start_date.strftime('%Y-%m-%d')}'"
    end_date_param = f"'{end_date.strftime('%Y-%m-%d')}'"
    material_ids_list = [str(p).replace("'", "''") for p in material_ids]
    material_ids_param = f"'{','.join(material_ids_list)}'" if material_ids_list else "NULL"
    material_filter_mode_param = 1 if is_strict_inclusion else 0

    SQL_QUERY = f"""
    EXEC stored_proc.sp_process_analyzer_orchestrator
        @output = 'kpi',
        @customer_id = {customer_id_param},
        @start_date = {start_date_param},
        @end_date = {end_date_param},
        @material_ids = {material_ids_param},
        @material_filter_mode = {material_filter_mode_param};
    """
    try:
        with pyodbc.connect(connection_string) as connection:
            df = pd.read_sql(SQL_QUERY, connection)
        return df
    except pyodbc.Error as ex:
        # st.error(f"Fehler bei der KPI-Datenbankabfrage: {ex}")
        return pd.DataFrame()


@st.cache_data(ttl=600)
def load_dfg_data(customer_ids, start_date, end_date, material_ids, is_strict_inclusion):
    """Lädt die DFG-Daten (Directly-Follows Graph), Cache-Key ist die Liste der Argumente."""
    connection_string = _get_db_connection()
    if not connection_string:
        return pd.DataFrame()

    # --- Parameter formatieren (liest direkt von den Funktionsargumenten) ---
    customer_id_param = f"'{','.join(map(str, customer_ids))}'" if customer_ids else "NULL"
    start_date_param = f"'{start_date.strftime('%Y-%m-%d')}'"
    end_date_param = f"'{end_date.strftime('%Y-%m-%d')}'"
    material_ids_list = [str(p).replace("'", "''") for p in material_ids]

    material_ids_param = f"'{','.join(material_ids_list)}'" if material_ids_list else "NULL"
    material_filter_mode_param = 1 if is_strict_inclusion else 0

    SQL_QUERY = f"""
    EXEC stored_proc.sp_process_analyzer_orchestrator
        @output = 'dfg',
        @customer_id = {customer_id_param},
        @start_date = {start_date_param},
        @end_date = {end_date_param},
        @material_ids = {material_ids_param},
        @material_filter_mode = {material_filter_mode_param};
    """
    try:
        with pyodbc.connect(connection_string) as connection:
            df = pd.read_sql(SQL_QUERY, connection)
        return df
    except pyodbc.Error as ex:
        st.error(f"Fehler bei der DFG-Datenbankabfrage: {ex}")
        return pd.DataFrame()


@st.cache_data(ttl=3600)
def load_lov_customers_data():
    """
    Lädt Kunden-IDs und Namen.
    Rückgabe: (Liste der IDs, Dictionary {ID: Name})
    """
    connection_string = _get_db_connection()
    if not connection_string:
        return [], {}

    # SQL angepasst auf Select *
    SQL_QUERY = "SELECT CUSTOMER_ID, CUSTOMER_LONG FROM LOV_CUSTOMER"

    try:
        with pyodbc.connect(connection_string) as connection:
            df = pd.read_sql(SQL_QUERY, connection)

        if df.empty:
            return [], {}

        # 1. Liste aller IDs für die Auswahl-Optionen
        ids = df['CUSTOMER_ID'].tolist()

        # 2. Dictionary für die Übersetzung ID -> Name
        # Ergebnis: {1: '01 / BikePro...', 2: '02 / BikePro...'}
        mapping = pd.Series(df.CUSTOMER_LONG.values, index=df.CUSTOMER_ID).to_dict()

        return ids, mapping

    except Exception as ex:
        st.error(f"Fehler beim Laden der Kunden-Liste: {ex}")
        return [], {}


@st.cache_data(ttl=3600)
def load_lov_products_data():
    """
    Lädt Material-IDs und Beschreibungen.
    Rückgabe: (Liste der IDs, Dictionary {ID: Name})
    """
    connection_string = _get_db_connection()
    if not connection_string:
        return [], {}

    SQL_QUERY = "exec stored_proc.sp_process_analyzer_orchestrator @output = 'material'"

    try:
        with pyodbc.connect(connection_string) as connection:
            df = pd.read_sql(SQL_QUERY, connection)

        if df.empty:
            return [], {}

        # Spaltennamen basierend auf deiner Info: ID_MAT und MAT_DESCR
        ids = df['ID_MAT'].tolist()

        # Dictionary: {2: 'Cube Aim Disc', 3: 'Bulls Copperhead 3'}
        mapping = pd.Series(df.MAT_DESCR.values, index=df.ID_MAT).to_dict()

        return ids, mapping

    except Exception as ex:
        st.error(f"Fehler beim Laden der Produkt-Liste: {ex}")
        return [], {}


########################################################################################################################
# SQL - Rückgabe
########################################################################################################################

# --- DATEN LADEN MIT APPLIED FILTERN ---

# Initialisierung der DataFrames, falls noch keine Daten geladen wurden
df_eventlog = pd.DataFrame()
df_kpi = pd.DataFrame()
df_dfg = pd.DataFrame()

# Bedingte Ausführung: Führe SQL-Abfrage nur aus, wenn der Button gedrückt wurde
if st.session_state.get('data_applied', False):

    # Applied Parameter aus dem Session State lesen
    applied_customer_ids = st.session_state.get('applied_kunde_input', [])
    applied_start_date = st.session_state.get('applied_start_date', DEFAULT_START_DATE)
    applied_end_date = st.session_state.get('applied_end_date', DEFAULT_END_DATE)
    applied_material_ids = st.session_state.get('applied_produkt_input', [])
    applied_is_strict_inclusion = st.session_state.get('applied_produkt_filter_exklusiv', False)

    # DATEN LADEN: Alle Datensätze werden geladen
    df_eventlog = load_eventlog_data(
        customer_ids=applied_customer_ids,
        start_date=applied_start_date,
        end_date=applied_end_date,
        material_ids=applied_material_ids,
        is_strict_inclusion=applied_is_strict_inclusion
    )
    df_kpi = load_kpi_data(
        customer_ids=applied_customer_ids,
        start_date=applied_start_date,
        end_date=applied_end_date,
        material_ids=applied_material_ids,
        is_strict_inclusion=applied_is_strict_inclusion
    )
    df_dfg = load_dfg_data(
        customer_ids=applied_customer_ids,
        start_date=applied_start_date,
        end_date=applied_end_date,
        material_ids=applied_material_ids,
        is_strict_inclusion=applied_is_strict_inclusion
    )

    # Sicherstellen, dass die App bei leeren Eventlog-Daten nicht stoppt, sondern eine Warnung ausgibt
    if df_eventlog.empty:
        st.warning(
            "Es konnten keine Eventlog-Daten geladen werden (aufgrund zu restriktiver Filter).")

    # Sicherstellen, dass Umsatz numerisch ist, um Summen berechnen zu können
    if 'Umsatz' in df_eventlog.columns:
        df_eventlog['Umsatz'] = pd.to_numeric(df_eventlog['Umsatz'], errors='coerce').fillna(0)

########################################################################################################################
# Frontend
#######################################################################################################################
# --- 2. Spaltendefinition ---
col1, col2, col3 = st.columns([2, 2, 3])  # Spaltenverhältnis: 2:2:3

# --- 3. Filter-Widgets (Innerhalb von col1) ---
with col1:
    # UMWICKELT DEN INHALT MIT EINEM ST.CONTAINER FÜR EINHEITLICHES STYLING
    filter_container = st.container()

    with filter_container:
        # DYNAMISCHES LADEN DER FILTEROPTIONEN

        customer_ids_options, customer_map = load_lov_customers_data()
        product_ids_options, product_map = load_lov_products_data()

        # --- DATUM BERECHNUNG FÜR UI-ANZEIGE ---
        current_end_date = date.today()
        # Fallback für minimales Datum
        min_data_date = df_eventlog[
            'Datum'].min().date() if 'Datum' in df_eventlog.columns and 'Datum' in df_eventlog.dtypes and not df_eventlog.empty else DEFAULT_START_DATE

        # Speichern des minimalen Datums im Session State für den Callback
        st.session_state['min_data_date'] = min_data_date

        zeitraum_selection = st.session_state.get('zeitraum_input', 'Gesamt')

        # 1. FILTER TITEL
        st.markdown("<h2 style='text-align: center;'>Filter</h2>", unsafe_allow_html=True)

        # --- ZEITRAUM FILTER (AUSSERHALB DES FORMS) ---
        st.markdown("#### **1. Zeitraum**", unsafe_allow_html=True)

        # Selectbox für Zeitraum mit Callback zur sofortigen State-Aktualisierung
        st.selectbox(
            'Zeitraum auswählen',
            ['Gesamt', 'Letzte 7 Tage', 'Letzte 30 Tage', 'Benutzerdefiniert'],
            key='zeitraum_input',
            on_change=update_dates_on_period_change,  # Callback
            index=['Gesamt', 'Letzte 7 Tage', 'Letzte 30 Tage', 'Benutzerdefiniert'].index(zeitraum_selection)
        )

        # --- DATUMSFELDER SIND IMMER SICHTBAR (LESEN DEN AKTUELLEN STATE) ---
        st.date_input(
            'Startdatum',
            value=st.session_state['start_date_input'],
            min_value=min_data_date,
            max_value=current_end_date,
            key='start_date_input'
        )

        st.date_input(
            'Enddatum',
            value=st.session_state['end_date_input'],
            min_value=min_data_date,
            max_value=current_end_date,
            key='end_date_input'
        )

        st.markdown("---")  # Trennlinie

        # 2. OPTIONALE FILTER (INNERHALB DES FORMS)
        with st.form(key='filter_form'):
            # 2. OPTIONALE FILTER
            st.markdown("#### **2. Weitere Filter**", unsafe_allow_html=True)  # Überschrift angepasst/verkleinert
            st.markdown("Bitte weitere Filter wählen:")

            # 2. Kunde (Multiselect)
            st.markdown("##### Kunde", unsafe_allow_html=True)
            st.multiselect(
                'Kunde auswählen',
                options=customer_ids_options,  # Die Box enthält technisch die IDs
                format_func=lambda x: customer_map.get(x, str(x)),  # Zeigt aber den Namen an!
                key='kunde_input'  # Speichert die gewählten IDs im State
            )

            # 3. Produkte (Multiselect)
            st.markdown("##### Produkt", unsafe_allow_html=True)
            st.multiselect(
                'Wähle ein Produkt',
                options=product_ids_options,  # Die Box enthält technisch die IDs
                format_func=lambda x: product_map.get(x, str(x)),  # Zeigt aber den Namen an!
                key='produkt_input'  # Speichert die gewählten IDs im State
            )

            st.checkbox(
                "Strikte Inklusion",
                value=False,
                key='produkt_filter_exklusiv'
            )

            st.markdown("---")

            submit_button = st.form_submit_button(label='Filter anwenden')

        # NEUE LOGIK: Führt apply_filters() NUR aus, wenn der Submit Button gedrückt wurde
        if submit_button:
            apply_filters()
            # KORREKTUR: Erzwinge sofortigen Rerun, um das "Zwei-Klick"-Problem zu lösen
            st.rerun()

        # --- BUTTONS NEBENEINANDER (MUSS AUSSERHALB DES FORMS SEIN) ---
        # st.button ruft reset_filters auf, was wiederum apply_filters aufruft
        st.button("Filter zurücksetzen", on_click=reset_filters, key='reset_button')

# --- 5. Filter-Anwendungslogik (ENTFERNT, DA IN DB AUSGEFÜHRT) ---

# filtered_df ist nun df_eventlog
filtered_df = df_eventlog.copy()

########################################################################################################################

with col2:
    # Beginnt den zentrierten Container für col2
    st.markdown("<div class='center-col-content'>", unsafe_allow_html=True)

    # st.markdown("<h3 style='text-align: center;'>Zusammenfassung</h3>", unsafe_allow_html=True)
    st.metric(
        label="Gefilterte Datensätze",
        value=f"{len(filtered_df):,}",
        delta=None,  # Delta entfernt, da wir die ungefilterte Größe nicht mehr sinnvoll vergleichen können
        delta_color="off"
    )





    with st.expander("Eventlog-Vorschau"):
        # Der DataFrame ist nun optional aufklappbar
        st.dataframe(
            filtered_df,  # Zeigt nun den gesamten DataFrame an
            width='stretch',
            hide_index=True
        )

    # Schließt den zentrierten Container für col2
    st.markdown("</div>", unsafe_allow_html=True)

########################################################################################################################

@st.cache_data(ttl=300)
def load_sollwerte():
    sql = """
        SELECT ATTRIBUTE_NAME, TARGET_VALUE
        FROM dbo.T_PROCESS_TO_BE_TIME
    """
    with pyodbc.connect(_get_db_connection()) as conn:
        df = pd.read_sql(sql, conn)

    return dict(zip(df["ATTRIBUTE_NAME"], df["TARGET_VALUE"]))


def update_sollwert(attribute_name, target_value, user_name):
    sql = """
        UPDATE dbo.T_PROCESS_TO_BE_TIME
        SET TARGET_VALUE = ?,
            INS_USER = ?,
            EVENT_TIME = GETDATE()
        WHERE ATTRIBUTE_NAME = ?
    """
    with pyodbc.connect(_get_db_connection()) as conn:
        cur = conn.cursor()
        cur.execute(sql, target_value, user_name, attribute_name)
        conn.commit()

    st.cache_data.clear()


########################################################################################################
with col3:

    st.markdown("<div class='center-col-content'>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align: center;'>KPI - Zielerreichung</h3>", unsafe_allow_html=True)

    # -----------------------------
    # SOLLWERTE AUS DB LADEN
    # -----------------------------
    def load_sollwerte():
        conn = pyodbc.connect(_get_db_connection())
        df = pd.read_sql(
            "SELECT ATTRIBUTE_NAME, TARGET_VALUE FROM dbo.T_PROCESS_TO_BE_TIME",
            conn
        )
        conn.close()
        return dict(zip(df["ATTRIBUTE_NAME"], df["TARGET_VALUE"]))

    # -----------------------------
    # SOLLWERT SPEICHERN (Stored Proc)
    # -----------------------------
    def save_sollwert(kpi_name, value):
        conn = pyodbc.connect(_get_db_connection())
        cur = conn.cursor()
        cur.execute(
            "EXEC stored_proc.sp_set_process_target_time ?, ?, ?",
            kpi_name,
            float(value),
            "w25s227"   # aktuell hart codiert
        )
        conn.commit()
        conn.close()

    # -----------------------------
    # DATEN VERARBEITEN
    # -----------------------------
    sollwerte = load_sollwerte()

    if df_kpi is None or df_kpi.empty:
        st.warning("Keine KPI-Daten vorhanden.")
    else:
        df = df_kpi.copy()

        # SOLL / IST
        df["SOLL"] = df["KPI_NAME"].map(sollwerte).fillna(0.0)
        df["IST"] = df["AVG_VALUE"]

        # IST Spalte für Anzeige umbenennen
        df.rename(columns={"IST": "IST (Durchschnitt)"}, inplace=True)

        # -----------------------------
        # AMPELLOGIK
        # -----------------------------
        def ampel(row):
            if row["IST (Durchschnitt)"] <= row["SOLL"]:
                return "🟢"
            elif row["IST (Durchschnitt)"] <= row["SOLL"] * 1.1:
                return "🟡"
            else:
                return "🔴"

        df["Ampel"] = df.apply(ampel, axis=1)

        # -----------------------------
        # EDITIERBARE TABELLE (NUR EINE)
        # -----------------------------
        edited_df = st.data_editor(
            df[["KPI_NAME", "SOLL", "IST (Durchschnitt)", "Ampel"]],
            hide_index=True,
            use_container_width=True,
            disabled=["KPI_NAME", "IST (Durchschnitt)", "Ampel"],
            column_config={
                "SOLL": st.column_config.NumberColumn(
                    "SOLL",
                    step=1.0,
                    format="%.2f"
                )
            },
            key="kpi_editor"
        )

        # -----------------------------
        # SPEICHERN
        # -----------------------------
        if st.button("SOLLWERTE speichern"):
            for _, row in edited_df.iterrows():
                save_sollwert(row["KPI_NAME"], row["SOLL"])

            st.success("SOLLWERTE erfolgreich gespeichert.")
            st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)
########################################################################################################

    ##################################################################################################################

    # 2. DFG-Visualisierung (NUR GRAPH, KEINE TABELLE)
    st.markdown("<h3 style='text-align: center;'>DFG - Prozessfluss</h3>", unsafe_allow_html=True)

    if not df_dfg.empty:
        # Netzwerkdiagramm mit Plotly
        try:
            import plotly.graph_objects as go

            # Kategorien und Farben definieren
            categories = ['SALESOFFER', 'SALESORDER', 'DELIVERY', 'INVOICE', 'PAYMENT']
            category_colors = {
                'SALESOFFER': '#4A90E2',  # Blau
                'SALESORDER': '#7ED321',  # Grün
                'DELIVERY': '#F5A623',  # Orange
                'INVOICE': '#BD10E0',  # Lila
                'PAYMENT': '#50E3C2'  # Türkis
            }


            # Funktion zum Extrahieren der Kategorie aus dem Activity-Namen
            def get_category(activity):
                for cat in categories:
                    if activity.startswith(cat):
                        return cat
                return 'UNKNOWN'


            # Funktion zum Extrahieren des Status aus dem Activity-Namen
            def get_status(activity):
                parts = activity.split('_')
                if len(parts) > 1:
                    return '_'.join(parts[1:])
                return ''


            # Hilfsfunktion zur Berechnung des Randpunkts eines Rechtecks
            def calculate_edge_intersection(x_center, y_center, x_target, y_target, node_width, node_height):
                """
                Berechnet den Punkt am Rand eines Rechtecks, wo die Linie vom Zentrum
                zum Zielpunkt das Rechteck verlässt bzw. eintritt.
                """
                # Richtungsvektor
                dx = x_target - x_center
                dy = y_target - y_center

                # Spezialfälle: keine Bewegung
                if dx == 0 and dy == 0:
                    return x_center, y_center

                # Berechne t-Werte für horizontale und vertikale Kanten
                if dx == 0:
                    # Vertikale Linie
                    edge_x = x_center
                    edge_y = y_center + (node_height / 2 if dy > 0 else -node_height / 2)
                elif dy == 0:
                    # Horizontale Linie
                    edge_x = x_center + (node_width / 2 if dx > 0 else -node_width / 2)
                    edge_y = y_center
                else:
                    # Berechne das Verhältnis für beide Achsen
                    t_x = (node_width / 2) / abs(dx)
                    t_y = (node_height / 2) / abs(dy)

                    # Nimm das kleinere t (das ist der erste Schnittpunkt mit dem Rechteck)
                    t = min(t_x, t_y)

                    edge_x = x_center + t * dx
                    edge_y = y_center + t * dy

                return edge_x, edge_y


            def line_intersects_rectangle(x1, y1, x2, y2, rect_x, rect_y, rect_width, rect_height):
                """
                Prüft, ob eine Linie von (x1,y1) nach (x2,y2) durch ein Rechteck geht.
                Rechteck ist definiert durch Mittelpunkt (rect_x, rect_y) und Dimensionen.
                """
                # Erweitere Rechteck leicht für bessere Erkennung
                margin = 5
                rect_left = rect_x - rect_width / 2 - margin
                rect_right = rect_x + rect_width / 2 + margin
                rect_top = rect_y - rect_height / 2 - margin
                rect_bottom = rect_y + rect_height / 2 + margin

                # Prüfe ob Liniensegment das Rechteck schneidet (Liang-Barsky Algorithmus vereinfacht)
                # Prüfe ob mindestens ein Endpunkt im Rechteck liegt
                def point_in_rect(px, py):
                    return rect_left <= px <= rect_right and rect_top <= py <= rect_bottom

                # Wenn einer der Endpunkte im Rechteck ist, gibt es eine Kollision
                # (außer es ist der Ziel- oder Start-Knoten selbst)
                if point_in_rect(x1, y1) or point_in_rect(x2, y2):
                    # Prüfe ob es der Mittelpunkt des Rechtecks selbst ist
                    tolerance = rect_width / 2 + 1
                    if (abs(x1 - rect_x) < tolerance and abs(y1 - rect_y) < tolerance):
                        return False  # Startknoten
                    if (abs(x2 - rect_x) < tolerance and abs(y2 - rect_y) < tolerance):
                        return False  # Zielknoten
                    return True

                # Prüfe ob Linie durch Rechteck geht (vereinfachte Version)
                # Berechne parametrische Form der Linie: P = P1 + t*(P2-P1)
                dx = x2 - x1
                dy = y2 - y1

                # Prüfe Schnittpunkte mit allen vier Kanten
                if dx != 0:
                    # Linke Kante
                    t = (rect_left - x1) / dx
                    if 0 < t < 1:
                        y = y1 + t * dy
                        if rect_top <= y <= rect_bottom:
                            return True
                    # Rechte Kante
                    t = (rect_right - x1) / dx
                    if 0 < t < 1:
                        y = y1 + t * dy
                        if rect_top <= y <= rect_bottom:
                            return True

                if dy != 0:
                    # Obere Kante
                    t = (rect_top - y1) / dy
                    if 0 < t < 1:
                        x = x1 + t * dx
                        if rect_left <= x <= rect_right:
                            return True
                    # Untere Kante
                    t = (rect_bottom - y1) / dy
                    if 0 < t < 1:
                        x = x1 + t * dx
                        if rect_left <= x <= rect_right:
                            return True

                return False


            def calculate_curved_path(x1, y1, x2, y2, all_obstacles, node_width, node_height):
                """
                Berechnet einen gebogenen Pfad, wenn die direkte Linie durch Knoten geht.
                Gibt Kontrollpunkte für eine Bezier-Kurve zurück.
                """
                # Prüfe ob direkte Linie Knoten schneidet
                has_collision = False
                collision_points = []

                for obs_node, (obs_x, obs_y) in all_obstacles.items():
                    if line_intersects_rectangle(x1, y1, x2, y2, obs_x, obs_y, node_width, node_height):
                        has_collision = True
                        collision_points.append((obs_x, obs_y))

                if not has_collision:
                    # Keine Kollision - direkte Linie
                    return None

                # Berechne Kontrollpunkt für Kurve
                # Mittelpunkt der Linie
                mid_x = (x1 + x2) / 2
                mid_y = (y1 + y2) / 2

                # Richtung der Linie
                dx = x2 - x1
                dy = y2 - y1
                length = (dx ** 2 + dy ** 2) ** 0.5

                if length == 0:
                    return None

                # Normalisierter Vektor senkrecht zur Linie
                perp_x = -dy / length
                perp_y = dx / length

                # Verschiebe Kontrollpunkt seitlich (30-50 Pixel)
                offset = 50

                # Prüfe beide Seiten und wähle die mit weniger Kollisionen
                ctrl1_x = mid_x + offset * perp_x
                ctrl1_y = mid_y + offset * perp_y
                ctrl2_x = mid_x - offset * perp_x
                ctrl2_y = mid_y - offset * perp_y

                # Zähle Kollisionen für beide Optionen
                collisions1 = sum(1 for obs_node, (obs_x, obs_y) in all_obstacles.items()
                                  if line_intersects_rectangle(x1, y1, ctrl1_x, ctrl1_y, obs_x, obs_y, node_width,
                                                               node_height)
                                  or line_intersects_rectangle(ctrl1_x, ctrl1_y, x2, y2, obs_x, obs_y, node_width,
                                                               node_height))

                collisions2 = sum(1 for obs_node, (obs_x, obs_y) in all_obstacles.items()
                                  if line_intersects_rectangle(x1, y1, ctrl2_x, ctrl2_y, obs_x, obs_y, node_width,
                                                               node_height)
                                  or line_intersects_rectangle(ctrl2_x, ctrl2_y, x2, y2, obs_x, obs_y, node_width,
                                                               node_height))

                # Wähle die Seite mit weniger Kollisionen
                if collisions1 <= collisions2:
                    ctrl_x, ctrl_y = ctrl1_x, ctrl1_y
                else:
                    ctrl_x, ctrl_y = ctrl2_x, ctrl2_y

                return (ctrl_x, ctrl_y)


            # Knoten sammeln und kategorisieren
            nodes_by_category = {cat: [] for cat in categories}
            all_nodes = set()

            for _, row in df_dfg.iterrows():
                all_nodes.add(row['FROM_ACTIVITY'])
                all_nodes.add(row['TO_ACTIVITY'])

            for node in all_nodes:
                cat = get_category(node)
                if cat in nodes_by_category:
                    nodes_by_category[cat].append(node)

            # Sortiere Knoten innerhalb jeder Kategorie
            for cat in categories:
                nodes_by_category[cat].sort()

            # Berechne Positionen für optimale Raumnutzung
            # Horizontaler Abstand zwischen Kategorien
            h_spacing = 200
            # Vertikaler Abstand zwischen Status (angepasst für 100x50 Knoten)
            v_spacing = 90

            # Finde maximale Anzahl von Status in einer Kategorie
            max_statuses = max([len(nodes) for nodes in nodes_by_category.values()]) if any(
                nodes_by_category.values()) else 1

            # Positionierung der Knoten
            node_positions = {}
            for cat_idx, cat in enumerate(categories):
                x = cat_idx * h_spacing
                nodes_in_cat = nodes_by_category[cat]

                # Zentriere vertikal wenn weniger Status als max
                y_offset = (max_statuses - len(nodes_in_cat)) * v_spacing / 2

                for node_idx, node in enumerate(nodes_in_cat):
                    y = node_idx * v_spacing + y_offset
                    node_positions[node] = (x, y)

            # Erstelle Figure
            fig = go.Figure()

            # Knotenabmessungen (Mittelweg für gute Balance)
            node_width = 100
            node_height = 50

            # BIDIREKTIONALE PFEILE ERKENNEN
            # Finde alle Paare (A→B und B→A), die übereinander liegen würden
            bidirectional_edges = set()
            for _, row in df_dfg.iterrows():
                from_node = row['FROM_ACTIVITY']
                to_node = row['TO_ACTIVITY']

                # Prüfe ob es auch einen Pfeil in die andere Richtung gibt
                reverse_exists = df_dfg[
                                     (df_dfg['FROM_ACTIVITY'] == to_node) &
                                     (df_dfg['TO_ACTIVITY'] == from_node)
                                     ].shape[0] > 0

                if reverse_exists and from_node != to_node:  # Nicht bei Self-Loops
                    # Speichere beide Richtungen als bidirektional
                    bidirectional_edges.add((from_node, to_node))
                    bidirectional_edges.add((to_node, from_node))

            # Zeichne Edges (Pfeile) mit Frequency-Labels
            annotations = []
            for _, row in df_dfg.iterrows():
                from_node = row['FROM_ACTIVITY']
                to_node = row['TO_ACTIVITY']
                frequency = row['FREQUENCY']

                if from_node in node_positions and to_node in node_positions:
                    x_from_center, y_from_center = node_positions[from_node]
                    x_to_center, y_to_center = node_positions[to_node]

                    # Prüfe ob dieser Edge bidirektional ist
                    is_bidirectional = (from_node, to_node) in bidirectional_edges

                    # SELF-LOOP: Task folgt auf sich selbst
                    if from_node == to_node:
                        # Zeichne GRÖßERE, RUNDE Schleife in der linken oberen Ecke
                        loop_size = 30  # Größer für bessere Sichtbarkeit

                        # WICHTIG: In Plotly sind GRÖSSERE Y-Werte OBEN!
                        # Startpunkt: Links am OBEREN Rand
                        start_x = x_from_center - node_width / 2
                        start_y = y_from_center + node_height / 2 - 5

                        # Endpunkt: OBEN am linken Rand
                        end_x = x_from_center - node_width / 2 + 5
                        end_y = y_from_center + node_height / 2

                        # Kontrollpunkte für RUNDE Schleife (weiter weg = runder)
                        ctrl1_x = start_x - loop_size * 0.8
                        ctrl1_y = start_y + loop_size * 0.4  # Weniger steil für rundere Form

                        ctrl2_x = end_x - loop_size * 0.4  # Weniger stark gekrümmt
                        ctrl2_y = end_y + loop_size * 0.8

                        # Erzeuge Punkte für kubische Bezier-Kurve
                        num_points = 50
                        curve_x = []
                        curve_y = []

                        for i in range(num_points + 1):
                            t = i / num_points
                            # Kubische Bezier: B(t) = (1-t)³P0 + 3(1-t)²tP1 + 3(1-t)t²P2 + t³P3
                            x = (1 - t) ** 3 * start_x + 3 * (1 - t) ** 2 * t * ctrl1_x + 3 * (
                                        1 - t) * t ** 2 * ctrl2_x + t ** 3 * end_x
                            y = (1 - t) ** 3 * start_y + 3 * (1 - t) ** 2 * t * ctrl1_y + 3 * (
                                        1 - t) * t ** 2 * ctrl2_y + t ** 3 * end_y
                            curve_x.append(x)
                            curve_y.append(y)

                        # Zeichne die Schleife
                        fig.add_trace(go.Scatter(
                            x=curve_x[:-3],
                            y=curve_y[:-3],
                            mode='lines',
                            line=dict(
                                width=1.5,
                                color='rgba(100, 100, 100, 0.8)'
                            ),
                            showlegend=False,
                            hoverinfo='skip'
                        ))

                        # Pfeil am Ende der Schleife
                        annotations.append(dict(
                            x=curve_x[-1],
                            y=curve_y[-1],
                            ax=curve_x[-6] if len(curve_x) > 6 else curve_x[-2],
                            ay=curve_y[-6] if len(curve_y) > 6 else curve_y[-2],
                            xref='x',
                            yref='y',
                            axref='x',
                            ayref='y',
                            showarrow=True,
                            arrowhead=2,
                            arrowsize=1.5,
                            arrowwidth=1.5,
                            arrowcolor='rgba(100, 100, 100, 0.8)'
                        ))

                        # Frequency-Label AUF dem Pfeil (am höchsten Punkt der Kurve)
                        mid_idx = len(curve_x) // 2
                        label_x = curve_x[mid_idx]
                        label_y = curve_y[mid_idx]

                        annotations.append(dict(
                            x=label_x,
                            y=label_y,
                            text=f'<b>{frequency}</b>',
                            showarrow=False,
                            font=dict(size=10, color='black'),
                            bgcolor='rgba(255, 255, 255, 0.8)',
                            bordercolor='rgba(0, 0, 0, 0.3)',
                            borderwidth=1,
                            borderpad=2
                        ))

                        # Springe zur nächsten Edge (Self-Loop ist fertig)
                        continue

                    # NORMALE EDGES (nicht Self-Loop)
                    # Berechne Start- und Endpunkte am Rand der Knoten
                    x_from, y_from = calculate_edge_intersection(
                        x_from_center, y_from_center,
                        x_to_center, y_to_center,
                        node_width, node_height
                    )

                    x_to, y_to = calculate_edge_intersection(
                        x_to_center, y_to_center,
                        x_from_center, y_from_center,
                        node_width, node_height
                    )

                    # BIDIREKTIONALER OFFSET
                    # Wenn Pfeile in beide Richtungen gehen, verschiebe sie parallel
                    if is_bidirectional:
                        # Berechne die Richtung der Verbindung
                        dx = x_to_center - x_from_center
                        dy = y_to_center - y_from_center
                        length = (dx ** 2 + dy ** 2) ** 0.5

                        if length > 0:
                            # Senkrechter Vektor (nach rechts gedreht)
                            perp_x = -dy / length
                            perp_y = dx / length

                            # Offset-Distanz (6 Pixel)
                            offset = 6

                            # Verschiebe beide Punkte senkrecht zur Verbindung
                            x_from += perp_x * offset
                            y_from += perp_y * offset
                            x_to += perp_x * offset
                            y_to += perp_y * offset

                    # Prüfe auf Kollisionen mit anderen Knoten
                    obstacles = {n: pos for n, pos in node_positions.items()
                                 if n != from_node and n != to_node}

                    control_point = calculate_curved_path(
                        x_from, y_from, x_to, y_to,
                        obstacles, node_width, node_height
                    )

                    if control_point is not None:
                        # Zeichne gebogene Linie (quadratische Bezier-Kurve)
                        ctrl_x, ctrl_y = control_point

                        # Erzeuge Punkte entlang der Bezier-Kurve
                        num_points = 50
                        curve_x = []
                        curve_y = []

                        for i in range(num_points + 1):
                            t = i / num_points
                            # Quadratische Bezier-Formel: B(t) = (1-t)²P0 + 2(1-t)tP1 + t²P2
                            x = (1 - t) ** 2 * x_from + 2 * (1 - t) * t * ctrl_x + t ** 2 * x_to
                            y = (1 - t) ** 2 * y_from + 2 * (1 - t) * t * ctrl_y + t ** 2 * y_to
                            curve_x.append(x)
                            curve_y.append(y)

                        # Zeichne nur die Kurve ohne Pfeil (Pfeil kommt als Annotation)
                        fig.add_trace(go.Scatter(
                            x=curve_x[:-3],  # Stoppe kurz vor dem Ende
                            y=curve_y[:-3],
                            mode='lines',
                            line=dict(
                                width=1.5,  # Konstante Breite für alle Pfeile
                                color='rgba(100, 100, 100, 0.8)'
                            ),
                            showlegend=False,
                            hoverinfo='skip'
                        ))

                        # Pfeil-Annotation für das Ende der Kurve
                        arrow_end_idx = -1
                        arrow_start_idx = -5 if len(curve_x) > 5 else -2

                        annotations.append(dict(
                            x=curve_x[arrow_end_idx],
                            y=curve_y[arrow_end_idx],
                            ax=curve_x[arrow_start_idx],
                            ay=curve_y[arrow_start_idx],
                            xref='x',
                            yref='y',
                            axref='x',
                            ayref='y',
                            showarrow=True,
                            arrowhead=2,
                            arrowsize=1.5,
                            arrowwidth=1.5,  # Konstante Breite für alle Pfeile
                            arrowcolor='rgba(100, 100, 100, 0.8)'
                        ))

                        # Frequency-Label in der Mitte der Kurve
                        mid_x = curve_x[len(curve_x) // 2]
                        mid_y = curve_y[len(curve_y) // 2]

                        # Füge Frequency-Label hinzu
                        annotations.append(dict(
                            x=mid_x,
                            y=mid_y,
                            text=f'<b>{frequency}</b>',
                            showarrow=False,
                            font=dict(size=10, color='black'),
                            bgcolor='rgba(255, 255, 255, 0.8)',
                            bordercolor='rgba(0, 0, 0, 0.3)',
                            borderwidth=1,
                            borderpad=2
                        ))

                    else:
                        # Zeichne geraden Pfeil (keine Kollision)
                        # Verwende Arrow-Annotation als komplette Linie (kein separates Scatter)
                        annotations.append(dict(
                            x=x_to,
                            y=y_to,
                            ax=x_from,
                            ay=y_from,
                            xref='x',
                            yref='y',
                            axref='x',
                            ayref='y',
                            showarrow=True,
                            arrowhead=2,
                            arrowsize=1.5,
                            arrowwidth=1.5,  # Konstante Breite für alle Pfeile
                            arrowcolor='rgba(100, 100, 100, 0.8)'
                        ))

                        # Frequency-Label in der Mitte
                        mid_x = (x_from + x_to) / 2
                        mid_y = (y_from + y_to) / 2

                        # Füge Frequency-Label hinzu
                        annotations.append(dict(
                            x=mid_x,
                            y=mid_y,
                            text=f'<b>{frequency}</b>',
                            showarrow=False,
                            font=dict(size=10, color='black'),
                            bgcolor='rgba(255, 255, 255, 0.8)',
                            bordercolor='rgba(0, 0, 0, 0.3)',
                            borderwidth=1,
                            borderpad=2
                        ))

            # Zeichne Knoten als Rechtecke (Shapes) mit Text
            shapes = []
            for node, (x, y) in node_positions.items():
                cat = get_category(node)
                status = get_status(node)
                color = category_colors.get(cat, '#999999')

                # Füge Rechteck als Shape hinzu (verwendet node_width und node_height von oben)
                shapes.append(dict(
                    type='rect',
                    x0=x - node_width / 2,
                    y0=y - node_height / 2,
                    x1=x + node_width / 2,
                    y1=y + node_height / 2,
                    fillcolor=color,
                    line=dict(color='white', width=2),
                    layer='below'
                ))


                # Füge Text-Annotation für jeden Knoten hinzu
                # Kategorie (fett) über Status

                # Dynamische Schriftgröße - SEHR KONSERVATIV für alle Fenstergrößen
                def calculate_font_size(text, actual_node_width):
                    """Berechnet optimale Schriftgröße für Text im Knoten."""
                    if not text:
                        return 7

                    # Entferne HTML-Tags für Längenberechnung
                    clean_text = text.replace('<b>', '').replace('</b>', '').replace('<br>', '\n')

                    # Finde längste Zeile
                    lines = clean_text.split('\n')
                    max_line_length = max(len(line) for line in lines)

                    # SEHR KONSERVATIVE Berechnung mit großem Sicherheitspuffer
                    # Da Plotly die Knoten skaliert, aber Schrift absolut ist,
                    # müssen wir sehr vorsichtig sein

                    # Verfügbare Breite: nur 70% der Knotenbreite nutzen
                    available_width = actual_node_width * 0.7

                    # Berechne mit großem Sicherheitsfaktor (0.7 statt 0.6)
                    optimal_size = available_width / (max_line_length * 0.7)

                    # Sehr enge Grenzen für Sicherheit
                    # Bei 80px: max 8pt (nicht mehr!)
                    min_size = 5
                    max_size = 8  # Reduziert von 9

                    font_size = max(min_size, min(max_size, optimal_size))

                    return int(font_size)


                if status:
                    display_text = f'<b>{cat}</b><br>{status}'
                else:
                    display_text = f'<b>{cat}</b>'

                # Berechne optimale Schriftgröße
                font_size = calculate_font_size(display_text, node_width)

                annotations.append(dict(
                    x=x,
                    y=y,
                    text=display_text,
                    showarrow=False,
                    font=dict(size=font_size, color='white', family='Arial'),
                    xanchor='center',
                    yanchor='middle'
                ))

                # Unsichtbarer Scatter-Point für Hover-Info
                fig.add_trace(go.Scatter(
                    x=[x],
                    y=[y],
                    mode='markers',
                    marker=dict(size=node_width, color='rgba(0,0,0,0)', symbol='square'),
                    showlegend=False,
                    hovertemplate=f'<b>{node}</b><extra></extra>'
                ))

            # Update Layout
            fig.update_layout(
                height=600,
                showlegend=False,
                xaxis=dict(
                    showgrid=False,
                    showticklabels=False,
                    zeroline=False,
                    range=[-50, (len(categories) - 1) * h_spacing + 50]
                ),
                yaxis=dict(
                    showgrid=False,
                    showticklabels=False,
                    zeroline=False,
                    range=[-50, max_statuses * v_spacing + 50]
                ),
                margin=dict(l=20, r=20, t=40, b=20),
                annotations=annotations,
                shapes=shapes,
                plot_bgcolor='rgba(240, 240, 245, 0.5)'
            )

            st.plotly_chart(fig, use_container_width=True)


        except ImportError:
            st.error("Plotly ist nicht installiert!")
            st.info("Bitte installiere Plotly mit: pip install plotly==5.24.1")
            st.code("""
# Versuche eine dieser Optionen:
pip install plotly==5.24.1
python -m pip install plotly==5.24.1
pip install --user plotly==5.24.1

# Prüfe welches Python Streamlit verwendet:
import sys
print(sys.executable)
            """, language="bash")

    else:
        st.warning("Keine DFG-Daten verfügbar. Bitte wenden Sie Filter an oder prüfen Sie die Datenbasis.")

    st.caption(f"Anzeige der Visualisierungen basierend auf {len(filtered_df)} von {len(df_eventlog)} Datensätzen.")

    # Schließt den zentrierten Container für col3
    st.markdown("</div>", unsafe_allow_html=True)

########################################################################################################################

# CSS für Zentrierung (optionales Styling aus dem Originalcode)
st.markdown("""
<style>
.center-col-content {
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
}
.stMetric > div:nth-child(1) {
    font-size: 1.2rem;
    font-weight: 500;
}
/* NEU: Entfernt die Umrandung des st.form-Elements */
div[data-testid="stForm"] {
    border: none !important;
    padding: 0 !important; /* Optional: Entfernt auch das Standard-Padding, falls vorhanden */
}
</style>
""", unsafe_allow_html=True)
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
    material_ids_list = [f"'{p.replace('\'', '\'\'')}'" for p in material_ids]
    material_ids_param = f"'{','.join(material_ids_list)}'" if material_ids_list else "NULL"
    material_filter_mode_param = 1 if is_strict_inclusion else 0

    SQL_QUERY = f"""
    EXEC process_analyzer_orchestrator
        @output = 'eventlog',
        @input_customer_id = {customer_id_param},
        @input_start_date = {start_date_param},
        @input_end_date = {end_date_param},
        @input_material_ids = {material_ids_param},
        @input_material_filter_mode = {material_filter_mode_param};
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
    material_ids_list = [f"'{p.replace('\'', '\'\'')}'" for p in material_ids]
    material_ids_param = f"'{','.join(material_ids_list)}'" if material_ids_list else "NULL"
    material_filter_mode_param = 1 if is_strict_inclusion else 0

    SQL_QUERY = f"""
    EXEC process_analyzer_orchestrator
        @output = 'kpi',
        @input_customer_id = {customer_id_param},
        @input_start_date = {start_date_param},
        @input_end_date = {end_date_param},
        @input_material_ids = {material_ids_param},
        @input_material_filter_mode = {material_filter_mode_param};
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
    material_ids_list = [f"'{p.replace('\'', '\'\'')}'" for p in material_ids]
    material_ids_param = f"'{','.join(material_ids_list)}'" if material_ids_list else "NULL"
    material_filter_mode_param = 1 if is_strict_inclusion else 0

    SQL_QUERY = f"""
    EXEC process_analyzer_orchestrator
        @output = 'dfg',
        @input_customer_id = {customer_id_param},
        @input_start_date = {start_date_param},
        @input_end_date = {end_date_param},
        @input_material_ids = {material_ids_param},
        @input_material_filter_mode = {material_filter_mode_param};
    """
    try:
        with pyodbc.connect(connection_string) as connection:
            df = pd.read_sql(SQL_QUERY, connection)
        return df
    except pyodbc.Error as ex:
        st.error(f"Fehler bei der DFG-Datenbankabfrage: {ex}")
        return pd.DataFrame()


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

        # HINWEIS: Filteroptionen werden nun basierend auf den Eventlog-Daten generiert
        # Fallback auf leere Liste, wenn df_eventlog leer ist
        if 'Produkt' in df_eventlog.columns and not df_eventlog.empty:
            PRODUKTE = df_eventlog['Produkt'].unique().tolist()
        else:
            PRODUKTE = []  # Fallback

        if 'Kunden_ID' in df_eventlog.columns and not df_eventlog.empty:
            KUNDEN_ID = df_eventlog['Kunden_ID'].unique().tolist()
        else:
            KUNDEN_ID = []  # Fallback

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
            st.multiselect('Kunde auswählen', KUNDEN_ID, key='kunde_input')

            # 3. Produkte (Multiselect)
            st.markdown("##### Produkt", unsafe_allow_html=True)
            st.multiselect('Wähle ein Produkt', PRODUKTE, key='produkt_input')

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

    # Sicherstellen, dass Umsatz existiert, bevor sum() aufgerufen wird
    total_sales = filtered_df['Umsatz'].sum() if 'Umsatz' in filtered_df.columns else 0

    st.metric(
        label="Gesamtumsatz (gefiltert)",
        value=f"€{total_sales:,.2f}"
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

with col3:
    # Beginnt den zentrierten Container für col3
    st.markdown("<div class='center-col-content'>", unsafe_allow_html=True)

    # 1. Prozess-Scorecard (Tabelle)
    # ZENTRIERTE UNTERÜBERSCHRIFT
    st.markdown("<h3 style='text-align: center;'>KPI - Zielerreichung</h3>", unsafe_allow_html=True)

    # Erstellung des simulierten DataFrames für die Prozess-Tabelle (KPI-Daten werden verwendet)
    # HINWEIS: Hier müsste nun df_kpi verwendet werden, falls die Struktur passt
    # Da wir KPI-Daten ignorieren sollten (Ihre Anweisung), belassen wir die simulierte Tabelle.
    # Wenn df_kpi verwendet werden soll, müsste hier die df_kpi Tabelle hinein: process_df = df_kpi.copy()
    process_data = {
        'Kennzahl': ['Prozesskennzahl 1', 'Prozesskennzahl 2', 'Prozesskennzahl 3', 'Prozesskennzahl 4'],
        'Einheit': ['h', 'h', 'h', 'h'],  # Einheit von % auf h geändert
        'Toleranz unten': [70.00, 70.00, 70.00, 70.00],
        'Ziel': [100.00, 100.00, 100.00, 100.00],
        'Ist': [60.00, 70.00, 100.00, 110.00],
    }
    process_df = pd.DataFrame(process_data)

    # Berechnung der Zielerreichung
    process_df['Zielerreichung'] = (process_df['Ist'] / process_df['Ziel'])
    process_df['Bewertung'] = "🟢"

    # Anzeige der Tabelle mit Formatierung
    st.dataframe(
        process_df.style.format({
            'Toleranz unten': "{:.2f}",
            'Ziel': "{:.2f}",
            'Ist': "{:.2f}",
            'Zielerreichung': "{:.2%}"
        }),
        width='stretch',  # KORREKTUR: use_container_width=True -> width='stretch'
        hide_index=True,
        column_config={
            "Bewertung": st.column_config.Column(
                label="",
                width="tiny"
            )
        }
    )

    # 2. DFG-Visualisierung (NUR GRAPH, KEINE TABELLE)
    st.markdown("<h3 style='text-align: center;'>DFG - Prozessfluss</h3>", unsafe_allow_html=True)

    if not df_dfg.empty:
        # Netzwerkdiagramm mit Plotly
        try:
            import plotly.graph_objects as go

            # Erstelle Netzwerkgraph
            fig = go.Figure()

            # Knoten sammeln
            nodes = set()
            for _, row in df_dfg.iterrows():
                nodes.add(row['From_Activity'])
                nodes.add(row['To_Activity'])

            nodes_list = list(nodes)
            node_indices = {node: i for i, node in enumerate(nodes_list)}

            # Edges hinzufügen (NUR Linien, keine permanenten Labels)
            for _, row in df_dfg.iterrows():
                from_idx = node_indices[row['From_Activity']]
                to_idx = node_indices[row['To_Activity']]

                # Berechne Position (einfaches Layout)
                x_from = (from_idx % 5) * 100
                y_from = (from_idx // 5) * 100
                x_to = (to_idx % 5) * 100
                y_to = (to_idx // 5) * 100

                # Zeichne Kante mit Hover-Info (OHNE None am Ende!)
                fig.add_trace(go.Scatter(
                    x=[x_from, x_to],
                    y=[y_from, y_to],
                    mode='lines',
                    line=dict(width=max(2, row['Frequency'] / 10), color='lightblue'),
                    showlegend=False,
                    text=f"{row['From_Activity']} → {row['To_Activity']}<br>Häufigkeit: {row['Frequency']}",
                    hoverinfo='text',
                    hoverlabel=dict(bgcolor="white", font_size=12)
                ))

            # Knoten hinzufügen
            for i, node in enumerate(nodes_list):
                x = (i % 5) * 100
                y = (i // 5) * 100
                fig.add_trace(go.Scatter(
                    x=[x],
                    y=[y],
                    mode='markers+text',
                    marker=dict(size=20, color='lightcoral'),
                    text=node,
                    textposition='top center',
                    showlegend=False,
                    hoverinfo='skip'  # Kein Hover auf Knoten
                ))

            fig.update_layout(
                height=500,
                showlegend=False,
                xaxis=dict(showgrid=False, showticklabels=False, zeroline=False),
                yaxis=dict(showgrid=False, showticklabels=False, zeroline=False),
                margin=dict(l=20, r=20, t=20, b=20)
            )

            st.plotly_chart(fig, use_container_width=True)

        except ImportError:
            st.error("⚠️ Plotly ist nicht installiert!")
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
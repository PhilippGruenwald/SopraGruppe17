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

# ÄNDERUNG 1: Initialisierung auf None (bedeutet "Alle Kunden") statt []
if 'kunde_input' not in st.session_state: st.session_state['kunde_input'] = None
if 'produkt_input' not in st.session_state: st.session_state['produkt_input'] = []

# Steuert, ob die angewendeten Filter die DB-Abfrage triggern sollen (Muss beim Start FALSE sein)
if 'data_applied' not in st.session_state: st.session_state['data_applied'] = False

# Applied State Keys (von DB-Funktion gelesen)
if 'applied_zeitraum' not in st.session_state: st.session_state['applied_zeitraum'] = 'Gesamt'
if 'applied_start_date' not in st.session_state: st.session_state['applied_start_date'] = DEFAULT_START_DATE
if 'applied_end_date' not in st.session_state: st.session_state['applied_end_date'] = DEFAULT_END_DATE
# ÄNDERUNG 2: Applied State auch auf None initialisieren
if 'applied_kunde_input' not in st.session_state: st.session_state['applied_kunde_input'] = None
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

    st.session_state.data_applied = True
    st.rerun()


def reset_filters():
    """Setzt alle Filter im Session State auf ihre Standardwerte zurück und wendet sie an."""
    st.session_state['zeitraum_input'] = 'Gesamt'
    st.session_state['start_date_input'] = DEFAULT_START_DATE
    st.session_state['end_date_input'] = DEFAULT_END_DATE

    # ÄNDERUNG 3: Reset auf None statt []
    st.session_state['kunde_input'] = None
    st.session_state['produkt_input'] = []
    st.session_state['produkt_filter_exklusiv'] = False

    apply_filters()


def update_dates_on_period_change():
    """Callback-Funktion für Zeiträume."""
    zeitraum = st.session_state.get('zeitraum_input', 'Gesamt')
    current_end_date = date.today()
    min_data_date_fallback = st.session_state.get('min_data_date', DEFAULT_START_DATE)

    target_start_date = None
    target_end_date = current_end_date

    if zeitraum == 'Letzte 7 Tage':
        target_start_date = current_end_date - timedelta(days=7)
    elif zeitraum == 'Letzte 30 Tage':
        target_start_date = current_end_date - timedelta(days=30)
    elif zeitraum == 'Gesamt':
        target_start_date = min_data_date_fallback
        target_end_date = current_end_date

    if target_start_date is not None and zeitraum != 'Benutzerdefiniert':
        st.session_state['start_date_input'] = target_start_date
        st.session_state['end_date_input'] = target_end_date


########################################################################################################################
# SQL Helper Functions
#######################################################################################################################

def _get_db_connection():
    server = os.environ.get('SERVER')
    database = os.environ.get('DATABASE')
    uid = os.environ.get('UID')
    pwd = os.environ.get('PWD')

    if not all([server, database, uid, pwd]):
        st.error("Datenbank-Konfiguration fehlt!")
        return None
    try:
        connection_string = (
            "Driver={ODBC Driver 17 for SQL Server};"
            f"Server={server};Database={database};UID={uid};PWD={pwd}"
        )
        return connection_string
    except Exception as e:
        st.error(f"Fehler Connection String: {e}")
        return None


@st.cache_data(ttl=600)
def load_eventlog_data(customer_ids, start_date, end_date, material_ids, is_strict_inclusion):
    connection_string = _get_db_connection()
    if not connection_string: return pd.DataFrame()

    # Logik: Leere Liste customer_ids bedeutet im SQL meist NULL -> Alle
    customer_id_param = f"'{','.join(map(str, customer_ids))}'" if customer_ids else "NULL"
    start_date_param = f"'{start_date.strftime('%Y-%m-%d')}'"
    end_date_param = f"'{end_date.strftime('%Y-%m-%d')}'"
    material_ids_list = [str(p).replace("'", "''") for p in material_ids]
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
        st.error(f"Fehler Eventlog: {ex}")
        return pd.DataFrame()


@st.cache_data(ttl=600)
def load_kpi_data(customer_ids, start_date, end_date, material_ids, is_strict_inclusion):
    connection_string = _get_db_connection()
    if not connection_string: return pd.DataFrame()

    customer_id_param = f"'{','.join(map(str, customer_ids))}'" if customer_ids else "NULL"
    start_date_param = f"'{start_date.strftime('%Y-%m-%d')}'"
    end_date_param = f"'{end_date.strftime('%Y-%m-%d')}'"
    material_ids_list = [str(p).replace("'", "''") for p in material_ids]
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
    except pyodbc.Error:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def load_dfg_data(customer_ids, start_date, end_date, material_ids, is_strict_inclusion):
    connection_string = _get_db_connection()
    if not connection_string: return pd.DataFrame()

    customer_id_param = f"'{','.join(map(str, customer_ids))}'" if customer_ids else "NULL"
    start_date_param = f"'{start_date.strftime('%Y-%m-%d')}'"
    end_date_param = f"'{end_date.strftime('%Y-%m-%d')}'"
    material_ids_list = [str(p).replace("'", "''") for p in material_ids]
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
        st.error(f"Fehler DFG: {ex}")
        return pd.DataFrame()


@st.cache_data(ttl=3600)
def load_lov_customers_data():
    connection_string = _get_db_connection()
    if not connection_string: return [], {}
    SQL_QUERY = "SELECT CUSTOMER_ID, CUSTOMER_LONG FROM LOV_CUSTOMER"
    try:
        with pyodbc.connect(connection_string) as connection:
            df = pd.read_sql(SQL_QUERY, connection)
        if df.empty: return [], {}
        ids = df['CUSTOMER_ID'].tolist()
        mapping = pd.Series(df.CUSTOMER_LONG.values, index=df.CUSTOMER_ID).to_dict()
        return ids, mapping
    except Exception as ex:
        st.error(f"Fehler LOV Customer: {ex}")
        return [], {}


@st.cache_data(ttl=3600)
def load_lov_products_data():
    connection_string = _get_db_connection()
    if not connection_string: return [], {}
    SQL_QUERY = "exec dbo.process_analyzer_orchestrator @output = 'material'"
    try:
        with pyodbc.connect(connection_string) as connection:
            df = pd.read_sql(SQL_QUERY, connection)
        if df.empty: return [], {}
        ids = df['ID_MAT'].tolist()
        mapping = pd.Series(df.MAT_DESCR.values, index=df.ID_MAT).to_dict()
        return ids, mapping
    except Exception as ex:
        st.error(f"Fehler LOV Product: {ex}")
        return [], {}


########################################################################################################################
# Main Logic / Data Loading
########################################################################################################################

df_eventlog = pd.DataFrame()
df_kpi = pd.DataFrame()
df_dfg = pd.DataFrame()

if st.session_state.get('data_applied', False):

    # Applied Parameter lesen
    applied_single_customer = st.session_state.get('applied_kunde_input', None)

    # ÄNDERUNG 4: Umwandlung Single Value -> List für SQL Funktion
    # Wenn None -> Leere Liste (SQL interpretiert das als ALLE)
    # Wenn Wert -> Liste mit einem Wert [ID]
    if applied_single_customer is None:
        applied_customer_ids = []
    else:
        applied_customer_ids = [applied_single_customer]

    applied_start_date = st.session_state.get('applied_start_date', DEFAULT_START_DATE)
    applied_end_date = st.session_state.get('applied_end_date', DEFAULT_END_DATE)
    applied_material_ids = st.session_state.get('applied_produkt_input', [])
    applied_is_strict_inclusion = st.session_state.get('applied_produkt_filter_exklusiv', False)

    # DATEN LADEN
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

    if df_eventlog.empty:
        st.warning("Es konnten keine Eventlog-Daten geladen werden (zu restriktive Filter).")

    if 'Umsatz' in df_eventlog.columns:
        df_eventlog['Umsatz'] = pd.to_numeric(df_eventlog['Umsatz'], errors='coerce').fillna(0)

########################################################################################################################
# Frontend
#######################################################################################################################

col1, col2, col3 = st.columns([2, 2, 3])

# --- Filter Spalte ---
with col1:
    filter_container = st.container()

    with filter_container:
        customer_ids_options, customer_map = load_lov_customers_data()
        product_ids_options, product_map = load_lov_products_data()

        current_end_date = date.today()
        min_data_date = df_eventlog[
            'Datum'].min().date() if 'Datum' in df_eventlog.columns and not df_eventlog.empty else DEFAULT_START_DATE
        st.session_state['min_data_date'] = min_data_date
        zeitraum_selection = st.session_state.get('zeitraum_input', 'Gesamt')

        st.markdown("<h2 style='text-align: center;'>Filter</h2>", unsafe_allow_html=True)
        st.markdown("#### **1. Zeitraum**", unsafe_allow_html=True)

        st.selectbox(
            'Zeitraum auswählen',
            ['Gesamt', 'Letzte 7 Tage', 'Letzte 30 Tage', 'Benutzerdefiniert'],
            key='zeitraum_input',
            on_change=update_dates_on_period_change,
            index=['Gesamt', 'Letzte 7 Tage', 'Letzte 30 Tage', 'Benutzerdefiniert'].index(zeitraum_selection)
        )

        st.date_input('Startdatum', value=st.session_state['start_date_input'], min_value=min_data_date,
                      max_value=current_end_date, key='start_date_input')
        st.date_input('Enddatum', value=st.session_state['end_date_input'], min_value=min_data_date,
                      max_value=current_end_date, key='end_date_input')

        st.markdown("---")

        with st.form(key='filter_form'):
            st.markdown("#### **2. Weitere Filter**", unsafe_allow_html=True)
            st.markdown("Bitte weitere Filter wählen:")

            # ÄNDERUNG 5: Kunde -> Selectbox (Single Select)
            st.markdown("##### Kunde", unsafe_allow_html=True)

            # Wir fügen None als erste Option hinzu für "Alle Kunden"
            options_with_all = [None] + customer_ids_options

            st.selectbox(
                'Kunde auswählen',
                options=options_with_all,
                # Formatierung: Wenn x None ist, zeige "Alle Kunden", sonst Mapping aus DB
                format_func=lambda x: "Alle Kunden (Standard)" if x is None else customer_map.get(x, str(x)),
                key='kunde_input'  # Speichert einzelne ID oder None
            )

            # Produkte bleibt Multiselect
            st.markdown("##### Produkt", unsafe_allow_html=True)
            st.multiselect(
                'Wähle ein Produkt',
                options=product_ids_options,
                format_func=lambda x: product_map.get(x, str(x)),
                key='produkt_input'
            )

            st.checkbox("Strikte Inklusion", value=False, key='produkt_filter_exklusiv')
            st.markdown("---")
            submit_button = st.form_submit_button(label='Filter anwenden')

        if submit_button:
            apply_filters()
            st.rerun()

        st.button("Filter zurücksetzen", on_click=reset_filters, key='reset_button')

filtered_df = df_eventlog.copy()

# --- Mittelspalte (KPIs) ---
with col2:
    st.markdown("<div class='center-col-content'>", unsafe_allow_html=True)
    st.metric(label="Gefilterte Datensätze", value=f"{len(filtered_df):,}", delta=None, delta_color="off")
    total_sales = filtered_df['Umsatz'].sum() if 'Umsatz' in filtered_df.columns else 0
    #st.metric(label="Gesamtumsatz (gefiltert)", value=f"€{total_sales:,.2f}")

    with st.expander("Eventlog-Vorschau"):
        st.dataframe(filtered_df, width='stretch', hide_index=True)
    st.markdown("</div>", unsafe_allow_html=True)

# --- Rechte Spalte (Visuals) ---
with col3:
    st.markdown("<div class='center-col-content'>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align: center;'>KPI - Zielerreichung</h3>", unsafe_allow_html=True)

    process_data = {
        'Kennzahl': ['Prozesskennzahl 1', 'Prozesskennzahl 2', 'Prozesskennzahl 3', 'Prozesskennzahl 4'],
        'Einheit': ['h', 'h', 'h', 'h'],
        'Toleranz unten': [70.00, 70.00, 70.00, 70.00],
        'Ziel': [100.00, 100.00, 100.00, 100.00],
        'Ist': [60.00, 70.00, 100.00, 110.00],
    }
    process_df = pd.DataFrame(process_data)
    process_df['Zielerreichung'] = (process_df['Ist'] / process_df['Ziel'])
    process_df['Bewertung'] = "🟢"

    st.dataframe(
        process_df.style.format({
            'Toleranz unten': "{:.2f}",
            'Ziel': "{:.2f}",
            'Ist': "{:.2f}",
            'Zielerreichung': "{:.2%}"
        }),
        width='stretch',
        hide_index=True,
        column_config={"Bewertung": st.column_config.Column(label="", width="tiny")}
    )

    st.markdown("<h3 style='text-align: center;'>DFG - Prozessfluss</h3>", unsafe_allow_html=True)

    if not df_dfg.empty:
        try:
            import plotly.graph_objects as go

            fig = go.Figure()
            nodes = set()
            for _, row in df_dfg.iterrows():
                nodes.add(row['From_Activity'])
                nodes.add(row['To_Activity'])
            nodes_list = list(nodes)
            node_indices = {node: i for i, node in enumerate(nodes_list)}

            for _, row in df_dfg.iterrows():
                from_idx = node_indices[row['From_Activity']]
                to_idx = node_indices[row['To_Activity']]
                x_from, y_from = (from_idx % 5) * 100, (from_idx // 5) * 100
                x_to, y_to = (to_idx % 5) * 100, (to_idx // 5) * 100

                fig.add_trace(go.Scatter(
                    x=[x_from, x_to], y=[y_from, y_to],
                    mode='lines',
                    line=dict(width=max(2, row['Frequency'] / 10), color='lightblue'),
                    showlegend=False,
                    text=f"{row['From_Activity']} → {row['To_Activity']}<br>Häufigkeit: {row['Frequency']}",
                    hoverinfo='text',
                    hoverlabel=dict(bgcolor="white", font_size=12)
                ))

            for i, node in enumerate(nodes_list):
                x, y = (i % 5) * 100, (i // 5) * 100
                fig.add_trace(go.Scatter(
                    x=[x], y=[y], mode='markers+text',
                    marker=dict(size=20, color='lightcoral'),
                    text=node, textposition='top center',
                    showlegend=False, hoverinfo='skip'
                ))
            fig.update_layout(
                height=500, showlegend=False,
                xaxis=dict(showgrid=False, showticklabels=False, zeroline=False),
                yaxis=dict(showgrid=False, showticklabels=False, zeroline=False),
                margin=dict(l=20, r=20, t=20, b=20)
            )
            st.plotly_chart(fig, use_container_width=True)
        except ImportError:
            st.error("Plotly ist nicht installiert.")
    else:
        st.warning("Keine DFG-Daten verfügbar.")

    st.caption(f"Anzeige basierend auf {len(filtered_df)} Datensätzen.")
    st.markdown("</div>", unsafe_allow_html=True)

st.markdown("""
<style>
.center-col-content { display: flex; flex-direction: column; align-items: center; text-align: center; }
.stMetric > div:nth-child(1) { font-size: 1.2rem; font-weight: 500; }
div[data-testid="stForm"] { border: none !important; padding: 0 !important; }
</style>
""", unsafe_allow_html=True)
import streamlit as st
import pyodbc
import os
from dotenv import load_dotenv

load_dotenv()


# ============================================================================
# AUTHENTIFIZIERUNGS-HILFSFUNKTIONEN
# ============================================================================

def get_connection_string():
    """
    Erstellt einen Connection String mit den FESTEN Technical User Credentials aus .env.
    Diese Credentials werden für ALLE Datenbankverbindungen verwendet.

    Returns:
        str: Connection String für pyodbc
    """
    # Server und Database aus .env
    server = os.environ.get('Server', 'edu.hdm-server.eu')
    database = os.environ.get('Database', 'ERPDEV')

    # FESTE Technical User Credentials aus .env
    username = os.environ.get('UID', 'ERP_REMOTE_USER')
    password = os.environ.get('PWD', 'Password123')

    connection_string = (
        "Driver={ODBC Driver 17 for SQL Server};"
        f"Server={server};"
        f"Database={database};"
        f"UID={username};"
        f"PWD={password}"
    )

    return connection_string


def get_user_info():
    """
    Gibt Informationen über den angemeldeten Benutzer zurück.

    Returns:
        dict: Dictionary mit User-Informationen oder None
    """
    if not st.session_state.get('authenticated', False):
        return None

    return {
        'username': st.session_state.get('display_username'),  # Der User aus der Login-Maske
        'database': 'ERPDEV',
        'display_name': st.session_state.get('display_username', 'Unbekannt')
    }


# ============================================================================
# LOGIN-FUNKTIONEN
# ============================================================================

def test_connection(username, password):
    """
    Testet die Login-Credentials gegen die T_USER Tabelle.
    Die Datenbankverbindung erfolgt über den FESTEN Technical User.

    Args:
        username: Der Benutzername aus der Login-Maske (z.B. w25s209)
        password: Das Passwort aus der Login-Maske

    Returns:
        tuple: (erfolg: bool, fehlermeldung: str oder None)
    """
    try:
        # Verbinde mit FESTEN Credentials
        connection_string = get_connection_string()

        # Teste die Verbindung
        conn = pyodbc.connect(connection_string, timeout=5)

        # Validiere User-Credentials gegen T_USER Tabelle (case-insensitive)
        cursor = conn.cursor()

        # SQL Query - Username ist case-insensitive durch UPPER()
        sql_query = """
            SELECT USERNAME, USERPASS, SECURITYLEVEL
            FROM T_USER
            WHERE UPPER(USERNAME) = UPPER(?)
        """

        cursor.execute(sql_query, username)
        result = cursor.fetchone()

        if result is None:
            conn.close()
            return False, f"Benutzer '{username}' nicht gefunden."

        db_username, db_password, security_level = result

        # Validiere Passwort
        if db_password != password:
            conn.close()
            return False, "Ungültiges Passwort."

        # Speichere zusätzliche User-Informationen im Session State
        st.session_state['security_level'] = security_level
        st.session_state['db_username'] = db_username  # Der tatsächliche Username aus der DB (Großbuchstaben)

        conn.close()
        return True, None

    except pyodbc.Error as ex:
        error_msg = str(ex)
        if "Login failed" in error_msg:
            return False, "Datenbankverbindung fehlgeschlagen. Bitte kontaktieren Sie den Administrator."
        elif "Cannot open database" in error_msg:
            return False, "Datenbank nicht erreichbar. Bitte kontaktieren Sie den Administrator."
        else:
            return False, f"Verbindungsfehler: {error_msg}"
    except Exception as ex:
        return False, f"Unerwarteter Fehler: {str(ex)}"


def show_login_page():
    """
    Zeigt die Login-Seite an und verarbeitet den Login-Versuch.
    """
    # Zentriertes Layout
    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        # Logo/Titel
        st.markdown("""
        <div style='text-align: center; padding: 2rem 0;'>
            <h1>🚴 Adventure Bikes</h1>
            <h3>Prozessanalyse Dashboard</h3>
        </div>
        """, unsafe_allow_html=True)

        # Login-Form
        with st.form("login_form"):
            st.markdown("#### Anmeldung")

            username = st.text_input(
                "Benutzername",
                placeholder="z.B. w25s209",
                help="Ihr Hochschul-Benutzername"
            )

            password = st.text_input(
                "Passwort",
                type="password",
                help="Ihr Passwort"
            )

            submit_button = st.form_submit_button(
                "Anmelden",
                use_container_width=True
            )

            if submit_button:
                if not username or not password:
                    st.error("⚠️ Bitte füllen Sie alle Felder aus.")
                else:
                    with st.spinner("Anmeldung wird geprüft..."):
                        success, error_msg = test_connection(username, password)

                        if success:
                            # Login erfolgreich - Daten im Session State speichern
                            st.session_state['authenticated'] = True
                            st.session_state[
                                'display_username'] = username  # Der User aus der Login-Maske (Kleinbuchstaben)
                            # security_level und db_username wurden bereits in test_connection() gespeichert

                            st.success("✅ Anmeldung erfolgreich!")
                            st.rerun()
                        else:
                            st.error(f"❌ {error_msg}")

        # Hilfe-Text
        st.markdown("""
        ---
        <div style='text-align: center; color: #666; font-size: 0.9em;'>
        <p>💡 <b>Hinweis:</b> Verwenden Sie Ihren W-User und Ihr Passwort aus der Datenbank.</p>
        </div>
        """, unsafe_allow_html=True)


def logout():
    """
    Meldet den Benutzer ab und löscht alle Session-Daten.
    """
    # Lösche alle authentifizierungsbezogenen Daten
    for key in ['authenticated', 'display_username', 'db_username', 'security_level']:
        if key in st.session_state:
            del st.session_state[key]

    st.rerun()


def is_authenticated():
    """
    Prüft, ob ein Benutzer angemeldet ist.

    Returns:
        bool: True wenn angemeldet, sonst False
    """
    return st.session_state.get('authenticated', False)


def get_user_credentials():
    """
    Gibt die Credentials des angemeldeten Benutzers zurück.
    ACHTUNG: Dies gibt die DISPLAY-Credentials zurück, nicht die DB-Credentials!

    Returns:
        dict: Dictionary mit display_username und security_level
    """
    if not is_authenticated():
        return None

    return {
        'display_username': st.session_state.get('display_username'),  # Aus Login-Maske
        'db_username': st.session_state.get('db_username'),  # Aus DB (Großbuchstaben)
        'security_level': st.session_state.get('security_level', 3)
    }
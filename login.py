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
    Erstellt einen Connection String basierend auf den Credentials des angemeldeten Users.

    Returns:
        str: Connection String für pyodbc oder None wenn nicht angemeldet
    """
    # Prüfe ob User angemeldet ist
    if not st.session_state.get('authenticated', False):
        return None

    # Server aus .env (Fallback auf den bekannten Server)
    server = os.environ.get('SERVER', 'edu.hdm-server.eu')

    # Database ist immer ERPDEV (für alle User gleich!)
    database = 'ERPDEV'

    # User-Credentials aus Session State
    username = st.session_state.get('username')
    password = st.session_state.get('password')

    if not all([username, password]):
        return None

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
        'username': st.session_state.get('username'),
        'database': 'ERPDEV',  # Database ist immer ERPDEV
        'display_name': st.session_state.get('username', 'Unbekannt')
    }


# ============================================================================
# LOGIN-FUNKTIONEN
# ============================================================================

def test_connection(username, password):
    """
    Testet die Datenbankverbindung mit den angegebenen Credentials.

    Args:
        username: Der Benutzername (z.B. w25s209 oder W25S209)
        password: Das Passwort

    Returns:
        tuple: (erfolg: bool, fehlermeldung: str oder None)
    """
    try:
        # Server aus .env
        server = os.environ.get('SERVER', 'edu.hdm-server.eu')

        # Database ist immer ERPDEV (für alle User gleich!)
        database = 'ERPDEV'

        connection_string = (
            "Driver={ODBC Driver 17 for SQL Server};"
            f"Server={server};"
            f"Database={database};"
            f"UID={username};"
            f"PWD={password}"
        )

        # Verbindung testen
        conn = pyodbc.connect(connection_string, timeout=5)
        conn.close()

        return True, None

    except pyodbc.Error as ex:
        error_msg = str(ex)
        if "Login failed" in error_msg:
            return False, "Ungültige Anmeldedaten. Bitte überprüfen Sie Benutzername und Passwort."
        elif "Cannot open database" in error_msg:
            return False, f"Datenbank '{database}' nicht gefunden oder nicht erreichbar."
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
                help="Ihr Datenbank-Passwort"
            )

            submit_button = st.form_submit_button(
                "Anmelden",
                use_container_width=True
            )

            if submit_button:
                if not username or not password:
                    st.error("⚠️ Bitte füllen Sie alle Felder aus.")
                else:
                    with st.spinner("Verbindung wird hergestellt..."):
                        success, error_msg = test_connection(username, password)

                        if success:
                            # Login erfolgreich - Daten im Session State speichern
                            st.session_state['authenticated'] = True
                            st.session_state['username'] = username
                            st.session_state['password'] = password
                            st.session_state['database'] = 'ERPDEV'  # Immer ERPDEV für alle User

                            st.success("✅ Anmeldung erfolgreich!")
                            st.rerun()
                        else:
                            st.error(f"❌ {error_msg}")

        # Hilfe-Text
        st.markdown("""
        ---
        <div style='text-align: center; color: #666; font-size: 0.9em;'>
        <p>💡 <b>Hinweis:</b> Verwenden Sie Ihren W-User </p>
        </div>
        """, unsafe_allow_html=True)


def logout():
    """
    Meldet den Benutzer ab und löscht alle Session-Daten.
    """
    # Lösche alle authentifizierungsbezogenen Daten
    for key in ['authenticated', 'username', 'password', 'database']:
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

    Returns:
        dict: Dictionary mit username, password und database
    """
    if not is_authenticated():
        return None

    return {
        'username': st.session_state.get('username'),
        'password': st.session_state.get('password'),
        'database': 'ERPDEV'  # Immer ERPDEV für alle User
    }
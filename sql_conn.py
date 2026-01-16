import pyodbc
import streamlit as st

connection_string = (
    "Driver={SQL Server};"
    f"Server={st.secrets['Server']};"
    f"Database={st.secrets['Database']};"
    f"UID={st.secrets['UID']};"
    f"PWD={st.secrets['PWD']}"
)

try:
    connection = pyodbc.connect(connection_string)
    print("Connection established")
except pyodbc.Error as e:
    print(e)
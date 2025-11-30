import pyodbc
from dotenv import load_dotenv
import os

load_dotenv()

connection_string = (
    "Driver={SQL Server};"
    f"Server={os.environ.get('Server')};"
    f"Database={os.environ.get('Database')};"
    f"UID={os.environ.get('UID')};"
    f"PWD={os.environ.get('PWD')}"
)


try:
    connection = pyodbc.connect(connection_string)
    print("Connection established")
except pyodbc.Error as e:
    print(e)
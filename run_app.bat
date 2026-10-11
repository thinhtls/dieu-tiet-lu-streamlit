@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Chua co moi truong Python. Xem README_streamlit.md de cai dat.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m streamlit run streamlit_app.py

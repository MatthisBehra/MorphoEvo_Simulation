@echo off
echo === MorphoEvo_Simulation - Setup ===

python --version >nul 2>&1
if errorlevel 1 (
    echo ERREUR: Python n'est pas installe ou pas dans le PATH.
    pause
    exit /b 1
)

echo Creation de l'environnement virtuel...
python -m venv venv

echo Activation de l'environnement virtuel...
call venv\Scripts\activate.bat

echo Installation des dependances...
pip install -r requirements.txt

echo.
echo === Setup termine ! ===
echo Pour activer l'environnement : venv\Scripts\activate.bat
echo Pour lancer la simulation    : python src/main.py
pause

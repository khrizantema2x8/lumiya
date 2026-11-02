@echo off
setlocal
echo This removes Lumiya's Python dependencies (the .env folder and the "lumiya" conda environment).
echo Close Lumiya first. Your results and this folder are kept.
echo Delete this folder, and Python, Miniconda and Git, manually if you no longer need them.
choice /C YN /M "Continue"
if errorlevel 2 exit /b 0
if exist "%~dp0.env" rmdir /s /q "%~dp0.env"
set "CONDA_BAT=%USERPROFILE%\miniconda3\Scripts\conda.exe"
if not exist "%CONDA_BAT%" set "CONDA_BAT=%USERPROFILE%\anaconda3\Scripts\conda.exe"
if exist "%CONDA_BAT%" "%CONDA_BAT%" env remove -n lumiya -y
echo Done.
pause

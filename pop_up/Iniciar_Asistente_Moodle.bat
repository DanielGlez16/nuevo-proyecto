@echo off
chcp 65001 >nul
title Moodle Desktop Assistant (Tema Oscuro)
cd /d "%~dp0"
echo Iniciando Asistente de Escritorio de Moodle...
python app.py
pause


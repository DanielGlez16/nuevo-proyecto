@echo off
chcp 65001 >nul
title Mini Pop-Up Flotante de Moodle
cd /d "%~dp0"
start "" pythonw popup_widget.py


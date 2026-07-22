@echo off
title TimeTable App Runner
echo 🚀 Starting TESSERA Smart Timetabling App...
cd /d "%~dp0"
streamlit run app.py
pause

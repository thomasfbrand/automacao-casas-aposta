@echo off
REM Liga o robo em modo automatico: escuta o grupo do Telegram e aposta sozinho a cada tip "Live".
REM Para desligar: feche esta janela (ou Ctrl+C). O log do dia fica em logs\robo_AAAA-MM-DD.log
cd /d "%~dp0"
call .venv\Scripts\activate
python main.py
pause

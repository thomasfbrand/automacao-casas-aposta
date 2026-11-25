@echo off
REM Chamado pelo Agendador do Windows: todo dia 08:00, e tambem ao ligar/entrar no PC.
REM Fora do horario (01:00 as 08:00) nao faz nada. Dentro do horario roda ate 01:00 e reinicia sozinho se cair.
cd /d "%~dp0"
if not exist logs mkdir logs
call .venv\Scripts\activate
:loop
python -c "import datetime as d; h=d.datetime.now().hour; raise SystemExit(0 if 1<=h<8 else 1)"
if %errorlevel%==0 goto fim
python main.py --ate 01:00
if %errorlevel%==0 goto fim
echo [%date% %time%] robo caiu (codigo %errorlevel%); reiniciando em 60s >> logs\reinicios.log
timeout /t 60 /nobreak >nul
goto loop
:fim
exit /b 0

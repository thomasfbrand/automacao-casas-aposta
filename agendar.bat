@echo off
REM Cria (ou atualiza) a tarefa "Robo Pinnacle" no Agendador do Windows. Rode UMA vez (dois cliques).
REM Liga: todo dia 08:00 E toda vez que voce entrar no Windows (se estiver no horario). Desliga sozinho a 01:00.
REM Se o PC estava desligado as 08:00, roda assim que ligar. Para remover: schtasks /Delete /TN "Robo Pinnacle" /F
cd /d "%~dp0"
schtasks /Create /TN "Robo Pinnacle" /XML "%~dp0tarefa_robo.xml" /F
if %errorlevel%==0 (echo. & echo Tarefa criada/atualizada.) else (echo. & echo Falhou ao criar a tarefa. Tente: botao direito ^> Executar como administrador.)
pause

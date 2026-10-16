@echo off
chcp 65001 >nul
set PYTHONDONTWRITEBYTECODE=1
title CP3 - Sistema Web de Orcamento Fotovoltaico (Sprint 3 - Equipe Lumos FIAP)
cd /d "%~dp0"

echo ========================================================================================
echo   SISTEMA INTEGRADO DE DIMENSIONAMENTO E ORCAMENTO FOTOVOLTAICO (SPRINT 3 - PB01 A PB21)
echo   Equipe Lumos FIAP: Pietro Lorande (RM569125) ^| Luiz Otavio (RM569977) ^| Maria Eduarda (RM574094)
echo ========================================================================================
echo.
echo [1/2] Executando validacao dos datasets CSV e bateria de testes automatizados...
python -B testes.py
echo.
echo [2/2] Iniciando Interface Grafica Web Full-Stack (Python + Navegador)...
python -B app_web.py

pause

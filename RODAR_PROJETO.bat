@echo off
chcp 65001 >nul
title CP3 - Sistema de Dimensionamento e Orcamento Fotovoltaico (Sprint 3 - Equipe Lumos FIAP)
cd /d "%~dp0"

echo ========================================================================================
echo   INICIANDO SPRINT REVIEW - SISTEMA DE ORCAMENTO FOTOVOLTAICO (EQUIPE LUMOS - FIAP)
echo   Integrantes: Pietro Lorande (RM569125) ^| Luiz Otavio (RM569977) ^| Maria Eduarda (RM574094)
echo ========================================================================================
echo.

python sistema_analise_casa.py --apresentacao

pause

# -*- coding: utf-8 -*-
"""
Aplicacao Web Full-Stack — Sistema de Dimensionamento e Orcamento Fotovoltaico (Sprint 3 Final)
Disciplina: Solucoes em Energias Renovaveis e Sustentaveis (Prof. Alvaro Goncalves)
Equipe Lumos (FIAP):
  - Pietro Lorande | RM 569125
  - Luiz Otavio Brito Freixo | RM 569977
  - Maria Eduarda Lemos | RM 574094

Servidor HTTP integrado (biblioteca padrao Python `http.server`) que conecta a interface
grafica no navegador diretamente ao motor Python (`fotovoltaico.py`), ao banco persistente
(`dados_sistema.json`) e aos datasets CSV (`dados_fv/*.csv`).
"""

import io
import json
import os
import socket
import sys
import threading
import webbrowser
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import fotovoltaico as fv
import sistema_analise_casa as sc
import testes as qa_testes

PASTA_BASE = os.path.dirname(os.path.abspath(__file__))

# Cache em memoria do ultimo estado/simulacao ativa para exportacao fiel (.txt / .html)
ESTADO_ATIVO_CACHE = {
    "imovel_id": None,
    "apelido": None,
    "resultado": None,
    "comparacao": None,
    "cargas": None,
}


def serializar_rejeitados(rejeitados, limite=12):
    """Converte a lista de tuplas (par, motivos) em objetos JSON estruturados para inspecao tecnica."""
    saida = []
    for item in (rejeitados or [])[:limite]:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            saida.append({"par": str(item[0]), "motivos": list(item[1])})
    return saida


def montar_estado_completo(id_imovel_selecionado=None):
    """Carrega dados persistidos, datasets CSV e calcula o estado completo para a interface web."""
    sc.carregar_dados()
    ds = fv.carregar_datasets_fv()
    ok_ds, msg_ds = fv.validar_datasets_fv()

    imoveis_lista = []
    for iid, im in sc.dados["imoveis"].items():
        loc = im.get("localizacao") or {"cidade": "São Paulo", "uf": "SP"}
        c_mes = sc.consumo_total_imovel(iid)
        c_dia = sc.consumo_diario_imovel(iid)
        pot_w = sc.potencia_instalada_imovel(iid)
        cargas = []
        for aid, a in sc.listar_associacoes_do_imovel(iid).items():
            eq = sc.dados["equipamentos"].get(a.get("equipamento_id"))
            if eq:
                kwh_m = round(sc.calcular_consumo_associacao(a), 2)
                cargas.append({
                    "assoc_id": aid,
                    "equipamento_id": a.get("equipamento_id"),
                    "nome": eq["nome"],
                    "categoria": eq["categoria"],
                    "potencia_w": float(eq["potencia"]),
                    "quantidade": int(a["quantidade"]),
                    "potencia_total_w": float(eq["potencia"]) * int(a["quantidade"]),
                    "tempo_uso_h": float(a["tempo_uso"]),
                    "consumo_mensal_kwh": kwh_m,
                    "consumo_diario_kwh": round(kwh_m / 30.0, 3),
                })
        cargas.sort(key=lambda x: x["consumo_mensal_kwh"], reverse=True)
        imoveis_lista.append({
            "id": iid,
            "apelido": im["apelido"],
            "endereco": im["endereco"],
            "numero": im["numero"],
            "tipo": im["tipo"],
            "cidade": loc["cidade"],
            "uf": loc["uf"],
            "consumo_mensal_kwh": round(c_mes, 2),
            "consumo_diario_kwh": round(c_dia, 3),
            "potencia_instalada_w": round(pot_w, 1),
            "potencia_instalada_kw": round(pot_w / 1000.0, 3),
            "cargas": cargas,
        })

    if not id_imovel_selecionado or id_imovel_selecionado not in sc.dados["imoveis"]:
        id_imovel_selecionado = imoveis_lista[0]["id"]

    imovel_atual = next(i for i in imoveis_lista if i["id"] == id_imovel_selecionado)
    try:
        hsp_info = fv.obter_hsp(imovel_atual["cidade"], imovel_atual["uf"], ds["hsp"])
    except ValueError:
        hsp_info = fv.obter_hsp("São Paulo", "SP", ds["hsp"])

    consumo_ref = imovel_atual["consumo_mensal_kwh"] if imovel_atual["consumo_mensal_kwh"] > 0 else 455.31

    comp = fv.comparar_cenarios(
        consumo_ref,
        100,
        hsp_info,
        ds,
        autonomia_h=12,
        tarifa_kwh=0.92,
        potencia_residencia_w=imovel_atual["potencia_instalada_w"],
        origem="calculado pelos equipamentos cadastrados na residencia",
    )

    if not sc.dados.get("dimensionamentos"):
        sc.salvar_dimensionamento_no_banco(
            id_imovel_selecionado,
            comp["sem_bateria"],
            {"cidade": imovel_atual["cidade"], "uf": imovel_atual["uf"]},
            hsp_info,
        )
        sc.salvar_dimensionamento_no_banco(
            id_imovel_selecionado,
            comp["com_bateria"],
            {"cidade": imovel_atual["cidade"], "uf": imovel_atual["uf"]},
            hsp_info,
        )

    catalogo_equip = [
        {"id": eid, "nome": eq["nome"], "categoria": eq["categoria"], "potencia": float(eq["potencia"])}
        for eid, eq in sc.dados["equipamentos"].items()
    ]
    catalogo_equip.sort(key=lambda x: (x["categoria"], x["nome"]))

    historico = []
    for did, d in sc.dados.get("dimensionamentos", {}).items():
        historico.append(dict(d, id=did))
    historico.sort(key=lambda x: int(x["id"]) if str(x["id"]).isdigit() else 0, reverse=True)

    # Converte o dicionario de localidades HSP para uma lista ordenada para consumo direto no frontend JS
    hsp_lista_ordenada = sorted(
        list(ds["hsp"].values()),
        key=lambda x: (str(x.get("uf", "")), str(x.get("cidade", ""))),
    )

    ESTADO_ATIVO_CACHE["imovel_id"] = id_imovel_selecionado
    ESTADO_ATIVO_CACHE["apelido"] = imovel_atual["apelido"]
    ESTADO_ATIVO_CACHE["resultado"] = comp["sem_bateria"]
    ESTADO_ATIVO_CACHE["comparacao"] = comp
    ESTADO_ATIVO_CACHE["cargas"] = [
        {
            "nome": c["nome"],
            "categoria": c["categoria"],
            "potencia_w": c["potencia_w"],
            "qtd": c["quantidade"],
            "horas_dia": c["tempo_uso_h"],
            "kwh_mes": c["consumo_mensal_kwh"],
        }
        for c in imovel_atual["cargas"]
    ]

    return {
        "ok": True,
        "imovel_selecionado_id": id_imovel_selecionado,
        "imoveis": imoveis_lista,
        "imovel_atual": imovel_atual,
        "catalogo_equipamentos": catalogo_equip,
        "datasets": {
            "modulos": ds["modulos"],
            "inversores": ds["inversores"],
            "baterias": ds["baterias"],
            "hsp_localidades": hsp_lista_ordenada,
            "validacao_ok": ok_ds,
            "validacao_texto": msg_ds,
        },
        "dimensionamento_atual": comp["sem_bateria"],
        "rejeitados_atuais": serializar_rejeitados(comp["sem_bateria"].get("rejeitados", []), limite=20),
        "total_rejeitados": len(comp["sem_bateria"].get("rejeitados", [])),
        "comparacao_atual": comp,
        "proposta_txt": fv.formatar_proposta(comp["sem_bateria"], imovel_atual["apelido"]),
        "comparacao_txt": fv.formatar_comparacao_cenarios(comp, imovel_atual["apelido"]),
        "dimensionamentos_salvos": historico,
    }


HTML_APP = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Lumos PV Studio — Sistema de Engenharia e Orçamento Fotovoltaico (FIAP)</title>
  <style>
    :root {
      --bg-canvas: #e2e8f0;
      --bg-surface: #ffffff;
      --bg-subtle: #f1f5f9;
      --bg-muted: #cbd5e1;
      --bg-command: #0b1120;
      --bg-command-elevated: #1e293b;
      --ink-primary: #0f172a;
      --ink-secondary: #1e293b;
      --ink-muted: #475569;
      --ink-on-dark: #f8fafc;
      --ink-on-dark-muted: #cbd5e1;
      --brand-primary: #0284c7;
      --brand-primary-hover: #0369a1;
      --brand-subtle: #e0f2fe;
      --brand-border: #7dd3fc;
      --status-success-fg: #065f46;
      --status-success-bg: #d1fae5;
      --status-success-border: #6ee7b7;
      --status-warning-fg: #92400e;
      --status-warning-bg: #fef3c7;
      --status-warning-border: #fcd34d;
      --status-danger-fg: #991b1b;
      --status-danger-bg: #fee2e2;
      --status-danger-border: #fca5a5;
      --border-subtle: #cbd5e1;
      --border-strong: #94a3b8;
      --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      --font-mono: 'JetBrains Mono', 'Cascadia Code', 'SFMono-Regular', Consolas, monospace;
      --shadow-sm: 0 1px 3px rgba(15, 23, 42, 0.08), 0 1px 2px rgba(15, 23, 42, 0.05);
      --shadow-md: 0 4px 12px rgba(15, 23, 42, 0.10);
    }

    *, *::before, *::after {
      box-sizing: border-box;
    }

    html {
      scroll-behavior: smooth;
      -webkit-text-size-adjust: 100%;
      text-underline-offset: 3px;
    }

    ::selection {
      background-color: var(--brand-subtle);
      color: var(--ink-primary);
    }

    ::-webkit-scrollbar {
      width: 8px;
      height: 8px;
    }
    ::-webkit-scrollbar-track {
      background: var(--bg-subtle);
    }
    ::-webkit-scrollbar-thumb {
      background: var(--border-strong);
      border-radius: 4px;
    }
    ::-webkit-scrollbar-thumb:hover {
      background: var(--ink-muted);
    }

    body {
      margin: 0;
      font-family: var(--font-sans);
      font-size: 0.875rem;
      line-height: 1.5;
      background-color: var(--bg-canvas);
      color: var(--ink-primary);
      font-variant-numeric: tabular-nums;
      caret-color: var(--brand-primary);
    }

    /* SKIP LINK (WCAG AA) */
    .skip-link {
      position: absolute;
      top: -48px;
      left: 16px;
      background: var(--brand-primary);
      color: #ffffff;
      padding: 8px 14px;
      border-radius: 6px;
      font-weight: 600;
      z-index: 200;
      text-decoration: none;
      transition: top 150ms ease;
    }
    .skip-link:focus {
      top: 12px;
    }

    :focus-visible {
      outline: 2px solid var(--brand-primary);
      outline-offset: 2px;
    }

    @media (prefers-reduced-motion: reduce) {
      html { scroll-behavior: auto; }
      *, *::before, *::after {
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.01ms !important;
      }
    }

    /* TOPBAR COMMAND HEADER */
    .command-header {
      position: sticky;
      top: 0;
      z-index: 100;
      background-color: var(--bg-command);
      color: var(--ink-on-dark);
      border-bottom: 1px solid #1e293b;
      box-shadow: 0 4px 12px rgba(15, 23, 42, 0.14);
    }

    .command-header-inner {
      max-width: 1320px;
      margin: 0 auto;
      padding: 12px 24px;
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
    }

    .brand-cluster {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .brand-mark {
      width: 34px;
      height: 34px;
      border-radius: 7px;
      background-color: var(--bg-command-elevated);
      border: 1px solid #334155;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      color: #38bdf8;
      flex-shrink: 0;
    }

    .brand-titles h1 {
      margin: 0;
      font-size: 1rem;
      font-weight: 700;
      letter-spacing: -0.02em;
      color: var(--ink-on-dark);
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }

    .brand-tag {
      font-family: var(--font-mono);
      font-size: 0.6875rem;
      font-weight: 600;
      padding: 2px 7px;
      border-radius: 4px;
      background-color: #1e293b;
      color: #38bdf8;
      border: 1px solid #334155;
    }

    .brand-titles p {
      margin: 2px 0 0 0;
      font-size: 0.75rem;
      color: var(--ink-on-dark-muted);
    }

    .nav-cluster {
      display: flex;
      align-items: center;
      gap: 6px;
      flex-wrap: wrap;
    }

    .nav-step-btn {
      appearance: none;
      background: transparent;
      color: #cbd5e1;
      border: 1px solid transparent;
      padding: 6px 11px;
      border-radius: 6px;
      font-family: var(--font-sans);
      font-size: 0.78125rem;
      font-weight: 600;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      text-decoration: none;
      touch-action: manipulation;
      transition: background-color 150ms ease, color 150ms ease, border-color 150ms ease;
    }

    .nav-step-btn:hover {
      background-color: var(--bg-command-elevated);
      color: #ffffff;
      border-color: #334155;
    }

    .nav-step-btn.active {
      background-color: var(--brand-primary);
      color: #ffffff;
      border-color: var(--brand-primary);
    }

    .nav-num {
      font-family: var(--font-mono);
      font-size: 0.6875rem;
      opacity: 0.85;
    }

    /* MAIN CONTAINER */
    .workspace-container {
      max-width: 1320px;
      margin: 20px auto 64px auto;
      padding: 0 24px;
    }

    /* CONTEXT & TELEMETRY CONTROL BAR */
    .context-bar {
      background-color: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 8px;
      padding: 14px 18px;
      margin-bottom: 16px;
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: center;
      gap: 14px;
      box-shadow: var(--shadow-sm);
    }

    .context-selector-group {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
      flex: 1 1 auto;
    }

    .context-label {
      font-size: 0.75rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: var(--ink-muted);
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }

    .context-select {
      height: 36px;
      padding: 0 12px;
      border-radius: 6px;
      border: 1px solid var(--border-strong);
      font-family: var(--font-sans);
      font-size: 0.84375rem;
      font-weight: 600;
      color: var(--ink-primary);
      background-color: var(--bg-canvas);
      min-width: 310px;
      cursor: pointer;
      transition: border-color 150ms ease, background-color 150ms ease;
    }

    .context-select:hover {
      border-color: var(--ink-muted);
    }

    .context-actions {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }

    .view-mode-switch {
      display: inline-flex;
      background-color: var(--bg-subtle);
      border: 1px solid var(--border-subtle);
      border-radius: 6px;
      padding: 2px;
    }

    .view-mode-btn {
      appearance: none;
      border: none;
      background: transparent;
      color: var(--ink-muted);
      font-family: var(--font-sans);
      font-size: 0.75rem;
      font-weight: 600;
      padding: 5px 10px;
      border-radius: 4px;
      cursor: pointer;
      transition: background-color 150ms ease, color 150ms ease, box-shadow 150ms ease;
    }

    .view-mode-btn.active {
      background-color: var(--bg-surface);
      color: var(--ink-primary);
      box-shadow: var(--shadow-sm);
    }

    /* TELEMETRY KPI STRIP */
    .telemetry-grid {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 14px;
      margin-bottom: 22px;
    }

    @media (max-width: 1024px) {
      .telemetry-grid {
        grid-template-columns: repeat(2, 1fr);
      }
    }
    @media (max-width: 640px) {
      .telemetry-grid {
        grid-template-columns: 1fr;
      }
      .context-select {
        min-width: 100%;
      }
    }

    .telemetry-card {
      background-color: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 8px;
      padding: 16px 18px;
      box-shadow: var(--shadow-sm);
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }

    .telemetry-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 8px;
      margin-bottom: 6px;
    }

    .telemetry-title {
      font-size: 0.75rem;
      font-weight: 600;
      color: var(--ink-muted);
      text-transform: uppercase;
      letter-spacing: 0.03em;
    }

    .telemetry-value {
      font-size: 1.4375rem;
      font-weight: 700;
      letter-spacing: -0.02em;
      color: var(--ink-primary);
      line-height: 1.2;
      margin: 2px 0 6px 0;
    }

    .telemetry-meta {
      font-size: 0.75rem;
      color: var(--ink-muted);
      line-height: 1.35;
    }

    /* MODULE SECTIONS */
    .module-section {
      background-color: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 8px;
      padding: 24px;
      margin-bottom: 22px;
      box-shadow: var(--shadow-sm);
      scroll-margin-top: 76px;
    }

    .module-section.hidden-module {
      display: none;
    }

    .module-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      flex-wrap: wrap;
      gap: 14px;
      padding-bottom: 16px;
      margin-bottom: 20px;
      border-bottom: 1px solid var(--border-subtle);
    }

    .module-title-cluster {
      display: flex;
      align-items: flex-start;
      gap: 12px;
    }

    .module-index {
      font-family: var(--font-mono);
      font-size: 0.75rem;
      font-weight: 700;
      color: var(--brand-primary);
      background-color: var(--brand-subtle);
      border: 1px solid var(--brand-border);
      padding: 4px 8px;
      border-radius: 5px;
      line-height: 1;
      margin-top: 2px;
      flex-shrink: 0;
    }

    .module-header h2 {
      margin: 0;
      font-size: 1.0625rem;
      font-weight: 700;
      letter-spacing: -0.015em;
      color: var(--ink-primary);
    }

    .module-header p {
      margin: 4px 0 0 0;
      font-size: 0.8125rem;
      color: var(--ink-muted);
    }

    .module-actions {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }

    /* BUTTONS */
    .btn {
      appearance: none;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      height: 36px;
      padding: 0 14px;
      border-radius: 6px;
      border: 1px solid transparent;
      font-family: var(--font-sans);
      font-size: 0.8125rem;
      font-weight: 600;
      cursor: pointer;
      text-decoration: none;
      white-space: nowrap;
      touch-action: manipulation;
      transition: background-color 150ms ease, border-color 150ms ease, color 150ms ease, box-shadow 150ms ease;
    }

    .btn:disabled {
      opacity: 0.55;
      cursor: not-allowed;
    }

    .btn-sm {
      height: 28px;
      padding: 0 10px;
      font-size: 0.75rem;
      border-radius: 5px;
    }

    .btn-primary {
      background-color: var(--brand-primary);
      color: #ffffff;
      border-color: var(--brand-primary);
    }
    .btn-primary:hover:not(:disabled) {
      background-color: var(--brand-primary-hover);
      border-color: var(--brand-primary-hover);
    }

    .btn-secondary {
      background-color: var(--bg-surface);
      color: var(--ink-primary);
      border-color: var(--border-strong);
    }
    .btn-secondary:hover:not(:disabled) {
      background-color: var(--bg-subtle);
      border-color: var(--ink-muted);
    }

    .btn-subtle {
      background-color: var(--bg-subtle);
      color: var(--ink-secondary);
      border-color: var(--border-subtle);
    }
    .btn-subtle:hover:not(:disabled) {
      background-color: var(--bg-muted);
      color: var(--ink-primary);
    }

    .btn-danger-ghost {
      background-color: transparent;
      color: var(--status-danger-fg);
      border-color: var(--status-danger-border);
    }
    .btn-danger-ghost:hover:not(:disabled) {
      background-color: var(--status-danger-bg);
    }

    /* BADGES & PILLS */
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      padding: 2px 8px;
      border-radius: 5px;
      font-size: 0.71875rem;
      font-weight: 600;
      line-height: 1.4;
      border: 1px solid transparent;
      white-space: nowrap;
    }

    .badge-mono {
      font-family: var(--font-mono);
      font-size: 0.71875rem;
    }

    .badge-success {
      background-color: var(--status-success-bg);
      color: var(--status-success-fg);
      border-color: var(--status-success-border);
    }

    .badge-warning {
      background-color: var(--status-warning-bg);
      color: var(--status-warning-fg);
      border-color: var(--status-warning-border);
    }

    .badge-danger {
      background-color: var(--status-danger-bg);
      color: var(--status-danger-fg);
      border-color: var(--status-danger-border);
    }

    .badge-info {
      background-color: var(--brand-subtle);
      color: #075985;
      border-color: var(--brand-border);
    }

    .badge-neutral {
      background-color: var(--bg-subtle);
      color: var(--ink-secondary);
      border-color: var(--border-subtle);
    }

    /* ENGINEERING WORKBENCH CONSOLE (STEP 2) */
    .sim-console {
      background-color: var(--bg-subtle);
      border: 1px solid var(--border-strong);
      border-radius: 8px;
      overflow: hidden;
      margin-bottom: 24px;
      box-shadow: var(--shadow-sm);
    }

    .sim-console-bar {
      background-color: #1e293b;
      color: #f8fafc;
      padding: 10px 18px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 10px;
      font-size: 0.78125rem;
      font-weight: 600;
    }

    .sim-console-body {
      padding: 18px;
    }

    .workbench-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 16px;
    }

    @media (max-width: 1080px) {
      .workbench-grid {
        grid-template-columns: 1fr;
      }
    }

    .param-group {
      background-color: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 8px;
      padding: 16px;
      margin: 0;
      box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }

    .param-group-title {
      font-size: 0.78125rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: var(--ink-primary);
      margin: 0 0 14px 0;
      padding-bottom: 10px;
      border-bottom: 2px solid var(--bg-subtle);
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .form-grid-2 {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }

    .form-grid-auto {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
      gap: 12px;
    }

    .field {
      margin-bottom: 12px;
    }
    .field:last-child {
      margin-bottom: 0;
    }

    .field-label-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 6px;
      margin-bottom: 5px;
    }

    .field label {
      display: block;
      font-size: 0.75rem;
      font-weight: 600;
      color: var(--ink-secondary);
    }

    .field-hint {
      font-size: 0.6875rem;
      color: var(--ink-muted);
    }

    .field input,
    .field select {
      width: 100%;
      height: 36px;
      padding: 0 10px;
      border-radius: 6px;
      border: 1px solid var(--border-strong);
      font-family: var(--font-sans);
      font-size: 0.8125rem;
      background-color: var(--bg-surface);
      color: var(--ink-primary);
      font-variant-numeric: tabular-nums;
      transition: border-color 150ms ease, background-color 150ms ease;
    }

    .field input:hover:not(:disabled):not([readonly]),
    .field select:hover:not(:disabled) {
      border-color: var(--ink-primary);
    }

    .field input[readonly],
    .field input:disabled,
    .field select:disabled {
      background-color: var(--bg-subtle);
      color: var(--ink-muted);
      border-color: var(--border-subtle);
      cursor: not-allowed;
    }

    @media (max-width: 640px) {
      .field input,
      .field select,
      .context-select {
        font-size: 1rem;
        height: 42px;
      }
      .btn {
        min-height: 40px;
      }
      .form-grid-2 {
        grid-template-columns: 1fr;
      }
    }

    /* COLLAPSIBLE DRAWERS */
    .drawer-panel {
      display: none;
      background-color: var(--bg-subtle);
      border: 1px solid var(--border-strong);
      border-radius: 8px;
      padding: 18px;
      margin-bottom: 18px;
    }

    .drawer-panel.open {
      display: block;
    }

    .drawer-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 14px;
      padding-bottom: 10px;
      border-bottom: 1px solid var(--border-subtle);
    }

    .drawer-header h3 {
      margin: 0;
      font-size: 0.875rem;
      font-weight: 700;
      color: var(--ink-primary);
    }

    /* DATA TABLES */
    .table-scroll {
      width: 100%;
      overflow-x: auto;
      border: 1px solid var(--border-subtle);
      border-radius: 8px;
      background-color: var(--bg-surface);
    }

    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.8125rem;
      font-variant-numeric: tabular-nums;
    }

    th, td {
      padding: 11px 14px;
      border-bottom: 1px solid var(--border-subtle);
      text-align: left;
      vertical-align: middle;
    }

    tbody tr:last-child td {
      border-bottom: none;
    }

    thead th {
      background-color: #f1f5f9;
      font-weight: 700;
      color: var(--ink-primary);
      font-size: 0.71875rem;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      white-space: nowrap;
      border-bottom: 2px solid var(--border-subtle);
    }

    tbody tr:nth-child(even) td {
      background-color: #f8fafc;
    }

    tbody tr:hover td {
      background-color: #f0f9ff;
    }

    tr.row-section-divider td {
      background-color: #e2e8f0 !important;
      color: var(--ink-primary);
      font-size: 0.71875rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      padding: 7px 14px;
      border-top: 1px solid var(--border-strong);
      border-bottom: 1px solid var(--border-strong);
    }

    tr.row-highlight td {
      background-color: #e0f2fe !important;
      border-top: 2px solid var(--brand-border);
    }

    tr.row-total td {
      background-color: #e2e8f0 !important;
      font-weight: 700;
      border-top: 2px solid var(--border-strong);
    }

    /* KEY-VALUE SPECIFICATION TABLE (LEFT PANEL OF STEP 2) */
    .kv-table th {
      background-color: #f1f5f9;
      width: 34%;
      font-weight: 700;
      color: var(--ink-secondary);
      font-size: 0.75rem;
      text-transform: none;
      letter-spacing: 0;
      border-right: 1px solid var(--border-subtle);
      white-space: normal;
    }

    .kv-table tbody tr:nth-child(even) td {
      background-color: #ffffff;
    }

    .num-col {
      text-align: right;
      white-space: nowrap;
    }

    .center-col {
      text-align: center;
      white-space: nowrap;
    }

    /* SOLID SHARE BAR */
    .share-cell {
      display: flex;
      align-items: center;
      gap: 8px;
      min-width: 120px;
    }
    .share-track {
      flex: 1;
      background-color: var(--bg-muted);
      height: 6px;
      border-radius: 3px;
      overflow: hidden;
    }
    .share-fill {
      background-color: var(--brand-primary);
      height: 100%;
      border-radius: 3px;
    }
    .share-pct {
      font-family: var(--font-mono);
      font-size: 0.71875rem;
      color: var(--ink-secondary);
      width: 42px;
      text-align: right;
    }

    /* FRAMED RESULT CARDS (STEP 2 OUTPUT DOSSIER) */
    .split-2 {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 20px;
      align-items: stretch;
    }

    @media (max-width: 1024px) {
      .split-2 {
        grid-template-columns: 1fr;
      }
    }

    .result-card {
      background-color: var(--bg-surface);
      border: 1px solid var(--border-strong);
      border-radius: 8px;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      box-shadow: var(--shadow-sm);
    }

    .result-card-head {
      background-color: #1e293b;
      color: #f8fafc;
      padding: 12px 16px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 10px;
    }

    .result-card-head h3 {
      margin: 0;
      font-size: 0.875rem;
      font-weight: 700;
      color: #ffffff;
      letter-spacing: -0.01em;
    }

    .result-card-body {
      flex: 1;
    }

    .result-card-foot {
      background-color: var(--bg-subtle);
      border-top: 1px solid var(--border-subtle);
      padding: 14px 16px;
    }

    .panel-subtitle {
      margin: 0 0 10px 0;
      font-size: 0.875rem;
      font-weight: 700;
      color: var(--ink-primary);
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    /* CALLOUTS & DIAGNOSTIC BOXES (NO 4PX LEFT BORDER) */
    .notice-box {
      padding: 14px 16px;
      border-radius: 8px;
      margin-top: 14px;
      font-size: 0.8125rem;
      border: 1px solid var(--border-strong);
      background-color: var(--bg-subtle);
      color: var(--ink-primary);
    }

    .notice-error {
      border-color: var(--status-danger-border);
      background-color: var(--status-danger-bg);
      color: var(--status-danger-fg);
    }

    .notice-success {
      border-color: var(--status-success-border);
      background-color: var(--status-success-bg);
      color: var(--status-success-fg);
    }

    .notice-info {
      border-color: var(--brand-border);
      background-color: #e0f2fe;
      color: #0c4a6e;
    }

    .prose-block {
      max-width: 72ch;
      line-height: 1.6;
    }

    /* SUB-NAVIGATION TABS (MODULE 4) */
    .sub-nav {
      display: flex;
      gap: 6px;
      margin-bottom: 16px;
      flex-wrap: wrap;
      border-bottom: 1px solid var(--border-subtle);
      padding-bottom: 12px;
    }

    .sub-nav-btn {
      appearance: none;
      padding: 7px 13px;
      border-radius: 6px;
      border: 1px solid var(--border-subtle);
      background-color: var(--bg-canvas);
      color: var(--ink-secondary);
      font-family: var(--font-sans);
      font-size: 0.78125rem;
      font-weight: 600;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: background-color 150ms ease, color 150ms ease, border-color 150ms ease;
    }

    .sub-nav-btn:hover {
      background-color: var(--bg-subtle);
      color: var(--ink-primary);
    }

    .sub-nav-btn.active {
      background-color: var(--ink-primary);
      color: #ffffff;
      border-color: var(--ink-primary);
    }

    .sub-pane {
      display: none;
    }
    .sub-pane.active {
      display: block;
    }

    /* 15-STEP SPRINT REVIEW GRID */
    .review-steps-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
      gap: 12px;
    }

    .review-step-card {
      background-color: var(--bg-canvas);
      border: 1px solid var(--border-subtle);
      border-radius: 8px;
      padding: 14px 16px;
    }

    .review-step-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 8px;
      margin-bottom: 6px;
    }

    .review-step-card p {
      margin: 0;
      font-size: 0.78125rem;
      color: var(--ink-secondary);
      line-height: 1.45;
    }

    .code-terminal {
      background-color: var(--bg-command);
      color: var(--ink-on-dark);
      font-family: var(--font-mono);
      padding: 18px;
      border-radius: 8px;
      border: 1px solid #1e293b;
      overflow-x: auto;
      font-size: 0.78125rem;
      line-height: 1.5;
      margin: 0;
    }

    code {
      font-family: var(--font-mono);
      font-size: 0.75rem;
      background-color: var(--bg-subtle);
      padding: 2px 5px;
      border-radius: 4px;
      color: var(--ink-primary);
    }

    @media print {
      .command-header, .no-print {
        display: none !important;
      }
      body {
        background: #ffffff;
      }
      .module-section, .module-section.hidden-module {
        display: block !important;
        box-shadow: none;
        border: 1px solid #cbd5e1;
        page-break-inside: avoid;
      }
    }
  </style>
</head>
<body>
  <a href="#main-workspace" class="skip-link">Pular para o conteúdo principal</a>

  <!-- CABEÇALHO EXECUTIVO DE COMANDO -->
  <header class="command-header">
    <div class="command-header-inner">
      <div class="brand-cluster">
        <div class="brand-mark" aria-hidden="true">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="2" y="4" width="20" height="16" rx="2"></rect>
            <line x1="2" y1="10" x2="22" y2="10"></line>
            <line x1="2" y1="15" x2="22" y2="15"></line>
            <line x1="9" y1="4" x2="9" y2="20"></line>
            <line x1="15" y1="4" x2="15" y2="20"></line>
          </svg>
        </div>
        <div class="brand-titles">
          <h1>
            Sistema de Dimensionamento e Orçamento Fotovoltaico
            <span class="brand-tag">SERS Sprint 3 Final</span>
          </h1>
          <p>Equipe Lumos (FIAP): Pietro Lorande (RM 569125) · Luiz Otávio (RM 569977) · Maria Eduarda (RM 574094)</p>
        </div>
      </div>

      <nav class="nav-cluster no-print" aria-label="Etapas do sistema">
        <button type="button" class="nav-step-btn active" id="nav-btn-1" onclick="selecionarModuloAtivo('passo-1')">
          <span class="nav-num">01</span> Residência e Consumo
        </button>
        <button type="button" class="nav-step-btn" id="nav-btn-2" onclick="selecionarModuloAtivo('passo-2')">
          <span class="nav-num">02</span> Dimensionamento e Orçamento
        </button>
        <button type="button" class="nav-step-btn" id="nav-btn-3" onclick="selecionarModuloAtivo('passo-3')">
          <span class="nav-num">03</span> On-Grid vs. Híbrido
        </button>
        <button type="button" class="nav-step-btn" id="nav-btn-4" onclick="selecionarModuloAtivo('passo-4')">
          <span class="nav-num">04</span> Catálogos, Roteiro e QA
        </button>
        <button type="button" class="nav-step-btn" id="nav-btn-all" onclick="selecionarModuloAtivo('all')" title="Exibir as 4 etapas simultaneamente na mesma página">
          Visão Completa
        </button>
      </nav>
    </div>
  </header>

  <main id="main-workspace" class="workspace-container">

    <!-- BARRA DE CONTEXTO DA RESIDÊNCIA E EXPORTAÇÃO -->
    <div class="context-bar">
      <div class="context-selector-group">
        <label for="top-imovel-select" class="context-label">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path>
            <polyline points="9 22 9 12 15 12 15 22"></polyline>
          </svg>
          Unidade Consumidora:
        </label>
        <select id="top-imovel-select" class="context-select" onchange="trocarImovelAtivo(this.value)"></select>
        <span id="badge-topologia-ativa" class="badge badge-info">Sistema On-Grid</span>
      </div>

      <div class="context-actions no-print">
        <button type="button" class="btn btn-secondary" onclick="window.print()">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <polyline points="6 9 6 2 18 2 18 9"></polyline>
            <path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"></path>
            <rect x="6" y="14" width="12" height="8"></rect>
          </svg>
          Imprimir / PDF
        </button>
        <a class="btn btn-secondary" href="/proposta_cliente.html" target="_blank" rel="noopener">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
            <polyline points="14 2 14 8 20 8"></polyline>
          </svg>
          Relatório Web (.html)
        </a>
        <a class="btn btn-secondary" href="/proposta_cliente.txt" download="proposta_cliente.txt">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
            <polyline points="7 10 12 15 17 10"></polyline>
            <line x1="12" y1="15" x2="12" y2="3"></line>
          </svg>
          Baixar Laudo (.txt)
        </a>
      </div>
    </div>

    <!-- 4 INDICADORES DE TELEMETRIA EXECUTIVA (SINCRONIZADOS EM TEMPO REAL) -->
    <section class="telemetry-grid" aria-label="Indicadores principais do projeto">
      <div class="telemetry-card">
        <div>
          <div class="telemetry-header">
            <span class="telemetry-title">Demanda da Residência</span>
            <span class="badge badge-neutral">Consumo Ativo</span>
          </div>
          <div class="telemetry-value" id="kpi-consumo">--</div>
        </div>
        <div class="telemetry-meta" id="kpi-demanda-sub">--</div>
      </div>

      <div class="telemetry-card">
        <div>
          <div class="telemetry-header">
            <span class="telemetry-title">Potência Solar Instalada</span>
            <span class="badge badge-info" id="kpi-fv-badge">Kit Fotovoltaico</span>
          </div>
          <div class="telemetry-value" id="kpi-potencia-fv">--</div>
        </div>
        <div class="telemetry-meta" id="kpi-fv-sub">--</div>
      </div>

      <div class="telemetry-card">
        <div>
          <div class="telemetry-header">
            <span class="telemetry-title">Geração Mensal Estimada</span>
            <span class="badge badge-success" id="kpi-atendimento-badge">Balanço Energético</span>
          </div>
          <div class="telemetry-value" id="kpi-geracao">--</div>
        </div>
        <div class="telemetry-meta" id="kpi-geracao-sub">--</div>
      </div>

      <div class="telemetry-card">
        <div>
          <div class="telemetry-header">
            <span class="telemetry-title">Investimento e Retorno</span>
            <span class="badge badge-warning" id="kpi-payback-badge">Orçamento Completo</span>
          </div>
          <div class="telemetry-value" id="kpi-orcamento">--</div>
        </div>
        <div class="telemetry-meta" id="kpi-payback-sub">--</div>
      </div>
    </section>

    <!-- =====================================================================
         MÓDULO 01: RESIDÊNCIA E DEMANDA ENERGÉTICA (PB01 E PB02)
         ===================================================================== -->
    <section id="passo-1" class="module-section">
      <div class="module-header">
        <div class="module-title-cluster">
          <span class="module-index">01</span>
          <div>
            <h2>Equipamentos e Demanda Energética da Residência</h2>
            <p>Inventário de cargas da unidade selecionada (<span id="lbl-endereco-res"></span>)</p>
          </div>
        </div>
        <div class="module-actions no-print">
          <button type="button" class="btn btn-primary" onclick="togglePainel('painel-add-equip')">
            Adicionar Equipamento
          </button>
          <button type="button" class="btn btn-secondary" onclick="togglePainel('painel-nova-casa')">
            Nova Residência
          </button>
          <button type="button" class="btn btn-subtle" onclick="restaurarCargasPadrao()" title="Restaura os 8 equipamentos originais de demonstração">
            Restaurar Padrão
          </button>
        </div>
      </div>

      <!-- Painel recolhível: Adicionar Equipamento -->
      <div id="painel-add-equip" class="drawer-panel no-print">
        <div class="drawer-header">
          <h3>Associar Equipamento Elétrico à Residência Ativa</h3>
          <button type="button" class="btn btn-sm btn-subtle" onclick="togglePainel('painel-add-equip')">Fechar</button>
        </div>
        <div class="form-grid-auto" style="margin-bottom: 14px;">
          <div class="field">
            <label for="assoc-eq-select">Modelo do Catálogo Base</label>
            <select id="assoc-eq-select" onchange="preencherEquipamentoCatalogo()"></select>
          </div>
          <div class="field">
            <label for="assoc-eq-nome">Descrição do Equipamento</label>
            <input type="text" id="assoc-eq-nome" placeholder="Ex.: Ar-Condicionado Split">
          </div>
          <div class="field">
            <label for="assoc-eq-cat">Ambiente / Categoria</label>
            <input type="text" id="assoc-eq-cat" placeholder="Ex.: Quarto">
          </div>
          <div class="field">
            <label for="assoc-eq-pot">Potência Unitária (W)</label>
            <input type="number" id="assoc-eq-pot" value="1200" min="1" step="10" inputmode="decimal">
          </div>
          <div class="field">
            <label for="assoc-eq-qtd">Quantidade (un.)</label>
            <input type="number" id="assoc-eq-qtd" value="1" min="1" step="1" inputmode="numeric">
          </div>
          <div class="field">
            <label for="assoc-eq-horas">Uso Diário (horas/dia, 0.1 a 24)</label>
            <input type="number" id="assoc-eq-horas" value="4" min="0.1" max="24" step="0.05" inputmode="decimal">
          </div>
        </div>
        <div style="display:flex; gap:8px; align-items:center;">
          <button type="button" class="btn btn-primary" onclick="adicionarCargaResidencia()">
            Salvar Equipamento e Recalcular Demanda
          </button>
          <span class="field-hint">Fórmula aplicada: E_mês = (Potência × Qtd × Horas/dia × 30) ÷ 1000</span>
        </div>
      </div>

      <!-- Painel recolhível: Editar Equipamento Existente -->
      <div id="painel-edit-equip" class="drawer-panel no-print">
        <div class="drawer-header">
          <h3 id="lbl-edit-equip-titulo">Editar Carga Associada</h3>
          <button type="button" class="btn btn-sm btn-subtle" onclick="fecharEdicaoCarga()">Cancelar</button>
        </div>
        <input type="hidden" id="edit-assoc-id">
        <div class="form-grid-auto" style="margin-bottom: 14px;">
          <div class="field">
            <label for="edit-eq-qtd">Nova Quantidade (un.)</label>
            <input type="number" id="edit-eq-qtd" min="1" step="1" inputmode="numeric">
          </div>
          <div class="field">
            <label for="edit-eq-horas">Novo Tempo de Uso Diário (horas/dia, 0.1 a 24)</label>
            <input type="number" id="edit-eq-horas" min="0.05" max="24" step="0.05" inputmode="decimal">
          </div>
        </div>
        <button type="button" class="btn btn-primary" onclick="salvarEdicaoCarga()">
          Atualizar Carga e Recalcular Sistema
        </button>
      </div>

      <!-- Painel recolhível: Cadastrar Nova Residência -->
      <div id="painel-nova-casa" class="drawer-panel no-print">
        <div class="drawer-header">
          <h3>Cadastrar Nova Unidade Consumidora</h3>
          <button type="button" class="btn btn-sm btn-subtle" onclick="togglePainel('painel-nova-casa')">Fechar</button>
        </div>
        <div class="form-grid-auto" style="margin-bottom: 14px;">
          <div class="field">
            <label for="nova-res-apelido">Identificação / Apelido</label>
            <input type="text" id="nova-res-apelido" placeholder="Ex.: Residência Família Costa">
          </div>
          <div class="field">
            <label for="nova-res-end">Logradouro / Endereço</label>
            <input type="text" id="nova-res-end" placeholder="Ex.: Rua dos Pinheiros">
          </div>
          <div class="field">
            <label for="nova-res-num">Número</label>
            <input type="text" id="nova-res-num" placeholder="450">
          </div>
          <div class="field">
            <label for="nova-res-cidade">Município</label>
            <input type="text" id="nova-res-cidade" value="São Paulo">
          </div>
          <div class="field">
            <label for="nova-res-uf">UF</label>
            <input type="text" id="nova-res-uf" value="SP" maxlength="2">
          </div>
          <div class="field">
            <label for="nova-res-tipo">Tipologia</label>
            <select id="nova-res-tipo">
              <option value="Casa">Casa Residencial</option>
              <option value="Apartamento">Apartamento</option>
            </select>
          </div>
        </div>
        <div style="display:flex; gap:14px; align-items:center; flex-wrap:wrap;">
          <button type="button" class="btn btn-primary" onclick="criarNovaResidencia()">Criar Unidade Consumidora</button>
          <label style="display:inline-flex; align-items:center; gap:6px; font-size:0.8125rem; cursor:pointer;">
            <input type="checkbox" id="nova-res-popular-padrao" checked>
            Incluir inventário inicial de eletrodomésticos padrão
          </label>
        </div>
      </div>

      <!-- Tabela de Equipamentos da Casa -->
      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th style="width:48px;">#</th>
              <th>Equipamento Elétrico</th>
              <th>Ambiente</th>
              <th class="num-col">Potência Unit.</th>
              <th class="center-col">Qtd.</th>
              <th class="num-col">Potência Total</th>
              <th class="num-col">Uso Diário</th>
              <th class="num-col">Consumo Diário</th>
              <th class="num-col">Consumo Mensal</th>
              <th style="width:165px;">Participação</th>
              <th class="no-print" style="text-align:right;">Ações</th>
            </tr>
          </thead>
          <tbody id="tabela-cargas-body"></tbody>
        </table>
      </div>

      <div class="no-print" style="display:flex; justify-content:space-between; align-items:center; margin-top:18px; padding-top:14px; border-top:1px solid var(--border-subtle);">
        <span style="font-size:0.78125rem; color:var(--ink-muted);">Demanda sincronizada automaticamente com o simulador fotovoltaico.</span>
        <button type="button" class="btn btn-primary" onclick="selecionarModuloAtivo('passo-2')">
          Avançar para Etapa 02: Dimensionamento e Orçamento &rarr;
        </button>
      </div>
    </section>

    <!-- =====================================================================
         MÓDULO 02: ENGENHARIA DE DIMENSIONAMENTO SOLAR, BATERIAS E ORÇAMENTO
         ===================================================================== -->
    <section id="passo-2" class="module-section hidden-module">
      <div class="module-header">
        <div class="module-title-cluster">
          <span class="module-index">02</span>
          <div>
            <h2>Dimensionamento Fotovoltaico e Orçamento do Sistema</h2>
            <p>Ajuste os parâmetros na bancada abaixo e consulte o memorial técnico e o orçamento lado a lado</p>
          </div>
        </div>
        <div class="module-actions no-print">
          <button type="button" class="btn btn-subtle" onclick="aplicarPresetRapido(false)">Preset: Sem Baterias (On-Grid)</button>
          <button type="button" class="btn btn-subtle" onclick="aplicarPresetRapido(true)">Preset: Com Baterias (12h)</button>
          <button type="button" class="btn btn-secondary" onclick="testarValidacaoErroPB18()" title="Demonstra o bloqueio automático quando um inversor incompatível é forçado">
            Simular Bloqueio Elétrico (PB18)
          </button>
        </div>
      </div>

      <!-- Bancada de Parâmetros Estruturada (Fundo contrastante + Cabeçalho escuro) -->
      <div class="sim-console no-print">
        <div class="sim-console-bar">
          <span>PAINEL DE PARÂMETROS DO SIMULADOR</span>
          <span style="color:#94a3b8; font-weight:500;">Seleção validada automaticamente pelas regras elétricas C1 a C8</span>
        </div>
        <div class="sim-console-body">
          <div class="workbench-grid">
            <!-- GRUPO A: DEMANDA E RECURSO SOLAR -->
            <div class="param-group">
              <div>
                <div class="param-group-title">
                  <span>1. Consumo e Localização</span>
                  <span class="badge badge-neutral">Demanda &amp; Sol</span>
                </div>
                <div class="field">
                  <div class="field-label-row">
                    <label for="dim-origem-consumo">Fonte do Consumo</label>
                  </div>
                  <select id="dim-origem-consumo" onchange="alternarOrigemConsumo()">
                    <option value="calculado">Equipamentos da Residência (Etapa 01)</option>
                    <option value="conta">Informar Valor da Conta Manualmente</option>
                  </select>
                </div>
                <div class="form-grid-2">
                  <div class="field">
                    <div class="field-label-row">
                      <label for="dim-consumo">Consumo Mensal (kWh)</label>
                      <span class="field-hint" id="lbl-status-consumo">Automático</span>
                    </div>
                    <input type="number" id="dim-consumo" step="10" min="1" readonly inputmode="decimal">
                  </div>
                  <div class="field">
                    <div class="field-label-row">
                      <label for="dim-percentual">Meta de Cobertura (%)</label>
                    </div>
                    <input type="number" id="dim-percentual" value="100" min="1" max="100" step="5" inputmode="numeric">
                  </div>
                </div>
                <div class="field">
                  <div class="field-label-row">
                    <label for="dim-localidade">Cidade / Estado (Base Solar CRESESB)</label>
                  </div>
                  <select id="dim-localidade" onchange="atualizarHspDaTabela()"></select>
                </div>
              </div>
              <div class="form-grid-2">
                <div class="field">
                  <div class="field-label-row">
                    <label for="dim-hsp">Sol Pleno — HSP (h/dia)</label>
                    <span class="field-hint">3,0 a 7,0</span>
                  </div>
                  <input type="number" id="dim-hsp" step="0.1" min="3.0" max="7.0" inputmode="decimal">
                </div>
                <div class="field">
                  <div class="field-label-row">
                    <label for="dim-pr">Rendimento Global (PR)</label>
                    <span class="field-hint">Padrão: 0,78</span>
                  </div>
                  <input type="number" id="dim-pr" value="0.78" step="0.01" min="0.50" max="0.95" inputmode="decimal">
                </div>
              </div>
            </div>

            <!-- GRUPO B: TOPOLOGIA, ARMAZENAMENTO E TARIFA -->
            <div class="param-group">
              <div>
                <div class="param-group-title">
                  <span>2. Modalidade e Tarifa</span>
                  <span class="badge badge-neutral">Rede &amp; Backup</span>
                </div>
                <div class="field">
                  <div class="field-label-row">
                    <label for="dim-com-bateria">Tipo de Sistema</label>
                  </div>
                  <select id="dim-com-bateria" onchange="alternarCamposBateria()">
                    <option value="false">Sem Baterias (On-Grid Convencional)</option>
                    <option value="true">Com Baterias (Híbrido com Backup LiFePO4)</option>
                  </select>
                </div>
                <div class="field" id="box-dim-autonomia">
                  <div class="field-label-row">
                    <label for="dim-autonomia">Autonomia de Baterias (horas)</label>
                    <span class="field-hint" id="lbl-status-autonomia">Desativado no On-Grid</span>
                  </div>
                  <input type="number" id="dim-autonomia" value="12" min="1" max="72" step="1" disabled inputmode="numeric">
                </div>
                <div class="field">
                  <div class="field-label-row">
                    <label for="dim-tarifa">Tarifa de Energia (R$/kWh)</label>
                    <span class="field-hint">Com impostos</span>
                  </div>
                  <input type="number" id="dim-tarifa" value="0.92" min="0.10" max="10.0" step="0.02" inputmode="decimal">
                </div>
              </div>
              <div style="margin-top: 12px; padding: 10px 12px; background-color: var(--bg-subtle); border-radius: 6px; border: 1px solid var(--border-subtle); font-size: 0.75rem; color: var(--ink-muted);">
                No modo <strong>Sem Baterias</strong>, a rede elétrica da concessionária absorve os créditos sem custo adicional de baterias.
              </div>
            </div>

            <!-- GRUPO C: SELEÇÃO DE HARDWARE NOS DATASETS CSV -->
            <div class="param-group">
              <div>
                <div class="param-group-title">
                  <span>3. Seleção de Equipamentos</span>
                  <span class="badge badge-neutral">Catálogo CSV</span>
                </div>
                <div class="field">
                  <div class="field-label-row">
                    <label for="dim-modulo">Módulo Fotovoltaico</label>
                  </div>
                  <select id="dim-modulo"></select>
                </div>
                <div class="field">
                  <div class="field-label-row">
                    <label for="dim-inversor">Inversor Solar</label>
                  </div>
                  <select id="dim-inversor"></select>
                </div>
                <div class="field" id="box-dim-bateria">
                  <div class="field-label-row">
                    <label for="dim-bateria">Banco de Baterias LiFePO4</label>
                  </div>
                  <select id="dim-bateria" disabled></select>
                </div>
              </div>
              <div style="margin-top: 12px;">
                <button type="button" class="btn btn-primary" style="width: 100%; height: 40px; font-size: 0.84375rem;" onclick="executarDimensionamentoAPI()">
                  Calcular Dimensionamento e Atualizar Orçamento
                </button>
              </div>
            </div>
          </div>

          <div id="dim-feedback" aria-live="polite"></div>
        </div>
      </div>

      <!-- Resultado Técnico + Orçamento + Economia/Payback -->
      <div id="painel-resultado-dimensionamento" style="margin-top: 18px;"></div>

      <div class="no-print" style="display:flex; justify-content:space-between; align-items:center; margin-top:20px; padding-top:14px; border-top:1px solid var(--border-subtle);">
        <button type="button" class="btn btn-secondary" onclick="selecionarModuloAtivo('passo-1')">
          &larr; Voltar para Etapa 01: Residência
        </button>
        <button type="button" class="btn btn-primary" onclick="selecionarModuloAtivo('passo-3')">
          Avançar para Etapa 03: Comparativo On-Grid vs. Híbrido &rarr;
        </button>
      </div>
    </section>

    <!-- =====================================================================
         MÓDULO 03: ESTUDO COMPARATIVO (SEM BATERIAS vs COM BATERIAS)
         ===================================================================== -->
    <section id="passo-3" class="module-section hidden-module">
      <div class="module-header">
        <div class="module-title-cluster">
          <span class="module-index">03</span>
          <div>
            <h2>Comparativo Técnico e Financeiro: Sem Baterias vs. Com Baterias</h2>
            <p>Análise lado a lado de custo de implantação, tempo de retorno (payback) e recomendação ao cliente</p>
          </div>
        </div>
        <div class="module-actions no-print">
          <label for="comp-autonomia-input" style="font-size:0.78125rem; font-weight:600; color:var(--ink-secondary);">
            Autonomia do Híbrido (horas):
          </label>
          <input type="number" id="comp-autonomia-input" value="12" min="1" max="72" style="width:72px; height:36px; padding:0 10px; border:1px solid var(--border-strong); border-radius:6px; font-family:var(--font-sans); font-size:0.8125rem;">
          <button type="button" class="btn btn-primary" onclick="recalcularComparacaoAPI()">
            Atualizar Comparativo
          </button>
        </div>
      </div>

      <div id="resumo-comparacao-cards" class="telemetry-grid" style="margin-bottom: 18px;"></div>

      <div id="tabela-comparacao-container" class="table-scroll"></div>

      <div id="box-questao-9-comp" class="notice-box notice-success" style="margin-top: 18px;"></div>

      <div class="no-print" style="display:flex; justify-content:space-between; align-items:center; margin-top:20px; padding-top:14px; border-top:1px solid var(--border-subtle);">
        <button type="button" class="btn btn-secondary" onclick="selecionarModuloAtivo('passo-2')">
          &larr; Voltar para Etapa 02: Dimensionamento
        </button>
        <button type="button" class="btn btn-primary" onclick="selecionarModuloAtivo('passo-4')">
          Avançar para Etapa 04: Catálogos, Roteiro e QA &rarr;
        </button>
      </div>
    </section>

    <!-- =====================================================================
         MÓDULO 04: CATÁLOGOS CSV, ROTEIRO SPRINT REVIEW, HISTÓRICO E QA
         ===================================================================== -->
    <section id="passo-4" class="module-section hidden-module">
      <div class="module-header">
        <div class="module-title-cluster">
          <span class="module-index">04</span>
          <div>
            <h2>Catálogos de Equipamentos, Roteiro de Apresentação, Histórico e Testes</h2>
            <p>Consulta às bases de dados oficiais (CSV), checklist das 15 etapas da Sprint Review, histórico salvo e bateria de testes</p>
          </div>
        </div>
      </div>

      <div class="sub-nav no-print" role="tablist" aria-label="Bases de dados e relatórios">
        <button type="button" class="sub-nav-btn active" onclick="abrirSubAba('sub-modulos', this)">
          Módulos Solares (10)
        </button>
        <button type="button" class="sub-nav-btn" onclick="abrirSubAba('sub-inversores', this)">
          Inversores (8)
        </button>
        <button type="button" class="sub-nav-btn" onclick="abrirSubAba('sub-baterias', this)">
          Baterias LiFePO4 (6)
        </button>
        <button type="button" class="sub-nav-btn" onclick="abrirSubAba('sub-localidades', this)">
          Irradiação CRESESB (18)
        </button>
        <button type="button" class="sub-nav-btn" onclick="abrirSubAba('sub-roteiro', this)">
          Roteiro Sprint Review (15 Etapas)
        </button>
        <button type="button" class="sub-nav-btn" onclick="abrirSubAba('sub-historico', this)">
          Projetos Salvos (JSON)
        </button>
        <button type="button" class="sub-nav-btn" onclick="abrirSubAba('sub-laudo', this)">
          Laudo Textual (.txt)
        </button>
        <button type="button" class="sub-nav-btn" onclick="abrirSubAba('sub-kanban', this)">
          Quadro Trello / Kanban (21/21)
        </button>
        <button type="button" class="sub-nav-btn" onclick="abrirSubAba('sub-codigo', this)">
          Código-Fonte Python (.py)
        </button>
        <button type="button" class="sub-nav-btn" onclick="abrirSubAba('sub-qa', this)">
          Validação &amp; Testes QA
        </button>
      </div>

      <div id="sub-modulos" class="sub-pane active">
        <div id="tabela-ds-modulos" class="table-scroll"></div>
      </div>

      <div id="sub-inversores" class="sub-pane">
        <div id="tabela-ds-inversores" class="table-scroll"></div>
      </div>

      <div id="sub-baterias" class="sub-pane">
        <div id="tabela-ds-baterias" class="table-scroll"></div>
      </div>

      <div id="sub-localidades" class="sub-pane">
        <div id="tabela-ds-localidades" class="table-scroll"></div>
      </div>

      <div id="sub-roteiro" class="sub-pane">
        <div id="painel-roteiro-15-etapas"></div>
      </div>

      <div id="sub-historico" class="sub-pane">
        <div id="tabela-historico-container" class="table-scroll"></div>
      </div>

      <div id="sub-laudo" class="sub-pane">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; margin-bottom:12px;">
          <span style="font-size:0.8125rem; color:var(--ink-muted);">
            Relatório técnico consolidado pronto para cópia ou download em formato texto (.txt).
          </span>
          <div style="display:flex; gap:8px;">
            <button type="button" class="btn btn-secondary btn-sm" onclick="copiarLaudoTexto(this)">Copiar Texto do Laudo</button>
            <a class="btn btn-primary btn-sm" href="/proposta_cliente.txt" download="proposta_cliente.txt">Baixar Arquivo .TXT</a>
          </div>
        </div>
        <pre id="pre-proposta-consolidada" class="code-terminal"></pre>
      </div>

      <div id="sub-kanban" class="sub-pane">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; margin-bottom:14px;">
          <div>
            <strong>Quadro Trello / Kanban Finalizado — Sprint 3 (PB01 a PB21 · 100% Concluído)</strong>
            <div style="font-size:0.78125rem; color:var(--ink-muted);">Rastreabilidade completa das 21 User Stories distribuídas entre as Sprints 1, 2 e 3 da Equipe Lumos.</div>
          </div>
          <span class="badge badge-success">21 / 21 Cards Concluídos (DONE)</span>
        </div>
        <div id="painel-kanban-cards" class="review-steps-grid"></div>
      </div>

      <div id="sub-codigo" class="sub-pane">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; margin-bottom:12px;">
          <div>
            <strong>Inspeção da Arquitetura e Código-Fonte Python (Zero Dependências Externas)</strong>
            <div style="font-size:0.78125rem; color:var(--ink-muted);">Consulte ao vivo os 4 módulos principais do sistema diretamente do servidor.</div>
          </div>
          <div style="display:flex; gap:6px; flex-wrap:wrap;">
            <button type="button" class="btn btn-sm btn-primary" id="btn-code-fv" onclick="carregarCodigoFonte('fotovoltaico.py', this)">fotovoltaico.py (Motor FV &amp; C1–C8)</button>
            <button type="button" class="btn btn-sm btn-secondary" id="btn-code-sc" onclick="carregarCodigoFonte('sistema_analise_casa.py', this)">sistema_analise_casa.py (JSON &amp; Cargas)</button>
            <button type="button" class="btn btn-sm btn-secondary" id="btn-code-web" onclick="carregarCodigoFonte('app_web.py', this)">app_web.py (Servidor HTTP &amp; REST)</button>
            <button type="button" class="btn btn-sm btn-secondary" id="btn-code-qa" onclick="carregarCodigoFonte('testes.py', this)">testes.py (13 Suítes QA)</button>
          </div>
        </div>
        <pre id="pre-codigo-fonte" class="code-terminal" style="max-height:520px; overflow-y:auto;"></pre>
      </div>

      <div id="sub-qa" class="sub-pane">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; margin-bottom:12px;">
          <div>
            <strong>Suíte de Verificação Automatizada (CP1 + CP2 + Sprint 3 Final)</strong>
            <div style="font-size:0.78125rem; color:var(--ink-muted);">Executa <code>testes.py</code> e <code>validar_datasets_fv()</code> diretamente no servidor Python.</div>
          </div>
          <button type="button" class="btn btn-primary" id="btn-run-qa" onclick="executarTestesQA()">
            Executar Bateria Completa de Testes (testes.py)
          </button>
        </div>
        <pre id="pre-qa-output" class="code-terminal" style="color:#a7f3d0;"></pre>
      </div>

      <div class="no-print" style="display:flex; justify-content:space-between; align-items:center; margin-top:20px; padding-top:14px; border-top:1px solid var(--border-subtle);">
        <button type="button" class="btn btn-secondary" onclick="selecionarModuloAtivo('passo-3')">
          &larr; Voltar para Etapa 03: Comparativo
        </button>
        <button type="button" class="btn btn-subtle" onclick="selecionarModuloAtivo('all')">
          Exibir Todas as Etapas na Mesma Página
        </button>
      </div>
    </section>

  </main>

  <script>
    let ESTADO = null;
    let MODULO_ATIVO = 'passo-1';

    function brl(v) {
      return 'R$ ' + Number(v || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    function num(v, c = 2) {
      return Number(v || 0).toLocaleString('pt-BR', { minimumFractionDigits: c, maximumFractionDigits: c });
    }

    function formatarHorasUso(h) {
      const val = Number(h || 0);
      const casas = (Math.round(val * 100) % 10 !== 0) ? 2 : 1;
      const base = num(val, casas) + ' h/dia';
      if (val > 0 && val < 1) {
        const mins = Math.round(val * 60);
        return `${base} (${mins} min)`;
      }
      return base;
    }

    function obterListaHsp(ds) {
      if (!ds || !ds.hsp_localidades) return [];
      if (Array.isArray(ds.hsp_localidades)) return ds.hsp_localidades;
      return Object.values(ds.hsp_localidades);
    }

    function selecionarModuloAtivo(alvo) {
      MODULO_ATIVO = alvo;
      const botoes = {
        'all': document.getElementById('nav-btn-all'),
        'passo-1': document.getElementById('nav-btn-1'),
        'passo-2': document.getElementById('nav-btn-2'),
        'passo-3': document.getElementById('nav-btn-3'),
        'passo-4': document.getElementById('nav-btn-4')
      };
      Object.keys(botoes).forEach(k => {
        if (botoes[k]) botoes[k].classList.toggle('active', k === alvo);
      });

      const secoes = ['passo-1', 'passo-2', 'passo-3', 'passo-4'];
      secoes.forEach(idSec => {
        const el = document.getElementById(idSec);
        if (!el) return;
        if (alvo === 'all' || idSec === alvo) {
          el.classList.remove('hidden-module');
        } else {
          el.classList.add('hidden-module');
        }
      });

      if (alvo !== 'all') {
        window.scrollTo({ top: 0, behavior: 'smooth' });
      }
    }

    function togglePainel(id) {
      const el = document.getElementById(id);
      if (el) el.classList.toggle('open');
    }

    function abrirSubAba(id, btn) {
      document.querySelectorAll('.sub-pane').forEach(p => p.classList.remove('active'));
      document.querySelectorAll('.sub-nav-btn').forEach(b => b.classList.remove('active'));
      const pane = document.getElementById(id);
      if (pane) pane.classList.add('active');
      if (btn) btn.classList.add('active');
    }

    async function carregarEstado(idImovel = '') {
      const url = idImovel ? `/api/estado?imovel_id=${encodeURIComponent(idImovel)}` : '/api/estado';
      const resp = await fetch(url);
      ESTADO = await resp.json();
      renderizarTudo();
    }

    function trocarImovelAtivo(idImovel) {
      carregarEstado(idImovel);
    }

    function atualizarKPIsTopo(im, dim) {
      if (!im || !dim) return;
      const comBat = Boolean(dim.armazenamento && dim.armazenamento.ativo);
      const badgeTop = document.getElementById('badge-topologia-ativa');
      if (badgeTop) {
        badgeTop.className = comBat ? 'badge badge-warning' : 'badge badge-info';
        badgeTop.textContent = comBat
          ? `Sistema Híbrido (${num(dim.armazenamento.autonomia_h, 0)}h Backup)`
          : 'Sistema On-Grid (Sem Baterias)';
      }

      document.getElementById('kpi-consumo').textContent = `${num(dim.consumo)} kWh/mês`;
      document.getElementById('kpi-demanda-sub').textContent =
        `Diário: ${num(dim.consumo_diario, 2)} kWh/dia · Potência Casa: ${num(im.potencia_instalada_w, 0)} W (${num(im.potencia_instalada_kw, 2)} kW)`;

      document.getElementById('kpi-potencia-fv').textContent =
        `${num(dim.p_inst, 2)} kWp (${dim.selecao.config.n_modulos} módulos)`;
      document.getElementById('kpi-fv-sub').textContent =
        `Necessário: ${num(dim.p_fv, 2)} kWp · HSP: ${num(dim.hsp_info.hsp, 1)} · PR: ${num(dim.pr * 100, 0)}%`;

      document.getElementById('kpi-geracao').textContent = `${num(dim.geracao_mes, 1)} kWh/mês`;
      document.getElementById('kpi-geracao-sub').textContent =
        `Diária: ${num(dim.geracao_dia, 2)} kWh/dia · Cobertura: ${num(dim.comparacao_geracao.atendimento_pct, 1)}%`;

      document.getElementById('kpi-orcamento').textContent = brl(dim.orcamento.c_total);
      document.getElementById('kpi-payback-sub').textContent =
        `Economia: ${brl(dim.economia.economia_mensal_brl)}/mês · Payback: ${num(dim.payback.payback_simples_anos)} anos`;
    }

    function renderizarTudo() {
      if (!ESTADO || !ESTADO.ok) return;
      const im = ESTADO.imovel_atual;
      const dim = ESTADO.dimensionamento_atual;
      const comp = ESTADO.comparacao_atual;
      const ds = ESTADO.datasets;

      document.getElementById('top-imovel-select').innerHTML = ESTADO.imoveis.map(i =>
        `<option value="${i.id}" ${i.id === im.id ? 'selected' : ''}>#${i.id} — ${i.apelido} (${i.cidade}/${i.uf} · ${num(i.consumo_mensal_kwh)} kWh/mês)</option>`
      ).join('');

      document.getElementById('lbl-endereco-res').textContent = `${im.endereco}, ${im.numero} — ${im.cidade}/${im.uf} (${im.tipo})`;

      atualizarKPIsTopo(im, dim);
      renderizarAbaResidencia(im);
      preencherFormularioDimensionamento(im, dim, ds);
      renderizarResultadoDimensionamento(dim, im.apelido, ESTADO.rejeitados_atuais, ESTADO.total_rejeitados);
      renderizarAbaComparacao(comp, im.apelido);
      renderizarAbaProposta(ESTADO);
      renderizarAbaDatasets(ds, dim);
      renderizarRoteiro15Etapas(im, comp);
      renderizarQuadroKanban();
      if (!document.getElementById('pre-codigo-fonte').textContent) {
        carregarCodigoFonte('fotovoltaico.py', document.getElementById('btn-code-fv'));
      }
    }

    function renderizarQuadroKanban() {
      const el = document.getElementById('painel-kanban-cards');
      if (!el) return;
      const cards = [
        { id: 'PB01', s: 'Sprint 1', m: 'sistema_analise_casa.py', r: 'Equipe Lumos', t: 'Recuperação Automática da Residência', d: 'Carrega a Residência Família Silva (SP) direto do dados_sistema.json sem exigir recadastro.' },
        { id: 'PB02', s: 'Sprint 1', m: 'fotovoltaico.py', r: 'Luiz Otávio (RM 569977)', t: 'Demanda Energética Residencial', d: 'Calcula E_mês = 455,31 kWh, E_dia = 15,18 kWh/dia e potência instalada de 9.013 W (9,01 kW).' },
        { id: 'PB03', s: 'Sprint 2', m: 'hsp_localidades.csv', r: 'Maria Eduarda (RM 574094)', t: 'Recurso Solar (HSP + PR = 0,78)', d: 'Consulta irradiação CRESESB (HSP = 5,00 em SP) e aplica PR = 78% fundamentado na NT EPE 009/2023.' },
        { id: 'PB04', s: 'Sprint 2', m: 'fotovoltaico.py', r: 'Luiz Otávio (RM 569977)', t: 'Potência Fotovoltaica Necessária', d: 'Aplica P_FV = E_dia ÷ (HSP × PR) = 15,18 ÷ (5,00 × 0,78) = 3,89 kWp.' },
        { id: 'PB05', s: 'Sprint 2', m: 'modulos.csv', r: 'Pietro Lorande (RM 569125)', t: 'Dataset Estruturado de Módulos (10)', d: 'Catálogo CSV auditado com 10 módulos reais (340 Wp a 665 Wp), tensões Voc/Vmp, área e preços.' },
        { id: 'PB06', s: 'Sprint 2', m: 'fotovoltaico.py', r: 'Luiz Otávio (RM 569977)', t: 'Dimensionamento do Arranjo Solar', d: 'Calcula N_mod = teto(3891,5 ÷ 405) = 10 módulos Trina Solar 405 Wp → P_inst = 4,05 kWp (19,2 m²).' },
        { id: 'PB07', s: 'Sprint 2', m: 'inversores.csv', r: 'Pietro Lorande (RM 569125)', t: 'Seleção de Inversor e Regras C1–C8', d: 'Verifica sobretensão Voc a frio (C1), janela MPPT (C2/C3), corrente (C4), R_DC/AC ≤ 1,35 (C6) e barramento (C7/C8).' },
        { id: 'PB08', s: 'Sprint 2', m: 'fotovoltaico.py', r: 'Maria Eduarda (RM 574094)', t: 'Estimativa de Geração Diária e Mensal', d: 'Calcula E_gerada,dia = 15,80 kWh/dia e E_gerada,mês = 473,85 kWh/mês.' },
        { id: 'PB09', s: 'Sprint 2', m: 'fotovoltaico.py', r: 'Luiz Otávio (RM 569977)', t: 'Balanço Geração × Consumo', d: 'Cobertura de 104,1%, separando 455,31 kWh compensados na fatura de 18,54 kWh excedentes.' },
        { id: 'PB10', s: 'Sprint 3', m: 'app_web.py', r: 'Pietro Lorande (RM 569125)', t: 'Topologia On-Grid vs. Híbrido', d: 'Alternância instantânea entre sistema Sem Baterias (Growatt 3.000 W) e Com Baterias (Deye 5.000 W).' },
        { id: 'PB11', s: 'Sprint 3', m: 'fotovoltaico.py', r: 'Luiz Otávio (RM 569977)', t: 'Dimensionamento do Banco de Baterias', d: 'Para 12h: E_aut = 7,59 kWh, C_bat = 8,88 kWh (DoD 90%, η 95%) → 2× Deye 5,12 kWh (10,24 kWh nominais).' },
        { id: 'PB12', s: 'Sprint 3', m: 'baterias.csv', r: 'Maria Eduarda (RM 574094)', t: 'Dataset de Baterias LiFePO4 (6)', d: 'Catálogo estruturado com 6 modelos LiFePO4 reais, tensão, Ah, kWh, DoD, ciclos e cotação.' },
        { id: 'PB13', s: 'Sprint 3', m: 'fotovoltaico.py', r: 'Pietro Lorande (RM 569125)', t: 'Orçamento Analítico Automatizado', d: 'Soma equipamentos CSV + BOS/instalação: R$ 11.590,88 (On-Grid) e R$ 33.317,78 (Híbrido).' },
        { id: 'PB14', s: 'Sprint 3', m: 'fotovoltaico.py', r: 'Luiz Otávio (RM 569977)', t: 'Comparativo Lado a Lado & Seção 9', d: 'Demonstra diferença de +R$ 21.726,90 (+187,5%) e fundamenta recomendação do sistema On-Grid.' },
        { id: 'PB15', s: 'Sprint 3', m: 'fotovoltaico.py', r: 'Maria Eduarda (RM 574094)', t: 'Economia Mensal e Anual na Fatura', d: 'Tarifa R$ 0,92/kWh → Economia de R$ 418,89/mês e R$ 5.026,68/ano.' },
        { id: 'PB16', s: 'Sprint 3', m: 'fotovoltaico.py', r: 'Luiz Otávio (RM 569977)', t: 'Payback Simples Preliminar', d: 'Retorno em 2,31 anos no On-Grid (1,49 anos só equip.) vs. 6,63 anos no Híbrido.' },
        { id: 'PB17', s: 'Sprint 3', m: 'app_web.py', r: 'Pietro Lorande (RM 569125)', t: 'Proposta Técnica Consolidada', d: 'Memorial descritivo completo unificando todas as 9 seções técnicas e financeiras.' },
        { id: 'PB18', s: 'Sprint 3', m: 'fotovoltaico.py', r: 'Maria Eduarda (RM 574094)', t: 'Validação e Bloqueio de Erros C1–C8', d: 'Exceção dedicada ErroDimensionamento que impede combinações elétricas incompatíveis.' },
        { id: 'PB19', s: 'Sprint 3', m: 'app_web.py', r: 'Pietro / Luiz', t: 'Interface Gráfica Web Full-Stack', d: 'Servidor HTTP nativo em Python puro com 4 etapas integradas sem exigir comandos no terminal.' },
        { id: 'PB20', s: 'Sprint 3', m: 'dados_sistema.json', r: 'Luiz Otávio (RM 569977)', t: 'Persistência Completa em JSON', d: 'Gravação e recarregamento de projetos dimensionados diretamente do arquivo dados_sistema.json.' },
        { id: 'PB21', s: 'Sprint 3', m: 'proposta_cliente.html', r: 'Luiz / Maria', t: 'Exportação .TXT, .HTML e PDF', d: 'Geração instantânea de laudo técnico em texto puro e relatório web formatado para impressão PDF.' }
      ];
      el.innerHTML = cards.map(c => `
        <div class="review-step-card">
          <div class="review-step-head">
            <strong>${c.id} · ${c.t}</strong>
            <span class="badge badge-success badge-mono">DONE · ${c.s}</span>
          </div>
          <p style="margin-bottom:8px;">${c.d}</p>
          <div style="display:flex; justify-content:space-between; font-size:0.71875rem; color:var(--ink-muted); border-top:1px solid var(--border-subtle); padding-top:6px;">
            <span>Módulo: <code>${c.m}</code></span>
            <span>Resp.: <strong>${c.r}</strong></span>
          </div>
        </div>
      `).join('');
    }

    async function carregarCodigoFonte(arquivo, btnEl) {
      const pre = document.getElementById('pre-codigo-fonte');
      if (!pre) return;
      ['btn-code-fv', 'btn-code-sc', 'btn-code-web', 'btn-code-qa'].forEach(id => {
        const b = document.getElementById(id);
        if (b) { b.className = 'btn btn-sm btn-secondary'; }
      });
      if (btnEl) btnEl.className = 'btn btn-sm btn-primary';
      pre.textContent = 'Carregando código-fonte de ' + arquivo + '...';
      try {
        const resp = await fetch('/api/codigo?arquivo=' + encodeURIComponent(arquivo));
        const res = await resp.json();
        if (res.ok) {
          pre.textContent = res.conteudo;
          pre.scrollTop = 0;
        } else {
          pre.textContent = 'Erro: ' + res.erro;
        }
      } catch (e) {
        pre.textContent = 'Falha ao carregar arquivo: ' + e;
      }
    }

    function renderizarAbaResidencia(im) {
      const selCat = document.getElementById('assoc-eq-select');
      selCat.innerHTML = `<option value="CUSTOM">-- Especificar equipamento personalizado --</option>` +
        ESTADO.catalogo_equipamentos.map(e =>
          `<option value="${e.id}" data-nome="${e.nome}" data-cat="${e.categoria}" data-pot="${e.potencia}">${e.nome} (${e.categoria} — ${e.potencia} W)</option>`
        ).join('');
      if (ESTADO.catalogo_equipamentos.length > 0) {
        selCat.selectedIndex = 1;
        preencherEquipamentoCatalogo();
      }

      const totalMes = im.consumo_mensal_kwh || 1;
      const tbody = document.getElementById('tabela-cargas-body');
      if (!im.cargas || im.cargas.length === 0) {
        tbody.innerHTML = `<tr><td colspan="11" class="center-col" style="padding:24px; color:var(--ink-muted);">Nenhum equipamento associado a esta residência. Utilize o botão "Adicionar Equipamento" ou "Restaurar Padrão".</td></tr>`;
        return;
      }

      tbody.innerHTML = im.cargas.map((c, idx) => {
        const pct = (c.consumo_mensal_kwh / totalMes) * 100;
        const nomeEsc = String(c.nome).replace(/'/g, "\\'");
        return `
          <tr>
            <td class="center-col"><span class="badge badge-neutral badge-mono">${String(idx + 1).padStart(2, '0')}</span></td>
            <td><strong>${c.nome}</strong></td>
            <td><span class="badge badge-neutral">${c.categoria}</span></td>
            <td class="num-col">${num(c.potencia_w, 0)} W</td>
            <td class="center-col">${c.quantidade}</td>
            <td class="num-col">${num(c.potencia_total_w, 0)} W</td>
            <td class="num-col">${formatarHorasUso(c.tempo_uso_h)}</td>
            <td class="num-col">${num(c.consumo_diario_kwh, 2)} kWh/dia</td>
            <td class="num-col"><strong>${num(c.consumo_mensal_kwh, 2)} kWh/mês</strong></td>
            <td>
              <div class="share-cell">
                <div class="share-track"><div class="share-fill" style="width:${Math.min(100, pct)}%"></div></div>
                <span class="share-pct">${num(pct, 1)}%</span>
              </div>
            </td>
            <td class="no-print" style="text-align:right; white-space:nowrap;">
              <button type="button" class="btn btn-sm btn-subtle" onclick="abrirEdicaoCarga('${c.assoc_id}', '${nomeEsc}', ${c.quantidade}, ${c.tempo_uso_h})">Editar</button>
              <button type="button" class="btn btn-sm btn-danger-ghost" onclick="removerCargaResidencia('${c.assoc_id}')">Remover</button>
            </td>
          </tr>
        `;
      }).join('') + `
        <tr class="row-total">
          <td colspan="4">TOTAL ACUMULADO DA RESIDÊNCIA (PB02)</td>
          <td class="center-col">${im.cargas.reduce((s, x) => s + x.quantidade, 0)} un.</td>
          <td class="num-col">${num(im.potencia_instalada_w, 0)} W (${num(im.potencia_instalada_kw, 2)} kW)</td>
          <td class="num-col">--</td>
          <td class="num-col">${num(im.consumo_diario_kwh, 2)} kWh/dia</td>
          <td class="num-col">${num(im.consumo_mensal_kwh, 2)} kWh/mês</td>
          <td>
            <div class="share-cell">
              <div class="share-track"><div class="share-fill" style="width:100%"></div></div>
              <span class="share-pct">100%</span>
            </div>
          </td>
          <td class="no-print"></td>
        </tr>
      `;
    }

    function preencherEquipamentoCatalogo() {
      const sel = document.getElementById('assoc-eq-select');
      const opt = sel.options[sel.selectedIndex];
      if (!opt || opt.value === 'CUSTOM') {
        document.getElementById('assoc-eq-nome').value = '';
        document.getElementById('assoc-eq-cat').value = '';
        return;
      }
      document.getElementById('assoc-eq-nome').value = opt.getAttribute('data-nome') || '';
      document.getElementById('assoc-eq-cat').value = opt.getAttribute('data-cat') || '';
      document.getElementById('assoc-eq-pot').value = opt.getAttribute('data-pot') || 100;
    }

    function abrirEdicaoCarga(assocId, nome, qtd, horas) {
      document.getElementById('edit-assoc-id').value = assocId;
      document.getElementById('lbl-edit-equip-titulo').textContent = `Editar Regime de Operação: ${nome}`;
      document.getElementById('edit-eq-qtd').value = qtd;
      document.getElementById('edit-eq-horas').value = horas;
      document.getElementById('painel-edit-equip').classList.add('open');
    }

    function fecharEdicaoCarga() {
      document.getElementById('painel-edit-equip').classList.remove('open');
    }

    async function salvarEdicaoCarga() {
      const assocId = document.getElementById('edit-assoc-id').value;
      const qtd = Number(document.getElementById('edit-eq-qtd').value);
      const horas = Number(document.getElementById('edit-eq-horas').value);
      const resp = await fetch('/api/associacoes/editar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ assoc_id: assocId, quantidade: qtd, tempo_uso_h: horas })
      });
      const res = await resp.json();
      if (!res.ok) {
        alert('Erro de validação: ' + res.erro);
        return;
      }
      fecharEdicaoCarga();
      await carregarEstado(ESTADO.imovel_selecionado_id);
    }

    function preencherFormularioDimensionamento(im, dim, ds) {
      const inpCons = document.getElementById('dim-consumo');
      if (document.getElementById('dim-origem-consumo').value === 'calculado') {
        inpCons.value = im.consumo_mensal_kwh.toFixed(2);
        inpCons.readOnly = true;
      }

      const listaHsp = obterListaHsp(ds);
      const selLoc = document.getElementById('dim-localidade');
      selLoc.innerHTML = listaHsp.map((l, idx) => {
        const isSel = String(l.cidade).toLowerCase() === String(im.cidade).toLowerCase() && String(l.uf).toUpperCase() === String(im.uf).toUpperCase();
        return `<option value="${idx}" data-hsp="${l.hsp}" ${isSel ? 'selected' : ''}>${l.cidade}/${l.uf} — HSP ${num(l.hsp, 1)} kWh/m²/dia</option>`;
      }).join('');

      document.getElementById('dim-hsp').value = dim.hsp_info.hsp;
      document.getElementById('dim-pr').value = dim.pr;
      document.getElementById('dim-tarifa').value = dim.economia.tarifa_brl_kwh;

      document.getElementById('dim-modulo').innerHTML =
        `<option value="">Otimização Automática (Menor Custo Compatível)</option>` +
        ds.modulos.map(m =>
          `<option value="${m.id}">[${m.id}] ${m.fabricante} ${m.modelo} (${m.potencia_wp} Wp · Ef. ${num(m.eficiencia_pct, 1)}% — ${brl(m.preco_brl)})</option>`
        ).join('');

      document.getElementById('dim-inversor').innerHTML =
        `<option value="">Otimização Automática Compatível (Regras C1–C8)</option>` +
        ds.inversores.map(i =>
          `<option value="${i.id}">[${i.id}] ${i.fabricante} ${i.modelo} (${i.compativel_bateria ? 'Híbrido' : 'On-Grid'}, ${i.potencia_nominal_w} W — ${brl(i.preco_brl)})</option>`
        ).join('');

      document.getElementById('dim-bateria').innerHTML =
        `<option value="">Otimização Automática Compatível (LiFePO4)</option>` +
        ds.baterias.map(b =>
          `<option value="${b.id}">[${b.id}] ${b.fabricante} ${b.modelo} (${num(b.capacidade_kwh)} kWh · ${num(b.tensao_nominal_v, 1)}V · DoD ${b.dod_pct}% — ${brl(b.preco_brl)})</option>`
        ).join('');

      alternarCamposBateria();
    }

    function alternarOrigemConsumo() {
      const modo = document.getElementById('dim-origem-consumo').value;
      const inp = document.getElementById('dim-consumo');
      const hint = document.getElementById('lbl-status-consumo');
      if (modo === 'calculado' && ESTADO) {
        inp.value = ESTADO.imovel_atual.consumo_mensal_kwh.toFixed(2);
        inp.readOnly = true;
        if (hint) hint.textContent = 'Sincronizado';
      } else {
        inp.readOnly = false;
        if (hint) hint.textContent = 'Manual';
        inp.focus();
      }
    }

    function atualizarHspDaTabela() {
      const sel = document.getElementById('dim-localidade');
      const opt = sel.options[sel.selectedIndex];
      if (opt) {
        document.getElementById('dim-hsp').value = opt.getAttribute('data-hsp');
      }
    }

    function alternarCamposBateria() {
      const comBat = document.getElementById('dim-com-bateria').value === 'true';
      const inpAut = document.getElementById('dim-autonomia');
      const selBat = document.getElementById('dim-bateria');
      const lblAut = document.getElementById('lbl-status-autonomia');
      if (inpAut) inpAut.disabled = !comBat;
      if (selBat) selBat.disabled = !comBat;
      if (lblAut) lblAut.textContent = comBat ? 'Ativo (1 a 72h)' : 'Inativo no On-Grid';
    }

    function aplicarPresetRapido(comBateria) {
      document.getElementById('dim-com-bateria').value = comBateria ? 'true' : 'false';
      document.getElementById('dim-modulo').value = '';
      document.getElementById('dim-inversor').value = '';
      document.getElementById('dim-bateria').value = '';
      if (comBateria) {
        document.getElementById('dim-autonomia').value = 12;
      }
      alternarCamposBateria();
      executarDimensionamentoAPI();
    }

    function formatarFonteCurta(fonteStr) {
      const s = String(fonteStr || '').trim();
      const idxHttp = s.indexOf('http');
      if (idxHttp > 0) {
        const fornecedorData = s.slice(0, idxHttp).trim();
        const url = s.slice(idxHttp).trim();
        return `Cotação: ${fornecedorData} · <a href="${url}" target="_blank" rel="noopener" style="color:var(--brand-primary); text-decoration:none; font-weight:600;">Ver fonte &nearr;</a>`;
      }
      return `Cotação: ${s}`;
    }

    function normalizarRotuloOrcamento(txt) {
      const mapa = {
        'Modulo Fotovoltaico': 'Módulo Solar',
        'Inversor Fotovoltaico': 'Inversor',
        'Bateria': 'Bateria LiFePO4',
        'Estrutura de fixacao': 'Estrutura de fixação metálica',
        'Cabeamento e conectores': 'Cabeamento CC/CA e conectores MC4',
        'Protecoes / string box': 'Proteções elétricas e String Box',
        'Instalacao (mao de obra)': 'Instalação e mão de obra especializada',
        'Projeto e homologacao': 'Projeto executivo e homologação na concessionária'
      };
      return mapa[txt] || txt;
    }

    function renderizarResultadoDimensionamento(r, apelido, rejeitadosLista = [], totalRejeitados = 0) {
      const s = r.selecao, arm = r.armazenamento, orc = r.orcamento, h = r.hsp_info;
      const compG = r.comparacao_geracao, econ = r.economia, pay = r.payback;
      const mod = s.modulo, inv = s.inversor, cfg = s.config;

      const areaCalc = cfg.area_m2 || ((r.p_inst) / Math.max(0.1, (mod.eficiencia_pct || 20) / 100));

      const linhasEquipamentos = orc.itens.map(i => `
        <tr>
          <td>
            <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap;">
              <span class="badge badge-info">${normalizarRotuloOrcamento(i.categoria)}</span>
              <strong>${i.fabricante} ${i.modelo}</strong>
              <span class="badge-mono" style="color:var(--ink-muted); font-size:0.71875rem;">[${i.id_equipamento}]</span>
            </div>
            <div style="font-size:0.75rem; color:var(--ink-muted); margin-top:3px;">${formatarFonteCurta(i.fonte)}</div>
          </td>
          <td class="center-col"><strong>${i.qtd}</strong></td>
          <td class="num-col">${brl(i.preco_unitario)}</td>
          <td class="num-col"><strong>${brl(i.subtotal)}</strong></td>
        </tr>
      `).join('');

      const linhasBos = orc.outros.map(o => `
        <tr>
          <td>
            <strong>${normalizarRotuloOrcamento(o[0])}</strong>
            <span style="font-size:0.75rem; color:var(--ink-muted); margin-left:4px;">(${o[2]})</span>
          </td>
          <td class="center-col">1</td>
          <td class="num-col">${brl(o[1])}</td>
          <td class="num-col">${brl(o[1])}</td>
        </tr>
      `).join('');

      let blocoBatHtml = `<span class="badge badge-info">On-Grid Sem Baterias</span> <span style="color:var(--ink-secondary);">Concessionária atua como backup virtual (0 kWh · R$ 0,00).</span>`;
      if (arm.ativo && arm.bateria) {
        const b = arm.bateria;
        blocoBatHtml = `
          <div><span class="badge badge-warning">Híbrido Com Backup</span> <strong>${arm.n_baterias}× ${b.fabricante} ${b.modelo}</strong> (${b.tecnologia}, ${num(b.capacidade_kwh)} kWh/un)</div>
          <div style="font-size:0.75rem; color:var(--ink-muted); margin-top:3px;">
            Autonomia de <strong>${num(arm.autonomia_h, 0)} horas</strong> · Capacidade instalada: <strong>${num(arm.capacidade_instalada_kwh)} kWh</strong> (${num(arm.capacidade_util_kwh)} kWh úteis)
          </div>
        `;
      }

      document.getElementById('painel-resultado-dimensionamento').innerHTML = `
        <div class="split-2">
          <!-- CARD ESQUERDO: ESPECIFICAÇÃO TÉCNICA -->
          <div class="result-card">
            <div>
              <div class="result-card-head">
                <h3>2.1 Ficha Técnica do Sistema Dimensionado</h3>
                <span class="badge badge-success">${s.alternativas_validas} combinações aprovadas</span>
              </div>
              <div class="result-card-body">
                <table class="kv-table">
                  <tbody>
                    <tr>
                      <th>Localização e Irradiação</th>
                      <td>
                        <strong>${h.cidade}/${h.uf}</strong> · Sol Pleno (HSP) = <strong>${num(h.hsp)} kWh/m²/dia</strong>
                        <div style="font-size:0.75rem; color:var(--ink-muted); margin-top:2px;">Rendimento Global (PR) = <strong>${num(r.pr * 100, 0)}%</strong> · Fonte: ${h.fonte}</div>
                      </td>
                    </tr>
                    <tr>
                      <th>Potência Fotovoltaica</th>
                      <td>
                        Necessária: <strong>${num(r.p_fv, 2)} kWp</strong> &rarr; Instalada: <strong>${num(r.p_inst, 2)} kWp</strong>
                        <div style="font-size:0.75rem; color:var(--ink-muted); margin-top:2px;">Meta: cobrir ${num(r.percentual, 0)}% de ${num(r.consumo)} kWh/mês (${num(r.consumo_diario, 2)} kWh/dia)</div>
                      </td>
                    </tr>
                    <tr>
                      <th>Módulos Solares</th>
                      <td>
                        <strong>${cfg.n_modulos} unidades · ${mod.fabricante} ${mod.modelo}</strong> (${mod.potencia_wp} Wp)
                        <div style="font-size:0.75rem; color:var(--ink-muted); margin-top:2px;">
                          Eficiência ${num(mod.eficiencia_pct)}% · ${cfg.n_strings} string(s) de ${cfg.por_string} módulos · Área: <strong>${num(areaCalc, 1)} m²</strong>
                        </div>
                      </td>
                    </tr>
                    <tr>
                      <th>Inversor Solar</th>
                      <td>
                        <strong>1 unidade · ${inv.fabricante} ${inv.modelo}</strong> (${inv.compativel_bateria ? 'Híbrido' : 'On-Grid'}, ${inv.potencia_nominal_w} W)
                        <div style="font-size:0.75rem; color:var(--ink-muted); margin-top:2px;">
                          Eficiência ${num(inv.eficiencia_pct, 1)}% · Relação CC/CA = <strong>${num(cfg.ratio_dc_ac)}</strong> (limite máx. 1,35)
                        </div>
                      </td>
                    </tr>
                    <tr>
                      <th>Tensões Elétricas de String</th>
                      <td>
                        Voc a frio: <strong>${num(cfg.voc_string_v, 1)} V</strong> (máx. ${inv.tensao_max_entrada_v} V) · Vmp: <strong>${num(cfg.vmp_string_v, 1)} V</strong>
                        <div style="font-size:0.75rem; color:var(--ink-muted); margin-top:2px;">
                          Janela MPPT do inversor: <strong>${inv.faixa_mppt_min_v} V a ${inv.faixa_mppt_max_v} V</strong> (${inv.numero_mppt} MPPT)
                        </div>
                      </td>
                    </tr>
                    <tr>
                      <th>Geração e Compensação</th>
                      <td>
                        <strong>${num(r.geracao_mes, 1)} kWh/mês</strong> (${num(r.geracao_dia, 2)} kWh/dia)
                        <span class="badge badge-success" style="margin-left:4px;">${num(compG.atendimento_pct, 1)}% da demanda</span>
                        <div style="font-size:0.75rem; color:var(--ink-muted); margin-top:2px;">
                          Abatido na conta: <strong>${num(compG.energia_compensada_kwh_mes)} kWh/mês</strong> · Crédito excedente: <strong>${num(compG.energia_excedente_kwh_mes)} kWh/mês</strong>
                        </div>
                      </td>
                    </tr>
                    <tr>
                      <th>Banco de Baterias</th>
                      <td>${blocoBatHtml}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <div class="result-card-foot no-print">
              <div style="font-size:0.75rem; color:var(--ink-secondary); margin-bottom:10px;">
                <strong>Equação Aplicada (PB04):</strong> <code>P_FV = E_dia ÷ (HSP × PR) = ${num(r.consumo_diario, 2)} ÷ (${num(h.hsp)} × ${num(r.pr)}) = ${num(r.p_fv, 3)} kWp</code>
              </div>
              <div style="display:flex; flex-wrap:wrap; gap:8px;">
                ${(rejeitadosLista && rejeitadosLista.length > 0) ? `
                  <button type="button" class="btn btn-sm btn-secondary" onclick="togglePainel('painel-matriz-c1-c8')">
                    Inspecionar Pares Reprovados nas Regras C1–C8 (${totalRejeitados || rejeitadosLista.length} bloqueados)
                  </button>
                ` : ''}
              </div>
            </div>
          </div>

          <!-- CARD DIREITO: ORÇAMENTO E RETORNO FINANCEIRO -->
          <div class="result-card">
            <div>
              <div class="result-card-head">
                <h3>2.2 Orçamento de Implantação e Retorno Financeiro</h3>
                <span class="badge badge-info">Cotações Reais (CSV)</span>
              </div>
              <div class="result-card-body">
                <table>
                  <thead>
                    <tr>
                      <th>Componente / Rubrica</th>
                      <th class="center-col">Qtd.</th>
                      <th class="num-col">Unitário</th>
                      <th class="num-col">Subtotal</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr class="row-section-divider">
                      <td colspan="4">Equipamentos Principais (Catálogo CSV)</td>
                    </tr>
                    ${linhasEquipamentos}
                    <tr style="background-color:var(--bg-subtle);">
                      <td colspan="3" class="num-col"><strong>Subtotal de Equipamentos Principais</strong></td>
                      <td class="num-col"><strong>${brl(orc.c_equipamentos)}</strong></td>
                    </tr>
                    <tr class="row-section-divider">
                      <td colspan="4">Infraestrutura, Homologação e Mão de Obra (BOS)</td>
                    </tr>
                    ${linhasBos}
                    <tr class="row-highlight">
                      <td colspan="3" class="num-col"><strong>INVESTIMENTO TOTAL ESTIMADO (SISTEMA INSTALADO)</strong></td>
                      <td class="num-col"><strong style="font-size:0.9375rem;">${brl(orc.c_total)}</strong></td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <div class="result-card-foot" style="background-color:#e0f2fe; border-top:2px solid var(--brand-border);">
              <div style="display:grid; grid-template-columns:repeat(3, 1fr); gap:10px; padding-bottom:10px; border-bottom:1px solid var(--brand-border);">
                <div>
                  <div style="font-size:0.6875rem; text-transform:uppercase; font-weight:700; color:#0369a1;">Economia Mensal</div>
                  <div style="font-size:1.0625rem; font-weight:700; color:var(--ink-primary);">${brl(econ.economia_mensal_brl)}/mês</div>
                </div>
                <div>
                  <div style="font-size:0.6875rem; text-transform:uppercase; font-weight:700; color:#0369a1;">Economia Anual</div>
                  <div style="font-size:1.0625rem; font-weight:700; color:var(--ink-primary);">${brl(econ.economia_anual_brl)}/ano</div>
                </div>
                <div>
                  <div style="font-size:0.6875rem; text-transform:uppercase; font-weight:700; color:#0369a1;">Payback Simples Total</div>
                  <div style="font-size:1.0625rem; font-weight:700; color:var(--status-success-fg);">${pay.payback_formatado}</div>
                </div>
              </div>
              <div style="margin-top:8px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; font-size:0.75rem; color:#0c4a6e;">
                <span><strong>Payback apenas Equipamentos:</strong> ${num(pay.payback_apenas_equipamentos_anos)} anos</span>
                <span><strong>Tarifa:</strong> ${brl(econ.tarifa_brl_kwh)}/kWh (Payback Simples preliminar, sem VPL/TIR)</span>
              </div>
            </div>
          </div>
        </div>

        ${(rejeitadosLista && rejeitadosLista.length > 0) ? `
          <div id="painel-matriz-c1-c8" class="drawer-panel no-print" style="margin-top:16px; margin-bottom:0;">
            <div class="drawer-header">
              <h3>Registro de Pares Bloqueados pelas Regras Elétricas C1 a C8 (PB07 / PB18)</h3>
              <button type="button" class="btn btn-sm btn-subtle" onclick="togglePainel('painel-matriz-c1-c8')">Fechar</button>
            </div>
            <div class="table-scroll">
              <table>
                <thead><tr><th style="width:160px;">Combinação</th><th>Critério Técnico de Bloqueio</th></tr></thead>
                <tbody>
                  ${rejeitadosLista.map(item => `
                    <tr>
                      <td><code class="badge-mono">${item.par}</code></td>
                      <td style="color:var(--status-danger-fg);">${item.motivos.join(' · ')}</td>
                    </tr>
                  `).join('')}
                </tbody>
              </table>
            </div>
          </div>
        ` : ''}
      `;
    }

    function renderizarAbaComparacao(comp, apelido) {
      const a = comp.sem_bateria, b = comp.com_bateria;
      const modA = a.selecao.modulo, invA = a.selecao.inversor, cfgA = a.selecao.config;
      const modB = b.selecao.modulo, invB = b.selecao.inversor, cfgB = b.selecao.config;
      const batB = b.armazenamento.bateria;

      document.getElementById('resumo-comparacao-cards').innerHTML = `
        <div class="telemetry-card">
          <div class="telemetry-title">Cenário 1 · On-Grid (Sem Baterias)</div>
          <div class="telemetry-value">${brl(a.orcamento.c_total)}</div>
          <div class="telemetry-meta">Payback Total: <strong>${num(a.payback.payback_simples_anos)} anos</strong> · Só Equip.: ${num(a.payback.payback_apenas_equipamentos_anos)} anos</div>
        </div>
        <div class="telemetry-card">
          <div class="telemetry-title">Cenário 2 · Híbrido (${num(b.armazenamento.autonomia_h, 0)}h Backup)</div>
          <div class="telemetry-value">${brl(b.orcamento.c_total)}</div>
          <div class="telemetry-meta">Payback Total: <strong>${num(b.payback.payback_simples_anos)} anos</strong> · Só Equip.: ${num(b.payback.payback_apenas_equipamentos_anos)} anos</div>
        </div>
        <div class="telemetry-card">
          <div class="telemetry-title">Acréscimo de Investimento (Baterias + Híbrido)</div>
          <div class="telemetry-value">+${brl(comp.diferenca_investimento_total_brl)}</div>
          <div class="telemetry-meta">Variação percentual: <strong>+${num(comp.acrescimo_percentual, 1)}%</strong> (+${num(comp.diferenca_payback_anos)} anos no payback)</div>
        </div>
        <div class="telemetry-card">
          <div class="telemetry-title">Parecer Técnico Recomendado (Seção 9)</div>
          <div class="telemetry-value" style="font-size:1.0625rem; color:var(--status-success-fg);">Sistema Sem Baterias (On-Grid)</div>
          <div class="telemetry-meta">Mesma geração (${num(a.geracao_mes, 1)} kWh/mês) e economia (${brl(a.economia.economia_mensal_brl)}/mês) com retorno 2,8× mais rápido</div>
        </div>
      `;

      document.getElementById('tabela-comparacao-container').innerHTML = `
        <table>
          <thead>
            <tr>
              <th style="width:30%;">Indicador Técnico / Financeiro</th>
              <th style="width:35%;">Cenário 1: Sem Baterias (On-Grid Convencional)</th>
              <th style="width:35%;">Cenário 2: Com Baterias (Híbrido + Backup ${num(b.armazenamento.autonomia_h, 0)}h)</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Arranjo de Módulos Fotovoltaicos</td>
              <td>${cfgA.n_modulos}× [${modA.id}] ${modA.fabricante} ${modA.modelo} (${modA.potencia_wp} Wp) → <strong>${num(a.p_inst, 2)} kWp</strong></td>
              <td>${cfgB.n_modulos}× [${modB.id}] ${modB.fabricante} ${modB.modelo} (${modB.potencia_wp} Wp) → <strong>${num(b.p_inst, 2)} kWp</strong></td>
            </tr>
            <tr>
              <td>Inversor Selecionado e R_DC/AC</td>
              <td><strong>[${invA.id}] ${invA.fabricante} ${invA.modelo}</strong> (On-Grid, ${invA.potencia_nominal_w} W · R_DC/AC = ${num(cfgA.ratio_dc_ac)})</td>
              <td><strong>[${invB.id}] ${invB.fabricante} ${invB.modelo}</strong> (Híbrido, ${invB.potencia_nominal_w} W · R_DC/AC = ${num(cfgB.ratio_dc_ac)})</td>
            </tr>
            <tr>
              <td>Geração Mensal e Atendimento</td>
              <td><strong>${num(a.geracao_mes, 1)} kWh/mês</strong> (${num(a.comparacao_geracao.atendimento_pct, 1)}% da demanda)</td>
              <td><strong>${num(b.geracao_mes, 1)} kWh/mês</strong> (${num(b.comparacao_geracao.atendimento_pct, 1)}% da demanda)</td>
            </tr>
            <tr>
              <td>Banco de Baterias e Autonomia</td>
              <td><span class="badge badge-neutral">Não possui (0 kWh · 0 h backup)</span></td>
              <td><strong>${b.armazenamento.n_baterias}× [${batB.id}] ${batB.fabricante} ${batB.modelo}</strong> (${num(b.armazenamento.capacidade_instalada_kwh)} kWh nominais / ${num(b.armazenamento.capacidade_util_kwh)} kWh úteis · ${num(b.armazenamento.autonomia_h, 0)}h)</td>
            </tr>
            <tr>
              <td>Subtotal de Equipamentos (CSV)</td>
              <td><strong>${brl(a.orcamento.c_equipamentos)}</strong></td>
              <td><strong>${brl(b.orcamento.c_equipamentos)}</strong> <span style="color:var(--ink-muted);">(+${brl(comp.diferenca_equipamentos_brl)})</span></td>
            </tr>
            <tr>
              <td>Custos Complementares e Instalação</td>
              <td>${brl(a.orcamento.c_outros)}</td>
              <td>${brl(b.orcamento.c_outros)}</td>
            </tr>
            <tr class="row-highlight">
              <td><strong>Investimento Total Instalado</strong></td>
              <td><strong>${brl(a.orcamento.c_total)}</strong></td>
              <td><strong>${brl(b.orcamento.c_total)}</strong> <span class="badge badge-warning">+${num(comp.acrescimo_percentual, 1)}%</span></td>
            </tr>
            <tr>
              <td>Economia Mensal / Anual na Fatura</td>
              <td><strong>${brl(a.economia.economia_mensal_brl)}/mês</strong> (${brl(a.economia.economia_anual_brl)}/ano)</td>
              <td><strong>${brl(b.economia.economia_mensal_brl)}/mês</strong> (${brl(b.economia.economia_anual_brl)}/ano)</td>
            </tr>
            <tr>
              <td>Payback Simples (Apenas Equipamentos)</td>
              <td><span class="badge badge-success">${num(a.payback.payback_apenas_equipamentos_anos)} anos</span></td>
              <td><span class="badge badge-warning">${num(b.payback.payback_apenas_equipamentos_anos)} anos</span></td>
            </tr>
            <tr>
              <td><strong>Payback Simples (Investimento Total)</strong></td>
              <td><span class="badge badge-success">${a.payback.payback_formatado}</span></td>
              <td><span class="badge badge-warning">${b.payback.payback_formatado}</span></td>
            </tr>
          </tbody>
        </table>
      `;

      document.getElementById('box-questao-9-comp').innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; margin-bottom:8px;">
          <strong style="font-size:0.9375rem;">Parecer Técnico-Econômico Conclusivo para ${apelido} (Questão Final — Seção 9)</strong>
          <span class="badge badge-success">Recomendação: Sistema On-Grid Sem Armazenamento</span>
        </div>
        <div class="prose-block" style="white-space:pre-line; color:var(--ink-primary);">${comp.analise_questao_final}</div>
      `;
    }

    function renderizarRoteiro15Etapas(im, comp) {
      const a = comp.sem_bateria, b = comp.com_bateria;
      const h = a.hsp_info;
      const modA = a.selecao.modulo, invA = a.selecao.inversor, cfgA = a.selecao.config;
      const invB = b.selecao.inversor, batB = b.armazenamento.bateria;
      const qtdUnidades = (im.cargas || []).reduce((acc, x) => acc + x.quantidade, 0);

      const etapas = [
        { n: '01', pb: 'PB01', t: 'Seleção da Residência Cadastrada', d: `Unidade #${im.id} (${im.apelido} — ${im.endereco}, ${im.numero}, ${im.cidade}/${im.uf}) recuperada de dados_sistema.json sem exigir recadastro.` },
        { n: '02', pb: 'PB02', t: 'Equipamentos e Demanda Energética', d: `${(im.cargas || []).length} grupos de equipamentos (${qtdUnidades} unidades), potência instalada de ${num(im.potencia_instalada_w, 0)} W (${num(im.potencia_instalada_kw, 2)} kW), E_mês = ${num(a.consumo)} kWh/mês e E_dia = ${num(a.consumo_diario, 2)} kWh/dia.` },
        { n: '03', pb: 'PB04', t: 'Potência Fotovoltaica Necessária', d: `Fórmula oficial: P_FV = E_dia ÷ (HSP × PR) = ${num(a.consumo_diario, 3)} ÷ (${num(h.hsp)} × ${num(a.pr)}) = ${num(a.p_fv, 3)} kWp.` },
        { n: '04', pb: 'PB03', t: 'Recurso Solar (HSP e PR Justificado)', d: `HSP = ${num(h.hsp)} kWh/m²/dia (${h.fonte}) e Performance Ratio PR = ${num(a.pr * 100, 0)}% conforme Nota Técnica EPE DEA-SEE 009/2023.` },
        { n: '05', pb: 'PB05/07/12', t: 'Consulta aos Datasets CSV', d: `Leitura estruturada e validada de 10 módulos (modulos.csv), 8 inversores (inversores.csv), 6 baterias LiFePO4 (baterias.csv) e 19 municípios (hsp_localidades.csv).` },
        { n: '06', pb: 'PB06', t: 'Dimensionamento dos Módulos FV', d: `Selecionado [${modA.id}] ${modA.fabricante} ${modA.modelo} (${modA.potencia_wp} Wp). N_mod = teto(${num(a.p_fv * 1000, 1)} ÷ ${modA.potencia_wp}) = ${cfgA.n_modulos} módulos → P_inst = ${num(a.p_inst, 2)} kWp.` },
        { n: '07', pb: 'PB07', t: 'Seleção e Compatibilidade do Inversor', d: `Regras elétricas C1–C8 verificadas (Voc frio ${num(cfgA.voc_string_v, 1)}V, faixa MPPT e R_DC/AC = ${num(cfgA.ratio_dc_ac)}). On-Grid: [${invA.id}] ${invA.fabricante}; Híbrido: [${invB.id}] ${invB.fabricante}.` },
        { n: '08', pb: 'PB08', t: 'Estimativa de Geração Diária e Mensal', d: `E_gerada,dia = ${num(a.p_inst, 2)} × ${num(h.hsp)} × ${num(a.pr)} = ${num(a.geracao_dia, 2)} kWh/dia e E_gerada,mês = E_dia × 30 = ${num(a.geracao_mes, 2)} kWh/mês.` },
        { n: '09', pb: 'PB09', t: 'Comparação Geração × Consumo', d: `Atendimento de ${num(a.comparacao_geracao.atendimento_pct, 1)}%, distinguindo energia compensada na fatura (${num(a.comparacao_geracao.energia_compensada_kwh_mes)} kWh/mês) do excedente (${num(a.comparacao_geracao.energia_excedente_kwh_mes)} kWh/mês).` },
        { n: '10', pb: 'PB10', t: 'Configuração Sem Baterias (On-Grid)', d: `${cfgA.n_modulos}× ${modA.fabricante} ${modA.potencia_wp}W + 1× [${invA.id}] ${invA.fabricante} ${invA.modelo} (${invA.potencia_nominal_w}W), sem armazenamento (0 kWh).` },
        { n: '11', pb: 'PB11/12', t: 'Configuração Com Baterias e Autonomia', d: `Autonomia de ${num(b.armazenamento.autonomia_h, 0)}h (E_aut = ${num(b.armazenamento.energia_autonomia_kwh)} kWh, C_bat = ${num(b.armazenamento.c_bat_kwh)} kWh) → ${b.armazenamento.n_baterias}× [${batB.id}] ${batB.fabricante} ${batB.modelo} (${num(b.armazenamento.capacidade_instalada_kwh)} kWh nominais).` },
        { n: '12', pb: 'PB13', t: 'Geração Automática do Orçamento', d: `On-Grid: Equipamentos ${brl(a.orcamento.c_equipamentos)} | Total ${brl(a.orcamento.c_total)}. Híbrido: Equipamentos ${brl(b.orcamento.c_equipamentos)} | Total ${brl(b.orcamento.c_total)}.` },
        { n: '13', pb: 'PB14', t: 'Comparação Lado a Lado dos Cenários', d: `Quadro comparativo demonstrando acréscimo de +${brl(comp.diferenca_investimento_total_brl)} (+${num(comp.acrescimo_percentual, 1)}%) para inclusão de backup de ${num(b.armazenamento.autonomia_h, 0)}h.` },
        { n: '14', pb: 'PB15/16', t: 'Economia Mensal/Anual e Payback Simples', d: `Tarifa ${brl(a.economia.tarifa_brl_kwh)}/kWh → Economia de ${brl(a.economia.economia_mensal_brl)}/mês (${brl(a.economia.economia_anual_brl)}/ano). Payback Simples: ${num(a.payback.payback_simples_anos)} anos (On-Grid) vs. ${num(b.payback.payback_simples_anos)} anos (Híbrido).` },
        { n: '15', pb: 'PB17/20/21', t: 'Persistência JSON e Exportação da Proposta', d: `Cálculos salvos em dados_sistema.json e relatórios consolidados disponíveis em formato .TXT, .HTML e impressão PDF.` }
      ];

      document.getElementById('painel-roteiro-15-etapas').innerHTML = `
        <div class="review-steps-grid">
          ${etapas.map(e => `
            <div class="review-step-card">
              <div class="review-step-head">
                <strong>Etapa ${e.n} · ${e.t}</strong>
                <span class="badge badge-info badge-mono">${e.pb}</span>
              </div>
              <p>${e.d}</p>
            </div>
          `).join('')}
        </div>
      `;
    }

    function renderizarAbaProposta(est) {
      document.getElementById('pre-proposta-consolidada').textContent =
        est.proposta_txt + "\\n\\n" + est.comparacao_txt;

      const hist = est.dimensionamentos_salvos || [];
      if (hist.length === 0) {
        document.getElementById('tabela-historico-container').innerHTML =
          `<div style="padding:20px; color:var(--ink-muted);">Nenhum dimensionamento salvo em dados_sistema.json.</div>`;
        return;
      }
      document.getElementById('tabela-historico-container').innerHTML = `
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Data / Hora</th>
              <th>Localidade / HSP</th>
              <th class="num-col">Consumo</th>
              <th class="num-col">Potência FV</th>
              <th>Arranjo (Módulos + Inversor)</th>
              <th>Armazenamento</th>
              <th class="num-col">Investimento Total</th>
              <th class="num-col">Economia/Mês</th>
              <th class="center-col">Payback</th>
              <th class="no-print" style="text-align:right;">Ação</th>
            </tr>
          </thead>
          <tbody>
            ${hist.map(d => `
              <tr>
                <td><strong class="badge-mono">#${d.id}</strong></td>
                <td>${d.data}</td>
                <td>${d.localidade} (HSP ${num(d.hsp, 1)})</td>
                <td class="num-col">${num(d.consumo_kwh_mes)} kWh/mês</td>
                <td class="num-col"><strong>${num(d.potencia_instalada_kwp, 2)} kWp</strong></td>
                <td>${d.n_modulos}× <code>${d.modulo_id}</code> + <code>${d.inversor_id}</code></td>
                <td>${d.bateria_id ? `<span class="badge badge-warning">${d.n_baterias}× ${d.bateria_id} (${d.autonomia_h}h)</span>` : '<span class="badge badge-info">On-Grid</span>'}</td>
                <td class="num-col"><strong>${brl(d.c_total)}</strong></td>
                <td class="num-col">${brl(d.economia_mensal_brl)}/mês</td>
                <td class="center-col"><span class="badge badge-neutral">${num(d.payback_simples_anos)} anos</span></td>
                <td class="no-print" style="text-align:right;">
                  <button type="button" class="btn btn-sm btn-secondary" onclick="carregarDimensionamentoDoHistorico('${d.id}')">Carregar no Simulador</button>
                </td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      `;
    }

    function renderizarAbaDatasets(ds, dimAtual) {
      document.getElementById('pre-qa-output').textContent = ds.validacao_texto;

      const modAtivoId = dimAtual && dimAtual.selecao && dimAtual.selecao.modulo ? dimAtual.selecao.modulo.id : '';
      const invAtivoId = dimAtual && dimAtual.selecao && dimAtual.selecao.inversor ? dimAtual.selecao.inversor.id : '';
      const batAtivaId = dimAtual && dimAtual.armazenamento && dimAtual.armazenamento.bateria ? dimAtual.armazenamento.bateria.id : '';

      document.getElementById('tabela-ds-modulos').innerHTML = `
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Fabricante</th>
              <th>Modelo</th>
              <th class="num-col">Potência</th>
              <th class="num-col">Voc / Vmp</th>
              <th class="num-col">Isc / Imp</th>
              <th class="num-col">Eficiência</th>
              <th class="num-col">Preço Unit.</th>
              <th>Fornecedor / Coleta</th>
            </tr>
          </thead>
          <tbody>
            ${ds.modulos.map(m => `
              <tr class="${m.id === modAtivoId ? 'row-highlight' : ''}">
                <td><strong class="badge-mono">${m.id}</strong> ${m.id === modAtivoId ? '<span class="badge badge-info">Em uso</span>' : ''}</td>
                <td>${m.fabricante}</td>
                <td><strong>${m.modelo}</strong></td>
                <td class="num-col"><strong>${m.potencia_wp} Wp</strong></td>
                <td class="num-col">${num(m.voc_v)} V / ${num(m.vmp_v)} V</td>
                <td class="num-col">${num(m.isc_a)} A / ${num(m.imp_a)} A</td>
                <td class="num-col">${num(m.eficiencia_pct)}%</td>
                <td class="num-col"><strong>${brl(m.preco_brl)}</strong></td>
                <td><a href="${m.url_fonte}" target="_blank" rel="noopener" style="color:var(--brand-primary); font-size:0.75rem;">${m.fornecedor} (${m.data_coleta})</a></td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      `;

      document.getElementById('tabela-ds-inversores').innerHTML = `
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Fabricante</th>
              <th>Modelo</th>
              <th>Topologia</th>
              <th class="num-col">Pot. Nom / Máx FV</th>
              <th class="num-col">Janela MPPT</th>
              <th class="num-col">Corrente Máx</th>
              <th class="num-col">Eficiência</th>
              <th class="center-col">Bateria</th>
              <th class="num-col">Preço Unit.</th>
            </tr>
          </thead>
          <tbody>
            ${ds.inversores.map(i => `
              <tr class="${i.id === invAtivoId ? 'row-highlight' : ''}">
                <td><strong class="badge-mono">${i.id}</strong> ${i.id === invAtivoId ? '<span class="badge badge-info">Em uso</span>' : ''}</td>
                <td>${i.fabricante}</td>
                <td><strong>${i.modelo}</strong></td>
                <td><span class="badge ${i.compativel_bateria ? 'badge-warning' : 'badge-info'}">${i.compativel_bateria ? 'Híbrido' : 'On-Grid'}</span></td>
                <td class="num-col">${i.potencia_nominal_w} W / ${i.potencia_max_fv_w} W</td>
                <td class="num-col">${i.faixa_mppt_min_v}–${i.faixa_mppt_max_v} V (${i.numero_mppt} MPPT)</td>
                <td class="num-col">${num(i.corrente_max_entrada_a, 1)} A</td>
                <td class="num-col">${num(i.eficiencia_pct, 1)}%</td>
                <td class="center-col">${i.compativel_bateria ? `Sim (${i.tensao_bateria_min_v}–${i.tensao_bateria_max_v}V)` : 'Não'}</td>
                <td class="num-col"><strong>${brl(i.preco_brl)}</strong></td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      `;

      document.getElementById('tabela-ds-baterias').innerHTML = `
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Fabricante</th>
              <th>Modelo</th>
              <th>Química</th>
              <th class="num-col">Tensão Nom.</th>
              <th class="num-col">Capacidade</th>
              <th class="num-col">DoD / Vida Útil</th>
              <th class="num-col">Preço Unit.</th>
              <th>Fornecedor / Coleta</th>
            </tr>
          </thead>
          <tbody>
            ${ds.baterias.map(b => `
              <tr class="${b.id === batAtivaId ? 'row-highlight' : ''}">
                <td><strong class="badge-mono">${b.id}</strong> ${b.id === batAtivaId ? '<span class="badge badge-warning">Em uso</span>' : ''}</td>
                <td>${b.fabricante}</td>
                <td><strong>${b.modelo}</strong></td>
                <td><span class="badge badge-neutral">${b.tecnologia}</span></td>
                <td class="num-col">${num(b.tensao_nominal_v, 1)} V</td>
                <td class="num-col">${b.capacidade_ah} Ah / <strong>${num(b.capacidade_kwh)} kWh</strong></td>
                <td class="num-col">${b.dod_pct}% (${b.ciclos} ciclos)</td>
                <td class="num-col"><strong>${brl(b.preco_brl)}</strong></td>
                <td><a href="${b.url_fonte}" target="_blank" rel="noopener" style="color:var(--brand-primary); font-size:0.75rem;">${b.fornecedor} (${b.data_coleta})</a></td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      `;

      const listaHsp = obterListaHsp(ds);
      document.getElementById('tabela-ds-localidades').innerHTML = `
        <table>
          <thead>
            <tr>
              <th>Município</th>
              <th class="center-col">UF</th>
              <th class="num-col">Irradiação HSP (kWh/m²/dia)</th>
              <th>Fonte Oficial</th>
            </tr>
          </thead>
          <tbody>
            ${listaHsp.map(l => `
              <tr>
                <td><strong>${l.cidade}</strong></td>
                <td class="center-col"><span class="badge badge-neutral badge-mono">${l.uf}</span></td>
                <td class="num-col"><strong>${num(l.hsp, 2)} kWh/m²/dia</strong></td>
                <td><a href="${l.url_fonte}" target="_blank" rel="noopener" style="color:var(--brand-primary); font-size:0.75rem;">${l.fonte}</a></td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      `;
    }

    async function criarNovaResidencia() {
      const payload = {
        apelido: document.getElementById('nova-res-apelido').value.trim(),
        endereco: document.getElementById('nova-res-end').value.trim(),
        numero: document.getElementById('nova-res-num').value.trim(),
        tipo: document.getElementById('nova-res-tipo').value,
        cidade: document.getElementById('nova-res-cidade').value.trim(),
        uf: document.getElementById('nova-res-uf').value.trim().toUpperCase(),
        popular_padrao: document.getElementById('nova-res-popular-padrao').checked
      };
      const resp = await fetch('/api/imoveis', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const res = await resp.json();
      if (!res.ok) {
        alert('Erro ao cadastrar residência: ' + res.erro);
        return;
      }
      document.getElementById('painel-nova-casa').classList.remove('open');
      await carregarEstado(res.imovel_id);
    }

    async function adicionarCargaResidencia() {
      const payload = {
        imovel_id: ESTADO.imovel_selecionado_id,
        equipamento_id: document.getElementById('assoc-eq-select').value,
        nome: document.getElementById('assoc-eq-nome').value.trim(),
        categoria: document.getElementById('assoc-eq-cat').value.trim(),
        potencia_w: Number(document.getElementById('assoc-eq-pot').value),
        quantidade: Number(document.getElementById('assoc-eq-qtd').value),
        tempo_uso_h: Number(document.getElementById('assoc-eq-horas').value),
      };
      const resp = await fetch('/api/associacoes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const res = await resp.json();
      if (!res.ok) {
        alert('Erro de validação: ' + res.erro);
        return;
      }
      document.getElementById('painel-add-equip').classList.remove('open');
      await carregarEstado(ESTADO.imovel_selecionado_id);
    }

    async function removerCargaResidencia(assocId) {
      await fetch('/api/associacoes/remover', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ assoc_id: assocId })
      });
      await carregarEstado(ESTADO.imovel_selecionado_id);
    }

    async function restaurarCargasPadrao() {
      await fetch('/api/associacoes/restaurar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ imovel_id: ESTADO.imovel_selecionado_id })
      });
      await carregarEstado(ESTADO.imovel_selecionado_id);
    }

    async function executarDimensionamentoAPI() {
      const fb = document.getElementById('dim-feedback');
      fb.innerHTML = '';
      const listaHsp = obterListaHsp(ESTADO.datasets);
      const selLoc = document.getElementById('dim-localidade');
      const idxLoc = Number(selLoc.value || 0);
      const locObj = listaHsp[idxLoc] || {
        cidade: ESTADO.imovel_atual.cidade,
        uf: ESTADO.imovel_atual.uf,
        fonte: 'CRESESB/SunData'
      };

      const payload = {
        imovel_id: ESTADO.imovel_selecionado_id,
        consumo: Number(document.getElementById('dim-consumo').value),
        percentual: Number(document.getElementById('dim-percentual').value),
        cidade: locObj.cidade,
        uf: locObj.uf,
        hsp: Number(document.getElementById('dim-hsp').value),
        fonte_hsp: locObj.fonte,
        pr: Number(document.getElementById('dim-pr').value),
        modulo_id: document.getElementById('dim-modulo').value || null,
        inversor_id: document.getElementById('dim-inversor').value || null,
        com_bateria: document.getElementById('dim-com-bateria').value === 'true',
        autonomia: Number(document.getElementById('dim-autonomia').value),
        bateria_id: document.getElementById('dim-bateria').value || null,
        tarifa_kwh: Number(document.getElementById('dim-tarifa').value),
      };

      const resp = await fetch('/api/dimensionar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const res = await resp.json();
      if (!res.ok) {
        fb.innerHTML = `
          <div class="notice-box notice-error">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
              <strong>Bloqueio de Validação / Compatibilidade Técnica (PB18)</strong>
              <button type="button" class="btn btn-sm btn-subtle" onclick="document.getElementById('dim-feedback').innerHTML=''">Fechar aviso</button>
            </div>
            <div style="white-space:pre-line; font-family:var(--font-mono); font-size:0.75rem;">${res.erro}</div>
          </div>
        `;
        return;
      }

      fb.innerHTML = `
        <div class="notice-box notice-success" style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
          <span><strong>Projeto #${res.id_salvo} calculado, validado pelas regras C1–C8 e persistido em dados_sistema.json.</strong></span>
          <button type="button" class="btn btn-sm btn-subtle" onclick="document.getElementById('dim-feedback').innerHTML=''">Ocultar</button>
        </div>
      `;

      ESTADO.dimensionamento_atual = res.resultado;
      ESTADO.rejeitados_atuais = res.rejeitados_atuais;
      ESTADO.total_rejeitados = res.total_rejeitados;
      ESTADO.comparacao_atual = res.comparacao;
      ESTADO.proposta_txt = res.proposta_txt;
      ESTADO.comparacao_txt = res.comparacao_txt;
      ESTADO.dimensionamentos_salvos = res.dimensionamentos_salvos;

      atualizarKPIsTopo(ESTADO.imovel_atual, res.resultado);
      renderizarResultadoDimensionamento(res.resultado, ESTADO.imovel_atual.apelido, res.rejeitados_atuais, res.total_rejeitados);
      renderizarAbaComparacao(res.comparacao, ESTADO.imovel_atual.apelido);
      renderizarAbaProposta(ESTADO);
      renderizarAbaDatasets(ESTADO.datasets, res.resultado);
    }

    async function carregarDimensionamentoDoHistorico(idDim) {
      const d = (ESTADO.dimensionamentos_salvos || []).find(x => String(x.id) === String(idDim));
      if (!d) return;

      document.getElementById('dim-origem-consumo').value = 'conta';
      alternarOrigemConsumo();
      document.getElementById('dim-consumo').value = d.consumo_kwh_mes;
      document.getElementById('dim-percentual').value = d.percentual || 100;
      document.getElementById('dim-hsp').value = d.hsp || 5.0;
      document.getElementById('dim-pr').value = d.pr || 0.78;
      document.getElementById('dim-tarifa').value = d.tarifa_brl_kwh || 0.92;
      document.getElementById('dim-modulo').value = d.modulo_id || '';
      document.getElementById('dim-inversor').value = d.inversor_id || '';
      const temBat = Boolean(d.bateria_id);
      document.getElementById('dim-com-bateria').value = temBat ? 'true' : 'false';
      alternarCamposBateria();
      if (temBat) {
        document.getElementById('dim-autonomia').value = d.autonomia_h || 12;
        document.getElementById('dim-bateria').value = d.bateria_id || '';
      }

      if (MODULO_ATIVO !== 'all') {
        selecionarModuloAtivo('passo-2');
      } else {
        document.getElementById('passo-2').scrollIntoView({ behavior: 'smooth' });
      }
      await executarDimensionamentoAPI();
    }

    async function testarValidacaoErroPB18() {
      const fb = document.getElementById('dim-feedback');
      const resp = await fetch('/api/dimensionar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          imovel_id: ESTADO.imovel_selecionado_id,
          consumo: 455.31,
          percentual: 100,
          hsp: 5.0,
          pr: 0.78,
          inversor_id: 'INV001',
          com_bateria: true,
          autonomia: 12,
          tarifa_kwh: 0.92
        })
      });
      const res = await resp.json();
      fb.innerHTML = `
        <div class="notice-box notice-error">
          <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; margin-bottom:8px;">
            <strong>Demonstração de Validação Técnica PB18 (Tentativa de alocar Inversor On-Grid INV001 em Sistema Híbrido com Baterias)</strong>
            <button type="button" class="btn btn-sm btn-subtle" onclick="document.getElementById('dim-feedback').innerHTML=''">Fechar diagnóstico</button>
          </div>
          <div style="white-space:pre-line; font-family:var(--font-mono); font-size:0.75rem;">${res.erro}</div>
        </div>
      `;
    }

    async function recalcularComparacaoAPI() {
      const aut = Number(document.getElementById('comp-autonomia-input').value || 12);
      const resp = await fetch('/api/comparar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          imovel_id: ESTADO.imovel_selecionado_id,
          autonomia: aut,
          tarifa_kwh: Number(document.getElementById('dim-tarifa').value || 0.92)
        })
      });
      const res = await resp.json();
      if (!res.ok) {
        alert('Erro: ' + res.erro);
        return;
      }
      ESTADO.comparacao_atual = res.comparacao;
      renderizarAbaComparacao(res.comparacao, ESTADO.imovel_atual.apelido);
    }

    async function executarTestesQA() {
      const pre = document.getElementById('pre-qa-output');
      const btn = document.getElementById('btn-run-qa');
      if (btn) btn.disabled = true;
      pre.textContent = 'Executando suíte completa de testes automatizados (testes.py)...';
      try {
        const resp = await fetch('/api/testes');
        const res = await resp.json();
        pre.textContent = res.output;
      } finally {
        if (btn) btn.disabled = false;
      }
    }

    async function copiarLaudoTexto(btn) {
      const txt = document.getElementById('pre-proposta-consolidada').textContent || '';
      try {
        await navigator.clipboard.writeText(txt);
        const original = btn.textContent;
        btn.textContent = 'Laudo Copiado';
        setTimeout(() => { btn.textContent = original; }, 1800);
      } catch (e) {
        alert('Não foi possível copiar automaticamente.');
      }
    }

    window.addEventListener('DOMContentLoaded', () => carregarEstado());
  </script>
</body>
</html>
"""


class ServidorFotovoltaicoHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _enviar_json(self, dados_obj, status=200):
        corpo = json.dumps(dados_obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def _enviar_html(self, html_str, status=200):
        corpo = html_str.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self):
        parsed = urlparse(self.path)
        rota = parsed.path
        qs = parse_qs(parsed.query)

        if rota in ("/", "/index.html"):
            return self._enviar_html(HTML_APP)

        if rota == "/api/estado":
            im_id = qs.get("imovel_id", [None])[0]
            try:
                return self._enviar_json(montar_estado_completo(im_id))
            except Exception as e:
                return self._enviar_json({"ok": False, "erro": str(e)}, status=400)

        if rota == "/api/codigo":
            arq = qs.get("arquivo", ["fotovoltaico.py"])[0]
            permitidos = {"fotovoltaico.py", "sistema_analise_casa.py", "app_web.py", "testes.py"}
            if arq not in permitidos:
                return self._enviar_json({"ok": False, "erro": "Arquivo nao autorizado."}, status=400)
            caminho_py = os.path.join(fv.BASE_DIR, arq)
            with open(caminho_py, "r", encoding="utf-8-sig") as f:
                linhas = f.read().splitlines()
            numerado = "\n".join(f"{i+1:4d} | {ln}" for i, ln in enumerate(linhas))
            cabecalho = (
                f"# ==============================================================================\n"
                f"# ARQUIVO: {arq} ({len(linhas)} linhas) — EQUIPE LUMOS (SPRINT 3 FINAL)\n"
                f"# ==============================================================================\n\n"
            )
            return self._enviar_json({"ok": True, "arquivo": arq, "linhas": len(linhas), "conteudo": cabecalho + numerado})

        if rota == "/api/testes":
            buf = io.StringIO()
            with redirect_stdout(buf):
                ok = qa_testes.rodar_todos_os_testes()
            return self._enviar_json({"ok": ok, "output": buf.getvalue()})

        if rota == "/proposta_cliente.txt":
            if not ESTADO_ATIVO_CACHE.get("resultado"):
                montar_estado_completo()
            r_ativo = ESTADO_ATIVO_CACHE["resultado"]
            comp_ativo = ESTADO_ATIVO_CACHE["comparacao"]
            apelido_ativo = ESTADO_ATIVO_CACHE["apelido"] or "Residencia"
            conteudo = (
                fv.formatar_proposta(r_ativo, apelido_ativo)
                + "\n\n"
                + fv.formatar_comparacao_cenarios(comp_ativo, apelido_ativo)
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(conteudo)))
            self.end_headers()
            self.wfile.write(conteudo)
            return

        if rota == "/proposta_cliente.html":
            if not ESTADO_ATIVO_CACHE.get("resultado"):
                montar_estado_completo()
            r_ativo = ESTADO_ATIVO_CACHE["resultado"]
            comp_ativo = ESTADO_ATIVO_CACHE["comparacao"]
            apelido_ativo = ESTADO_ATIVO_CACHE["apelido"] or "Residencia"
            cargas_ativas = ESTADO_ATIVO_CACHE.get("cargas")
            caminho_html = fv.exportar_proposta_html(
                r_ativo, comp_ativo, apelido_ativo, cargas_residencia=cargas_ativas
            )
            with open(caminho_html, "r", encoding="utf-8-sig") as f:
                conteudo_html = f.read()
            return self._enviar_html(conteudo_html)

        self.send_error(404, "Rota nao encontrada")

    def do_POST(self):
        tamanho = int(self.headers.get("Content-Length", 0))
        bruto = self.rfile.read(tamanho).decode("utf-8") if tamanho > 0 else "{}"
        try:
            body = json.loads(bruto)
        except Exception:
            body = {}

        rota = urlparse(self.path).path
        sc.carregar_dados()

        if rota == "/api/imoveis":
            apelido = str(body.get("apelido") or "").strip()
            endereco = str(body.get("endereco") or "").strip()
            numero = str(body.get("numero") or "S/N").strip()
            tipo = str(body.get("tipo") or "Casa").strip()
            cidade = str(body.get("cidade") or "São Paulo").strip()
            uf = str(body.get("uf") or "SP").strip().upper()
            popular_padrao = bool(body.get("popular_padrao", True))
            if not apelido or not endereco:
                return self._enviar_json({"ok": False, "erro": "Informe o apelido e o endereco da residencia."}, status=400)
            if uf not in sc.UFS:
                return self._enviar_json({"ok": False, "erro": f"UF '{uf}' invalida."}, status=400)
            novo_id = sc.proximo_id("imovel")
            sc.dados["imoveis"][novo_id] = {
                "endereco": endereco,
                "numero": numero,
                "apelido": apelido,
                "tipo": tipo,
                "localizacao": {"cidade": cidade, "uf": uf},
                "dono_email": "demo@lumos.com",
            }
            if popular_padrao:
                cargas_demo = [
                    ("1", 1, 24.0),
                    ("2", 1, 0.75),
                    ("3", 2, 4.0),
                    ("4", 1, 4.0),
                    ("5", 1, 0.30),
                    ("7", 1, 1.0),
                    ("8", 1, 5.0),
                    ("10", 8, 5.0),
                ]
                for eq_id, qtd, horas in cargas_demo:
                    if eq_id in sc.dados["equipamentos"]:
                        sc.dados["associacoes"][sc.proximo_id("associacao")] = {
                            "imovel_id": novo_id,
                            "equipamento_id": eq_id,
                            "quantidade": qtd,
                            "tempo_uso": horas,
                        }
            sc.salvar_dados()
            return self._enviar_json({"ok": True, "imovel_id": novo_id})

        if rota == "/api/associacoes":
            imovel_id = str(body.get("imovel_id") or "")
            if imovel_id not in sc.dados["imoveis"]:
                return self._enviar_json({"ok": False, "erro": "Residencia nao encontrada."}, status=400)
            try:
                pot = fv.positivo("Potencia do equipamento (W)", body.get("potencia_w"))
                qtd = int(fv.positivo("Quantidade", body.get("quantidade")))
                horas = float(fv.nao_negativo("Tempo de uso diario (h)", body.get("tempo_uso_h")))
                if horas <= 0 or horas > 24:
                    raise ValueError("Tempo de uso diario deve estar entre 0,05 e 24 horas.")
            except ValueError as e:
                return self._enviar_json({"ok": False, "erro": str(e)}, status=400)

            eq_id = str(body.get("equipamento_id") or "")
            nome_eq = str(body.get("nome") or "Equipamento").strip()
            cat_eq = str(body.get("categoria") or "Geral").strip()

            if (
                eq_id not in sc.dados["equipamentos"]
                or sc.dados["equipamentos"][eq_id]["potencia"] != pot
                or sc.dados["equipamentos"][eq_id]["nome"] != nome_eq
            ):
                eq_id = sc.proximo_id("equipamento")
                sc.dados["equipamentos"][eq_id] = {
                    "nome": nome_eq,
                    "categoria": cat_eq,
                    "potencia": pot,
                    "pre_cadastrado": False,
                }

            assoc_id = sc.proximo_id("associacao")
            sc.dados["associacoes"][assoc_id] = {
                "imovel_id": imovel_id,
                "equipamento_id": eq_id,
                "quantidade": qtd,
                "tempo_uso": horas,
            }
            sc.salvar_dados()
            return self._enviar_json({"ok": True, "assoc_id": assoc_id})

        if rota == "/api/associacoes/editar":
            assoc_id = str(body.get("assoc_id") or "")
            if assoc_id not in sc.dados["associacoes"]:
                return self._enviar_json({"ok": False, "erro": "Associacao nao encontrada."}, status=400)
            try:
                qtd = int(fv.positivo("Quantidade", body.get("quantidade")))
                horas = float(fv.nao_negativo("Tempo de uso diario (h)", body.get("tempo_uso_h")))
                if horas <= 0 or horas > 24:
                    raise ValueError("Tempo de uso diario deve estar entre 0,05 e 24 horas.")
            except ValueError as e:
                return self._enviar_json({"ok": False, "erro": str(e)}, status=400)
            sc.dados["associacoes"][assoc_id]["quantidade"] = qtd
            sc.dados["associacoes"][assoc_id]["tempo_uso"] = horas
            sc.salvar_dados()
            return self._enviar_json({"ok": True})

        if rota == "/api/associacoes/remover":
            assoc_id = str(body.get("assoc_id") or "")
            if assoc_id in sc.dados["associacoes"]:
                del sc.dados["associacoes"][assoc_id]
                sc.salvar_dados()
            return self._enviar_json({"ok": True})

        if rota == "/api/associacoes/restaurar":
            imovel_id = str(body.get("imovel_id") or next(iter(sc.dados["imoveis"].keys())))
            for aid in [k for k, v in sc.dados["associacoes"].items() if v.get("imovel_id") == imovel_id]:
                del sc.dados["associacoes"][aid]
            cargas_demo = [
                ("1", 1, 24.0),
                ("2", 1, 0.75),
                ("3", 2, 4.0),
                ("4", 1, 4.0),
                ("5", 1, 0.30),
                ("7", 1, 1.0),
                ("8", 1, 5.0),
                ("10", 8, 5.0),
            ]
            for eq_id, qtd, horas in cargas_demo:
                if eq_id in sc.dados["equipamentos"]:
                    sc.dados["associacoes"][sc.proximo_id("associacao")] = {
                        "imovel_id": imovel_id,
                        "equipamento_id": eq_id,
                        "quantidade": qtd,
                        "tempo_uso": horas,
                    }
            sc.salvar_dados()
            return self._enviar_json({"ok": True})

        if rota == "/api/dimensionar":
            try:
                ds = fv.carregar_datasets_fv()
                imovel_id = str(body.get("imovel_id") or next(iter(sc.dados["imoveis"].keys())))
                imovel = sc.dados["imoveis"][imovel_id]
                pot_casa_w = sc.potencia_instalada_imovel(imovel_id)
                cidade = str(body.get("cidade") or imovel["localizacao"]["cidade"])
                uf = str(body.get("uf") or imovel["localizacao"]["uf"])
                hsp_val = fv.validar_hsp(body.get("hsp"))
                hsp_info = {
                    "cidade": cidade,
                    "uf": uf,
                    "hsp": hsp_val,
                    "fonte": str(body.get("fonte_hsp") or "CRESESB/SunData"),
                    "url_fonte": "https://cresesb.cepel.br/index.php?section=sundata",
                }
                consumo = fv.positivo("Consumo mensal (kWh/mes)", body.get("consumo"))
                percentual = body.get("percentual", 100)
                pr = fv.validar_pr(body.get("pr", 0.78))
                com_bateria = bool(body.get("com_bateria", False))
                autonomia = body.get("autonomia", 12) if com_bateria else None
                tarifa = fv.validar_tarifa(body.get("tarifa_kwh", 0.92))
                mod_id = body.get("modulo_id") or None
                inv_id = body.get("inversor_id") or None
                bat_id = body.get("bateria_id") or None

                r = fv.dimensionar_fv(
                    consumo,
                    percentual,
                    hsp_info,
                    ds,
                    com_bateria=com_bateria,
                    autonomia=autonomia,
                    origem="interface grafica web integrada",
                    tarifa_kwh=tarifa,
                    pr=pr,
                    potencia_residencia_w=pot_casa_w,
                    modulo_id=mod_id,
                    inversor_id=inv_id,
                    bateria_id=bat_id,
                )
                comp = fv.comparar_cenarios(
                    consumo,
                    percentual,
                    hsp_info,
                    ds,
                    autonomia_h=autonomia or 12,
                    tarifa_kwh=tarifa,
                    pr=pr,
                    potencia_residencia_w=pot_casa_w,
                )
                id_salvo = sc.salvar_dimensionamento_no_banco(imovel_id, r, {"cidade": cidade, "uf": uf}, hsp_info)

                ESTADO_ATIVO_CACHE["imovel_id"] = imovel_id
                ESTADO_ATIVO_CACHE["apelido"] = imovel["apelido"]
                ESTADO_ATIVO_CACHE["resultado"] = r
                ESTADO_ATIVO_CACHE["comparacao"] = comp

                historico = [dict(d, id=k) for k, d in sc.dados.get("dimensionamentos", {}).items()]
                historico.sort(key=lambda x: int(x["id"]) if str(x["id"]).isdigit() else 0, reverse=True)
                return self._enviar_json({
                    "ok": True,
                    "id_salvo": id_salvo,
                    "resultado": r,
                    "rejeitados_atuais": serializar_rejeitados(r.get("rejeitados", []), limite=20),
                    "total_rejeitados": len(r.get("rejeitados", [])),
                    "comparacao": comp,
                    "proposta_txt": fv.formatar_proposta(r, imovel["apelido"]),
                    "comparacao_txt": fv.formatar_comparacao_cenarios(comp, imovel["apelido"]),
                    "dimensionamentos_salvos": historico,
                })
            except fv.ErroDimensionamento as e:
                msg = f"{e}\n{fv.formatar_incompatibilidades(e.rejeitados, limite=8)}"
                return self._enviar_json({"ok": False, "erro": msg}, status=400)
            except Exception as e:
                return self._enviar_json({"ok": False, "erro": str(e)}, status=400)

        if rota == "/api/comparar":
            try:
                ds = fv.carregar_datasets_fv()
                imovel_id = str(body.get("imovel_id") or next(iter(sc.dados["imoveis"].keys())))
                imovel = sc.dados["imoveis"][imovel_id]
                loc = imovel.get("localizacao") or {"cidade": "São Paulo", "uf": "SP"}
                try:
                    hsp_info = fv.obter_hsp(loc["cidade"], loc["uf"], ds["hsp"])
                except ValueError:
                    hsp_info = fv.obter_hsp("São Paulo", "SP", ds["hsp"])
                consumo = sc.consumo_total_imovel(imovel_id) or 455.31
                pot_casa_w = sc.potencia_instalada_imovel(imovel_id)
                autonomia = fv.validar_autonomia(body.get("autonomia", 12))
                tarifa = fv.validar_tarifa(body.get("tarifa_kwh", 0.92))
                comp = fv.comparar_cenarios(
                    consumo,
                    100,
                    hsp_info,
                    ds,
                    autonomia_h=autonomia,
                    tarifa_kwh=tarifa,
                    potencia_residencia_w=pot_casa_w,
                )
                ESTADO_ATIVO_CACHE["comparacao"] = comp
                return self._enviar_json({"ok": True, "comparacao": comp})
            except Exception as e:
                return self._enviar_json({"ok": False, "erro": str(e)}, status=400)

        self.send_error(404, "Endpoint POST nao encontrado")


def encontrar_porta_livre(porta_inicial=8080):
    for p in range(porta_inicial, porta_inicial + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    return porta_inicial


def iniciar_servidor_web(abrir_navegador=True, porta=8080):
    sc.carregar_dados()
    montar_estado_completo()
    porta_real = encontrar_porta_livre(porta)
    servidor = HTTPServer(("127.0.0.1", porta_real), ServidorFotovoltaicoHandler)
    url = f"http://127.0.0.1:{porta_real}"

    print("=" * 84)
    print("  INTERFACE GRAFICA WEB INTEGRADA ATIVA (SPRINT 3 - EQUIPE LUMOS)")
    print(f"  Acesse no navegador: {url}")
    print("  (Para encerrar o servidor, feche esta janela ou pressione Ctrl+C)")
    print("=" * 84)

    if abrir_navegador:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()

    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor web encerrado.")
    finally:
        servidor.server_close()


if __name__ == "__main__":
    iniciar_servidor_web(abrir_navegador="--no-browser" not in sys.argv)

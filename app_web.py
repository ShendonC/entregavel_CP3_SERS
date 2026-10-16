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
    hsp_info = fv.obter_hsp(imovel_atual["cidade"], imovel_atual["uf"], ds["hsp"])
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
            "hsp_localidades": ds["hsp"],
            "validacao_ok": ok_ds,
            "validacao_texto": msg_ds,
        },
        "dimensionamento_atual": comp["sem_bateria"],
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
  <title>Sistema de Orçamento Fotovoltaico — Equipe Lumos (FIAP)</title>
  <style>
    :root {
      --bg: #f1f5f9;
      --card: #ffffff;
      --ink: #0f172a;
      --muted: #475569;
      --accent: #0284c7;
      --accent-dark: #0369a1;
      --green: #059669;
      --amber: #d97706;
      --red: #dc2626;
      --border: #e2e8f0;
    }
    * { box-sizing: border-box; }
    html { scroll-behavior: smooth; }
    body {
      margin: 0;
      font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
      background: var(--bg);
      color: var(--ink);
      line-height: 1.5;
    }
    /* TOPBAR FIXA */
    .topbar {
      position: sticky;
      top: 0;
      z-index: 50;
      background: #0f172a;
      color: #fff;
      padding: 14px 24px;
      box-shadow: 0 4px 14px rgba(15, 23, 42, 0.18);
    }
    .topbar-inner {
      max-width: 1240px;
      margin: 0 auto;
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: center;
      gap: 14px;
    }
    .brand h1 {
      margin: 0;
      font-size: 19px;
      font-weight: 700;
      color: #f8fafc;
    }
    .brand p {
      margin: 2px 0 0 0;
      font-size: 12.5px;
      color: #94a3b8;
    }
    .nav-steps {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      align-items: center;
    }
    .nav-pill {
      text-decoration: none;
      color: #cbd5e1;
      background: rgba(255,255,255,0.08);
      padding: 7px 13px;
      border-radius: 8px;
      font-size: 13px;
      font-weight: 600;
      transition: 0.15s;
      border: 1px solid rgba(255,255,255,0.12);
    }
    .nav-pill:hover {
      background: var(--accent);
      color: #fff;
      border-color: var(--accent);
    }
    .container {
      max-width: 1240px;
      margin: 22px auto 60px auto;
      padding: 0 20px;
    }
    /* BARRA DE SELEÇÃO DA RESIDÊNCIA E KPIS */
    .residence-bar {
      background: #fff;
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 16px 20px;
      margin-bottom: 18px;
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: center;
      gap: 14px;
      box-shadow: 0 1px 3px rgba(15, 23, 42, 0.05);
    }
    .residence-selector {
      display: flex;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
    }
    .residence-selector label {
      font-size: 13px;
      font-weight: 700;
      color: var(--muted);
      text-transform: uppercase;
    }
    .residence-selector select {
      padding: 9px 14px;
      border-radius: 8px;
      border: 1px solid #cbd5e1;
      font-size: 14.5px;
      font-weight: 600;
      color: var(--ink);
      background: #f8fafc;
      min-width: 320px;
      cursor: pointer;
    }
    .kpi-strip {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 14px;
      margin-bottom: 24px;
    }
    @media (max-width: 900px) {
      .kpi-strip { grid-template-columns: repeat(2, 1fr); }
    }
    .kpi-card {
      background: var(--card);
      border: 1px solid var(--border);
      border-top: 4px solid var(--accent);
      border-radius: 12px;
      padding: 15px 18px;
      box-shadow: 0 1px 3px rgba(15, 23, 42, 0.05);
    }
    .kpi-card.green { border-top-color: var(--green); }
    .kpi-card.amber { border-top-color: var(--amber); }
    .kpi-card .k-title {
      font-size: 11.5px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: var(--muted);
      font-weight: 700;
    }
    .kpi-card .k-val {
      font-size: 22px;
      font-weight: 800;
      margin-top: 4px;
      color: var(--ink);
    }
    .kpi-card .k-sub {
      font-size: 12px;
      color: var(--muted);
      margin-top: 3px;
    }
    /* SEÇÕES NUMERADAS (FLUXO PASSO A PASSO) */
    .step-section {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 24px;
      margin-bottom: 26px;
      box-shadow: 0 2px 6px rgba(15, 23, 42, 0.04);
      scroll-margin-top: 84px;
    }
    .step-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 12px;
      border-bottom: 2px solid #f1f5f9;
      padding-bottom: 14px;
      margin-bottom: 18px;
    }
    .step-title-group {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .step-number {
      background: var(--accent);
      color: #fff;
      width: 34px;
      height: 34px;
      border-radius: 50%;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font-weight: 800;
      font-size: 16px;
      flex-shrink: 0;
    }
    .step-header h2 {
      margin: 0;
      font-size: 19px;
      color: var(--ink);
    }
    .step-header p {
      margin: 2px 0 0 0;
      font-size: 13px;
      color: var(--muted);
    }
    .grid-2 {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 18px;
    }
    @media (max-width: 900px) {
      .grid-2 { grid-template-columns: 1fr; }
    }
    .form-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
      gap: 14px;
      margin-bottom: 16px;
    }
    .field label {
      display: block;
      font-size: 12px;
      font-weight: 700;
      color: #334155;
      margin-bottom: 5px;
    }
    .field input, .field select {
      width: 100%;
      padding: 9px 11px;
      border-radius: 8px;
      border: 1px solid #cbd5e1;
      font-size: 13.5px;
      background: #fff;
      color: var(--ink);
    }
    .btn {
      display: inline-flex;
      align-items: center;
      gap: 7px;
      padding: 9px 16px;
      border-radius: 8px;
      border: none;
      font-size: 13.5px;
      font-weight: 600;
      cursor: pointer;
      transition: 0.15s;
      text-decoration: none;
    }
    .btn-primary { background: var(--accent); color: #fff; }
    .btn-primary:hover { background: var(--accent-dark); }
    .btn-success { background: var(--green); color: #fff; }
    .btn-success:hover { background: #047857; }
    .btn-danger { background: #fee2e2; color: #b91c1c; padding: 5px 10px; font-size: 12px; }
    .btn-danger:hover { background: #fecaca; }
    .btn-outline { background: #f8fafc; color: var(--ink); border: 1px solid #cbd5e1; }
    .btn-outline:hover { background: #e2e8f0; }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13.2px;
      margin-top: 6px;
    }
    th, td {
      padding: 10px 12px;
      border-bottom: 1px solid var(--border);
      text-align: left;
      vertical-align: middle;
    }
    th {
      background: #f8fafc;
      font-weight: 700;
      color: #334155;
      font-size: 12px;
      text-transform: uppercase;
    }
    tr:hover td { background: #f8fafc; }
    .badge {
      display: inline-block;
      padding: 3px 9px;
      border-radius: 999px;
      font-size: 11.5px;
      font-weight: 700;
    }
    .badge-green { background: #d1fae5; color: #065f46; }
    .badge-amber { background: #fef3c7; color: #92400e; }
    .badge-blue { background: #e0f2fe; color: #075985; }
    .alert-box {
      padding: 15px 18px;
      border-radius: 10px;
      margin-top: 14px;
      font-size: 13.5px;
      border-left: 4px solid var(--accent);
      background: #f0f9ff;
    }
    .alert-error {
      border-left-color: var(--red);
      background: #fef2f2;
      color: #991b1b;
      white-space: pre-line;
    }
    .alert-success {
      border-left-color: var(--green);
      background: #ecfdf5;
      color: #065f46;
    }
    .bar-bg {
      width: 100%;
      background: #e2e8f0;
      height: 8px;
      border-radius: 999px;
      overflow: hidden;
    }
    .bar-fill {
      background: linear-gradient(90deg, #0284c7, #10b981);
      height: 100%;
    }
    .collapsible-panel {
      display: none;
      background: #f8fafc;
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 18px;
      margin-bottom: 18px;
    }
    .collapsible-panel.open { display: block; }
    .sub-tabs {
      display: flex;
      gap: 8px;
      margin-bottom: 14px;
      flex-wrap: wrap;
    }
    .sub-tab-btn {
      padding: 7px 14px;
      border-radius: 8px;
      border: 1px solid #cbd5e1;
      background: #f8fafc;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
    }
    .sub-tab-btn.active {
      background: var(--ink);
      color: #fff;
      border-color: var(--ink);
    }
    .sub-pane { display: none; }
    .sub-pane.active { display: block; }
    @media print {
      .topbar, .no-print { display: none !important; }
      body { background: #fff; }
      .step-section { box-shadow: none; border: 1px solid #cbd5e1; page-break-inside: avoid; }
    }
  </style>
</head>
<body>

  <!-- BARRA DE NAVEGAÇÃO SUPERIOR (4 PASSOS DIRETOS) -->
  <header class="topbar">
    <div class="topbar-inner">
      <div class="brand">
        <h1>☀️ Sistema de Dimensionamento e Orçamento Fotovoltaico</h1>
        <p>Equipe Lumos (FIAP): Pietro Lorande (RM 569125) • Luiz Otávio (RM 569977) • Maria Eduarda (RM 574094)</p>
      </div>
      <nav class="nav-steps no-print">
        <a class="nav-pill" href="#passo-1">1. Residência e Consumo</a>
        <a class="nav-pill" href="#passo-2">2. Dimensionamento e Orçamento</a>
        <a class="nav-pill" href="#passo-3">3. Sem vs. Com Baterias</a>
        <a class="nav-pill" href="#passo-4">4. Catálogo CSV & Proposta</a>
      </nav>
    </div>
  </header>

  <main class="container">

    <!-- SELETOR DA RESIDÊNCIA ATIVA + BOTÕES DE AÇÃO RÁPIDA -->
    <div class="residence-bar">
      <div class="residence-selector">
        <label for="top-imovel-select">🏠 Residência Selecionada:</label>
        <select id="top-imovel-select" onchange="trocarImovelAtivo(this.value)"></select>
      </div>
      <div class="no-print" style="display:flex; gap:10px; flex-wrap:wrap;">
        <button class="btn btn-outline" onclick="window.print()">🖨️ Imprimir / Salvar Proposta em PDF</button>
        <a class="btn btn-outline" href="/proposta_cliente.txt" download="proposta_cliente.txt">📥 Baixar Proposta (.txt)</a>
      </div>
    </div>

    <!-- 4 INDICADORES PRINCIPAIS NO TOPO -->
    <div class="kpi-strip">
      <div class="kpi-card">
        <div class="k-title">Demanda da Residência</div>
        <div class="k-val" id="kpi-consumo">--</div>
        <div class="k-sub" id="kpi-demanda-sub">--</div>
      </div>
      <div class="kpi-card">
        <div class="k-title">Sistema Solar Dimensionado</div>
        <div class="k-val" id="kpi-potencia-fv">--</div>
        <div class="k-sub" id="kpi-fv-sub">--</div>
      </div>
      <div class="kpi-card green">
        <div class="k-title">Geração Estimada & Atendimento</div>
        <div class="k-val" id="kpi-geracao">--</div>
        <div class="k-sub" id="kpi-geracao-sub">--</div>
      </div>
      <div class="kpi-card amber">
        <div class="k-title">Investimento & Payback Simples</div>
        <div class="k-val" id="kpi-orcamento">--</div>
        <div class="k-sub" id="kpi-payback-sub">--</div>
      </div>
    </div>

    <!-- =====================================================================
         PASSO 1: RESIDÊNCIA E DEMANDA ENERGÉTICA (SPRINTS 1 E 2 -> SPRINT 3)
         ===================================================================== -->
    <section id="passo-1" class="step-section">
      <div class="step-header">
        <div class="step-title-group">
          <span class="step-number">1</span>
          <div>
            <h2>Residência e Consumo dos Equipamentos Elétricos</h2>
            <p>Dados recuperados automaticamente do cadastro da residência (<code id="lbl-endereco-res"></code>)</p>
          </div>
        </div>
        <div class="no-print" style="display:flex; gap:8px; flex-wrap:wrap;">
          <button class="btn btn-outline" onclick="togglePainel('painel-add-equip')">+ Adicionar Equipamento</button>
          <button class="btn btn-outline" onclick="togglePainel('painel-nova-casa')">+ Cadastrar Outra Residência</button>
        </div>
      </div>

      <!-- Painel recolhível: Adicionar Equipamento -->
      <div id="painel-add-equip" class="collapsible-panel no-print">
        <h3 style="margin-top:0; font-size:15px;">Associar Equipamento Elétrico à Residência</h3>
        <div class="form-grid">
          <div class="field">
            <label>Escolher do Catálogo</label>
            <select id="assoc-eq-select" onchange="preencherEquipamentoCatalogo()"></select>
          </div>
          <div class="field">
            <label>Nome do Aparelho</label>
            <input type="text" id="assoc-eq-nome" placeholder="Ex.: Ar-Condicionado Split">
          </div>
          <div class="field">
            <label>Cômodo / Categoria</label>
            <input type="text" id="assoc-eq-cat" placeholder="Ex.: Climatização">
          </div>
          <div class="field">
            <label>Potência Unitária (W)</label>
            <input type="number" id="assoc-eq-pot" value="1200" min="1" step="10">
          </div>
          <div class="field">
            <label>Quantidade</label>
            <input type="number" id="assoc-eq-qtd" value="1" min="1" step="1">
          </div>
          <div class="field">
            <label>Uso Diário (horas/dia, 0 a 24)</label>
            <input type="number" id="assoc-eq-horas" value="4" min="0.1" max="24" step="0.25">
          </div>
        </div>
        <button class="btn btn-success" onclick="adicionarCargaResidencia()">Salvar Equipamento e Recalcular Demanda</button>
      </div>

      <!-- Painel recolhível: Cadastrar Nova Residência -->
      <div id="painel-nova-casa" class="collapsible-panel no-print">
        <h3 style="margin-top:0; font-size:15px;">Cadastrar Nova Residência</h3>
        <div class="form-grid">
          <div class="field">
            <label>Identificação / Apelido</label>
            <input type="text" id="nova-res-apelido" placeholder="Ex.: Casa de Praia - Santos">
          </div>
          <div class="field">
            <label>Endereço</label>
            <input type="text" id="nova-res-end" placeholder="Ex.: Av. Atlântica">
          </div>
          <div class="field">
            <label>Número</label>
            <input type="text" id="nova-res-num" placeholder="250">
          </div>
          <div class="field">
            <label>Cidade</label>
            <input type="text" id="nova-res-cidade" value="São Paulo">
          </div>
          <div class="field">
            <label>UF</label>
            <input type="text" id="nova-res-uf" value="SP" maxlength="2">
          </div>
          <div class="field">
            <label>Tipo</label>
            <select id="nova-res-tipo">
              <option value="Casa">Casa Residencial</option>
              <option value="Apartamento">Apartamento</option>
            </select>
          </div>
        </div>
        <button class="btn btn-primary" onclick="criarNovaResidencia()">Criar Residência</button>
      </div>

      <!-- Tabela de Equipamentos da Casa -->
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Equipamento Elétrico</th>
            <th>Categoria</th>
            <th style="text-align:right">Potência Unit.</th>
            <th style="text-align:center">Qtd</th>
            <th style="text-align:right">Potência Instalada</th>
            <th style="text-align:right">Uso/Dia</th>
            <th style="text-align:right">Consumo Diário (E_dia)</th>
            <th style="text-align:right">Consumo Mensal (E_mês)</th>
            <th style="width:140px">Participação</th>
            <th class="no-print"></th>
          </tr>
        </thead>
        <tbody id="tabela-cargas-body"></tbody>
      </table>
    </section>

    <!-- =====================================================================
         PASSO 2: SIMULADOR DE DIMENSIONAMENTO SOLAR, BATERIAS E ORÇAMENTO
         ===================================================================== -->
    <section id="passo-2" class="step-section">
      <div class="step-header">
        <div class="step-title-group">
          <span class="step-number">2</span>
          <div>
            <h2>Dimensionamento Solar Fotovoltaico, Armazenamento e Orçamento</h2>
            <p>Configure os parâmetros abaixo ou utilize a seleção automática otimizada nos datasets CSV</p>
          </div>
        </div>
        <div class="no-print">
          <button class="btn btn-outline" onclick="testarValidacaoErroPB18()">🛡️ Testar Bloqueio de Erro / Incompatibilidade</button>
        </div>
      </div>

      <!-- Formulário Limpo de Configuração -->
      <div class="no-print" style="background:#f8fafc; border:1px solid var(--border); border-radius:10px; padding:18px; margin-bottom:20px;">
        <div class="form-grid">
          <div class="field">
            <label>Origem da Demanda</label>
            <select id="dim-origem-consumo" onchange="alternarOrigemConsumo()">
              <option value="calculado">Calculado pelos Equipamentos da Casa</option>
              <option value="conta">Informar Consumo da Conta Manualmente</option>
            </select>
          </div>
          <div class="field">
            <label>Consumo Mensal E_mês (kWh/mês)</label>
            <input type="number" id="dim-consumo" step="10" min="1">
          </div>
          <div class="field">
            <label>Meta de Atendimento (%)</label>
            <input type="number" id="dim-percentual" value="100" min="1" max="100" step="5">
          </div>
          <div class="field">
            <label>Município / Irradiação Solar (CRESESB)</label>
            <select id="dim-localidade" onchange="atualizarHspDaTabela()"></select>
          </div>
          <div class="field">
            <label>HSP (kWh/m²/dia)</label>
            <input type="number" id="dim-hsp" step="0.1" min="3.0" max="7.0">
          </div>
          <div class="field">
            <label>Performance Ratio — PR (padrão 0,78)</label>
            <input type="number" id="dim-pr" value="0.78" step="0.01" min="0.50" max="0.95">
          </div>
          <div class="field">
            <label>Tipo de Sistema (Com ou Sem Baterias)</label>
            <select id="dim-com-bateria" onchange="alternarCamposBateria()">
              <option value="false">Sem Baterias (On-Grid Convencional)</option>
              <option value="true">Com Baterias (Híbrido com Backup)</option>
            </select>
          </div>
          <div class="field" id="box-dim-autonomia">
            <label>Autonomia de Baterias (horas)</label>
            <input type="number" id="dim-autonomia" value="12" min="1" max="72" step="1">
          </div>
          <div class="field">
            <label>Tarifa da Concessionária (R$/kWh)</label>
            <input type="number" id="dim-tarifa" value="0.92" min="0.10" max="10.0" step="0.02">
          </div>
          <div class="field">
            <label>Módulo Fotovoltaico (modulos.csv)</label>
            <select id="dim-modulo"></select>
          </div>
          <div class="field">
            <label>Inversor Solar (inversores.csv)</label>
            <select id="dim-inversor"></select>
          </div>
          <div class="field" id="box-dim-bateria">
            <label>Bateria LiFePO4 (baterias.csv)</label>
            <select id="dim-bateria"></select>
          </div>
        </div>
        <button class="btn btn-primary" onclick="executarDimensionamentoAPI()">⚡ Calcular Dimensionamento e Atualizar Orçamento</button>
        <div id="dim-feedback"></div>
      </div>

      <!-- Resultado Técnico + Orçamento + Economia/Payback -->
      <div id="painel-resultado-dimensionamento"></div>
    </section>

    <!-- =====================================================================
         PASSO 3: COMPARAÇÃO LADO A LADO (SEM BATERIAS vs COM BATERIAS)
         ===================================================================== -->
    <section id="passo-3" class="step-section">
      <div class="step-header">
        <div class="step-title-group">
          <span class="step-number">3</span>
          <div>
            <h2>Comparativo Lado a Lado: Sem Baterias (On-Grid) vs. Com Baterias (Híbrido)</h2>
            <p>Análise técnica, financeira e de tempo de retorno (Payback Simples) para tomada de decisão do cliente</p>
          </div>
        </div>
        <div class="no-print" style="display:flex; gap:8px; align-items:center;">
          <label style="font-size:12.5px; font-weight:700; color:var(--muted);">Autonomia do Cenário Híbrido (h):</label>
          <input type="number" id="comp-autonomia-input" value="12" min="1" max="72" style="width:74px; padding:6px 10px; border:1px solid #cbd5e1; border-radius:6px;">
          <button class="btn btn-primary" onclick="recalcularComparacaoAPI()">Atualizar Comparativo</button>
        </div>
      </div>

      <div id="tabela-comparacao-container"></div>

      <div id="box-questao-9-comp" class="alert-box alert-success" style="margin-top:18px;"></div>
    </section>

    <!-- =====================================================================
         PASSO 4: CATÁLOGO DE EQUIPAMENTOS (CSV), HISTÓRICO E PROPOSTA FORMAL
         ===================================================================== -->
    <section id="passo-4" class="step-section">
      <div class="step-header">
        <div class="step-title-group">
          <span class="step-number">4</span>
          <div>
            <h2>Catálogo de Equipamentos (Datasets CSV), Histórico Salvo e Proposta Formal</h2>
            <p>Consulte as bases de dados utilizadas pelo sistema, os dimensionamentos salvos em JSON e o laudo completo</p>
          </div>
        </div>
      </div>

      <div class="sub-tabs no-print">
        <button class="sub-tab-btn active" onclick="abrirSubAba('sub-modulos', this)">Módulos Fotovoltaicos (10)</button>
        <button class="sub-tab-btn" onclick="abrirSubAba('sub-inversores', this)">Inversores Solares (8)</button>
        <button class="sub-tab-btn" onclick="abrirSubAba('sub-baterias', this)">Baterias LiFePO4 (6)</button>
        <button class="sub-tab-btn" onclick="abrirSubAba('sub-historico', this)">Histórico Salvo (JSON)</button>
        <button class="sub-tab-btn" onclick="abrirSubAba('sub-laudo', this)">Laudo Textual Completo (.txt)</button>
        <button class="sub-tab-btn" onclick="abrirSubAba('sub-qa', this)">Validação & Testes QA</button>
      </div>

      <div id="sub-modulos" class="sub-pane active">
        <div id="tabela-ds-modulos"></div>
      </div>
      <div id="sub-inversores" class="sub-pane">
        <div id="tabela-ds-inversores"></div>
      </div>
      <div id="sub-baterias" class="sub-pane">
        <div id="tabela-ds-baterias"></div>
      </div>
      <div id="sub-historico" class="sub-pane">
        <div id="tabela-historico-container"></div>
      </div>
      <div id="sub-laudo" class="sub-pane">
        <pre id="pre-proposta-consolidada" style="background:#0f172a; color:#f8fafc; padding:18px; border-radius:8px; overflow-x:auto; font-size:12.5px; line-height:1.45;"></pre>
      </div>
      <div id="sub-qa" class="sub-pane">
        <div style="margin-bottom:10px;">
          <button class="btn btn-success" onclick="executarTestesQA()">🧪 Executar Bateria Completa de Testes Automatizados (testes.py)</button>
        </div>
        <pre id="pre-qa-output" style="background:#0f172a; color:#a7f3d0; padding:16px; border-radius:8px; overflow-x:auto; font-size:13px;"></pre>
      </div>
    </section>

  </main>

  <script>
    let ESTADO = null;

    function brl(v) {
      return 'R$ ' + Number(v || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }
    function num(v, c = 2) {
      return Number(v || 0).toLocaleString('pt-BR', { minimumFractionDigits: c, maximumFractionDigits: c });
    }

    function togglePainel(id) {
      document.getElementById(id).classList.toggle('open');
    }

    function abrirSubAba(id, btn) {
      document.querySelectorAll('.sub-pane').forEach(p => p.classList.remove('active'));
      document.querySelectorAll('.sub-tab-btn').forEach(b => b.classList.remove('active'));
      document.getElementById(id).classList.add('active');
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

    function renderizarTudo() {
      if (!ESTADO || !ESTADO.ok) return;
      const im = ESTADO.imovel_atual;
      const dim = ESTADO.dimensionamento_atual;
      const comp = ESTADO.comparacao_atual;
      const ds = ESTADO.datasets;

      document.getElementById('top-imovel-select').innerHTML = ESTADO.imoveis.map(i =>
        `<option value="${i.id}" ${i.id === im.id ? 'selected' : ''}>#${i.id} — ${i.apelido} (${i.cidade}/${i.uf} • ${num(i.consumo_mensal_kwh)} kWh/mês)</option>`
      ).join('');

      document.getElementById('lbl-endereco-res').textContent = `${im.endereco}, ${im.numero} — ${im.cidade}/${im.uf}`;

      document.getElementById('kpi-consumo').textContent = `${num(im.consumo_mensal_kwh)} kWh/mês`;
      document.getElementById('kpi-demanda-sub').textContent = `Diário: ${num(im.consumo_diario_kwh, 2)} kWh/dia • Potência: ${num(im.potencia_instalada_w, 0)} W (${num(im.potencia_instalada_kw, 2)} kW)`;
      document.getElementById('kpi-potencia-fv').textContent = `${num(dim.p_inst, 2)} kWp (${dim.selecao.config.n_modulos} módulos)`;
      document.getElementById('kpi-fv-sub').textContent = `Necessário: ${num(dim.p_fv, 2)} kWp • HSP: ${num(dim.hsp_info.hsp, 1)} • PR: ${num(dim.pr * 100, 0)}%`;
      document.getElementById('kpi-geracao').textContent = `${num(dim.geracao_mes, 1)} kWh/mês`;
      document.getElementById('kpi-geracao-sub').textContent = `Diária: ${num(dim.geracao_dia, 2)} kWh/dia • Atendimento: ${num(dim.comparacao_geracao.atendimento_pct, 1)}%`;
      document.getElementById('kpi-orcamento').textContent = brl(dim.orcamento.c_total);
      document.getElementById('kpi-payback-sub').textContent = `Economia: ${brl(dim.economia.economia_mensal_brl)}/mês • Payback: ${num(dim.payback.payback_simples_anos)} anos`;

      renderizarAbaResidencia(im);
      preencherFormularioDimensionamento(im, dim, ds);
      renderizarResultadoDimensionamento(dim, im.apelido);
      renderizarAbaComparacao(comp, im.apelido);
      renderizarAbaProposta(ESTADO);
      renderizarAbaDatasets(ds);
    }

    function renderizarAbaResidencia(im) {
      const selCat = document.getElementById('assoc-eq-select');
      selCat.innerHTML = `<option value="CUSTOM">-- Digitar equipamento personalizado --</option>` +
        ESTADO.catalogo_equipamentos.map(e =>
          `<option value="${e.id}" data-nome="${e.nome}" data-cat="${e.categoria}" data-pot="${e.potencia}">${e.nome} (${e.categoria} — ${e.potencia} W)</option>`
        ).join('');
      if (ESTADO.catalogo_equipamentos.length > 0) {
        selCat.selectedIndex = 1;
        preencherEquipamentoCatalogo();
      }

      const totalMes = im.consumo_mensal_kwh || 1;
      const tbody = document.getElementById('tabela-cargas-body');
      if (im.cargas.length === 0) {
        tbody.innerHTML = `<tr><td colspan="11" style="text-align:center;">Nenhum equipamento associado a esta residência.</td></tr>`;
        return;
      }
      tbody.innerHTML = im.cargas.map((c, idx) => {
        const pct = (c.consumo_mensal_kwh / totalMes) * 100;
        return `
          <tr>
            <td>${idx + 1}º</td>
            <td><strong>${c.nome}</strong></td>
            <td>${c.categoria}</td>
            <td style="text-align:right">${num(c.potencia_w, 0)} W</td>
            <td style="text-align:center">${c.quantidade}</td>
            <td style="text-align:right">${num(c.potencia_total_w, 0)} W</td>
            <td style="text-align:right">${num(c.tempo_uso_h, 1)} h/dia</td>
            <td style="text-align:right">${num(c.consumo_diario_kwh, 2)} kWh/dia</td>
            <td style="text-align:right"><strong>${num(c.consumo_mensal_kwh, 2)} kWh/mês</strong></td>
            <td><div class="bar-bg"><div class="bar-fill" style="width:${Math.min(100, pct)}%"></div></div> <small>${num(pct, 1)}%</small></td>
            <td class="no-print"><button class="btn btn-danger" onclick="removerCargaResidencia('${c.assoc_id}')">Remover</button></td>
          </tr>
        `;
      }).join('') + `
        <tr style="background:#f0f9ff; font-weight:700;">
          <td colspan="4">TOTAL DA RESIDÊNCIA</td>
          <td style="text-align:center">${im.cargas.reduce((s, x) => s + x.quantidade, 0)} un.</td>
          <td style="text-align:right">${num(im.potencia_instalada_w, 0)} W (${num(im.potencia_instalada_kw, 2)} kW)</td>
          <td style="text-align:right">--</td>
          <td style="text-align:right">${num(im.consumo_diario_kwh, 2)} kWh/dia</td>
          <td style="text-align:right">${num(im.consumo_mensal_kwh, 2)} kWh/mês</td>
          <td>100%</td>
          <td class="no-print"></td>
        </tr>
      `;
    }

    function preencherEquipamentoCatalogo() {
      const sel = document.getElementById('assoc-eq-select');
      const opt = sel.options[sel.selectedIndex];
      if (!opt || opt.value === 'CUSTOM') return;
      document.getElementById('assoc-eq-nome').value = opt.getAttribute('data-nome') || '';
      document.getElementById('assoc-eq-cat').value = opt.getAttribute('data-cat') || '';
      document.getElementById('assoc-eq-pot').value = opt.getAttribute('data-pot') || 100;
    }

    function preencherFormularioDimensionamento(im, dim, ds) {
      const inpCons = document.getElementById('dim-consumo');
      if (document.getElementById('dim-origem-consumo').value === 'calculado') {
        inpCons.value = im.consumo_mensal_kwh.toFixed(2);
      }

      const selLoc = document.getElementById('dim-localidade');
      selLoc.innerHTML = ds.hsp_localidades.map((l, idx) =>
        `<option value="${idx}" data-hsp="${l.hsp}" ${l.cidade.toLowerCase() === im.cidade.toLowerCase() && l.uf === im.uf ? 'selected' : ''}>${l.cidade}/${l.uf} — HSP ${num(l.hsp, 1)} kWh/m²/dia</option>`
      ).join('');
      document.getElementById('dim-hsp').value = dim.hsp_info.hsp;

      document.getElementById('dim-modulo').innerHTML =
        `<option value="">Automático (Menor Custo Compatível)</option>` +
        ds.modulos.map(m => `<option value="${m.id}">[${m.id}] ${m.fabricante} ${m.modelo} (${m.potencia_wp} Wp — ${brl(m.preco_brl)})</option>`).join('');

      document.getElementById('dim-inversor').innerHTML =
        `<option value="">Automático Compatível</option>` +
        ds.inversores.map(i => `<option value="${i.id}">[${i.id}] ${i.fabricante} ${i.modelo} (${i.tipo}, ${i.potencia_nominal_w}W — ${brl(i.preco_brl)})</option>`).join('');

      document.getElementById('dim-bateria').innerHTML =
        `<option value="">Automático Compatível (LiFePO4)</option>` +
        ds.baterias.map(b => `<option value="${b.id}">[${b.id}] ${b.fabricante} ${b.modelo} (${b.capacidade_kwh} kWh, DoD ${b.dod_pct}% — ${brl(b.preco_brl)})</option>`).join('');

      alternarCamposBateria();
    }

    function alternarOrigemConsumo() {
      const modo = document.getElementById('dim-origem-consumo').value;
      const inp = document.getElementById('dim-consumo');
      if (modo === 'calculado' && ESTADO) {
        inp.value = ESTADO.imovel_atual.consumo_mensal_kwh.toFixed(2);
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
      document.getElementById('box-dim-autonomia').style.opacity = comBat ? '1' : '0.4';
      document.getElementById('box-dim-bateria').style.opacity = comBat ? '1' : '0.4';
    }

    function renderizarResultadoDimensionamento(r, apelido) {
      const s = r.selecao, arm = r.armazenamento, orc = r.orcamento, h = r.hsp_info;
      const compG = r.comparacao_geracao, econ = r.economia, pay = r.payback;
      const mod = s.modulo, inv = s.inversor, cfg = s.config;

      const linhasOrc = orc.itens.map(i => `
        <tr>
          <td><strong>${i.categoria}</strong></td>
          <td><strong>[${i.id_equipamento}] ${i.fabricante} ${i.modelo}</strong><br><small style="color:var(--muted)">Fonte: ${i.fonte}</small></td>
          <td style="text-align:center">${i.qtd}</td>
          <td style="text-align:right">${brl(i.preco_unitario)}</td>
          <td style="text-align:right"><strong>${brl(i.subtotal)}</strong></td>
        </tr>
      `).join('') + orc.outros.map(o => `
        <tr>
          <td>Instalação e Homologação</td>
          <td>${o[0]} <small style="color:var(--muted)">(${o[2]})</small></td>
          <td style="text-align:center">1</td>
          <td style="text-align:right">${brl(o[1])}</td>
          <td style="text-align:right">${brl(o[1])}</td>
        </tr>
      `).join('');

      let blocoBatHtml = `<span class="badge badge-blue">Sistema On-Grid Sem Baterias</span> Sem banco de armazenamento (0 kWh, custo adicional R$ 0,00).`;
      if (arm.ativo && arm.bateria) {
        const b = arm.bateria;
        blocoBatHtml = `
          <strong>${arm.n_baterias}× [${b.id}] ${b.fabricante} ${b.modelo}</strong> (${b.tecnologia}, ${num(b.tensao_nominal_v, 1)}V, ${num(b.capacidade_kwh)} kWh/un, DoD ${num(b.dod_pct, 0)}%)<br>
          Autonomia de <strong>${num(arm.autonomia_h, 0)}h</strong> (Energia necessária: ${num(arm.energia_autonomia_kwh, 2)} kWh • Capacidade instalada: <strong>${num(arm.capacidade_instalada_kwh)} kWh nominais / ${num(arm.capacidade_util_kwh)} kWh úteis</strong>)
        `;
      }

      document.getElementById('painel-resultado-dimensionamento').innerHTML = `
        <div class="grid-2">
          <div>
            <h3 style="margin-top:0; font-size:16px;">2.1 Especificação Técnica do Sistema Dimensionado</h3>
            <table>
              <tbody>
                <tr><th style="width:36%">Recurso Solar</th><td><strong>${h.cidade}/${h.uf}</strong> • HSP = <strong>${num(h.hsp)} kWh/m²/dia</strong> • PR = <strong>${num(r.pr * 100, 0)}%</strong><br><small style="color:var(--muted)">Fonte: ${h.fonte}</small></td></tr>
                <tr><th>Potência Fotovoltaica</th><td>Necessária: <strong>${num(r.p_fv, 2)} kWp</strong> • Instalada: <strong>${num(r.p_inst, 2)} kWp</strong><br><small style="color:var(--muted)">Cálculo: P_FV = ${num(r.consumo_diario, 2)} kWh/dia ÷ (${num(h.hsp)} × ${num(r.pr)})</small></td></tr>
                <tr><th>Módulos Selecionados</th><td><strong>${cfg.n_modulos}× [${mod.id}] ${mod.fabricante} ${mod.modelo}</strong><br><small style="color:var(--muted)">${mod.potencia_wp} Wp • Eficiência ${num(mod.eficiencia_pct)}% • Área total ${num(cfg.area_m2, 1)} m²</small></td></tr>
                <tr><th>Inversor Compatível</th><td><strong>[${inv.id}] ${inv.fabricante} ${inv.modelo}</strong> (${inv.tipo}, ${inv.potencia_nominal_w}W)<br><small style="color:var(--muted)">Eficiência ${num(inv.eficiencia_pct, 1)}% • Carregamento DC/AC = ${num(cfg.ratio_dc_ac)} • MPPT ${inv.faixa_mppt_min_v}-${inv.faixa_mppt_max_v}V</small></td></tr>
                <tr><th>Geração & Atendimento</th><td><strong>${num(r.geracao_dia, 2)} kWh/dia</strong> • <strong>${num(r.geracao_mes, 1)} kWh/mês</strong> (<span class="badge badge-green">${num(compG.atendimento_pct, 1)}% da demanda</span>)<br><small style="color:var(--muted)">Compensada na conta: ${num(compG.energia_compensada_kwh_mes)} kWh/mês • Excedente: ${num(compG.energia_excedente_kwh_mes)} kWh/mês</small></td></tr>
                <tr><th>Armazenamento</th><td>${blocoBatHtml}</td></tr>
              </tbody>
            </table>
          </div>

          <div>
            <h3 style="margin-top:0; font-size:16px;">2.2 Orçamento Detalhado, Economia e Payback Simples</h3>
            <table>
              <thead>
                <tr><th>Item</th><th>Equipamento / Descrição</th><th style="text-align:center">Qtd</th><th style="text-align:right">Unitário</th><th style="text-align:right">Subtotal</th></tr>
              </thead>
              <tbody>
                ${linhasOrc}
                <tr style="background:#f8fafc"><td colspan="4" style="text-align:right"><strong>Subtotal dos Equipamentos (Datasets CSV)</strong></td><td style="text-align:right"><strong>${brl(orc.c_equipamentos)}</strong></td></tr>
                <tr style="background:#e0f2fe"><td colspan="4" style="text-align:right"><strong>Investimento Total (Sistema Instalado)</strong></td><td style="text-align:right"><strong>${brl(orc.c_total)}</strong></td></tr>
              </tbody>
            </table>

            <div class="alert-box" style="margin-top:12px;">
              <div style="display:flex; justify-content:space-between; flex-wrap:wrap; gap:8px;">
                <div><strong>Economia Mensal:</strong> ${brl(econ.economia_mensal_brl)}/mês</div>
                <div><strong>Economia Anual:</strong> ${brl(econ.economia_anual_brl)}/ano</div>
              </div>
              <div style="margin-top:8px;">
                <strong>Payback Simples:</strong>
                <span class="badge badge-green">${pay.payback_formatado} (Investimento Total)</span>
                <span class="badge badge-blue">${num(pay.payback_apenas_equipamentos_anos)} anos (Apenas Equipamentos)</span>
              </div>
              <div style="margin-top:6px; font-size:11.5px; color:var(--muted);">
                * Estimativa preliminar simples (Investimento ÷ Economia Anual), sem considerar inflação energética ou reajustes tarifários futuros.
              </div>
            </div>
          </div>
        </div>
      `;
    }

    function renderizarAbaComparacao(comp, apelido) {
      const a = comp.sem_bateria, b = comp.com_bateria;
      const modA = a.selecao.modulo, invA = a.selecao.inversor, cfgA = a.selecao.config;
      const modB = b.selecao.modulo, invB = b.selecao.inversor, cfgB = b.selecao.config;
      const batB = b.armazenamento.bateria;

      document.getElementById('tabela-comparacao-container').innerHTML = `
        <table>
          <thead>
            <tr>
              <th>Indicador Técnico / Financeiro</th>
              <th>Cenário 1: Sem Baterias (On-Grid Convencional)</th>
              <th>Cenário 2: Com Baterias (Híbrido + Backup ${num(b.armazenamento.autonomia_h, 0)}h)</th>
            </tr>
          </thead>
          <tbody>
            <tr><td>Módulos Fotovoltaicos</td><td>${cfgA.n_modulos}× ${modA.fabricante} ${modA.modelo} (${modA.potencia_wp}W) → <strong>${num(a.p_inst, 2)} kWp</strong></td><td>${cfgB.n_modulos}× ${modB.fabricante} ${modB.modelo} (${modB.potencia_wp}W) → <strong>${num(b.p_inst, 2)} kWp</strong></td></tr>
            <tr><td>Inversor Selecionado</td><td>[${invA.id}] ${invA.fabricante} ${invA.modelo} (${invA.tipo}, ${invA.potencia_nominal_w}W)</td><td>[${invB.id}] ${invB.fabricante} ${invB.modelo} (${invB.tipo}, ${invB.potencia_nominal_w}W)</td></tr>
            <tr><td>Geração Mensal e Atendimento</td><td><strong>${num(a.geracao_mes, 1)} kWh/mês</strong> (${num(a.comparacao_geracao.atendimento_pct, 1)}% do consumo)</td><td><strong>${num(b.geracao_mes, 1)} kWh/mês</strong> (${num(b.comparacao_geracao.atendimento_pct, 1)}% do consumo)</td></tr>
            <tr><td>Banco de Baterias e Autonomia</td><td>Sem baterias (0 h de backup em queda de rede)</td><td><strong>${b.armazenamento.n_baterias}× [${batB.id}] ${batB.fabricante} ${batB.modelo}</strong> (${num(b.armazenamento.capacidade_instalada_kwh)} kWh / ${num(b.armazenamento.autonomia_h, 0)}h de autonomia)</td></tr>
            <tr><td>Custo dos Equipamentos (CSV)</td><td><strong>${brl(a.orcamento.c_equipamentos)}</strong></td><td><strong>${brl(b.orcamento.c_equipamentos)}</strong> (+${brl(comp.diferenca_equipamentos_brl)})</td></tr>
            <tr><td>Investimento Total Instalado</td><td><strong>${brl(a.orcamento.c_total)}</strong></td><td><strong>${brl(b.orcamento.c_total)}</strong> (+${brl(comp.diferenca_investimento_total_brl)} / +${num(comp.acrescimo_percentual, 1)}%)</td></tr>
            <tr><td>Economia Mensal / Anual na Fatura</td><td><strong>${brl(a.economia.economia_mensal_brl)}/mês</strong> (${brl(a.economia.economia_anual_brl)}/ano)</td><td><strong>${brl(b.economia.economia_mensal_brl)}/mês</strong> (${brl(b.economia.economia_anual_brl)}/ano)</td></tr>
            <tr><td>Payback Simples (Só Equipamentos)</td><td><span class="badge badge-green">${num(a.payback.payback_apenas_equipamentos_anos)} anos</span></td><td><span class="badge badge-amber">${num(b.payback.payback_apenas_equipamentos_anos)} anos</span></td></tr>
            <tr><td>Payback Simples (Investimento Total)</td><td><span class="badge badge-green">${a.payback.payback_formatado}</span></td><td><span class="badge badge-amber">${b.payback.payback_formatado}</span></td></tr>
          </tbody>
        </table>
      `;

      document.getElementById('box-questao-9-comp').innerHTML = `
        <h3 style="margin-top:0; font-size:15.5px; color:#065f46;">Recomendação Técnica e Econômica para ${apelido}</h3>
        <p style="white-space:pre-line; margin:0;">${comp.analise_questao_final}</p>
      `;
    }

    function renderizarAbaProposta(est) {
      document.getElementById('pre-proposta-consolidada').textContent =
        est.proposta_txt + "\\n\\n" + est.comparacao_txt;

      const hist = est.dimensionamentos_salvos || [];
      if (hist.length === 0) {
        document.getElementById('tabela-historico-container').innerHTML = `<p>Nenhum dimensionamento salvo ainda.</p>`;
        return;
      }
      document.getElementById('tabela-historico-container').innerHTML = `
        <table>
          <thead>
            <tr><th>ID</th><th>Data</th><th>Localidade / HSP</th><th>Consumo</th><th>Potência FV</th><th>Módulos & Inversor</th><th>Armazenamento</th><th style="text-align:right">Investimento Total</th><th style="text-align:right">Economia/Mês</th><th>Payback</th></tr>
          </thead>
          <tbody>
            ${hist.map(d => `
              <tr>
                <td><strong>#${d.id}</strong></td>
                <td>${d.data}</td>
                <td>${d.localidade} (HSP ${num(d.hsp, 1)})</td>
                <td>${num(d.consumo_kwh_mes)} kWh/mês</td>
                <td><strong>${num(d.potencia_instalada_kwp, 2)} kWp</strong></td>
                <td>${d.n_modulos}× ${d.modulo_id} + ${d.inversor_id}</td>
                <td>${d.bateria_id ? `${d.n_baterias}× ${d.bateria_id} (${d.autonomia_h}h)` : 'Sem baterias (On-Grid)'}</td>
                <td style="text-align:right"><strong>${brl(d.c_total)}</strong></td>
                <td style="text-align:right">${brl(d.economia_mensal_brl)}/mês</td>
                <td><span class="badge badge-blue">${num(d.payback_simples_anos)} anos</span></td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      `;
    }

    function renderizarAbaDatasets(ds) {
      document.getElementById('pre-qa-output').textContent = ds.validacao_texto;

      document.getElementById('tabela-ds-modulos').innerHTML = `
        <table>
          <thead><tr><th>ID</th><th>Fabricante</th><th>Modelo</th><th style="text-align:right">Potência</th><th style="text-align:right">Voc / Vmp</th><th style="text-align:right">Isc / Imp</th><th style="text-align:right">Eficiência</th><th style="text-align:right">Preço Unit.</th><th>Fonte</th></tr></thead>
          <tbody>
            ${ds.modulos.map(m => `
              <tr>
                <td><strong>${m.id}</strong></td><td>${m.fabricante}</td><td>${m.modelo}</td>
                <td style="text-align:right"><strong>${m.potencia_wp} Wp</strong></td>
                <td style="text-align:right">${num(m.voc_v)} V / ${num(m.vmp_v)} V</td>
                <td style="text-align:right">${num(m.isc_a)} A / ${num(m.imp_a)} A</td>
                <td style="text-align:right">${num(m.eficiencia_pct)}%</td>
                <td style="text-align:right"><strong>${brl(m.preco_brl)}</strong></td>
                <td><small>${m.fornecedor} (${m.data_coleta})</small></td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      `;

      document.getElementById('tabela-ds-inversores').innerHTML = `
        <table>
          <thead><tr><th>ID</th><th>Fabricante</th><th>Modelo</th><th>Tipo</th><th style="text-align:right">Pot. Nom / Máx FV</th><th style="text-align:right">Faixa MPPT</th><th style="text-align:right">Eficiência</th><th style="text-align:center">Bateria</th><th style="text-align:right">Preço Unit.</th></tr></thead>
          <tbody>
            ${ds.inversores.map(i => `
              <tr>
                <td><strong>${i.id}</strong></td><td>${i.fabricante}</td><td>${i.modelo}</td>
                <td><span class="badge ${i.compativel_bateria ? 'badge-amber' : 'badge-blue'}">${i.tipo}</span></td>
                <td style="text-align:right">${i.potencia_nominal_w} W / ${i.potencia_max_fv_w} W</td>
                <td style="text-align:right">${i.faixa_mppt_min_v}-${i.faixa_mppt_max_v} V (${i.numero_mppt} MPPT)</td>
                <td style="text-align:right">${num(i.eficiencia_pct, 1)}%</td>
                <td style="text-align:center">${i.compativel_bateria ? 'SIM (40-60V)' : 'NÃO'}</td>
                <td style="text-align:right"><strong>${brl(i.preco_brl)}</strong></td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      `;

      document.getElementById('tabela-ds-baterias').innerHTML = `
        <table>
          <thead><tr><th>ID</th><th>Fabricante</th><th>Modelo</th><th>Tecnologia</th><th style="text-align:right">Tensão</th><th style="text-align:right">Capacidade</th><th style="text-align:right">DoD / Ciclos</th><th style="text-align:right">Preço Unit.</th><th>Fonte</th></tr></thead>
          <tbody>
            ${ds.baterias.map(b => `
              <tr>
                <td><strong>${b.id}</strong></td><td>${b.fabricante}</td><td>${b.modelo}</td><td>${b.tecnologia}</td>
                <td style="text-align:right">${num(b.tensao_nominal_v, 1)} V</td>
                <td style="text-align:right">${b.capacidade_ah} Ah / <strong>${num(b.capacidade_kwh)} kWh</strong></td>
                <td style="text-align:right">${b.dod_pct}% (${b.ciclos} ciclos)</td>
                <td style="text-align:right"><strong>${brl(b.preco_brl)}</strong></td>
                <td><small>${b.fornecedor} (${b.data_coleta})</small></td>
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

    async function executarDimensionamentoAPI() {
      const fb = document.getElementById('dim-feedback');
      fb.innerHTML = '';
      const selLoc = document.getElementById('dim-localidade');
      const idxLoc = Number(selLoc.value || 0);
      const locObj = ESTADO.datasets.hsp_localidades[idxLoc] || { cidade: ESTADO.imovel_atual.cidade, uf: ESTADO.imovel_atual.uf, fonte: 'CRESESB' };

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
        fb.innerHTML = `<div class="alert-box alert-error"><strong>❌ Erro de Validação / Compatibilidade Técnica:</strong>\n${res.erro}</div>`;
        return;
      }
      fb.innerHTML = `<div class="alert-box alert-success">✅ <strong>Dimensionamento #${res.id_salvo} calculado e salvo em dados_sistema.json!</strong></div>`;
      ESTADO.dimensionamento_atual = res.resultado;
      ESTADO.comparacao_atual = res.comparacao;
      ESTADO.proposta_txt = res.proposta_txt;
      ESTADO.comparacao_txt = res.comparacao_txt;
      ESTADO.dimensionamentos_salvos = res.dimensionamentos_salvos;
      renderizarResultadoDimensionamento(res.resultado, ESTADO.imovel_atual.apelido);
      renderizarAbaComparacao(res.comparacao, ESTADO.imovel_atual.apelido);
      renderizarAbaProposta(ESTADO);
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
      fb.innerHTML = `<div class="alert-box alert-error"><strong>🛡️ Demonstração de Validação Técnica (Tentativa de usar Inversor On-Grid INV001 num Sistema com Baterias):</strong>\n${res.erro}</div>`;
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
      pre.textContent = 'Executando bateria completa de testes automatizados (testes.py)...';
      const resp = await fetch('/api/testes');
      const res = await resp.json();
      pre.textContent = res.output;
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

        if rota == "/api/testes":
            buf = io.StringIO()
            with redirect_stdout(buf):
                ok = qa_testes.rodar_todos_os_testes()
            return self._enviar_json({"ok": ok, "output": buf.getvalue()})

        if rota == "/proposta_cliente.txt":
            est = montar_estado_completo()
            conteudo = (est["proposta_txt"] + "\n\n" + est["comparacao_txt"]).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(conteudo)))
            self.end_headers()
            self.wfile.write(conteudo)
            return

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
                    raise ValueError("Tempo de uso diario deve estar entre 0,1 e 24 horas.")
            except ValueError as e:
                return self._enviar_json({"ok": False, "erro": str(e)}, status=400)

            eq_id = str(body.get("equipamento_id") or "")
            nome_eq = str(body.get("nome") or "Equipamento").strip()
            cat_eq = str(body.get("categoria") or "Geral").strip()

            if eq_id not in sc.dados["equipamentos"] or sc.dados["equipamentos"][eq_id]["potencia"] != pot or sc.dados["equipamentos"][eq_id]["nome"] != nome_eq:
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

        if rota == "/api/associacoes/remover":
            assoc_id = str(body.get("assoc_id") or "")
            if assoc_id in sc.dados["associacoes"]:
                del sc.dados["associacoes"][assoc_id]
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

                historico = [dict(d, id=k) for k, d in sc.dados.get("dimensionamentos", {}).items()]
                historico.reverse()
                return self._enviar_json({
                    "ok": True,
                    "id_salvo": id_salvo,
                    "resultado": r,
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
                hsp_info = fv.obter_hsp(loc["cidade"], loc["uf"], ds["hsp"])
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
        servidor.server_close()


if __name__ == "__main__":
    iniciar_servidor_web(abrir_navegador="--no-browser" not in sys.argv)

#   ============================================================
#   app_web.py - INTERFACE GRAFICA WEB INTEGRADA (SPRINT 3 - FINAL)
#   Sistema de Dimensionamento Energetico Residencial
#   Disciplina: Solucoes em Energias Renovaveis e Sustentaveis (Prof. Alvaro Goncalves)
#
#   Equipe Lumos - FIAP:
#   - Pietro Lorande | RM 569125
#   - Luiz Otavio Brito Freixo (Luiz Otavio Britto Freixo) | RM 569977
#   - Maria Eduarda Lemos | RM 574094
#   ============================================================
#
#   Servidor Web Full-Stack usando biblioteca padrao do Python (http.server)
#   integrado diretamente ao motor de calculo (fotovoltaico.py), ao banco JSON
#   (dados_sistema.json) e aos datasets estruturados (modulos.csv, inversores.csv,
#   baterias.csv e hsp_localidades.csv).
#
#   Executar: python app_web.py  (ou duplo clique em RODAR_PROJETO.bat)
#   ============================================================

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
    """Carrega dados persistidos, datasets e calcula o estado completo para a interface grafica."""
    sc.carregar_dados()
    ds = fv.carregar_datasets_fv()
    val_ok, val_texto = fv.validar_datasets_fv()

    imoveis_lista = []
    for im_id, im in sc.dados["imoveis"].items():
        loc = im.get("localizacao") or {"cidade": "São Paulo", "uf": "SP"}
        e_mes = round(sc.consumo_total_imovel(im_id), 2)
        e_dia = round(sc.consumo_diario_imovel(im_id), 3)
        pot_w = round(sc.potencia_instalada_imovel(im_id), 1)
        cargas = []
        for assoc_id, a in sc.listar_associacoes_do_imovel(im_id).items():
            eq = sc.dados["equipamentos"].get(a.get("equipamento_id"))
            if eq:
                kwh_m = round(sc.calcular_consumo_associacao(a), 2)
                cargas.append({
                    "assoc_id": assoc_id,
                    "equipamento_id": a["equipamento_id"],
                    "nome": eq["nome"],
                    "categoria": eq["categoria"],
                    "potencia_w": float(eq["potencia"]),
                    "quantidade": int(a["quantidade"]),
                    "tempo_uso_h": float(a["tempo_uso"]),
                    "consumo_mensal_kwh": kwh_m,
                    "consumo_diario_kwh": round(kwh_m / 30.0, 3),
                    "potencia_total_w": round(float(eq["potencia"]) * int(a["quantidade"]), 1),
                })
        cargas.sort(key=lambda x: x["consumo_mensal_kwh"], reverse=True)
        imoveis_lista.append({
            "id": im_id,
            "apelido": im["apelido"],
            "endereco": im["endereco"],
            "numero": im["numero"],
            "tipo": im["tipo"],
            "cidade": loc["cidade"],
            "uf": loc["uf"],
            "dono_email": im.get("dono_email", "demo@lumos.com"),
            "consumo_mensal_kwh": e_mes,
            "consumo_diario_kwh": e_dia,
            "potencia_instalada_w": pot_w,
            "potencia_instalada_kw": round(pot_w / 1000.0, 3),
            "cargas": cargas,
        })

    if not imoveis_lista:
        sc.popular_residencia_demonstracao()
        sc.salvar_dados()
        return montar_estado_completo()

    ids_validos = {im["id"] for im in imoveis_lista}
    if not id_imovel_selecionado or str(id_imovel_selecionado) not in ids_validos:
        id_imovel_selecionado = imoveis_lista[0]["id"]

    imovel_atual = next(im for im in imoveis_lista if im["id"] == str(id_imovel_selecionado))

    try:
        hsp_info = fv.obter_hsp(imovel_atual["cidade"], imovel_atual["uf"], ds["hsp"])
    except ValueError:
        hsp_info = {
            "cidade": imovel_atual["cidade"],
            "uf": imovel_atual["uf"],
            "hsp": 5.0,
            "fonte": "CRESESB/SunData (valor de referencia)",
            "url_fonte": "https://cresesb.cepel.br/index.php?section=sundata",
        }

    consumo_ref = imovel_atual["consumo_mensal_kwh"] if imovel_atual["consumo_mensal_kwh"] > 0 else 455.31
    comp = fv.comparar_cenarios(
        consumo_ref,
        100,
        hsp_info,
        ds,
        autonomia_h=12,
        tarifa_kwh=fv.PARAMETROS_FV["tarifa_padrao_brl_kwh"],
        pr=fv.PARAMETROS_FV["eta_global"],
        potencia_residencia_w=imovel_atual["potencia_instalada_w"],
        origem="calculado pelos equipamentos cadastrados na residencia",
    )

    if not sc.dados.get("dimensionamentos"):
        loc_obj = {"cidade": imovel_atual["cidade"], "uf": imovel_atual["uf"]}
        sc.salvar_dimensionamento_no_banco(imovel_atual["id"], comp["sem_bateria"], loc_obj, hsp_info)
        sc.salvar_dimensionamento_no_banco(imovel_atual["id"], comp["com_bateria"], loc_obj, hsp_info)

    cargas_html = [
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
    fv.exportar_proposta_txt(comp["sem_bateria"], comp, imovel_atual["apelido"])
    fv.exportar_proposta_html(comp["sem_bateria"], comp, imovel_atual["apelido"], cargas_residencia=cargas_html)

    catalogo_eq = [
        {"id": eq_id, "nome": eq["nome"], "categoria": eq["categoria"], "potencia": eq["potencia"]}
        for eq_id, eq in sc.dados["equipamentos"].items()
    ]
    historico_dim = [
        dict(d, id=dim_id)
        for dim_id, d in sc.dados.get("dimensionamentos", {}).items()
    ]
    historico_dim.reverse()

    return {
        "ok": True,
        "imovel_selecionado_id": imovel_atual["id"],
        "imovel_atual": imovel_atual,
        "imoveis": imoveis_lista,
        "catalogo_equipamentos": catalogo_eq,
        "datasets": {
            "modulos": ds["modulos"],
            "inversores": ds["inversores"],
            "baterias": ds["baterias"],
            "hsp_localidades": list(ds["hsp"].values()),
            "validacao_ok": val_ok,
            "validacao_texto": val_texto,
        },
        "parametros_padrao": fv.PARAMETROS_FV,
        "hsp_atual": hsp_info,
        "dimensionamento_atual": comp["sem_bateria"],
        "comparacao_atual": comp,
        "proposta_txt": fv.formatar_proposta(comp["sem_bateria"], imovel_atual["apelido"]),
        "comparacao_txt": fv.formatar_comparacao_cenarios(comp, imovel_atual["apelido"]),
        "dimensionamentos_salvos": historico_dim,
    }


HTML_APP = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Sistema de Dimensionamento e Orcamento Fotovoltaico | Equipe Lumos - FIAP (Sprint 3 Final)</title>
  <style>
    :root {
      --bg: #f1f5f9;
      --surface: #ffffff;
      --ink: #0f172a;
      --muted: #475569;
      --primary: #0284c7;
      --primary-dark: #0369a1;
      --navy: #0f172a;
      --navy-light: #1e3a8a;
      --green: #059669;
      --green-bg: #d1fae5;
      --amber: #d97706;
      --amber-bg: #fef3c7;
      --red: #dc2626;
      --red-bg: #fee2e2;
      --border: #e2e8f0;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
      background: var(--bg);
      color: var(--ink);
      line-height: 1.5;
    }
    .topbar {
      background: linear-gradient(135deg, var(--navy) 0%, var(--navy-light) 100%);
      color: #fff;
      padding: 20px 28px;
      box-shadow: 0 4px 12px rgba(15, 23, 42, 0.15);
    }
    .topbar-inner {
      max-width: 1280px;
      margin: 0 auto;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 16px;
    }
    .topbar h1 { margin: 0; font-size: 21px; font-weight: 700; letter-spacing: -0.01em; }
    .topbar .sub { margin: 4px 0 0 0; font-size: 13px; color: #cbd5e1; }
    .res-selector-box {
      background: rgba(255, 255, 255, 0.12);
      border: 1px solid rgba(255, 255, 255, 0.25);
      padding: 10px 14px;
      border-radius: 10px;
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .res-selector-box label { font-size: 12px; font-weight: 600; color: #e2e8f0; text-transform: uppercase; }
    .res-selector-box select {
      padding: 7px 12px;
      border-radius: 6px;
      border: none;
      font-weight: 600;
      font-size: 13.5px;
      color: var(--ink);
      background: #fff;
      cursor: pointer;
    }
    .main-wrap { max-width: 1280px; margin: 20px auto; padding: 0 20px 40px 20px; }
    .kpi-row {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 14px;
      margin-bottom: 18px;
    }
    .kpi-card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 14px 18px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.03);
    }
    .kpi-card .k-label { font-size: 11.5px; font-weight: 700; text-transform: uppercase; color: var(--muted); }
    .kpi-card .k-val { font-size: 21px; font-weight: 800; color: var(--ink); margin-top: 4px; }
    .kpi-card .k-sub { font-size: 12px; color: var(--muted); margin-top: 2px; }
    .tabs-nav {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      background: var(--surface);
      padding: 10px;
      border-radius: 10px;
      border: 1px solid var(--border);
      margin-bottom: 20px;
    }
    .tab-btn {
      border: 1px solid transparent;
      background: #f8fafc;
      color: var(--muted);
      font-weight: 600;
      font-size: 13.5px;
      padding: 10px 16px;
      border-radius: 8px;
      cursor: pointer;
      transition: all 0.15s;
    }
    .tab-btn:hover { background: #e0f2fe; color: var(--primary-dark); }
    .tab-btn.active {
      background: var(--primary);
      color: #fff;
      box-shadow: 0 2px 6px rgba(2, 132, 199, 0.25);
    }
    .tab-pane { display: none; }
    .tab-pane.active { display: block; }
    .card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 22px 24px;
      margin-bottom: 20px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.03);
    }
    .card h2 {
      margin: 0 0 14px 0;
      font-size: 17.5px;
      color: var(--navy-light);
      border-bottom: 2px solid var(--border);
      padding-bottom: 10px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 10px;
    }
    .card h3 { margin: 16px 0 8px 0; font-size: 15px; color: var(--ink); }
    .form-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
      gap: 14px;
      margin-bottom: 16px;
    }
    .field label {
      display: block;
      font-size: 12px;
      font-weight: 600;
      color: var(--muted);
      margin-bottom: 5px;
    }
    .field input, .field select {
      width: 100%;
      padding: 9px 11px;
      border: 1px solid #cbd5e1;
      border-radius: 7px;
      font-size: 13.5px;
      color: var(--ink);
      background: #fff;
    }
    .field input:focus, .field select:focus {
      outline: none;
      border-color: var(--primary);
      box-shadow: 0 0 0 3px rgba(2, 132, 199, 0.15);
    }
    .btn {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 9px 16px;
      border-radius: 7px;
      font-size: 13.5px;
      font-weight: 600;
      border: 1px solid transparent;
      cursor: pointer;
      text-decoration: none;
    }
    .btn-primary { background: var(--primary); color: #fff; }
    .btn-primary:hover { background: var(--primary-dark); }
    .btn-success { background: var(--green); color: #fff; }
    .btn-success:hover { background: #047857; }
    .btn-outline { background: #f8fafc; color: var(--ink); border-color: #cbd5e1; }
    .btn-outline:hover { background: #e2e8f0; }
    .btn-danger { background: var(--red-bg); color: var(--red); border-color: #fca5a5; padding: 5px 10px; font-size: 12px; }
    .btn-danger:hover { background: #fecaca; }
    table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 13.5px; }
    th, td { border: 1px solid var(--border); padding: 9px 12px; text-align: left; vertical-align: middle; }
    th { background: #f8fafc; font-weight: 600; color: var(--ink); }
    tr:hover td { background: #f8fafc; }
    .badge {
      display: inline-block;
      padding: 3px 9px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 700;
    }
    .badge-green { background: var(--green-bg); color: #065f46; }
    .badge-amber { background: var(--amber-bg); color: #92400e; }
    .badge-red { background: var(--red-bg); color: #991b1b; }
    .badge-blue { background: #e0f2fe; color: #075985; }
    .alert-box {
      padding: 14px 18px;
      border-radius: 8px;
      margin: 14px 0;
      font-size: 13.5px;
      border-left: 4px solid var(--primary);
      background: #f0f9ff;
    }
    .alert-error { border-left-color: var(--red); background: var(--red-bg); color: #7f1d1d; }
    .alert-success { border-left-color: var(--green); background: #ecfdf5; color: #064e3b; }
    .bar-bg { width: 120px; height: 8px; background: #e2e8f0; border-radius: 4px; overflow: hidden; display: inline-block; vertical-align: middle; margin-right: 6px; }
    .bar-fill { height: 100%; background: var(--primary); }
    .steps-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
      gap: 14px;
    }
    .step-card {
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 14px 16px;
      background: #f8fafc;
    }
    .step-card .st-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
    .step-card .st-num { background: var(--navy-light); color: #fff; font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 4px; }
    .two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
    @media (max-width: 900px) { .two-col { grid-template-columns: 1fr; } }
    @media print {
      .tabs-nav, .no-print { display: none !important; }
      .tab-pane { display: block !important; }
      body { background: #fff; }
    }
  </style>
</head>
<body>

  <header class="topbar">
    <div class="topbar-inner">
      <div>
        <h1>☀️ Sistema de Dimensionamento Energético e Orçamento Fotovoltaico (Sprint 3 Final)</h1>
        <p class="sub">
          <strong>Disciplina:</strong> Soluções em Energias Renováveis e Sustentáveis (Prof. Álvaro Gonçalves) &nbsp;|&nbsp;
          <strong>Equipe Lumos:</strong> Pietro Lorande (RM 569125) • Luiz Otávio Brito Freixo (RM 569977) • Maria Eduarda Lemos (RM 574094)
        </p>
      </div>
      <div class="res-selector-box no-print">
        <label for="top-imovel-select">Residência Ativa (PB01):</label>
        <select id="top-imovel-select" onchange="trocarImovelAtivo(this.value)"></select>
      </div>
    </div>
  </header>

  <main class="main-wrap">
    <div id="global-feedback"></div>

    <!-- KPIs Dinâmicos da Residência e Dimensionamento -->
    <section class="kpi-row">
      <div class="kpi-card">
        <div class="k-label">1. Demanda da Residência (PB01 / PB02)</div>
        <div class="k-val" id="kpi-consumo">-- kWh/mês</div>
        <div class="k-sub" id="kpi-demanda-sub">E_dia: -- kWh/dia | Pot. Casa: -- W</div>
      </div>
      <div class="kpi-card">
        <div class="k-label">2. Dimensionamento FV (PB03 / PB04 / PB06)</div>
        <div class="k-val" id="kpi-potencia-fv">-- kWp</div>
        <div class="k-sub" id="kpi-fv-sub">Necessária: -- kWp | HSP: -- | PR: --%</div>
      </div>
      <div class="kpi-card">
        <div class="k-label">3. Geração & Atendimento (PB08 / PB09)</div>
        <div class="k-val" id="kpi-geracao">-- kWh/mês</div>
        <div class="k-sub" id="kpi-geracao-sub">Diária: -- kWh/dia | Atendimento: --%</div>
      </div>
      <div class="kpi-card">
        <div class="k-label">4. Orçamento & Payback Simples (PB13 / PB16)</div>
        <div class="k-val" id="kpi-orcamento">R$ --</div>
        <div class="k-sub" id="kpi-payback-sub">Economia: R$ --/mês | Payback: -- anos</div>
      </div>
    </section>

    <!-- Navegação Principal por Abas -->
    <nav class="tabs-nav no-print">
      <button class="tab-btn active" onclick="abrirAba('aba-sprint-review', this)">🎯 1. Apresentação Sprint Review (15 Etapas + Seção 9)</button>
      <button class="tab-btn" onclick="abrirAba('aba-residencia', this)">🏠 2. Residência & Equipamentos (PB01 / PB02)</button>
      <button class="tab-btn" onclick="abrirAba('aba-dimensionamento', this)">☀️ 3. Dimensionar Sistema FV & Baterias (PB03 a PB13)</button>
      <button class="tab-btn" onclick="abrirAba('aba-comparacao', this)">⚖️ 4. Comparar Sem vs. Com Baterias & Questão 9 (PB14)</button>
      <button class="tab-btn" onclick="abrirAba('aba-proposta', this)">📄 5. Proposta Consolidada ao Cliente (PB17 / PB20 / PB21)</button>
      <button class="tab-btn" onclick="abrirAba('aba-datasets', this)">📊 6. Datasets CSV & Testes QA (PB05 / PB07 / PB12)</button>
    </nav>

    <!-- ABA 1: APRESENTAÇÃO SPRINT REVIEW (15 ETAPAS + QUESTÃO 9) -->
    <div id="aba-sprint-review" class="tab-pane active">
      <div class="card">
        <h2>
          <span>Roteiro Completo da Sprint Review (Seção 7 do PDF — Etapas 1 a 15 em Tempo Real)</span>
          <div class="no-print">
            <button class="btn btn-primary" onclick="abrirAbaPorId('aba-dimensionamento')">Ir para Simulador de Dimensionamento</button>
            <button class="btn btn-success" onclick="abrirAbaPorId('aba-comparacao')">Ver Comparação e Questão 9</button>
          </div>
        </h2>
        <p style="margin-top:0; color:var(--muted); font-size:13.5px;">
          Todos os 15 itens abaixo são calculados dinamicamente pelo motor Python (<code>fotovoltaico.py</code>) a partir da residência selecionada (<code>dados_sistema.json</code>) e dos datasets estruturados (<code>.csv</code>):
        </p>
        <div id="grid-15-etapas" class="steps-grid"></div>
      </div>

      <div class="card">
        <h2>Resposta Fundamentada à Questão Final da Sprint Review (Seção 9 do PDF)</h2>
        <div id="box-questao-9-home" class="alert-box alert-success"></div>
      </div>
    </div>

    <!-- ABA 2: RESIDÊNCIA E EQUIPAMENTOS (SPRINTS 1 E 2 + PB01 / PB02) -->
    <div id="aba-residencia" class="tab-pane">
      <div class="two-col">
        <div class="card">
          <h2>1. Dados da Residência Selecionada (PB01 / PB02)</h2>
          <div id="detalhes-residencia-atual"></div>
          <hr style="border:none; border-top:1px solid var(--border); margin:18px 0;">
          <h3>Cadastrar Nova Residência no Sistema</h3>
          <div class="form-grid">
            <div class="field"><label>Apelido da Residência</label><input type="text" id="nova-res-apelido" placeholder="Ex.: Casa de Praia (Santos)"></div>
            <div class="field"><label>Endereço</label><input type="text" id="nova-res-end" placeholder="Ex.: Av. Atlântica"></div>
            <div class="field"><label>Número</label><input type="text" id="nova-res-num" placeholder="Ex.: 500"></div>
            <div class="field"><label>Tipo</label><select id="nova-res-tipo"><option value="Casa">Casa</option><option value="Apartamento">Apartamento</option><option value="Outro">Outro</option></select></div>
            <div class="field"><label>Cidade</label><input type="text" id="nova-res-cidade" value="São Paulo"></div>
            <div class="field"><label>UF</label><input type="text" id="nova-res-uf" value="SP" maxlength="2"></div>
          </div>
          <button class="btn btn-primary" onclick="criarNovaResidencia()">+ Cadastrar Residência</button>
        </div>

        <div class="card">
          <h2>2. Adicionar Equipamento / Carga à Residência (PB01 / PB02)</h2>
          <p style="margin-top:0; font-size:13px; color:var(--muted);">Selecione um equipamento do catálogo ou cadastre um equipamento personalizado para recalcular o consumo mensal (<code>E_mês</code>), diário (<code>E_dia</code>) e a potência instalada (<code>W / kW</code>):</p>
          <div class="form-grid">
            <div class="field">
              <label>Equipamento do Catálogo</label>
              <select id="assoc-eq-select" onchange="preencherEquipamentoCatalogo()"></select>
            </div>
            <div class="field">
              <label>Nome do Equipamento</label>
              <input type="text" id="assoc-eq-nome" placeholder="Ex.: Ar-condicionado Split">
            </div>
            <div class="field">
              <label>Categoria / Cômodo</label>
              <input type="text" id="assoc-eq-cat" placeholder="Ex.: Quarto">
            </div>
            <div class="field">
              <label>Potência Unitária (Watts)</label>
              <input type="number" id="assoc-eq-pot" value="1200" min="1" step="10">
            </div>
            <div class="field">
              <label>Quantidade na Residência</label>
              <input type="number" id="assoc-eq-qtd" value="1" min="1" step="1">
            </div>
            <div class="field">
              <label>Tempo de Uso Diário (horas/dia, 0 a 24)</label>
              <input type="number" id="assoc-eq-horas" value="4" min="0.1" max="24" step="0.25">
            </div>
          </div>
          <button class="btn btn-success" onclick="adicionarCargaResidencia()">+ Associar Equipamento à Residência</button>
        </div>
      </div>

      <div class="card">
        <h2>3. Equipamentos Instalados na Residência e Ranking de Demanda Energética (PB02)</h2>
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>Equipamento</th>
              <th>Cômodo / Categoria</th>
              <th style="text-align:right">Potência Unit. (W)</th>
              <th style="text-align:center">Qtd</th>
              <th style="text-align:right">Potência Instalada (W)</th>
              <th style="text-align:right">Uso Diário</th>
              <th style="text-align:right">Consumo Diário (kWh/dia)</th>
              <th style="text-align:right">Consumo Mensal (kWh/mês)</th>
              <th>Participação</th>
              <th class="no-print">Ação</th>
            </tr>
          </thead>
          <tbody id="tabela-cargas-body"></tbody>
        </table>
      </div>
    </div>

    <!-- ABA 3: DIMENSIONAMENTO FOTOVOLTAICO INTERATIVO (PB03 A PB18) -->
    <div id="aba-dimensionamento" class="tab-pane">
      <div class="card">
        <h2>Parâmetros do Dimensionamento Fotovoltaico e Armazenamento (PB03 a PB18)</h2>
        <p style="margin-top:0; font-size:13.5px; color:var(--muted);">
          Configure os parâmetros abaixo e clique em <strong>Executar Dimensionamento no Motor Python</strong>. O sistema valida os dados (PB18), consulta os datasets CSV (PB05, PB07, PB12), verifica as regras elétricas C1–C8 e salva a simulação no banco JSON (PB20).
        </p>
        <div class="form-grid">
          <div class="field">
            <label>Origem do Consumo Mensal (PB02)</label>
            <select id="dim-origem-consumo" onchange="alternarOrigemConsumo()">
              <option value="calculado">Recuperado dos Equipamentos da Residência</option>
              <option value="conta">Informar Média da Conta de Luz Manualmente</option>
            </select>
          </div>
          <div class="field">
            <label>Consumo Mensal E_mês (kWh/mês)</label>
            <input type="number" id="dim-consumo" step="10" min="1">
          </div>
          <div class="field">
            <label>Percentual de Atendimento (%) (PB04)</label>
            <input type="number" id="dim-percentual" value="100" min="1" max="100" step="5">
          </div>
          <div class="field">
            <label>Localidade / HSP da Tabela CRESESB (PB03)</label>
            <select id="dim-localidade" onchange="atualizarHspDaTabela()"></select>
          </div>
          <div class="field">
            <label>HSP Utilizado (kWh/m²/dia) (PB03)</label>
            <input type="number" id="dim-hsp" step="0.1" min="3.0" max="7.0">
          </div>
          <div class="field">
            <label>Performance Ratio — PR (0,10 a 1,00) (PB03)</label>
            <input type="number" id="dim-pr" value="0.78" step="0.01" min="0.50" max="0.95">
          </div>
          <div class="field">
            <label>Módulo Fotovoltaico (`modulos.csv` - PB05)</label>
            <select id="dim-modulo"></select>
          </div>
          <div class="field">
            <label>Inversor (`inversores.csv` - PB07)</label>
            <select id="dim-inversor"></select>
          </div>
          <div class="field">
            <label>Sistema de Armazenamento (PB10)</label>
            <select id="dim-com-bateria" onchange="alternarCamposBateria()">
              <option value="false">Sem Baterias (On-Grid Convencional)</option>
              <option value="true">Com Baterias (Híbrido + Backup de Autonomia)</option>
            </select>
          </div>
          <div class="field" id="box-dim-autonomia">
            <label>Autonomia Desejada (horas, até 72h) (PB11)</label>
            <input type="number" id="dim-autonomia" value="12" min="1" max="72" step="1">
          </div>
          <div class="field" id="box-dim-bateria">
            <label>Modelo da Bateria (`baterias.csv` - PB12)</label>
            <select id="dim-bateria"></select>
          </div>
          <div class="field">
            <label>Tarifa de Energia da Concessionária (R$/kWh) (PB15)</label>
            <input type="number" id="dim-tarifa" value="0.92" min="0.10" max="10.0" step="0.02">
          </div>
        </div>
        <div style="display:flex; gap:12px; flex-wrap:wrap; align-items:center;">
          <button class="btn btn-primary" onclick="executarDimensionamentoAPI()">⚡ Executar Dimensionamento no Motor Python e Salvar</button>
          <button class="btn btn-outline" onclick="testarValidacaoErroPB18()">🛡️ Testar Validação de Erro / Incompatibilidade (PB18)</button>
        </div>
        <div id="dim-feedback"></div>
      </div>

      <div id="painel-resultado-dimensionamento"></div>
    </div>

    <!-- ABA 4: COMPARAÇÃO DE CENÁRIOS E QUESTÃO FINAL (PB14 + SEÇÃO 9) -->
    <div id="aba-comparacao" class="tab-pane">
      <div class="card">
        <h2>
          <span>Comparação Lado a Lado: Sem Baterias (On-Grid) vs. Com Baterias (Híbrido) — PB14</span>
          <div class="no-print" style="display:flex; gap:10px; align-items:center;">
            <label style="font-size:13px; color:var(--muted);">Autonomia p/ Comparação (h):</label>
            <input type="number" id="comp-autonomia-input" value="12" min="1" max="72" style="width:80px; padding:6px 10px; border:1px solid #cbd5e1; border-radius:6px;">
            <button class="btn btn-primary" onclick="recalcularComparacaoAPI()">Recalcular Comparação</button>
          </div>
        </h2>
        <div id="tabela-comparacao-container"></div>
      </div>

      <div class="card">
        <h2>Análise Técnica e Econômica — Questão Final da Sprint Review (Seção 9)</h2>
        <div id="box-questao-9-comp" class="alert-box alert-success"></div>
      </div>
    </div>

    <!-- ABA 5: PROPOSTA CONSOLIDADA E HISTÓRICO SALVO (PB17, PB20, PB21) -->
    <div id="aba-proposta" class="tab-pane">
      <div class="card no-print">
        <h2>
          <span>Exportação e Apresentação da Proposta Final ao Cliente (PB17 / PB21)</span>
          <div style="display:flex; gap:10px; flex-wrap:wrap;">
            <button class="btn btn-primary" onclick="window.print()">🖨️ Imprimir / Salvar Proposta em PDF</button>
            <a class="btn btn-success" href="/proposta_cliente.html" target="_blank">🌐 Abrir Página da Proposta Isolada (.html)</a>
            <a class="btn btn-outline" href="/proposta_cliente.txt" download="proposta_cliente.txt">📥 Baixar Relatório Consolidado (.txt)</a>
          </div>
        </h2>
        <p style="margin:0; font-size:13.5px; color:var(--muted);">
          Abaixo está o relatório consolidado oficial gerado pelo sistema contendo todos os dados da residência, recurso solar, dimensionamento FV, inversor, armazenamento, orçamento item a item, economia, payback simples e comparação de cenários.
        </p>
      </div>

      <div class="card">
        <h2>Relatório Executivo Consolidado do Cliente (PB17)</h2>
        <pre id="pre-proposta-consolidada" style="background:#0f172a; color:#f8fafc; padding:20px; border-radius:8px; overflow-x:auto; font-size:12.8px; line-height:1.45;"></pre>
      </div>

      <div class="card">
        <h2>Histórico de Dimensionamentos Salvos no Banco (`dados_sistema.json` — PB20)</h2>
        <div id="tabela-historico-container"></div>
      </div>
    </div>

    <!-- ABA 6: DATASETS ESTRUTURADOS E TESTES AUTOMATIZADOS (PB05, PB07, PB12) -->
    <div id="aba-datasets" class="tab-pane">
      <div class="card">
        <h2>
          <span>Validação dos Datasets Estruturados e Bateria de Testes Automatizados (`testes.py`)</span>
          <button class="btn btn-success no-print" onclick="executarTestesQA()">🧪 Rodar 12 Baterias de Testes Automatizados Agora</button>
        </h2>
        <pre id="pre-qa-output" style="background:#0f172a; color:#a7f3d0; padding:16px; border-radius:8px; overflow-x:auto; font-size:13px;"></pre>
      </div>

      <div class="card">
        <h2>1. Dataset de Módulos Fotovoltaicos (`dados_fv/modulos.csv` — PB05)</h2>
        <div id="tabela-ds-modulos"></div>
      </div>

      <div class="card">
        <h2>2. Dataset de Inversores On-Grid e Híbridos (`dados_fv/inversores.csv` — PB07)</h2>
        <div id="tabela-ds-inversores"></div>
      </div>

      <div class="card">
        <h2>3. Dataset de Baterias LiFePO4 (`dados_fv/baterias.csv` — PB12)</h2>
        <div id="tabela-ds-baterias"></div>
      </div>
    </div>
  </main>

  <script>
    let ESTADO = null;

    function brl(v) {
      return 'R$ ' + Number(v || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }
    function num(v, c = 2) {
      return Number(v || 0).toLocaleString('pt-BR', { minimumFractionDigits: c, maximumFractionDigits: c });
    }

    function abrirAba(abaId, btnEl) {
      document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.getElementById(abaId).classList.add('active');
      if (btnEl) btnEl.classList.add('active');
    }

    function abrirAbaPorId(abaId) {
      const botoes = document.querySelectorAll('.tab-btn');
      const mapa = ['aba-sprint-review', 'aba-residencia', 'aba-dimensionamento', 'aba-comparacao', 'aba-proposta', 'aba-datasets'];
      const idx = mapa.indexOf(abaId);
      abrirAba(abaId, idx >= 0 ? botoes[idx] : null);
      window.scrollTo({ top: 0, behavior: 'smooth' });
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

      // Seletor de residências no topo
      const selTop = document.getElementById('top-imovel-select');
      selTop.innerHTML = ESTADO.imoveis.map(i =>
        `<option value="${i.id}" ${i.id === im.id ? 'selected' : ''}>#${i.id} - ${i.apelido} (${i.cidade}/${i.uf} • ${num(i.consumo_mensal_kwh)} kWh/mês)</option>`
      ).join('');

      // KPIs do topo
      document.getElementById('kpi-consumo').textContent = `${num(im.consumo_mensal_kwh)} kWh/mês`;
      document.getElementById('kpi-demanda-sub').textContent = `E_dia: ${num(im.consumo_diario_kwh, 2)} kWh/dia | Pot. Casa: ${num(im.potencia_instalada_w, 0)} W (${num(im.potencia_instalada_kw, 2)} kW)`;
      document.getElementById('kpi-potencia-fv').textContent = `${num(dim.p_inst, 2)} kWp (${dim.selecao.config.n_modulos} módulos)`;
      document.getElementById('kpi-fv-sub').textContent = `P_FV nec.: ${num(dim.p_fv, 3)} kWp | HSP: ${num(dim.hsp_info.hsp, 1)} | PR: ${num(dim.pr * 100, 0)}%`;
      document.getElementById('kpi-geracao').textContent = `${num(dim.geracao_mes, 1)} kWh/mês`;
      document.getElementById('kpi-geracao-sub').textContent = `Diária: ${num(dim.geracao_dia, 2)} kWh/dia | Atendimento: ${num(dim.comparacao_geracao.atendimento_pct, 1)}%`;
      document.getElementById('kpi-orcamento').textContent = brl(dim.orcamento.c_total);
      document.getElementById('kpi-payback-sub').textContent = `Econ.: ${brl(dim.economia.economia_mensal_brl)}/mês | Payback: ${num(dim.payback.payback_simples_anos)} anos`;

      renderizarSprintReview15Etapas(im, comp, ds);
      renderizarAbaResidencia(im);
      preencherFormularioDimensionamento(im, dim, ds);
      renderizarResultadoDimensionamento(dim, im.apelido);
      renderizarAbaComparacao(comp, im.apelido);
      renderizarAbaProposta(ESTADO);
      renderizarAbaDatasets(ds);
    }

    function renderizarSprintReview15Etapas(im, comp, ds) {
      const a = comp.sem_bateria;
      const b = comp.com_bateria;
      const modA = a.selecao.modulo, invA = a.selecao.inversor, cfgA = a.selecao.config;
      const invB = b.selecao.inversor, armB = b.armazenamento, batB = armB.bateria;
      const h = a.hsp_info;

      const etapas = [
        { n: 'Etapa 01', pb: 'PB01', t: 'Seleção da Residência Cadastrada', d: `Residência <strong>#${im.id} ${im.apelido}</strong> (${im.endereco}, ${im.numero} — ${im.cidade}/${im.uf}) recuperada do banco <code>dados_sistema.json</code> sem necessidade de recadastro.` },
        { n: 'Etapa 02', pb: 'PB02', t: 'Equipamentos e Demanda Calculada', d: `<strong>${im.cargas.length} grupos de equipamentos</strong> instalados | Potência instalada da casa: <strong>${num(im.potencia_instalada_w, 0)} W (${num(im.potencia_instalada_kw, 3)} kW)</strong> | Consumo mensal: <strong>E_mês = ${num(im.consumo_mensal_kwh)} kWh/mês</strong> | Consumo diário: <strong>E_dia = ${num(im.consumo_diario_kwh, 2)} kWh/dia</strong>.` },
        { n: 'Etapa 03', pb: 'PB04', t: 'Dimensionamento Fotovoltaico (P_FV)', d: `Fórmula: <code>P_FV = E_dia / (HSP × PR) = ${num(a.consumo_diario, 3)} / (${num(h.hsp)} × ${num(a.pr)})</code> = <strong>${num(a.p_fv, 3)} kWp</strong> necessários para atender ${num(a.percentual, 0)}% do consumo.` },
        { n: 'Etapa 04', pb: 'PB03', t: 'Recurso Solar: HSP e PR Justificado', d: `Localidade <strong>${h.cidade}/${h.uf}</strong> com <strong>HSP = ${num(h.hsp)} kWh/m²/dia</strong> (${h.fonte}) e <strong>PR = ${num(a.pr * 100, 0)}% (0,78)</strong> justificado pela NT EPE DEA-SEE 009/2023 (perdas térmicas, cabos e inversor).` },
        { n: 'Etapa 05', pb: 'PB05/07/12', t: 'Consulta aos Datasets Estruturados', d: `Leitura dinâmica dos CSVs separados do código: <strong>${ds.modulos.length} módulos</strong> (<code>modulos.csv</code>), <strong>${ds.inversores.length} inversores</strong> (<code>inversores.csv</code>) e <strong>${ds.baterias.length} baterias LiFePO4</strong> (<code>baterias.csv</code>) com preços e fontes reais.` },
        { n: 'Etapa 06', pb: 'PB06', t: 'Seleção e Quantidade de Módulos', d: `Módulo selecionado: <strong>[${modA.id}] ${modA.fabricante} ${modA.modelo} (${modA.potencia_wp} Wp, efic. ${num(modA.eficiencia_pct)}%)</strong>.<br><code>N_mod = teto(${num(a.p_fv * 1000, 1)} / ${modA.potencia_wp}) = ${cfgA.n_modulos} módulos</code> → <strong>P_inst = ${num(a.p_inst, 3)} kWp</strong>.` },
        { n: 'Etapa 07', pb: 'PB07', t: 'Seleção e Compatibilidade do Inversor', d: `Regras elétricas C1–C8 validadas (Voc frio ${num(cfgA.voc_string_v, 1)}V ≤ ${invA.tensao_max_entrada_v}V, Vmp ${num(cfgA.vmp_string_v, 1)}V dentro do MPPT ${invA.faixa_mppt_min_v}-${invA.faixa_mppt_max_v}V, <code>R_DC/AC = ${num(cfgA.ratio_dc_ac)}</code>).<br>On-Grid: <strong>[${invA.id}] ${invA.fabricante} ${invA.modelo}</strong> | Híbrido: <strong>[${invB.id}] ${invB.fabricante} ${invB.modelo}</strong>.` },
        { n: 'Etapa 08', pb: 'PB08', t: 'Estimativa de Geração Diária e Mensal', d: `<code>E_gerada,dia = P_inst × HSP × PR = ${num(a.p_inst, 3)} × ${num(h.hsp)} × ${num(a.pr)}</code> = <strong>${num(a.geracao_dia, 2)} kWh/dia</strong>.<br><code>E_gerada,mês = E_dia × 30</code> = <strong>${num(a.geracao_mes, 2)} kWh/mês</strong>.` },
        { n: 'Etapa 09', pb: 'PB09', t: 'Comparação Geração × Consumo', d: `Atendimento: <strong>${num(a.comparacao_geracao.atendimento_pct, 1)}%</strong> do consumo mensal.<br>Energia efetivamente compensada: <strong>${num(a.comparacao_geracao.energia_compensada_kwh_mes)} kWh/mês</strong> | Excedente injetado na rede: <strong>${num(a.comparacao_geracao.energia_excedente_kwh_mes)} kWh/mês</strong>.` },
        { n: 'Etapa 10', pb: 'PB10', t: 'Opção Sem Baterias (On-Grid)', d: `${cfgA.n_modulos}× ${modA.fabricante} ${modA.potencia_wp}W + 1× [${invA.id}] ${invA.fabricante} ${invA.modelo} (${invA.potencia_nominal_w}W, efic. ${num(invA.eficiencia_pct, 1)}%), sem armazenamento (0 kWh).` },
        { n: 'Etapa 11', pb: 'PB11/12', t: 'Opção Com Baterias e Autonomia', d: `Para <strong>${armB.autonomia_h}h de autonomia</strong> (<code>E_aut = ${num(armB.energia_autonomia_kwh)} kWh</code>, <code>C_bat = ${num(armB.c_bat_kwh)} kWh</code>): selecionadas <strong>${armB.n_baterias}× [${batB.id}] ${batB.fabricante} ${batB.modelo}</strong> (${num(armB.capacidade_instalada_kwh)} kWh nominais / ${num(armB.capacidade_util_kwh)} kWh úteis, DoD ${batB.dod_pct}%).` },
        { n: 'Etapa 12', pb: 'PB13', t: 'Orçamento Automático dos Equipamentos', d: `<strong>Sem Baterias:</strong> Equipamentos ${brl(a.orcamento.c_equipamentos)} | Total instalado <strong>${brl(a.orcamento.c_total)}</strong>.<br><strong>Com Baterias:</strong> Equipamentos ${brl(b.orcamento.c_equipamentos)} | Total instalado <strong>${brl(b.orcamento.c_total)}</strong>.` },
        { n: 'Etapa 13', pb: 'PB14', t: 'Comparação Lado a Lado dos Cenários', d: `Adicionar baterias para ${armB.autonomia_h}h de backup eleva o investimento total em <strong>+${brl(comp.diferenca_investimento_total_brl)} (+${num(comp.acrescimo_percentual, 1)}%)</strong> para a mesma geração mensal (${num(a.geracao_mes, 1)} kWh/mês).` },
        { n: 'Etapa 14', pb: 'PB15/16', t: 'Economia Estimada e Payback Simples', d: `Tarifa ${brl(a.economia.tarifa_brl_kwh)}/kWh → Economia de <strong>${brl(a.economia.economia_mensal_brl)}/mês (${brl(a.economia.economia_anual_brl)}/ano)</strong>.<br><strong>Payback Simples:</strong> <span class="badge badge-green">${num(a.payback.payback_simples_anos)} anos (Sem Bat.)</span> vs. <span class="badge badge-amber">${num(b.payback.payback_simples_anos)} anos (Com Bat.)</span>.` },
        { n: 'Etapa 15', pb: 'PB17/20/21', t: 'Proposta Final ao Cliente e Persistência', d: `Proposta consolidada disponível na Aba 5, salva automaticamente em <code>dados_sistema.json</code> e exportada em <code>proposta_cliente.html</code> e <code>proposta_cliente.txt</code>.` },
      ];

      document.getElementById('grid-15-etapas').innerHTML = etapas.map(e => `
        <div class="step-card">
          <div class="st-head">
            <span class="st-num">${e.n}</span>
            <span class="badge badge-blue">${e.pb}</span>
          </div>
          <strong style="font-size:14px; color:var(--ink);">${e.t}</strong>
          <p style="margin:6px 0 0 0; font-size:13px; color:#334155;">${e.d}</p>
        </div>
      `).join('');

      const htmlQ9 = `
        <h3 style="margin-top:0; color:#065f46;">Parecer Técnico-Econômico Conclusivo (Seção 9 — ${im.apelido})</h3>
        <p style="margin:4px 0;"><strong>Pergunta da Sprint Review:</strong> <em>"Para a residência utilizada na demonstração, qual solução faz mais sentido: sistema fotovoltaico sem armazenamento ou sistema com baterias? Quais resultados técnicos e econômicos do projeto sustentam a análise?"</em></p>
        <p style="white-space:pre-line; margin:10px 0 0 0;">${comp.analise_questao_final}</p>
      `;
      document.getElementById('box-questao-9-home').innerHTML = htmlQ9;
    }

    function renderizarAbaResidencia(im) {
      document.getElementById('detalhes-residencia-atual').innerHTML = `
        <table>
          <tbody>
            <tr><th style="width:38%">Identificação / Apelido</th><td><strong>#${im.id} — ${im.apelido}</strong> (${im.tipo})</td></tr>
            <tr><th>Endereço e Localidade</th><td>${im.endereco}, ${im.numero} — <strong>${im.cidade}/${im.uf}</strong></td></tr>
            <tr><th>Potência Elétrica Instalada (PB02)</th><td><strong>${num(im.potencia_instalada_w, 0)} W</strong> (<strong>${num(im.potencia_instalada_kw, 3)} kW</strong>)</td></tr>
            <tr><th>Consumo Mensal Calculado (E_mês)</th><td><strong>${num(im.consumo_mensal_kwh, 2)} kWh/mês</strong></td></tr>
            <tr><th>Consumo Médio Diário (E_dia = E_mês / 30)</th><td><strong>${num(im.consumo_diario_kwh, 3)} kWh/dia</strong></td></tr>
          </tbody>
        </table>
      `;

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
            <td style="text-align:right">${num(c.tempo_uso_h, 2)} h/dia</td>
            <td style="text-align:right">${num(c.consumo_diario_kwh, 2)} kWh/dia</td>
            <td style="text-align:right"><strong>${num(c.consumo_mensal_kwh, 2)} kWh/mês</strong></td>
            <td><div class="bar-bg"><div class="bar-fill" style="width:${Math.min(100, pct)}%"></div></div> ${num(pct, 1)}%</td>
            <td class="no-print"><button class="btn btn-danger" onclick="removerCargaResidencia('${c.assoc_id}')">Remover</button></td>
          </tr>
        `;
      }).join('') + `
        <tr style="background:#e0f2fe; font-weight:700;">
          <td colspan="4">TOTAL DA RESIDÊNCIA (PB02)</td>
          <td style="text-align:center">${im.cargas.reduce((s, x) => s + x.quantidade, 0)}</td>
          <td style="text-align:right">${num(im.potencia_instalada_w, 0)} W (${num(im.potencia_instalada_kw, 3)} kW)</td>
          <td style="text-align:right">--</td>
          <td style="text-align:right">${num(im.consumo_diario_kwh, 2)} kWh/dia</td>
          <td style="text-align:right">${num(im.consumo_mensal_kwh, 2)} kWh/mês</td>
          <td>100,0%</td>
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
        `<option value="">Seleção Automática Otimizada (Menor Custo Compatível)</option>` +
        ds.modulos.map(m => `<option value="${m.id}">[${m.id}] ${m.fabricante} ${m.modelo} (${m.potencia_wp} Wp — ${brl(m.preco_brl)})</option>`).join('');

      document.getElementById('dim-inversor').innerHTML =
        `<option value="">Seleção Automática Compatível (Regras C1–C8)</option>` +
        ds.inversores.map(i => `<option value="${i.id}">[${i.id}] ${i.fabricante} ${i.modelo} (${i.tipo}, ${i.potencia_nominal_w}W — ${brl(i.preco_brl)})</option>`).join('');

      document.getElementById('dim-bateria').innerHTML =
        `<option value="">Seleção Automática Compatível (Menor Custo LiFePO4)</option>` +
        ds.baterias.map(b => `<option value="${b.id}">[${b.id}] ${b.fabricante} ${b.modelo} (${b.tensao_nominal_v}V, ${b.capacidade_kwh} kWh, DoD ${b.dod_pct}% — ${brl(b.preco_brl)})</option>`).join('');

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
      document.getElementById('box-dim-autonomia').style.opacity = comBat ? '1' : '0.45';
      document.getElementById('box-dim-bateria').style.opacity = comBat ? '1' : '0.45';
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
          <td>Custos Complementares</td>
          <td>${o[0]} <small style="color:var(--muted)">(${o[2]})</small></td>
          <td style="text-align:center">1</td>
          <td style="text-align:right">${brl(o[1])}</td>
          <td style="text-align:right">${brl(o[1])}</td>
        </tr>
      `).join('');

      let blocoBatHtml = `<p style="margin:0;"><strong>Sem Armazenamento (On-Grid Convencional):</strong> Capacidade instalada 0 kWh, custo adicional R$ 0,00.</p>`;
      if (arm.ativo && arm.bateria) {
        const b = arm.bateria;
        blocoBatHtml = `
          <p style="margin:4px 0;"><strong>Autonomia Solicitada (PB11):</strong> ${num(arm.autonomia_h, 1)} horas | Consumo Diário: ${num(arm.consumo_diario_kwh, 2)} kWh/dia | Energia de Autonomia (<code>E_aut = E_dia × A/24</code>): <strong>${num(arm.energia_autonomia_kwh, 2)} kWh</strong> | Capacidade Nominal Necessária (<code>C_bat = E_aut / (DoD × η_bat)</code>): <strong>${num(arm.c_bat_kwh, 2)} kWh</strong></p>
          <p style="margin:4px 0;"><strong>Banco Selecionado (PB12):</strong> <strong>${arm.n_baterias}× [${b.id}] ${b.fabricante} ${b.modelo}</strong> (${b.tecnologia}, ${num(b.tensao_nominal_v, 1)} V, ${num(b.capacidade_ah, 0)} Ah, ${num(b.capacidade_kwh)} kWh/un, DoD ${num(b.dod_pct, 0)}%, ${num(b.ciclos, 0)} ciclos)</p>
          <p style="margin:4px 0;"><strong>Capacidade Total Instalada:</strong> <strong>${num(arm.capacidade_instalada_kwh)} kWh nominais</strong> / <strong>${num(arm.capacidade_util_kwh)} kWh úteis</strong> — Subtotal: <strong>${brl(arm.custo)}</strong></p>
        `;
      }

      document.getElementById('painel-resultado-dimensionamento').innerHTML = `
        <div class="card">
          <h2>Resultado Técnico do Dimensionamento (${apelido} — ${arm.ativo ? 'Com Baterias Híbrido' : 'Sem Baterias On-Grid'})</h2>
          <table>
            <tbody>
              <tr><th style="width:28%">Demanda e Recurso Solar (PB02/PB03)</th><td>Consumo Mensal: <strong>${num(r.consumo)} kWh/mês</strong> (E_dia = <strong>${num(r.consumo_diario)} kWh/dia</strong>) | Localidade: <strong>${h.cidade}/${h.uf}</strong> (HSP = <strong>${num(h.hsp)} kWh/m²/dia</strong>) | PR = <strong>${num(r.pr * 100, 0)}%</strong><br><small style="color:var(--muted)">${r.justificativa_pr}</small></td></tr>
              <tr><th>Potência FV e Módulos (PB04/PB05/PB06)</th><td>Potência Necessária (<code>P_FV = E_dia / (HSP × PR)</code>): <strong>${num(r.p_fv, 3)} kWp</strong> | Potência Instalada: <strong>${num(r.p_inst, 3)} kWp</strong><br>Módulos: <strong>${cfg.n_modulos}× [${mod.id}] ${mod.fabricante} ${mod.modelo}</strong> (${mod.potencia_wp} Wp, Eficiência ${num(mod.eficiencia_pct)}%, Voc ${num(mod.voc_v)}V, Vmp ${num(mod.vmp_v)}V, Imp ${num(mod.imp_a)}A — ${cfg.n_strings} string(s) de ${cfg.por_string} módulos)</td></tr>
              <tr><th>Inversor e Compatibilidade (PB07)</th><td><strong>[${inv.id}] ${inv.fabricante} ${inv.modelo}</strong> (Tipo: <strong>${inv.tipo}</strong>, Potência Nominal: ${inv.potencia_nominal_w} W, Máx FV: ${inv.potencia_max_fv_w} W, Eficiência: ${num(inv.eficiencia_pct, 1)}%)<br>Verificação Elétrica (C1–C8): Voc string frio = ${num(cfg.voc_string_v, 1)} V (máx ${inv.tensao_max_entrada_v} V) | Vmp string = ${num(cfg.vmp_string_v, 1)} V (MPPT ${inv.faixa_mppt_min_v}-${inv.faixa_mppt_max_v} V) | Razão <code>R_DC/AC = ${num(cfg.ratio_dc_ac)}</code></td></tr>
              <tr><th>Geração e Atendimento (PB08/PB09)</th><td>Geração Diária: <strong>${num(r.geracao_dia, 2)} kWh/dia</strong> | Geração Mensal: <strong>${num(r.geracao_mes, 2)} kWh/mês</strong> (Atendimento: <span class="badge badge-green">${num(compG.atendimento_pct, 1)}%</span>)<br>Energia Efetivamente Compensada na Fatura: <strong>${num(compG.energia_compensada_kwh_mes)} kWh/mês</strong> | Excedente Injetado na Rede: <strong>${num(compG.energia_excedente_kwh_mes)} kWh/mês</strong></td></tr>
              <tr><th>Armazenamento em Baterias (PB10/PB11/PB12)</th><td>${blocoBatHtml}</td></tr>
            </tbody>
          </table>
        </div>

        <div class="card">
          <h2>Orçamento Automático (PB13), Economia (PB15) e Payback Simples (PB16)</h2>
          <table>
            <thead>
              <tr><th>Categoria</th><th>Equipamento / Descrição e Fonte</th><th style="text-align:center">Qtd</th><th style="text-align:right">Preço Unitário</th><th style="text-align:right">Subtotal</th></tr>
            </thead>
            <tbody>
              ${linhasOrc}
              <tr style="background:#f8fafc"><td colspan="4" style="text-align:right"><strong>CUSTO DOS EQUIPAMENTOS DOS DATASETS (Custo_total = Σ Custo_item)</strong></td><td style="text-align:right"><strong>${brl(orc.c_equipamentos)}</strong></td></tr>
              <tr style="background:#e0f2fe"><td colspan="4" style="text-align:right"><strong>INVESTIMENTO TOTAL ESTIMADO (EQUIPAMENTOS + ESTRUTURA, INSTALAÇÃO E PROJETO)</strong></td><td style="text-align:right"><strong>${brl(orc.c_total)}</strong></td></tr>
            </tbody>
          </table>
          <div class="alert-box" style="margin-top:16px;">
            <p style="margin:4px 0;"><strong>Economia Estimada (PB15):</strong> Tarifa ${brl(econ.tarifa_brl_kwh)}/kWh × Energia Compensada ${num(econ.energia_compensada_kwh_mes)} kWh/mês = <strong>${brl(econ.economia_mensal_brl)} / mês</strong> (<strong>${brl(econ.economia_anual_brl)} / ano</strong>)</p>
            <p style="margin:4px 0;"><strong>Payback Simples (PB16):</strong> <span class="badge badge-green">${pay.payback_formatado} (Sobre Investimento Total)</span> &nbsp;|&nbsp; <span class="badge badge-blue">${num(pay.payback_apenas_equipamentos_anos)} anos (Considerando apenas Equipamentos do Dataset)</span></p>
            <p style="margin:4px 0; font-size:12px; color:var(--muted);">${pay.aviso_nao_exato}</p>
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
              <th>Indicador Técnico / Econômico</th>
              <th>Cenário 1: Sem Baterias (On-Grid Convencional)</th>
              <th>Cenário 2: Com Baterias (Híbrido + Backup ${num(b.armazenamento.autonomia_h, 0)}h)</th>
            </tr>
          </thead>
          <tbody>
            <tr><td>Demanda da Residência (PB01/PB02)</td><td>${num(a.consumo)} kWh/mês (${num(a.consumo_diario)} kWh/dia) | ${num(a.potencia_residencia_w, 0)} W</td><td>${num(b.consumo)} kWh/mês (${num(b.consumo_diario)} kWh/dia) | ${num(b.potencia_residencia_w, 0)} W</td></tr>
            <tr><td>Potência FV Necessária / Instalada (PB04/PB06)</td><td>${num(a.p_fv, 3)} kWp / <strong>${num(a.p_inst, 3)} kWp</strong></td><td>${num(b.p_fv, 3)} kWp / <strong>${num(b.p_inst, 3)} kWp</strong></td></tr>
            <tr><td>Módulos Fotovoltaicos (PB05/PB06)</td><td>${cfgA.n_modulos}× [${modA.id}] ${modA.fabricante} ${modA.modelo} (${modA.potencia_wp} Wp)</td><td>${cfgB.n_modulos}× [${modB.id}] ${modB.fabricante} ${modB.modelo} (${modB.potencia_wp} Wp)</td></tr>
            <tr><td>Inversor Selecionado e R_DC/AC (PB07)</td><td>[${invA.id}] ${invA.fabricante} ${invA.modelo} (${invA.tipo}, ${invA.potencia_nominal_w}W, efic. ${num(invA.eficiencia_pct, 1)}%, R_DC/AC = ${num(cfgA.ratio_dc_ac)})</td><td>[${invB.id}] ${invB.fabricante} ${invB.modelo} (${invB.tipo}, ${invB.potencia_nominal_w}W, efic. ${num(invB.eficiencia_pct, 1)}%, R_DC/AC = ${num(cfgB.ratio_dc_ac)})</td></tr>
            <tr><td>Geração Estimada: Dia / Mês (PB08)</td><td>${num(a.geracao_dia, 2)} kWh/dia | <strong>${num(a.geracao_mes, 1)} kWh/mês</strong></td><td>${num(b.geracao_dia, 2)} kWh/dia | <strong>${num(b.geracao_mes, 1)} kWh/mês</strong></td></tr>
            <tr><td>Atendimento / Energia Compensada (PB09)</td><td><strong>${num(a.comparacao_geracao.atendimento_pct, 1)}%</strong> (${num(a.economia.energia_compensada_kwh_mes)} kWh/mês compensados + ${num(a.economia.energia_excedente_kwh_mes)} kWh/mês excedente)</td><td><strong>${num(b.comparacao_geracao.atendimento_pct, 1)}%</strong> (${num(b.economia.energia_compensada_kwh_mes)} kWh/mês compensados + ${num(b.economia.energia_excedente_kwh_mes)} kWh/mês excedente)</td></tr>
            <tr><td>Armazenamento em Baterias (PB10/PB11/PB12)</td><td>Sem armazenamento (0 kWh, R$ 0,00)</td><td><strong>${b.armazenamento.n_baterias}× [${batB.id}] ${batB.fabricante} ${batB.modelo}</strong> (${num(b.armazenamento.capacidade_instalada_kwh)} kWh nominais / ${num(b.armazenamento.capacidade_util_kwh)} kWh úteis, DoD ${batB.dod_pct}%)</td></tr>
            <tr><td>Autonomia de Backup (PB11)</td><td>0 h (desliga em queda de rede por anti-ilhamento)</td><td><strong>${num(b.armazenamento.autonomia_h, 1)} horas</strong> (E_aut = ${num(b.armazenamento.energia_autonomia_kwh)} kWh | C_bat = ${num(b.armazenamento.c_bat_kwh)} kWh)</td></tr>
            <tr><td>Custo dos Equipamentos — Σ Datasets (PB13)</td><td><strong>${brl(a.orcamento.c_equipamentos)}</strong></td><td><strong>${brl(b.orcamento.c_equipamentos)}</strong> (+${brl(comp.diferenca_equipamentos_brl)})</td></tr>
            <tr><td>Outros Custos e Instalação</td><td>${brl(a.orcamento.c_outros)}</td><td>${brl(b.orcamento.c_outros)}</td></tr>
            <tr><td>Investimento Total Estimado</td><td><strong>${brl(a.orcamento.c_total)}</strong></td><td><strong>${brl(b.orcamento.c_total)}</strong> (+${brl(comp.diferenca_investimento_total_brl)} / +${num(comp.acrescimo_percentual, 1)}%)</td></tr>
            <tr><td>Economia Mensal / Anual na Conta (PB15)</td><td><strong>${brl(a.economia.economia_mensal_brl)}/mês</strong> | <strong>${brl(a.economia.economia_anual_brl)}/ano</strong></td><td><strong>${brl(b.economia.economia_mensal_brl)}/mês</strong> | <strong>${brl(b.economia.economia_anual_brl)}/ano</strong></td></tr>
            <tr><td>Payback Simples (Só Equipamentos Dataset)</td><td><span class="badge badge-green">${num(a.payback.payback_apenas_equipamentos_anos)} anos</span></td><td><span class="badge badge-amber">${num(b.payback.payback_apenas_equipamentos_anos)} anos</span></td></tr>
            <tr><td>Payback Simples (Investimento Total / Economia Anual) (PB16)</td><td><span class="badge badge-green">${a.payback.payback_formatado}</span></td><td><span class="badge badge-amber">${b.payback.payback_formatado}</span></td></tr>
          </tbody>
        </table>
      `;

      document.getElementById('box-questao-9-comp').innerHTML = `
        <h3 style="margin-top:0; color:#065f46;">Conclusão Fundamentada da Equipe Lumos (Seção 9 — ${apelido})</h3>
        <p style="white-space:pre-line; margin:0;">${comp.analise_questao_final}</p>
      `;
    }

    function renderizarAbaProposta(est) {
      document.getElementById('pre-proposta-consolidada').textContent =
        est.proposta_txt + "\n\n" + est.comparacao_txt;

      const hist = est.dimensionamentos_salvos || [];
      if (hist.length === 0) {
        document.getElementById('tabela-historico-container').innerHTML = `<p>Nenhum dimensionamento salvo ainda.</p>`;
        return;
      }
      document.getElementById('tabela-historico-container').innerHTML = `
        <table>
          <thead>
            <tr><th>ID</th><th>Data</th><th>Localidade / HSP</th><th>Consumo</th><th>Potência FV</th><th>Módulos & Inversor</th><th>Armazenamento</th><th style="text-align:right">Investimento Total</th><th style="text-align:right">Economia/Mês</th><th>Payback Simples</th></tr>
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
          <thead><tr><th>ID</th><th>Fabricante</th><th>Modelo</th><th style="text-align:right">Potência</th><th style="text-align:right">Voc / Vmp</th><th style="text-align:right">Isc / Imp</th><th style="text-align:right">Eficiência</th><th style="text-align:right">Preço Unit.</th><th>Fornecedor / Data</th></tr></thead>
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
          <thead><tr><th>ID</th><th>Fabricante</th><th>Modelo</th><th>Tecnologia</th><th style="text-align:right">Tensão</th><th style="text-align:right">Capacidade</th><th style="text-align:right">DoD / Ciclos</th><th style="text-align:right">Preço Unit.</th><th>Fornecedor / Data</th></tr></thead>
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
        alert('Erro ao adicionar equipamento: ' + res.erro);
        return;
      }
      await carregarEstado(ESTADO.imovel_selecionado_id);
    }

    async function removerCargaResidencia(assocId) {
      const resp = await fetch('/api/associacoes/remover', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ assoc_id: assocId, imovel_id: ESTADO.imovel_selecionado_id })
      });
      const res = await resp.json();
      if (res.ok) {
        await carregarEstado(ESTADO.imovel_selecionado_id);
      }
    }

    async function executarDimensionamentoAPI() {
      const selLoc = document.getElementById('dim-localidade');
      const idxLoc = Number(selLoc.value);
      const locInfo = ESTADO.datasets.hsp_localidades[idxLoc] || ESTADO.hsp_atual;

      const payload = {
        imovel_id: ESTADO.imovel_selecionado_id,
        consumo: Number(document.getElementById('dim-consumo').value),
        percentual: Number(document.getElementById('dim-percentual').value),
        cidade: locInfo.cidade,
        uf: locInfo.uf,
        hsp: Number(document.getElementById('dim-hsp').value),
        fonte_hsp: locInfo.fonte,
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
      const fb = document.getElementById('dim-feedback');
      if (!res.ok) {
        fb.innerHTML = `<div class="alert-box alert-error"><strong>Bloqueio / Validação de Dados (PB18):</strong><br><pre style="margin:6px 0 0 0; white-space:pre-wrap; font-family:inherit;">${res.erro}</pre></div>`;
        return;
      }
      fb.innerHTML = `<div class="alert-box alert-success"><strong>Dimensionamento #${res.id_salvo} calculado pelo motor Python e salvo em <code>dados_sistema.json</code> (PB20/PB21)!</strong></div>`;
      ESTADO.dimensionamento_atual = res.resultado;
      ESTADO.comparacao_atual = res.comparacao;
      ESTADO.proposta_txt = res.proposta_txt;
      ESTADO.comparacao_txt = res.comparacao_txt;
      ESTADO.dimensionamentos_salvos = res.dimensionamentos_salvos;

      // Atualiza KPIs e painéis
      const dim = res.resultado;
      document.getElementById('kpi-potencia-fv').textContent = `${num(dim.p_inst, 2)} kWp (${dim.selecao.config.n_modulos} módulos)`;
      document.getElementById('kpi-fv-sub').textContent = `P_FV nec.: ${num(dim.p_fv, 3)} kWp | HSP: ${num(dim.hsp_info.hsp, 1)} | PR: ${num(dim.pr * 100, 0)}%`;
      document.getElementById('kpi-geracao').textContent = `${num(dim.geracao_mes, 1)} kWh/mês`;
      document.getElementById('kpi-geracao-sub').textContent = `Diária: ${num(dim.geracao_dia, 2)} kWh/dia | Atendimento: ${num(dim.comparacao_geracao.atendimento_pct, 1)}%`;
      document.getElementById('kpi-orcamento').textContent = brl(dim.orcamento.c_total);
      document.getElementById('kpi-payback-sub').textContent = `Econ.: ${brl(dim.economia.economia_mensal_brl)}/mês | Payback: ${num(dim.payback.payback_simples_anos)} anos`;

      renderizarResultadoDimensionamento(res.resultado, ESTADO.imovel_atual.apelido);
      renderizarAbaComparacao(res.comparacao, ESTADO.imovel_atual.apelido);
      renderizarAbaProposta(ESTADO);
    }

    async function testarValidacaoErroPB18() {
      // Simula tentativa inválida (inversor on-grid INV001 com baterias ativadas) para demonstrar PB18 ao vivo
      const resp = await fetch('/api/dimensionar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          imovel_id: ESTADO.imovel_selecionado_id,
          consumo: ESTADO.imovel_atual.consumo_mensal_kwh,
          percentual: 100,
          cidade: ESTADO.imovel_atual.cidade,
          uf: ESTADO.imovel_atual.uf,
          hsp: ESTADO.hsp_atual.hsp,
          pr: 0.78,
          modulo_id: 'FV006',
          inversor_id: 'INV001',
          com_bateria: true,
          autonomia: 12,
          tarifa_kwh: 0.92
        })
      });
      const res = await resp.json();
      const fb = document.getElementById('dim-feedback');
      fb.innerHTML = `<div class="alert-box alert-error"><strong>Demonstração de Validação Técnica (PB18 — Tentativa de usar Inversor On-Grid INV001 com Baterias):</strong><br><pre style="margin:6px 0 0 0; white-space:pre-wrap; font-family:inherit;">${res.erro}</pre></div>`;
    }

    async function recalcularComparacaoAPI() {
      const aut = Number(document.getElementById('comp-autonomia-input').value) || 12;
      const resp = await fetch('/api/comparar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          imovel_id: ESTADO.imovel_selecionado_id,
          autonomia: aut,
          tarifa_kwh: Number(document.getElementById('dim-tarifa').value) || 0.92
        })
      });
      const res = await resp.json();
      if (res.ok) {
        ESTADO.comparacao_atual = res.comparacao;
        renderizarAbaComparacao(res.comparacao, ESTADO.imovel_atual.apelido);
        renderizarSprintReview15Etapas(ESTADO.imovel_atual, res.comparacao, ESTADO.datasets);
      }
    }

    async function executarTestesQA() {
      const pre = document.getElementById('pre-qa-output');
      pre.textContent = 'Executando bateria de testes automatizados (testes.py)...';
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
        # Mantem o log do console limpo
        pass

    def _enviar_json(self, dados_dict, status=200):
        corpo = json.dumps(dados_dict, ensure_ascii=False).encode("utf-8")
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

        if rota in ("/proposta_cliente.html", "/proposta_cliente.txt"):
            arq = os.path.join(PASTA_BASE, rota.lstrip("/"))
            if os.path.exists(arq):
                with open(arq, "rb") as f:
                    conteudo = f.read()
                ctype = "text/html; charset=utf-8" if rota.endswith(".html") else "text/plain; charset=utf-8"
                self.send_response(200)
                self.send_header("Content-Type", ctype)
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
                cargas_det = sc.obter_cargas_detalhadas_imovel(imovel_id)
                fv.exportar_proposta_txt(r, comp, imovel["apelido"])
                fv.exportar_proposta_html(r, comp, imovel["apelido"], cargas_residencia=cargas_det)

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
    print("  INTERFACE GRAFICA WEB INTEGRADA ATIVA (SPRINT 3 - PB01 A PB21)")
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

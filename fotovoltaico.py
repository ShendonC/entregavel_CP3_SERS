#   ============================================================
#   fotovoltaico.py - REGRAS DE NEGOCIO DA EVOLUCAO FOTOVOLTAICA
#   Sistema de Dimensionamento Energetico Residencial (Sprint 3 - Final)
#   Disciplina: Solucoes em Energias Renovaveis e Sustentaveis (Prof. Alvaro Goncalves)
#
#   Equipe Lumos - FIAP:
#   - Pietro Lorande | RM 569125
#   - Luiz Otavio Brito Freixo (Luiz Otavio Britto Freixo) | RM 569977
#   - Maria Eduarda Lemos | RM 574094
#
#   So calculos, datasets, comparacao de cenarios, analise economica,
#   orcamento e exportacao da proposta: este arquivo NAO faz perguntas
#   ao usuario nem altera o dados_sistema.json diretamente.
#   As telas ficam em sistema_analise_casa.py e os testes em testes.py.
#
#   Cobertura completa da Sprint 3 (Product Backlog Final - PB01 a PB21):
#   PB01 Recuperacao da residencia         PB12 Dataset de baterias
#   PB02 Demanda energetica (E_dia/E_mes)  PB13 Orcamento automatico (preco unitario/total)
#   PB03 Recurso solar (HSP e PR)          PB14 Comparacao de cenarios (sem vs com bateria)
#   PB04 Potencia FV necessaria (kWp)      PB15 Estimativa de economia (mensal e anual)
#   PB05 Dataset de modulos FV             PB16 Payback simples
#   PB06 Dimensionamento dos modulos       PB17 Relatorio consolidado
#   PB07 Selecao e compatibilidade inv.    PB18 Validacao de dados
#   PB08 Estimativa de geracao (dia/mes)   PB19 Interface integrada
#   PB09 Comparacao geracao x consumo      PB20 Persistencia do projeto
#   PB10 Opcao sem ou com baterias         PB21 Exportacao da proposta (TXT e HTML)
#   PB11 Dimensionamento das baterias
#   ============================================================

import os
import csv
import math
import unicodedata
from datetime import datetime

PASTA_BASE = os.path.dirname(os.path.abspath(__file__))
PASTA_FV = os.path.join(PASTA_BASE, "dados_fv")


# Parametros tecnicos e premissas adotadas pela equipe (PB03, PB07, PB11, PB13, PB15, PB16)
PARAMETROS_FV = {
    "dias_mes": 30,             # D = 30 dias/mes (PB02, PB08)
    "eta_global": 0.78,         # PR (Performance Ratio) = 0,78 (78%) - EPE NT DEA-SEE 009/2023 (faixa tipica 75-80%)
    "justificativa_pr": (
        "PR = 0,78 (78%) adotado conforme Nota Tecnica EPE DEA-SEE 009/2023 e manual CRESESB/CEPEL "
        "(faixa tipica residencial de 75% a 80%), contabilizando perdas termicas nos modulos (~8%), "
        "sujeira e sombreamento leve (~5%), quedas ohmicas em cabos CC/CA (~3%), mismatch (~2%) e "
        "eficiencia de conversao do inversor (~2% a 4%)."
    ),
    "eta_bateria": 0.95,        # Rendimento round-trip tipico de bancos LiFePO4 (95%)
    "hsp_min": 3.0,             # Faixa plausivel de HSP no Brasil (CRESESB / Atlas Solarimetrico 2017)
    "hsp_max": 7.0,
    "fator_voc_frio": 1.10,     # Margem de seguranca para aumento de Voc em baixas temperaturas (+10%)
    "fator_vmp_quente": 0.90,   # Margem para reducao de Vmp em altas temperaturas de operacao (-10%)
    "ratio_dc_ac_min": 0.60,    # Limite inferior de carregamento DC/AC para inversores on-grid
    "ratio_dc_ac_min_hibrido": 0.30,  # Limite inferior DC/AC para inversores hibridos de 5 kW
    "ratio_dc_ac_max": 1.35,    # Limite superior de sobrecarregamento (overload) DC/AC
    "autonomia_max_h": 72,      # Limite maximo de autonomia em horas para bancos residenciais
    "tarifa_padrao_brl_kwh": 0.92,  # Tarifa residencial media B1 com tributos (ICMS/PIS/COFINS) - ANEEL/Enel SP
    "fonte_tarifa_padrao": "Tarifa convencional B1 residencial com impostos (referencia ANEEL / Enel SP 2026)",
    "outros_custos_pct": {
        "Estrutura de fixacao": 8,
        "Cabeamento e conectores": 4,
        "Protecoes / string box": 5,
    },
    "instalacao_por_kwp": 500.0,
    "projeto_homologacao": 800.0,
}

# Schemas dos datasets estruturados (PB05, PB07, PB12, Secao 4)
RASTREIO = ["fornecedor", "data_coleta", "url_fonte"]
DATASETS_FV = {
    "modulos": (
        "modulos.csv",
        10,
        ["id", "fabricante", "modelo"] + RASTREIO,
        ["potencia_wp", "voc_v", "isc_a", "vmp_v", "imp_a", "eficiencia_pct", "preco_brl"],
    ),
    "inversores": (
        "inversores.csv",
        8,
        ["id", "fabricante", "modelo", "tipo", "compativel_bateria"] + RASTREIO,
        [
            "potencia_nominal_w",
            "potencia_max_fv_w",
            "tensao_max_entrada_v",
            "faixa_mppt_min_v",
            "faixa_mppt_max_v",
            "corrente_max_entrada_a",
            "numero_mppt",
            "strings_por_mppt",
            "eficiencia_pct",
            "tensao_bateria_min_v",
            "tensao_bateria_max_v",
            "preco_brl",
        ],
    ),
    "baterias": (
        "baterias.csv",
        6,
        ["id", "fabricante", "modelo", "tecnologia"] + RASTREIO,
        ["tensao_nominal_v", "capacidade_ah", "capacidade_kwh", "dod_pct", "ciclos", "preco_brl"],
    ),
}


# ------------------------------------------------------------------
# Leitura e validacao dos datasets (PB05, PB07, PB12, PB18)
# ------------------------------------------------------------------

def localizar_caminho_csv(nome_arquivo):
    """
    Procura o arquivo CSV primeiro em dados_fv/ e depois na mesma pasta do script,
    garantindo funcionamento tanto com subpasta dados_fv/ quanto na raiz do repositorio.
    """
    caminho_subpasta = os.path.join(PASTA_FV, nome_arquivo)
    if os.path.exists(caminho_subpasta):
        return caminho_subpasta
    caminho_raiz = os.path.join(PASTA_BASE, nome_arquivo)
    if os.path.exists(caminho_raiz):
        return caminho_raiz
    raise FileNotFoundError(
        f"Arquivo '{nome_arquivo}' nao encontrado em '{PASTA_FV}' nem em '{PASTA_BASE}'."
    )


def ler_csv(nome_arquivo):
    """Le um CSV convertendo para float todos os campos numericos (FV-PB11-T06)."""
    caminho = localizar_caminho_csv(nome_arquivo)
    with open(caminho, "r", encoding="utf-8-sig", newline="") as f:
        linhas = list(csv.DictReader(f))
    for linha in linhas:
        # Compatibilidade retroativa caso inversores.csv antigo nao tenha a coluna eficiencia_pct
        if nome_arquivo == "inversores.csv" and "eficiencia_pct" not in linha:
            linha["eficiencia_pct"] = "97.8"
        for campo, valor in list(linha.items()):
            valor = (valor or "").strip()
            try:
                linha[campo] = float(valor)
            except ValueError:
                linha[campo] = valor
    return linhas


def carregar_dataset(categoria):
    """
    PB05 / PB07 / PB12 - devolve (validos, pendentes).
    Linha pendente = item incompleto, sem preco ou sem link: fica fora dos calculos.
    """
    arquivo, _, textos, numeros = DATASETS_FV[categoria]
    validos, pendentes = [], []
    for item in ler_csv(arquivo):
        if any(item.get(c, "") == "" for c in textos):
            motivo = "campo de texto vazio"
        elif any(not isinstance(item.get(c), float) for c in numeros):
            motivo = "campo numerico vazio ou invalido"
        elif item["preco_brl"] <= 0 or not str(item["url_fonte"]).startswith("http"):
            motivo = "sem preco ou sem URL de fonte"
        else:
            motivo = None
        if motivo:
            pendentes.append((item.get("id", "?"), motivo))
        else:
            validos.append(item)
    if categoria == "inversores":
        for inv in validos:
            inv["compativel_bateria"] = str(inv["compativel_bateria"]).upper() == "SIM"
    return validos, pendentes


def normalizar_localidade(cidade, uf):
    texto = unicodedata.normalize("NFKD", f"{str(cidade).strip()}/{str(uf).strip()}".upper())
    return "".join(c for c in texto if not unicodedata.combining(c))


def carregar_datasets_fv():
    """Carrega todos os datasets estruturados (modulos, inversores, baterias e HSP)."""
    hsp = {
        normalizar_localidade(l["cidade"], l["uf"]): {
            "cidade": l["cidade"],
            "uf": l["uf"],
            "hsp": l["hsp_kwh_m2_dia"],
            "fonte": l["fonte"],
            "url_fonte": l["url_fonte"],
        }
        for l in ler_csv("hsp_localidades.csv")
    }
    ds = {cat: carregar_dataset(cat)[0] for cat in DATASETS_FV}
    ds["hsp"] = hsp
    return ds


def validar_datasets_fv():
    """FV-PB11-T08 / PB05 / PB07 / PB12 - quantidade minima, dados completos, rastreabilidade de fonte e preco."""
    aprovado, linhas = True, ["==== VALIDACAO DOS DATASETS (FV-PB11-T08 / SPRINT 3) ===="]
    for categoria, (arquivo, minimo, _, _) in DATASETS_FV.items():
        validos, pendentes = carregar_dataset(categoria)
        ids = [v["id"] for v in validos]
        ok = len(validos) >= minimo and len(ids) == len(set(ids))
        aprovado = aprovado and ok
        linhas.append(f"[{'OK' if ok else 'PENDENTE'}] {arquivo}: {len(validos)} validos / minimo {minimo}")
        linhas += [f"   - pendente {pid}: {motivo}" for pid, motivo in pendentes]
        conferir = [v["id"] for v in validos if str(v.get("status_validacao", "")).startswith("CONFERIR")]
        if conferir:
            linhas.append(f"   - conferir datasheet/preco antes da entrega: {', '.join(conferir)}")
    linhas.append(f"RESULTADO GERAL: {'APROVADO' if aprovado else 'COM PENDENCIAS'}")
    return aprovado, "\n".join(linhas)


# ------------------------------------------------------------------
# Formulas e validacoes (PB02, PB03, PB04, PB06, PB08, PB09, PB11, PB15, PB16, PB18)
# ------------------------------------------------------------------

def positivo(nome, valor):
    if valor is None or isinstance(valor, bool):
        raise ValueError(f"{nome} nao informado ou nao numerico.")
    try:
        valor = float(str(valor).replace(",", "."))
    except (TypeError, ValueError):
        raise ValueError(f"{nome} nao informado ou nao numerico.")
    if not math.isfinite(valor) or valor <= 0:
        raise ValueError(f"{nome} deve ser maior que zero.")
    return valor


def nao_negativo(nome, valor):
    if valor is None or isinstance(valor, bool):
        raise ValueError(f"{nome} nao informado ou nao numerico.")
    try:
        valor = float(str(valor).replace(",", "."))
    except (TypeError, ValueError):
        raise ValueError(f"{nome} nao informado ou nao numerico.")
    if not math.isfinite(valor) or valor < 0:
        raise ValueError(f"{nome} nao pode ser negativo.")
    return valor


def arredondar_para_cima(valor):
    """Evita que 8.0000000001 vire 9 por erro de ponto flutuante."""
    return math.ceil(round(valor, 9))


def validar_percentual(texto):
    """PB02 / FV-PB02-T02 - aceita (0, 100]. 0% nao gera sistema. Devolve a fracao f."""
    if texto is None or str(texto).strip() == "":
        raise ValueError("Percentual nao informado.")
    p = positivo("Percentual", str(texto).replace("%", ""))
    if p > 100:
        raise ValueError("Percentual deve ser no maximo 100%.")
    return p / 100


def validar_hsp(valor):
    """PB03 / PB18 - valida HSP > 0 e dentro da faixa plausivel (3,0 a 7,0 kWh/m2/dia)."""
    hsp = positivo("HSP", valor)
    if not PARAMETROS_FV["hsp_min"] <= hsp <= PARAMETROS_FV["hsp_max"]:
        raise ValueError(f"HSP {hsp} fora da faixa plausivel (3,0 a 7,0 kWh/m2/dia).")
    return hsp


def validar_pr(valor):
    """PB03 / PB18 - valida Performance Ratio (PR) no intervalo (0, 1] (ou percentual entre 10 e 100)."""
    pr = positivo("Performance Ratio (PR)", valor)
    if pr > 1.0 and pr <= 100.0:
        pr = pr / 100.0
    if not (0.10 <= pr <= 1.0):
        raise ValueError("Performance Ratio (PR) invalido: informe valor entre 0,10 e 1,00 (ex.: 0,78).")
    return pr


def validar_tarifa(valor):
    """PB15 / PB18 - valida tarifa de energia eletrica em R$/kWh (> 0)."""
    tarifa = positivo("Tarifa de energia (R$/kWh)", valor)
    if tarifa > 10.0:
        raise ValueError("Tarifa de energia fora da faixa residencial plausivel (ate R$ 10,00/kWh).")
    return tarifa


def validar_autonomia(valor):
    """PB11 / FV-PB06-T02 - autonomia em (0, 72] horas."""
    horas = positivo("Autonomia", valor)
    if horas > PARAMETROS_FV["autonomia_max_h"]:
        raise ValueError("Autonomia maxima aceita: 72 h.")
    return horas


def consumo_diario(cm):
    """PB02 - E_dia = E_mes / 30 [kWh/dia]"""
    return positivo("Consumo mensal", cm) / PARAMETROS_FV["dias_mes"]


def demanda_energetica_residencia(consumo_mensal_kwh, potencia_instalada_w=0.0):
    """
    PB02 - Recuperacao da demanda energetica da residencia:
    Apresenta consumo medio diario (E_dia = E_mes / 30) e mensal em kWh,
    alem da potencia instalada da residencia em W e kW.
    """
    e_mes = positivo("Consumo mensal da residencia (kWh/mes)", consumo_mensal_kwh)
    p_res_w = nao_negativo("Potencia instalada da residencia (W)", potencia_instalada_w)
    e_dia = e_mes / PARAMETROS_FV["dias_mes"]
    return {
        "consumo_mensal_kwh": round(e_mes, 3),
        "consumo_diario_kwh": round(e_dia, 3),
        "potencia_instalada_w": round(p_res_w, 2),
        "potencia_instalada_kw": round(p_res_w / 1000.0, 3),
        "unidades": {
            "consumo_mensal": "kWh/mes",
            "consumo_diario": "kWh/dia",
            "potencia_instalada_w": "W",
            "potencia_instalada_kw": "kW",
        },
    }


def energia_mensal_desejada(cm, f):
    """FV-PB03-T02 - E_FV = Cm * f [kWh/mes]"""
    if positivo("Fracao de atendimento", f) > 1:
        raise ValueError("Fracao de atendimento nao pode passar de 1 (100%).")
    return positivo("Consumo de referencia", cm) * f


def potencia_fv_por_consumo_diario(e_dia, hsp, pr):
    """
    PB04 - Calculo da potencia fotovoltaica necessaria pela formula da Sprint 3:
    P_FV = E_dia / (HSP * PR) [kWp]
    """
    pr_val = positivo("PR", pr)
    if pr_val > 1:
        raise ValueError("PR deve estar entre 0 e 1.")
    return positivo("Consumo diario (E_dia)", e_dia) / (positivo("HSP", hsp) * pr_val)


def potencia_fv_necessaria(e_fv, hsp, dias, eta):
    """
    PB04 / FV-PB03-T04 - P_FV = E_FV / (HSP * D * PR) = E_dia / (HSP * PR) [kWp]
    """
    if positivo("PR (eta)", eta) > 1:
        raise ValueError("PR (eta) deve estar entre 0 e 1.")
    return positivo("Energia desejada", e_fv) / (positivo("HSP", hsp) * positivo("Dias", dias) * eta)


def quantidade_minima_modulos(p_fv, p_modulo):
    """PB06 - N_mod = teto[(P_FV * 1000) / P_mod]"""
    return arredondar_para_cima(positivo("P_FV", p_fv) * 1000 / positivo("Potencia do modulo", p_modulo))


def potencia_instalada(n, p_modulo):
    """PB06 - P_inst = (N_mod * P_mod) / 1000 [kWp]"""
    return positivo("Quantidade de modulos", n) * positivo("Potencia do modulo", p_modulo) / 1000


def geracao_estimada_diaria(p_inst, hsp, pr):
    """PB08 - E_gerada,dia = P_inst * HSP * PR [kWh/dia]"""
    pr_val = positivo("PR", pr)
    if pr_val > 1:
        raise ValueError("PR deve estar entre 0 e 1.")
    return positivo("Potencia instalada (kWp)", p_inst) * positivo("HSP", hsp) * pr_val


def geracao_estimada_mensal(p_inst, hsp, dias=30, pr=0.78):
    """PB08 - E_gerada,mes = E_gerada,dia * 30 [kWh/mes]"""
    e_dia = geracao_estimada_diaria(p_inst, hsp, pr)
    return e_dia * positivo("Dias no mes", dias)


def comparar_geracao_consumo(consumo_mes, geracao_mes):
    """
    PB09 - Comparacao geracao x consumo:
    Atendimento (%) = (E_gerada,mes / E_consumida,mes) * 100
    Quando a geracao superar o consumo, distingue a energia total gerada da
    energia efetivamente consumida/compensada na fatura e o excedente injetado na rede.
    """
    e_cons = positivo("Consumo mensal (E_consumida,mes)", consumo_mes)
    e_ger = nao_negativo("Geracao mensal (E_gerada,mes)", geracao_mes)
    atendimento_pct = (e_ger / e_cons) * 100.0
    e_compensada = min(e_ger, e_cons)
    e_excedente = max(0.0, e_ger - e_cons)
    return {
        "consumo_mensal_kwh": round(e_cons, 2),
        "geracao_mensal_kwh": round(e_ger, 2),
        "atendimento_pct": round(atendimento_pct, 2),
        "atendimento_efetivo_pct": round(min(100.0, atendimento_pct), 2),
        "energia_compensada_kwh_mes": round(e_compensada, 2),
        "energia_excedente_kwh_mes": round(e_excedente, 2),
        "supera_consumo": e_ger > e_cons,
    }


def energia_autonomia(e_d, horas):
    """PB11 / FV-PB06-T04 - E_autonomia = E_d * (A / 24) [kWh]"""
    return positivo("Consumo diario", e_d) * positivo("Autonomia", horas) / 24


def capacidade_bateria_necessaria(e_aut, dod, eta_bat):
    """PB11 - C_bat = E_aut / (DoD * eta_bat) [kWh nominais]"""
    if positivo("DoD", dod) > 1 or positivo("eta_bat", eta_bat) > 1:
        raise ValueError("DoD e eta_bat devem estar entre 0 e 1.")
    return positivo("Energia de autonomia", e_aut) / (dod * eta_bat)


def capacidade_util(c_nominal, dod):
    """PB11 / FV-PB07-T04 - C_util = C_nominal * DoD [kWh]"""
    return positivo("Capacidade nominal", c_nominal) * positivo("DoD", dod)


def quantidade_baterias(c_necessaria, c_util):
    """
    PB11 / FV-PB07-T05 - N_bat = teto(C_bat / C_unidade) = teto(C_necessaria / C_util),
    onde C_necessaria = E_aut / eta_bat e C_util = C_unidade * DoD.
    Evita aplicar o DoD duas vezes e equivale exatamente a teto(C_bat / C_unidade).
    """
    return arredondar_para_cima(positivo("Capacidade necessaria", c_necessaria) / positivo("C_util", c_util))


def obter_hsp(cidade, uf, tabela, hsp_manual=None, fonte_manual=None):
    """PB03 / FV-PB01-T04 - HSP da tabela; cidade fora da tabela exige valor E fonte."""
    if hsp_manual is not None:
        if not str(fonte_manual or "").strip():
            raise ValueError("Informe a origem do HSP (ex.: 'CRESESB SunData - Osasco/SP').")
        return {
            "cidade": cidade,
            "uf": uf.upper(),
            "hsp": validar_hsp(hsp_manual),
            "fonte": fonte_manual.strip(),
            "url_fonte": "informado pelo usuario",
        }
    registro = tabela.get(normalizar_localidade(cidade, uf))
    if registro is None:
        raise ValueError(f"Nao ha HSP cadastrado para {cidade}/{uf}.")
    validar_hsp(registro["hsp"])
    return dict(registro)


# ------------------------------------------------------------------
# Criterios de compatibilidade tecnica (PB07, PB11, PB18 - C1 a C8)
# ------------------------------------------------------------------

def verificar_modulo_inversor(n_minimo, mod, inv, com_bateria, P=PARAMETROS_FV):
    """
    PB07 + FV-PB08-T02/T04 - Verifica compatibilidade eletrica entre arranjo FV e inversor:
      C1: Voc_string * 1,10 <= tensao max. de entrada do inversor
      C2: Vmp_string <= faixa MPPT maxima
      C3: Vmp_string * 0,90 >= faixa MPPT minima
      C4: corrente das strings em paralelo <= corrente max. por MPPT
      C5: P_instalada <= potencia FV maxima do inversor
      C6: razao R_DC/AC = P_FV_instalada / P_inversor dentro da faixa operacional
      C7: com armazenamento -> inversor hibrido obrigatorio
    """
    motivos = []
    if com_bateria and not inv["compativel_bateria"]:
        motivos.append("C7: armazenamento pedido, mas o inversor nao e hibrido")

    serie_max = min(
        math.floor(inv["tensao_max_entrada_v"] / (mod["voc_v"] * P["fator_voc_frio"])),
        math.floor(inv["faixa_mppt_max_v"] / mod["vmp_v"]),
    )
    serie_min = math.ceil(inv["faixa_mppt_min_v"] / (mod["vmp_v"] * P["fator_vmp_quente"]))
    paralelo_max = min(int(inv["strings_por_mppt"]), math.floor(inv["corrente_max_entrada_a"] / mod["imp_a"]))

    if paralelo_max < 1:
        motivos.append(
            f"C4: corrente do modulo ({mod['imp_a']} A) > max. do inversor ({inv['corrente_max_entrada_a']} A)"
        )
    if serie_max < 1 or serie_min > serie_max:
        motivos.append("C1-C3: nenhuma quantidade de modulos em serie cabe na faixa de tensao do inversor")
    if motivos:
        return None, motivos

    n_strings = math.ceil(n_minimo / serie_max)
    if n_strings > int(inv["numero_mppt"]) * paralelo_max:
        return None, [f"C1-C4: {n_minimo} modulos nao cabem nas entradas do inversor"]
    por_string = max(math.ceil(n_minimo / n_strings), serie_min)
    n_final = n_strings * por_string
    p_inst = potencia_instalada(n_final, mod["potencia_wp"])
    ratio = p_inst * 1000 / inv["potencia_nominal_w"]
    ratio_min = P["ratio_dc_ac_min_hibrido"] if inv["compativel_bateria"] else P["ratio_dc_ac_min"]

    if p_inst * 1000 > inv["potencia_max_fv_w"]:
        motivos.append(f"C5: {p_inst * 1000:.0f} Wp > maximo do inversor ({inv['potencia_max_fv_w']:.0f} W)")
    if not ratio_min <= ratio <= P["ratio_dc_ac_max"]:
        motivos.append(f"C6: razao DC/AC {ratio:.2f} fora da faixa {ratio_min}-{P['ratio_dc_ac_max']}")
    if motivos:
        return None, motivos
    return {
        "n_modulos": n_final,
        "n_strings": n_strings,
        "por_string": por_string,
        "potencia_instalada_kwp": p_inst,
        "ratio_dc_ac": ratio,
        "voc_string_v": por_string * mod["voc_v"] * P["fator_voc_frio"],
        "vmp_string_v": por_string * mod["vmp_v"],
    }, []


def verificar_inversor_bateria(inv, bat):
    """PB11 / FV-PB08-T03 - devolve lista de motivos (vazia = compativel)."""
    if not inv["compativel_bateria"]:
        return ["C7: inversor on-grid nao aceita baterias"]
    if not inv["tensao_bateria_min_v"] <= bat["tensao_nominal_v"] <= inv["tensao_bateria_max_v"]:
        return [
            f"C8: bateria de {bat['tensao_nominal_v']} V fora da faixa do inversor "
            f"({inv['tensao_bateria_min_v']:.0f}-{inv['tensao_bateria_max_v']:.0f} V)"
        ]
    return []


def selecionar_modulo_inversor(p_fv, ds, com_bateria, modulo_id=None, inversor_id=None):
    """
    PB05 / PB06 / PB07 - Testa todas as combinacoes modulo x inversor (ou filtra pelo ID
    escolhido pelo usuario), bloqueia as incompativeis pelas regras C1-C7 e seleciona
    a combinacao tecnicamente compativel de melhor relacao custo/ajuste.
    """
    modulos_cand = [m for m in ds["modulos"] if modulo_id is None or m["id"] == modulo_id]
    inversores_cand = [i for i in ds["inversores"] if inversor_id is None or i["id"] == inversor_id]
    if not modulos_cand:
        raise ValueError(f"Modulo '{modulo_id}' nao encontrado no dataset modulos.csv.")
    if not inversores_cand:
        raise ValueError(f"Inversor '{inversor_id}' nao encontrado no dataset inversores.csv.")

    candidatos, rejeitados = [], []
    for mod in modulos_cand:
        n_min = quantidade_minima_modulos(p_fv, mod["potencia_wp"])
        for inv in inversores_cand:
            config, motivos = verificar_modulo_inversor(n_min, mod, inv, com_bateria)
            if config is None:
                rejeitados.append((f"{mod['id']} x {inv['id']}", motivos))
            else:
                custo = config["n_modulos"] * mod["preco_brl"] + inv["preco_brl"]
                candidatos.append((
                    custo,
                    config["potencia_instalada_kwp"],
                    {"modulo": mod, "inversor": inv, "n_minimo": n_min, "config": config},
                ))
    if not candidatos:
        return None, rejeitados
    candidatos.sort(key=lambda c: (c[0], c[1]))
    escolhido = candidatos[0][2]
    escolhido["alternativas_validas"] = len(candidatos)
    return escolhido, rejeitados


def selecionar_bateria(e_aut, baterias, inv, bateria_id=None):
    """PB11 / PB12 - Entre as baterias compativeis com o inversor, seleciona a melhor opcao."""
    baterias_cand = [b for b in baterias if bateria_id is None or b["id"] == bateria_id]
    if not baterias_cand:
        raise ValueError(f"Bateria '{bateria_id}' nao encontrada no dataset baterias.csv.")

    eta = PARAMETROS_FV["eta_bateria"]
    candidatos, rejeitados = [], []
    for bat in baterias_cand:
        motivos = verificar_inversor_bateria(inv, bat)
        if motivos:
            rejeitados.append((f"{inv['id']} x {bat['id']}", motivos))
            continue
        dod = bat["dod_pct"] / 100
        c_bat = capacidade_bateria_necessaria(e_aut, dod, eta)
        c_util = capacidade_util(bat["capacidade_kwh"], dod)
        n_bat = quantidade_baterias(e_aut / eta, c_util)
        candidatos.append({
            "ativo": True,
            "bateria": bat,
            "n_baterias": n_bat,
            "c_bat_kwh": c_bat,
            "capacidade_instalada_kwh": round(n_bat * bat["capacidade_kwh"], 3),
            "capacidade_util_kwh": round(n_bat * c_util, 3),
            "capacidade_instalada_ah": round(n_bat * bat["capacidade_ah"], 1),
            "custo": round(n_bat * bat["preco_brl"], 2),
        })
    if not candidatos:
        return None, rejeitados
    return min(candidatos, key=lambda c: c["custo"]), rejeitados


# ------------------------------------------------------------------
# Orcamento, Economia e Payback Simples (PB13, PB14, PB15, PB16)
# ------------------------------------------------------------------

def calcular_orcamento(sel, arm):
    """
    PB13 - Geracao automatica do orcamento:
      Custo_item = quantidade * preco_unitario
      Custo_total = Soma(Custo_item)
    Apresenta equipamento, fabricante/modelo, quantidade, preco unitario, subtotal e total.
    """
    mod, inv, cfg = sel["modulo"], sel["inversor"], sel["config"]
    brutos = [
        (cfg["n_modulos"], "Modulo Fotovoltaico", f"Modulo {mod['fabricante']} {mod['modelo']}", mod),
        (1, "Inversor Fotovoltaico", f"Inversor {inv['fabricante']} {inv['modelo']}", inv),
    ]
    if arm["ativo"]:
        b = arm["bateria"]
        brutos.append((arm["n_baterias"], "Bateria de Armazenamento", f"Bateria {b['fabricante']} {b['modelo']}", b))

    itens = []
    for q, categoria_eq, nome, eq in brutos:
        preco_unit = round(float(eq["preco_brl"]), 2)
        subtotal = round(q * preco_unit, 2)
        itens.append({
            "qtd": q,
            "categoria": categoria_eq,
            "fabricante": eq["fabricante"],
            "modelo": eq["modelo"],
            "id_equipamento": eq["id"],
            "item": nome,
            "preco_unitario": preco_unit,
            "subtotal": subtotal,
            "fonte": f"{eq['fornecedor']} ({eq['data_coleta']}) {eq['url_fonte']}",
        })

    c_baterias = arm["custo"] if arm["ativo"] else 0.0
    c_equip = round(sum(i["subtotal"] for i in itens), 2)
    outros = [
        (nome, round(c_equip * pct / 100, 2), f"{pct}% dos equipamentos")
        for nome, pct in PARAMETROS_FV["outros_custos_pct"].items()
    ]
    outros.append((
        "Instalacao (mao de obra)",
        round(PARAMETROS_FV["instalacao_por_kwp"] * cfg["potencia_instalada_kwp"], 2),
        f"R$ {PARAMETROS_FV['instalacao_por_kwp']:.0f}/kWp",
    ))
    outros.append(("Projeto e homologacao", round(PARAMETROS_FV["projeto_homologacao"], 2), "valor fixo"))
    c_outros = round(sum(v for _, v, _ in outros), 2)
    return {
        "itens": itens,
        "c_baterias": c_baterias,
        "c_equipamentos": c_equip,
        "outros": outros,
        "c_outros": c_outros,
        "c_total": round(c_equip + c_outros, 2),
    }


def calcular_economia(geracao_mes, consumo_mes, tarifa_kwh=None):
    """
    PB15 - Estimativa de economia:
      Economia_mensal = E_compensada * tarifa
      Economia_anual = Economia_mensal * 12
    Onde E_compensada = min(E_gerada,mes, E_consumida,mes), distinguindo a energia
    efetivamente abatida do consumo mensal da eventual sobra injetada como credito.
    """
    tarifa = validar_tarifa(tarifa_kwh if tarifa_kwh is not None else PARAMETROS_FV["tarifa_padrao_brl_kwh"])
    comp = comparar_geracao_consumo(consumo_mes, geracao_mes)
    e_compensada = comp["energia_compensada_kwh_mes"]
    economia_mensal = round(e_compensada * tarifa, 2)
    economia_anual = round(economia_mensal * 12.0, 2)
    return {
        "tarifa_brl_kwh": round(tarifa, 4),
        "fonte_tarifa": PARAMETROS_FV["fonte_tarifa_padrao"],
        "energia_gerada_kwh_mes": comp["geracao_mensal_kwh"],
        "energia_consumida_kwh_mes": comp["consumo_mensal_kwh"],
        "energia_compensada_kwh_mes": e_compensada,
        "energia_excedente_kwh_mes": comp["energia_excedente_kwh_mes"],
        "economia_mensal_brl": economia_mensal,
        "economia_anual_brl": economia_anual,
        "premissas": (
            f"Tarifa considerada: R$ {tarifa:.2f}/kWh ({PARAMETROS_FV['fonte_tarifa_padrao']}). "
            f"Energia compensada limitada ao consumo da residencia "
            f"(min(E_gerada, E_consumo) = {e_compensada:.2f} kWh/mes). "
            "Calculo estimativo de 12 meses constantes, sem considerar reajustes tarifarios futuros ou fio B."
        ),
    }


def calcular_payback_simples(investimento_total, economia_anual, c_equipamentos=None):
    """
    PB16 - Payback simples:
      Payback = Investimento / Economia_anual
    Apresenta explicitamente como payback simples e nao como previsao financeira exata.
    """
    inv_total = positivo("Investimento total (R$)", investimento_total)
    econ_anual = positivo("Economia anual (R$/ano)", economia_anual)
    payback_total_anos = inv_total / econ_anual
    anos_int = int(math.floor(payback_total_anos))
    meses_rest = int(round((payback_total_anos - anos_int) * 12))
    if meses_rest == 12:
        anos_int += 1
        meses_rest = 0

    payback_equip_anos = None
    if c_equipamentos is not None and c_equipamentos > 0:
        payback_equip_anos = round(positivo("Custo dos equipamentos", c_equipamentos) / econ_anual, 2)

    return {
        "tipo_indicador": "Payback Simples (Estimativa Preliminar)",
        "investimento_considerado_brl": round(inv_total, 2),
        "economia_anual_brl": round(econ_anual, 2),
        "payback_simples_anos": round(payback_total_anos, 2),
        "payback_simples_meses": round(payback_total_anos * 12.0, 1),
        "payback_formatado": f"{payback_total_anos:.2f} anos (~{anos_int} anos e {meses_rest} meses)",
        "payback_apenas_equipamentos_anos": payback_equip_anos,
        "aviso_nao_exato": (
            "Resultado calculado como PAYBACK SIMPLES (Investimento / Economia_anual). "
            "Trata-se de uma estimativa preliminar de tempo de retorno e NAO representa previsao financeira "
            "exata (nao inclui taxa de desconto/VPL, inflacao energetica, degradacao anual dos modulos "
            "nem custos de substituicao de baterias ao longo de 25 anos)."
        ),
    }


class ErroDimensionamento(Exception):
    """FV-PB08-T04 / PB18 - combinacao bloqueada; guarda os motivos para exibir."""

    def __init__(self, mensagem, rejeitados):
        super().__init__(mensagem)
        self.rejeitados = rejeitados


def dimensionar_fv(
    consumo,
    percentual,
    hsp_info,
    ds,
    com_bateria=False,
    autonomia=None,
    origem="informado",
    tarifa_kwh=None,
    pr=None,
    potencia_residencia_w=0.0,
    modulo_id=None,
    inversor_id=None,
    bateria_id=None,
):
    """
    Fluxo integrado completo da Sprint 3 (PB01 a PB21):
    Residencia -> demanda (E_mes, E_dia, P_instalada) -> recurso solar (HSP, PR) ->
    P_FV -> modulos -> inversor -> geracao (dia/mes) -> comparacao geracao x consumo ->
    baterias opcionais -> orcamento -> economia -> payback simples -> proposta ao cliente.
    """
    P = PARAMETROS_FV
    f = validar_percentual(percentual)
    pr_adotado = validar_pr(pr if pr is not None else P["eta_global"])
    hsp_val = validar_hsp(hsp_info["hsp"])

    demanda = demanda_energetica_residencia(consumo, potencia_residencia_w)
    e_fv = energia_mensal_desejada(consumo, f)
    e_dia_meta = e_fv / P["dias_mes"]
    p_fv = potencia_fv_por_consumo_diario(e_dia_meta, hsp_val, pr_adotado)

    sel, rejeitados = selecionar_modulo_inversor(
        p_fv, ds, com_bateria, modulo_id=modulo_id, inversor_id=inversor_id
    )
    if sel is None:
        raise ErroDimensionamento("Nenhuma combinacao modulo x inversor e compativel.", rejeitados)

    if com_bateria:
        autonomia = validar_autonomia(autonomia)
        e_d = consumo_diario(consumo)
        e_aut = energia_autonomia(e_d, autonomia)
        arm, rej_bat = selecionar_bateria(e_aut, ds["baterias"], sel["inversor"], bateria_id=bateria_id)
        rejeitados += rej_bat
        if arm is None:
            raise ErroDimensionamento("Nenhuma bateria e compativel com o inversor escolhido.", rej_bat)
        arm.update({
            "autonomia_h": autonomia,
            "consumo_diario_kwh": e_d,
            "energia_autonomia_kwh": e_aut,
            "eta_bateria": P["eta_bateria"],
        })
    else:
        arm = {
            "ativo": False,
            "bateria": None,
            "n_baterias": 0,
            "autonomia_h": 0,
            "c_bat_kwh": 0.0,
            "capacidade_instalada_kwh": 0.0,
            "capacidade_util_kwh": 0.0,
            "capacidade_instalada_ah": 0.0,
            "custo": 0.0,
        }

    p_inst = sel["config"]["potencia_instalada_kwp"]
    geracao_dia = geracao_estimada_diaria(p_inst, hsp_val, pr_adotado)
    geracao_mes = geracao_estimada_mensal(p_inst, hsp_val, P["dias_mes"], pr_adotado)
    comp_geracao = comparar_geracao_consumo(consumo, geracao_mes)
    orcamento = calcular_orcamento(sel, arm)
    economia = calcular_economia(geracao_mes, consumo, tarifa_kwh=tarifa_kwh)
    payback = calcular_payback_simples(
        orcamento["c_total"],
        economia["economia_anual_brl"],
        c_equipamentos=orcamento["c_equipamentos"],
    )

    return {
        "data": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "consumo": float(consumo),
        "consumo_diario": demanda["consumo_diario_kwh"],
        "potencia_residencia_w": demanda["potencia_instalada_w"],
        "potencia_residencia_kw": demanda["potencia_instalada_kw"],
        "demanda": demanda,
        "origem_consumo": origem,
        "percentual": f * 100,
        "hsp_info": hsp_info,
        "pr": pr_adotado,
        "justificativa_pr": P["justificativa_pr"],
        "e_fv": e_fv,
        "e_dia_meta": e_dia_meta,
        "p_fv": p_fv,
        "selecao": sel,
        "p_inst": p_inst,
        "geracao_dia": geracao_dia,
        "geracao_mes": geracao_mes,
        "geracao": geracao_mes,  # mantido para retrocompatibilidade com testes CP2
        "comparacao_geracao": comp_geracao,
        "armazenamento": arm,
        "orcamento": orcamento,
        "economia": economia,
        "payback": payback,
        "rejeitados": rejeitados,
    }


def comparar_cenarios(
    consumo,
    percentual,
    hsp_info,
    ds,
    autonomia_h=12,
    tarifa_kwh=None,
    pr=None,
    potencia_residencia_w=0.0,
    origem="calculado pelos equipamentos do imovel",
):
    """
    PB14 + Secao 9 (Questao Final da Sprint Review):
    Executa o dimensionamento paralelo das duas solucoes para a mesma residencia:
      1. Cenario Sem Baterias (On-Grid convencional)
      2. Cenario Com Baterias (Hibrido com armazenamento e backup de autonomia_h horas)
    Compara potencia FV, modulos, inversor, geracao, atendimento, armazenamento,
    autonomia, investimento, economia e payback simples, gerando a analise conclusiva
    sustentada pelos indicadores tecnicos e economicos reais do projeto.
    """
    sem_bat = dimensionar_fv(
        consumo,
        percentual,
        hsp_info,
        ds,
        com_bateria=False,
        autonomia=None,
        origem=origem,
        tarifa_kwh=tarifa_kwh,
        pr=pr,
        potencia_residencia_w=potencia_residencia_w,
    )
    com_bat = dimensionar_fv(
        consumo,
        percentual,
        hsp_info,
        ds,
        com_bateria=True,
        autonomia=autonomia_h,
        origem=origem,
        tarifa_kwh=tarifa_kwh,
        pr=pr,
        potencia_residencia_w=potencia_residencia_w,
    )

    dif_equip = round(com_bat["orcamento"]["c_equipamentos"] - sem_bat["orcamento"]["c_equipamentos"], 2)
    dif_total = round(com_bat["orcamento"]["c_total"] - sem_bat["orcamento"]["c_total"], 2)
    acrescimo_pct = round((dif_total / sem_bat["orcamento"]["c_total"]) * 100.0, 1)
    dif_payback = round(com_bat["payback"]["payback_simples_anos"] - sem_bat["payback"]["payback_simples_anos"], 2)

    analise_questao_9 = (
        f"Para a residencia analisada (consumo de {sem_bat['consumo']:.2f} kWh/mes ou "
        f"{sem_bat['consumo_diario']:.2f} kWh/dia em {hsp_info['cidade']}/{hsp_info['uf']}, HSP = {hsp_info['hsp']:.2f} kWh/m2/dia, "
        f"PR = {sem_bat['pr']*100:.0f}%), o sistema SEM ARMAZENAMENTO (On-Grid) e a solucao que faz mais sentido "
        f"sob a otica tecnico-economica para um consumidor residencial conectado a rede urbana confiavel.\n"
        f"  1) Desempenho Tecnico e Geracao: Ambos os cenarios instalam {sem_bat['p_inst']:.3f} kWp "
        f"({sem_bat['selecao']['config']['n_modulos']} modulos {sem_bat['selecao']['modulo']['fabricante']} "
        f"{sem_bat['selecao']['modulo']['modelo']} de {sem_bat['selecao']['modulo']['potencia_wp']:.0f} Wp) e geram "
        f"{sem_bat['geracao_mes']:.2f} kWh/mes ({sem_bat['geracao_dia']:.2f} kWh/dia), atendendo "
        f"{sem_bat['comparacao_geracao']['atendimento_pct']:.1f}% do consumo mensal com "
        f"{sem_bat['comparacao_geracao']['energia_compensada_kwh_mes']:.2f} kWh/mes efetivamente compensados.\n"
        f"  2) Impacto dos Equipamentos e Armazenamento: A opcao COM BATERIAS exige substituir o inversor on-grid "
        f"({sem_bat['selecao']['inversor']['fabricante']} {sem_bat['selecao']['inversor']['modelo']}, "
        f"R$ {sem_bat['selecao']['inversor']['preco_brl']:.2f}) por um inversor hibrido "
        f"({com_bat['selecao']['inversor']['fabricante']} {com_bat['selecao']['inversor']['modelo']}, "
        f"R$ {com_bat['selecao']['inversor']['preco_brl']:.2f}) e adicionar {com_bat['armazenamento']['n_baterias']} "
        f"bateria(s) {com_bat['armazenamento']['bateria']['fabricante']} {com_bat['armazenamento']['bateria']['modelo']} "
        f"({com_bat['armazenamento']['capacidade_instalada_kwh']:.2f} kWh nominais / "
        f"{com_bat['armazenamento']['capacidade_util_kwh']:.2f} kWh uteis, custo de R$ {com_bat['armazenamento']['custo']:.2f}) "
        f"para garantir {com_bat['armazenamento']['autonomia_h']:.0f} h de autonomia ({com_bat['armazenamento']['energia_autonomia_kwh']:.2f} kWh).\n"
        f"  3) Viabilidade Economica e Payback Simples: Como na modalidade de compensacao de creditos (GD) a economia "
        f"na conta de luz e identica nos dois cenarios (R$ {sem_bat['economia']['economia_mensal_brl']:.2f}/mes ou "
        f"R$ {sem_bat['economia']['economia_anual_brl']:.2f}/ano a tarifa de R$ {sem_bat['economia']['tarifa_brl_kwh']:.2f}/kWh), "
        f"o investimento total salta de R$ {sem_bat['orcamento']['c_total']:.2f} (Sem Baterias) para "
        f"R$ {com_bat['orcamento']['c_total']:.2f} (Com Baterias), um acrescimo de R$ {dif_total:.2f} (+{acrescimo_pct:.1f}%). "
        f"Isso eleva o Payback Simples de {sem_bat['payback']['payback_simples_anos']:.2f} anos para "
        f"{com_bat['payback']['payback_simples_anos']:.2f} anos (+{dif_payback:.2f} anos). Portanto, o sistema com baterias "
        f"so se justifica caso a residencia sofra interrupcoes frequentes da concessionaria ou possua cargas criticas "
        f"que exijam nobreak solar de {com_bat['armazenamento']['autonomia_h']:.0f} h."
    )

    return {
        "sem_bateria": sem_bat,
        "com_bateria": com_bat,
        "diferenca_equipamentos_brl": dif_equip,
        "diferenca_investimento_total_brl": dif_total,
        "acrescimo_percentual": acrescimo_pct,
        "diferenca_payback_anos": dif_payback,
        "recomendacao": "Sistema Fotovoltaico Sem Armazenamento (On-Grid)",
        "analise_questao_final": analise_questao_9,
    }


# ------------------------------------------------------------------
# Formatacao da Proposta, Comparacao de Cenarios e Exportacao (PB17, PB21)
# ------------------------------------------------------------------

def brl(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def num(valor, casas=2):
    return f"{valor:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def formatar_proposta(r, apelido=""):
    """
    PB17 - Tela ou relatorio consolidado:
    Apresenta residencia, consumo (mensal/diario e potencia instalada), HSP, PR e justificativa,
    potencia necessaria e instalada, modulos, inversor (com eficiencia e limites), geracao
    (diaria e mensal), comparacao geracao x consumo (distinguindo compensada e excedente),
    baterias/autonomia quando aplicavel, orcamento (com preco unitario, subtotal e total),
    economia (mensal e anual) e payback simples.
    """
    s, arm, orc, h = r["selecao"], r["armazenamento"], r["orcamento"], r["hsp_info"]
    comp_g, econ, pay = r["comparacao_geracao"], r["economia"], r["payback"]
    mod, inv, cfg = s["modulo"], s["inversor"], s["config"]

    L = [
        "=" * 74,
        f"  PROPOSTA PRELIMINAR E RELATORIO CONSOLIDADO - SISTEMA FOTOVOLTAICO  {apelido}",
        f"  Gerada em {r['data']} | Equipe Lumos (FIAP - SERS Sprint 3)",
        "  Integrantes: Pietro Lorande (RM 569125) | Luiz Otavio Brito Freixo (RM 569977) | Maria Eduarda Lemos (RM 574094)",
        "=" * 74,
        "\n[1] CONSUMO E DEMANDA ENERGETICA DA RESIDENCIA (PB01 / PB02)",
        f"  Consumo de referencia .... {num(r['consumo'])} kWh/mes ({r['origem_consumo']})",
        f"  Consumo medio diario ..... {num(r['consumo_diario'], 3)} kWh/dia  (E_dia = E_mes / 30)",
        f"  Potencia instalada (casa)  {num(r['potencia_residencia_w'], 0)} W ({num(r['potencia_residencia_kw'], 3)} kW)",
        f"  Percentual de atendimento  {num(r['percentual'], 0)} %",
        f"  Energia mensal pretendida  {num(r['e_fv'])} kWh/mes  (E_FV = Cm * f)",
        "\n[2] RECURSO SOLAR E DESEMPENHO DO SISTEMA (PB03)",
        f"  Localidade ............... {h['cidade']}/{h['uf']} - HSP {num(h['hsp'])} kWh/m2/dia",
        f"  Origem do dado ........... {h['fonte']} - {h['url_fonte']}",
        f"  Performance Ratio (PR) ... {num(r['pr'] * 100, 1)} % (fator {num(r['pr'])})",
        f"  Justificativa do PR ...... {r['justificativa_pr']}",
        "\n[3] DIMENSIONAMENTO E GERACAO FOTOVOLTAICA (PB04 / PB08 / PB09)",
        f"  Potencia FV calculada .... {num(r['p_fv'], 3)} kWp  (P_FV = E_dia / (HSP * PR) = E_FV / (HSP * 30 * 0,78))",
        f"  Potencia instalada ....... {num(r['p_inst'], 3)} kWp  (P_inst = N_mod * P_mod / 1000)",
        f"  Geracao estimada diaria .. {num(r['geracao_dia'], 2)} kWh/dia  (E_gerada,dia = P_inst * HSP * PR)",
        f"  Geracao estimada mensal .. {num(r['geracao_mes'], 1)} kWh/mes ({num(comp_g['atendimento_pct'], 1)} % do consumo)",
        f"  Energia compensada/mes ... {num(comp_g['energia_compensada_kwh_mes'], 2)} kWh/mes (abatida da fatura)",
    ]
    if comp_g["supera_consumo"]:
        L.append(
            f"  Excedente injetado/mes ... {num(comp_g['energia_excedente_kwh_mes'], 2)} kWh/mes "
            "(geracao supera o consumo; vira credito energetico na concessionaria)"
        )
    else:
        L.append("  Excedente injetado/mes ... 0,00 kWh/mes (toda a energia gerada e consumida/compensada no mes)")

    L += [
        "\n[4] MODULOS FOTOVOLTAICOS (PB05 / PB06)",
        f"  Modulo escolhido ......... [{mod['id']}] {mod['fabricante']} {mod['modelo']}",
        f"  Especificacoes do modulo . Potencia: {mod['potencia_wp']:.0f} Wp | Eficiencia: {num(mod['eficiencia_pct'])} % | "
        f"Vmp: {num(mod['vmp_v'])} V | Imp: {num(mod['imp_a'])} A | Voc: {num(mod['voc_v'])} V",
        f"  Quantidade dimensionada .. {cfg['n_modulos']} x {mod['fabricante']} {mod['modelo']} ({mod['potencia_wp']:.0f} Wp)",
        f"  Arranjo eletrico ......... N minimo {s['n_minimo']} -> N final {cfg['n_modulos']} "
        f"({cfg['n_strings']} string(s) de {cfg['por_string']} modulos)",
        "\n[5] INVERSOR SELECIONADO E COMPATIBILIDADE (PB07)",
        f"  Inversor escolhido ....... [{inv['id']}] {inv['fabricante']} {inv['modelo']} ({inv['tipo']}, {inv['potencia_nominal_w']:.0f} W)",
        f"  Limites e eficiencia ..... Pot. FV max: {inv['potencia_max_fv_w']:.0f} W | MPPT: {inv['faixa_mppt_min_v']:.0f}-{inv['faixa_mppt_max_v']:.0f} V "
        f"({int(inv['numero_mppt'])} MPPT, max {num(inv['corrente_max_entrada_a'], 1)} A) | Eficiencia: {num(inv['eficiencia_pct'], 1)} %",
        f"  Verificacao eletrica ..... Voc string {num(cfg['voc_string_v'], 1)} V | Vmp string {num(cfg['vmp_string_v'], 1)} V | "
        f"R_DC/AC {num(cfg['ratio_dc_ac'])} | combinacoes validas: {s['alternativas_validas']}",
        "\n[6] ARMAZENAMENTO / BATERIAS (PB10 / PB11 / PB12)",
    ]
    if arm["ativo"]:
        b = arm["bateria"]
        L += [
            f"  Autonomia desejada ....... {num(arm['autonomia_h'], 1)} h | E_d {num(arm['consumo_diario_kwh'], 3)} kWh/dia | "
            f"E_autonomia {num(arm['energia_autonomia_kwh'], 3)} kWh | C_bat {num(arm['c_bat_kwh'], 3)} kWh",
            f"  Bateria selecionada ...... [{b['id']}] {arm['n_baterias']} x {b['fabricante']} {b['modelo']} "
            f"({b['tecnologia']}, {num(b['tensao_nominal_v'], 1)} V, {b['capacidade_ah']:.0f} Ah, "
            f"{num(b['capacidade_kwh'])} kWh, DoD {b['dod_pct']:.0f} %, {b['ciclos']:.0f} ciclos)",
            f"  Capacidade instalada ..... {num(arm['capacidade_instalada_kwh'])} kWh nominais / "
            f"{num(arm['capacidade_util_kwh'])} kWh uteis ({num(arm.get('capacidade_instalada_ah', b['capacidade_ah']*arm['n_baterias']), 0)} Ah totais)",
        ]
    else:
        L.append("  Sem armazenamento - capacidade 0 kWh, custo R$ 0,00.")

    L.append("\n[7] ORCAMENTO ESTIMADO (PB13)")
    L.append(f"  {'QTD':>3} | {'EQUIPAMENTO (FABRICANTE / MODELO)':<36} | {'PRECO UNIT.':>14} | {'SUBTOTAL':>14}")
    L.append("  " + "-" * 72)
    for i in orc["itens"]:
        L.append(
            f"  {i['qtd']:>3} x {i['item'][:36]:<36} | {brl(i['preco_unitario']):>14} | {brl(i['subtotal']):>14}"
        )
    L.append("  " + "-" * 72)
    L.append(f"  {'CUSTO DOS EQUIPAMENTOS':<56} {brl(orc['c_equipamentos']):>15}")
    L.append("  Outros custos (premissas da equipe):")
    L += [f"     {nome:<34} {regra:<20} {brl(valor):>15}" for nome, valor, regra in orc["outros"]]
    L.append(f"  {'CUSTO TOTAL ESTIMADO':<56} {brl(orc['c_total']):>15}")

    L += [
        "\n[8] ANALISE ECONOMICA E PAYBACK SIMPLES (PB15 / PB16)",
        f"  Tarifa utilizada ......... {brl(econ['tarifa_brl_kwh'])}/kWh ({econ['fonte_tarifa']})",
        f"  Energia compensada ....... {num(econ['energia_compensada_kwh_mes'])} kWh/mes (de {num(econ['energia_gerada_kwh_mes'])} kWh/mes gerados)",
        f"  Economia mensal estimada . {brl(econ['economia_mensal_brl'])} / mes  (Economia_mensal = E_compensada * tarifa)",
        f"  Economia anual estimada .. {brl(econ['economia_anual_brl'])} / ano  (Economia_anual = Economia_mensal * 12)",
        f"  Payback simples (total) .. {pay['payback_formatado']}  (Payback = Investimento / Economia_anual)",
        f"  Payback simples (equip.) . {num(pay['payback_apenas_equipamentos_anos'])} anos (considerando apenas equipamentos)",
        f"  Premissas do calculo ..... {econ['premissas']}",
        f"  Nota sobre payback ....... {pay['aviso_nao_exato']}",
        "\n[9] ORIGEM DOS PRECOS E RASTREABILIDADE DOS DATASETS (PB05 / PB07 / PB12)",
    ]
    L += [f"  - {i['item']}: {i['fonte']}" for i in orc["itens"]]
    L += [
        "\nAviso: estimativa academica (Payback Simples). Nao substitui projeto eletrico executivo, ART nem vistoria.",
        "=" * 74,
    ]
    return "\n".join(L)


def formatar_comparacao_cenarios(comp, apelido=""):
    """
    PB14 + Secao 9 (Questao Final da Sprint Review):
    Formata quadro comparativo lado a lado entre o Cenario Sem Baterias (On-Grid)
    e o Cenario Com Baterias (Hibrido), seguido da resposta fundamentada a Questao 9.
    """
    a = comp["sem_bateria"]
    b = comp["com_bateria"]
    mod_a, inv_a, cfg_a = a["selecao"]["modulo"], a["selecao"]["inversor"], a["selecao"]["config"]
    mod_b, inv_b, cfg_b = b["selecao"]["modulo"], b["selecao"]["inversor"], b["selecao"]["config"]
    bat_b = b["armazenamento"]["bateria"]

    linhas = [
        "=" * 88,
        f"  COMPARACAO DE CENARIOS (PB14) E DEFESA TECNICO-ECONOMICA (SECAO 9) - {apelido}",
        "=" * 88,
        f"  {'INDICADOR / CARACTERISTICA':<32} | {'CENARIO 1: SEM BATERIAS':<24} | {'CENARIO 2: COM BATERIAS':<24}",
        "  " + "-" * 84,
        f"  {'Consumo Mensal / Diario':<32} | {num(a['consumo'])+' kWh / '+num(a['consumo_diario'])+' kWh/d':<24} | {num(b['consumo'])+' kWh / '+num(b['consumo_diario'])+' kWh/d':<24}",
        f"  {'Potencia FV Calculada':<32} | {num(a['p_fv'], 3)+' kWp':<24} | {num(b['p_fv'], 3)+' kWp':<24}",
        f"  {'Potencia FV Instalada':<32} | {num(a['p_inst'], 3)+' kWp':<24} | {num(b['p_inst'], 3)+' kWp':<24}",
        f"  {'Modulos Fotovoltaicos':<32} | {str(cfg_a['n_modulos'])+'x '+mod_a['id']+' ('+str(int(mod_a['potencia_wp']))+'Wp)':<24} | {str(cfg_b['n_modulos'])+'x '+mod_b['id']+' ('+str(int(mod_b['potencia_wp']))+'Wp)':<24}",
        f"  {'Inversor Selecionado':<32} | {inv_a['id']+' '+inv_a['fabricante']+' ('+inv_a['tipo']+')':<24} | {inv_b['id']+' '+inv_b['fabricante']+' ('+inv_b['tipo']+')':<24}",
        f"  {'Potencia / Efic. Inversor':<32} | {str(int(inv_a['potencia_nominal_w']))+' W / '+num(inv_a['eficiencia_pct'],1)+'%':<24} | {str(int(inv_b['potencia_nominal_w']))+' W / '+num(inv_b['eficiencia_pct'],1)+'%':<24}",
        f"  {'Geracao Mensal Estimada':<32} | {num(a['geracao_mes'], 1)+' kWh/mes':<24} | {num(b['geracao_mes'], 1)+' kWh/mes':<24}",
        f"  {'Atendimento da Demanda':<32} | {num(a['comparacao_geracao']['atendimento_pct'], 1)+' %':<24} | {num(b['comparacao_geracao']['atendimento_pct'], 1)+' %':<24}",
        f"  {'Energia Compensada / Mes':<32} | {num(a['economia']['energia_compensada_kwh_mes'])+' kWh/mes':<24} | {num(b['economia']['energia_compensada_kwh_mes'])+' kWh/mes':<24}",
        f"  {'Banco de Baterias':<32} | {'Nao possui (0 kWh)':<24} | {str(b['armazenamento']['n_baterias'])+'x '+bat_b['id']+' ('+bat_b['fabricante']+')':<24}",
        f"  {'Capacidade Armazenada':<32} | {'0,00 kWh':<24} | {num(b['armazenamento']['capacidade_instalada_kwh'])+' kWh ('+num(b['armazenamento']['capacidade_util_kwh'])+' uteis)':<24}",
        f"  {'Autonomia de Backup':<32} | {'0 h (depende da rede)':<24} | {num(b['armazenamento']['autonomia_h'], 1)+' h ('+num(b['armazenamento']['energia_autonomia_kwh'], 2)+' kWh)':<24}",
        f"  {'Custo dos Equipamentos':<32} | {brl(a['orcamento']['c_equipamentos']):<24} | {brl(b['orcamento']['c_equipamentos']):<24}",
        f"  {'Outros Custos / Instalacao':<32} | {brl(a['orcamento']['c_outros']):<24} | {brl(b['orcamento']['c_outros']):<24}",
        f"  {'INVESTIMENTO TOTAL':<32} | {brl(a['orcamento']['c_total']):<24} | {brl(b['orcamento']['c_total']):<24}",
        f"  {'Economia Mensal Estimada':<32} | {brl(a['economia']['economia_mensal_brl'])+'/mes':<24} | {brl(b['economia']['economia_mensal_brl'])+'/mes':<24}",
        f"  {'Economia Anual Estimada':<32} | {brl(a['economia']['economia_anual_brl'])+'/ano':<24} | {brl(b['economia']['economia_anual_brl'])+'/ano':<24}",
        f"  {'Payback Simples (So Equip.)':<32} | {num(a['payback']['payback_apenas_equipamentos_anos'])+' anos':<24} | {num(b['payback']['payback_apenas_equipamentos_anos'])+' anos':<24}",
        f"  {'PAYBACK SIMPLES (TOTAL)':<32} | {num(a['payback']['payback_simples_anos'])+' anos':<24} | {num(b['payback']['payback_simples_anos'])+' anos':<24}",
        "  " + "-" * 84,
        f"  Diferenca de investimento: +{brl(comp['diferenca_investimento_total_brl'])} (+{num(comp['acrescimo_percentual'], 1)}%) no sistema com baterias.",
        f"  Diferenca de payback simples: +{num(comp['diferenca_payback_anos'])} anos para recuperar o investimento adicional.",
        "\n[PARECER TECNICO E ECONOMICO - QUESTAO FINAL DA SPRINT REVIEW (SECAO 9)]",
        comp["analise_questao_final"],
        "=" * 88,
    ]
    return "\n".join(linhas)


def exportar_proposta_txt(r, comp=None, apelido="Residencia", caminho_arquivo=None):
    """PB21 - Exporta a proposta completa e comparacao de cenarios em arquivo texto/relatorio."""
    if caminho_arquivo is None:
        caminho_arquivo = os.path.join(PASTA_BASE, "proposta_cliente.txt")
    blocos = [formatar_proposta(r, apelido)]
    if comp is not None:
        blocos.append("\n\n" + formatar_comparacao_cenarios(comp, apelido))
    conteudo = "\n".join(blocos) + "\n"
    with open(caminho_arquivo, "w", encoding="utf-8-sig") as f:
        f.write(conteudo)
    return caminho_arquivo


def exportar_proposta_html(r, comp=None, apelido="Residencia", caminho_arquivo=None, cargas_residencia=None):
    """
    PB19 / PB21 - Gera pagina HTML interativa e consolidada com:
      1. Proposta Tecnica, Orcamento Detalhado, Economia e Payback Simples (PB01 a PB21)
      2. Simulador Web Interativo conectado aos datasets reais (modulos, inversores, baterias e HSP)
      3. Roteiro Guiado das 15 Etapas da Sprint Review (Secao 7)
      4. Comparacao Lado a Lado (Sem Baterias vs Com Baterias) + Resposta da Questao Final (Secao 9)
      5. Tabelas completas dos Datasets Estruturados e Equipamentos da Residencia
    """
    import json as _json

    if caminho_arquivo is None:
        caminho_arquivo = os.path.join(PASTA_BASE, "proposta_cliente.html")

    ds_completo = carregar_datasets_fv()
    s, arm, orc, h = r["selecao"], r["armazenamento"], r["orcamento"], r["hsp_info"]
    comp_g, econ, pay = r["comparacao_geracao"], r["economia"], r["payback"]
    mod, inv, cfg = s["modulo"], s["inversor"], s["config"]

    linhas_orc = ""
    for i in orc["itens"]:
        linhas_orc += (
            f"<tr><td>{i['categoria']}</td><td><strong>[{i['id_equipamento']}] {i['fabricante']} {i['modelo']}</strong>"
            f"<br><small>{i['fonte']}</small></td>"
            f"<td style='text-align:center'>{i['qtd']}</td>"
            f"<td style='text-align:right'>{brl(i['preco_unitario'])}</td>"
            f"<td style='text-align:right'><strong>{brl(i['subtotal'])}</strong></td></tr>\n"
        )
    for nome_o, val_o, regra_o in orc["outros"]:
        linhas_orc += (
            f"<tr><td>Custos Complementares</td><td>{nome_o} <small>({regra_o})</small></td>"
            f"<td style='text-align:center'>1</td>"
            f"<td style='text-align:right'>{brl(val_o)}</td>"
            f"<td style='text-align:right'>{brl(val_o)}</td></tr>\n"
        )

    # Tabela de cargas da residencia (PB01 / PB02)
    if not cargas_residencia:
        cargas_residencia = [
            {"nome": "Chuveiro eletrico", "categoria": "Banheiro", "potencia_w": 5500, "qtd": 1, "horas_dia": 0.75, "kwh_mes": 123.75},
            {"nome": "Ar-condicionado", "categoria": "Quarto", "potencia_w": 1200, "qtd": 1, "horas_dia": 4.0, "kwh_mes": 144.00},
            {"nome": "Geladeira", "categoria": "Cozinha", "potencia_w": 133, "qtd": 1, "horas_dia": 24.0, "kwh_mes": 95.76},
            {"nome": "Computador desktop", "categoria": "Escritorio", "potencia_w": 200, "qtd": 1, "horas_dia": 5.0, "kwh_mes": 30.00},
            {"nome": "Televisao", "categoria": "Sala", "potencia_w": 100, "qtd": 2, "horas_dia": 4.0, "kwh_mes": 24.00},
            {"nome": "Maquina de lavar roupa", "categoria": "Lavanderia", "potencia_w": 500, "qtd": 1, "horas_dia": 1.0, "kwh_mes": 15.00},
            {"nome": "Lampada LED", "categoria": "Geral", "potencia_w": 10, "qtd": 8, "horas_dia": 5.0, "kwh_mes": 12.00},
            {"nome": "Micro-ondas", "categoria": "Cozinha", "potencia_w": 1200, "qtd": 1, "horas_dia": 0.3, "kwh_mes": 10.80},
        ]
    linhas_cargas_html = ""
    for c_item in cargas_residencia:
        linhas_cargas_html += (
            f"<tr><td><strong>{c_item['nome']}</strong></td><td>{c_item['categoria']}</td>"
            f"<td style='text-align:right'>{num(c_item['potencia_w'], 0)} W</td>"
            f"<td style='text-align:center'>{c_item['qtd']}</td>"
            f"<td style='text-align:right'>{num(c_item['horas_dia'], 2)} h/dia</td>"
            f"<td style='text-align:right'><strong>{num(c_item['kwh_mes'], 2)} kWh/mes</strong></td></tr>\n"
        )

    # Tabelas dos Datasets (PB05, PB07, PB12)
    linhas_ds_mod = "".join(
        f"<tr><td><strong>{m['id']}</strong></td><td>{m['fabricante']}</td><td>{m['modelo']}</td>"
        f"<td style='text-align:right'>{m['potencia_wp']:.0f} Wp</td><td style='text-align:right'>{num(m['voc_v'])} V / {num(m['vmp_v'])} V</td>"
        f"<td style='text-align:right'>{num(m['isc_a'])} A / {num(m['imp_a'])} A</td><td style='text-align:right'>{num(m['eficiencia_pct'])}%</td>"
        f"<td style='text-align:right'><strong>{brl(m['preco_brl'])}</strong></td><td><small>{m['fornecedor']} ({m['data_coleta']})</small></td></tr>\n"
        for m in ds_completo["modulos"]
    )
    linhas_ds_inv = "".join(
        f"<tr><td><strong>{iv['id']}</strong></td><td>{iv['fabricante']}</td><td>{iv['modelo']}</td>"
        f"<td>{iv['tipo']}</td><td style='text-align:right'>{iv['potencia_nominal_w']:.0f} W / {iv['potencia_max_fv_w']:.0f} W</td>"
        f"<td style='text-align:right'>{iv['faixa_mppt_min_v']:.0f}-{iv['faixa_mppt_max_v']:.0f} V ({int(iv['numero_mppt'])} MPPT)</td>"
        f"<td style='text-align:right'>{num(iv['eficiencia_pct'], 1)}%</td>"
        f"<td style='text-align:center'>{'SIM' if iv['compativel_bateria'] else 'NAO'}</td>"
        f"<td style='text-align:right'><strong>{brl(iv['preco_brl'])}</strong></td></tr>\n"
        for iv in ds_completo["inversores"]
    )
    linhas_ds_bat = "".join(
        f"<tr><td><strong>{bt['id']}</strong></td><td>{bt['fabricante']}</td><td>{bt['modelo']}</td>"
        f"<td>{bt['tecnologia']}</td><td style='text-align:right'>{num(bt['tensao_nominal_v'], 1)} V</td>"
        f"<td style='text-align:right'>{bt['capacidade_ah']:.0f} Ah / {num(bt['capacidade_kwh'])} kWh</td>"
        f"<td style='text-align:right'>{bt['dod_pct']:.0f}% ({bt['ciclos']:.0f} ciclos)</td>"
        f"<td style='text-align:right'><strong>{brl(bt['preco_brl'])}</strong></td><td><small>{bt['fornecedor']} ({bt['data_coleta']})</small></td></tr>\n"
        for bt in ds_completo["baterias"]
    )

    bloco_comp_html = ""
    bloco_15_etapas_html = ""
    if comp is not None:
        a = comp["sem_bateria"]
        b = comp["com_bateria"]
        mod_a, inv_a, cfg_a = a["selecao"]["modulo"], a["selecao"]["inversor"], a["selecao"]["config"]
        mod_b, inv_b, cfg_b = b["selecao"]["modulo"], b["selecao"]["inversor"], b["selecao"]["config"]
        bat_b = b["armazenamento"]["bateria"]
        bloco_comp_html = f"""
        <section class="card" id="secao-comparacao">
          <h2>3. Comparacao de Cenarios (PB14) e Questao Final da Sprint Review (Secao 9)</h2>
          <table>
            <thead>
              <tr>
                <th>Indicador Tecnico / Economico</th>
                <th>Cenario 1: Sem Baterias (On-Grid Convencional)</th>
                <th>Cenario 2: Com Baterias (Hibrido + Backup 12h)</th>
              </tr>
            </thead>
            <tbody>
              <tr><td>Demanda da Residencia (PB01/PB02)</td><td>{num(a['consumo'])} kWh/mes ({num(a['consumo_diario'])} kWh/dia) | {num(a['potencia_residencia_w'], 0)} W</td><td>{num(b['consumo'])} kWh/mes ({num(b['consumo_diario'])} kWh/dia) | {num(b['potencia_residencia_w'], 0)} W</td></tr>
              <tr><td>Potencia FV Necessaria / Instalada (PB04/PB06)</td><td>{num(a['p_fv'], 3)} kWp / <strong>{num(a['p_inst'], 3)} kWp</strong></td><td>{num(b['p_fv'], 3)} kWp / <strong>{num(b['p_inst'], 3)} kWp</strong></td></tr>
              <tr><td>Modulos Fotovoltaicos (PB05/PB06)</td><td>{cfg_a['n_modulos']}x [{mod_a['id']}] {mod_a['fabricante']} {mod_a['modelo']} ({mod_a['potencia_wp']:.0f} Wp)</td><td>{cfg_b['n_modulos']}x [{mod_b['id']}] {mod_b['fabricante']} {mod_b['modelo']} ({mod_b['potencia_wp']:.0f} Wp)</td></tr>
              <tr><td>Inversor Selecionado e R_DC/AC (PB07)</td><td>[{inv_a['id']}] {inv_a['fabricante']} {inv_a['modelo']} ({inv_a['tipo']}, {inv_a['potencia_nominal_w']:.0f} W, efic. {num(inv_a['eficiencia_pct'],1)}%, R_DC/AC = {num(cfg_a['ratio_dc_ac'])})</td><td>[{inv_b['id']}] {inv_b['fabricante']} {inv_b['modelo']} ({inv_b['tipo']}, {inv_b['potencia_nominal_w']:.0f} W, efic. {num(inv_b['eficiencia_pct'],1)}%, R_DC/AC = {num(cfg_b['ratio_dc_ac'])})</td></tr>
              <tr><td>Geracao Estimada: Dia / Mes (PB08)</td><td>{num(a['geracao_dia'], 2)} kWh/dia | <strong>{num(a['geracao_mes'], 1)} kWh/mes</strong></td><td>{num(b['geracao_dia'], 2)} kWh/dia | <strong>{num(b['geracao_mes'], 1)} kWh/mes</strong></td></tr>
              <tr><td>Atendimento / Energia Compensada (PB09)</td><td><strong>{num(a['comparacao_geracao']['atendimento_pct'], 1)}%</strong> ({num(a['economia']['energia_compensada_kwh_mes'])} kWh/mes compensados + {num(a['economia']['energia_excedente_kwh_mes'])} kWh/mes excedente)</td><td><strong>{num(b['comparacao_geracao']['atendimento_pct'], 1)}%</strong> ({num(b['economia']['energia_compensada_kwh_mes'])} kWh/mes compensados + {num(b['economia']['energia_excedente_kwh_mes'])} kWh/mes excedente)</td></tr>
              <tr><td>Armazenamento em Baterias (PB10/PB11/PB12)</td><td>Sem armazenamento (0 kWh, R$ 0,00)</td><td><strong>{b['armazenamento']['n_baterias']}x [{bat_b['id']}] {bat_b['fabricante']} {bat_b['modelo']}</strong> ({num(b['armazenamento']['capacidade_instalada_kwh'])} kWh nominais / {num(b['armazenamento']['capacidade_util_kwh'])} kWh uteis, DoD {bat_b['dod_pct']:.0f}%)</td></tr>
              <tr><td>Autonomia de Backup (PB11)</td><td>0 h (desliga em queda de rede por anti-ilhamento)</td><td><strong>{num(b['armazenamento']['autonomia_h'], 1)} horas</strong> (E_aut = {num(b['armazenamento']['energia_autonomia_kwh'], 2)} kWh | C_bat = {num(b['armazenamento']['c_bat_kwh'], 2)} kWh)</td></tr>
              <tr><td>Custo dos Equipamentos - Soma Datasets (PB13)</td><td><strong>{brl(a['orcamento']['c_equipamentos'])}</strong></td><td><strong>{brl(b['orcamento']['c_equipamentos'])}</strong> (+{brl(comp['diferenca_equipamentos_brl'])})</td></tr>
              <tr><td>Outros Custos (Estrutura, Cabos, Instalacao, Projeto)</td><td>{brl(a['orcamento']['c_outros'])}</td><td>{brl(b['orcamento']['c_outros'])}</td></tr>
              <tr><td>Investimento Total Estimado (Turn-Key)</td><td><strong>{brl(a['orcamento']['c_total'])}</strong></td><td><strong>{brl(b['orcamento']['c_total'])}</strong> (+{brl(comp['diferenca_investimento_total_brl'])} / +{num(comp['acrescimo_percentual'], 1)}%)</td></tr>
              <tr><td>Economia Mensal / Anual na Conta (PB15)</td><td><strong>{brl(a['economia']['economia_mensal_brl'])}/mes</strong> | <strong>{brl(a['economia']['economia_anual_brl'])}/ano</strong></td><td><strong>{brl(b['economia']['economia_mensal_brl'])}/mes</strong> | <strong>{brl(b['economia']['economia_anual_brl'])}/ano</strong></td></tr>
              <tr><td>Payback Simples (Considerando So Equipamentos)</td><td>{num(a['payback']['payback_apenas_equipamentos_anos'])} anos</td><td>{num(b['payback']['payback_apenas_equipamentos_anos'])} anos</td></tr>
              <tr><td>Payback Simples (Investimento Total / Economia Anual) (PB16)</td><td><span class="badge-ok">{a['payback']['payback_formatado']}</span></td><td><span class="badge-warn">{b['payback']['payback_formatado']}</span></td></tr>
            </tbody>
          </table>
          <div class="callout" style="border-left-color:#059669; background:#ecfdf5;">
            <h3 style="color:#065f46;">Resposta da Questao Final da Sprint Review (Secao 9 do PDF)</h3>
            <p style="margin:6px 0;"><strong>Pergunta do Professor:</strong> <em>"Para a residencia utilizada na demonstracao, qual solucao faz mais sentido: sistema fotovoltaico sem armazenamento ou sistema com baterias? Quais resultados tecnicos e economicos do projeto sustentam a analise?"</em></p>
            <p style="white-space: pre-line; margin-top:10px;">{comp['analise_questao_final']}</p>
          </div>
        </section>
        """

        bloco_15_etapas_html = f"""
        <section class="card" id="secao-roteiro">
          <h2>4. Roteiro Guiado das 15 Etapas da Sprint Review (Secao 7 do PDF)</h2>
          <p style="color:var(--muted); margin-top:0;">Use este quadro durante a apresentacao ao vivo na aula de 23/10 para demonstrar cada um dos 15 itens exigidos pelo Prof. Alvaro:</p>
          <div class="steps-grid">
            <div class="step-box"><span class="step-num">Etapa 1</span><strong>Selecao da Residencia (PB01)</strong><p>Imovel #1 recuperado do banco JSON: <strong>{apelido}</strong> (Av. Paulista, 1106 - {h['cidade']}/{h['uf']}), sem exigir novo cadastro.</p></div>
            <div class="step-box"><span class="step-num">Etapa 2</span><strong>Equipamentos e Consumo (PB02)</strong><p>8 tipos de equipamentos (16 unidades), potencia instalada de <strong>{num(a['potencia_residencia_w'], 0)} W ({num(a['potencia_residencia_kw'], 3)} kW)</strong>, consumo <strong>E_mes = {num(a['consumo'])} kWh/mes</strong> e <strong>E_dia = {num(a['consumo_diario'])} kWh/dia</strong>.</p></div>
            <div class="step-box"><span class="step-num">Etapa 3</span><strong>Dimensionamento FV (PB04)</strong><p>Formula: <code>P_FV = E_dia / (HSP x PR) = {num(a['consumo_diario'], 3)} / ({num(h['hsp'])} x {num(a['pr'])})</code> = <strong>{num(a['p_fv'], 3)} kWp</strong> necessarios para 100% da demanda.</p></div>
            <div class="step-box"><span class="step-num">Etapa 4</span><strong>HSP e PR Utilizados (PB03)</strong><p><strong>HSP = {num(h['hsp'])} kWh/m2/dia</strong> ({h['fonte']}) e <strong>PR = {num(a['pr']*100, 0)}% (0,78)</strong> justificado pela NT EPE DEA-SEE 009/2023 (perdas termicas, cabos e inversor).</p></div>
            <div class="step-box"><span class="step-num">Etapa 5</span><strong>Consulta aos Datasets (PB05/PB07/PB12)</strong><p>Leitura dinamica dos arquivos CSV separados: <strong>10 modulos</strong> (<code>modulos.csv</code>), <strong>8 inversores</strong> (<code>inversores.csv</code>) e <strong>6 baterias LiFePO4</strong> (<code>baterias.csv</code>).</p></div>
            <div class="step-box"><span class="step-num">Etapa 6</span><strong>Selecao dos Modulos (PB06)</strong><p>Escolhido <strong>[{mod_a['id']}] {mod_a['fabricante']} {mod_a['modelo']} ({mod_a['potencia_wp']:.0f} Wp)</strong>. <code>N_mod = teto({num(a['p_fv']*1000, 1)} / {mod_a['potencia_wp']:.0f}) = {cfg_a['n_modulos']} modulos</code> -> <strong>P_inst = {num(a['p_inst'], 2)} kWp</strong>.</p></div>
            <div class="step-box"><span class="step-num">Etapa 7</span><strong>Compatibilidade do Inversor (PB07)</strong><p>Verificadas regras C1 a C8 (Voc frio {num(cfg_a['voc_string_v'], 1)}V, Vmp {num(cfg_a['vmp_string_v'], 1)}V no MPPT, corrente e <code>R_DC/AC = {num(cfg_a['ratio_dc_ac'])}</code>). On-Grid: <strong>[{inv_a['id']}] {inv_a['fabricante']}</strong>; Hibrido: <strong>[{inv_b['id']}] {inv_b['fabricante']}</strong>.</p></div>
            <div class="step-box"><span class="step-num">Etapa 8</span><strong>Geracao Estimada (PB08)</strong><p><code>E_gerada,dia = {num(a['p_inst'], 2)} x {num(h['hsp'])} x {num(a['pr'])}</code> = <strong>{num(a['geracao_dia'], 2)} kWh/dia</strong> e <code>E_gerada,mes = E_dia x 30</code> = <strong>{num(a['geracao_mes'], 2)} kWh/mes</strong>.</p></div>
            <div class="step-box"><span class="step-num">Etapa 9</span><strong>Comparacao Geracao x Consumo (PB09)</strong><p>Atendimento de <strong>{num(a['comparacao_geracao']['atendimento_pct'], 2)}%</strong>. Distingue energia compensada (<strong>{num(a['comparacao_geracao']['energia_compensada_kwh_mes'])} kWh/mes</strong>) do excedente injetado (<strong>{num(a['comparacao_geracao']['energia_excedente_kwh_mes'])} kWh/mes</strong>).</p></div>
            <div class="step-box"><span class="step-num">Etapa 10</span><strong>Opcao Sem Baterias (PB10)</strong><p>Sistema On-Grid convencional: {cfg_a['n_modulos']}x {mod_a['fabricante']} {mod_a['potencia_wp']:.0f}W + 1x [{inv_a['id']}] {inv_a['fabricante']} {inv_a['modelo']} ({inv_a['potencia_nominal_w']:.0f}W), sem banco de baterias (0 kWh).</p></div>
            <div class="step-box"><span class="step-num">Etapa 11</span><strong>Opcao Com Baterias e Autonomia (PB11)</strong><p>Para <strong>{b['armazenamento']['autonomia_h']:.0f}h de autonomia</strong> (<code>E_aut = {num(b['armazenamento']['energia_autonomia_kwh'])} kWh</code>, <code>C_bat = {num(b['armazenamento']['c_bat_kwh'])} kWh</code>): selecionadas <strong>{b['armazenamento']['n_baterias']}x [{bat_b['id']}] {bat_b['fabricante']} {bat_b['modelo']}</strong> ({num(b['armazenamento']['capacidade_instalada_kwh'])} kWh nominais / {num(b['armazenamento']['capacidade_util_kwh'])} kWh uteis, {num(bat_b['tensao_nominal_v'], 1)}V LiFePO4).</p></div>
            <div class="step-box"><span class="step-num">Etapa 12</span><strong>Orcamento Automatico (PB13)</strong><p>On-Grid: Equipamentos <strong>{brl(a['orcamento']['c_equipamentos'])}</strong> | Total <strong>{brl(a['orcamento']['c_total'])}</strong>.<br>Hibrido: Equipamentos <strong>{brl(b['orcamento']['c_equipamentos'])}</strong> | Total <strong>{brl(b['orcamento']['c_total'])}</strong>.</p></div>
            <div class="step-box"><span class="step-num">Etapa 13</span><strong>Comparacao dos Cenarios (PB14)</strong><p>Tabela comparativa lado a lado demonstrando acrescimo de <strong>+{brl(comp['diferenca_investimento_total_brl'])} (+{num(comp['acrescimo_percentual'], 1)}%)</strong> para incluir backup de 12h.</p></div>
            <div class="step-box"><span class="step-num">Etapa 14</span><strong>Economia e Payback Simples (PB15/PB16)</strong><p>Tarifa R$ 0,92/kWh -> Economia de <strong>{brl(a['economia']['economia_mensal_brl'])}/mes ({brl(a['economia']['economia_anual_brl'])}/ano)</strong>. Payback Simples: <strong>{num(a['payback']['payback_simples_anos'])} anos (On-Grid)</strong> vs <strong>{num(b['payback']['payback_simples_anos'])} anos (Hibrido)</strong>.</p></div>
            <div class="step-box"><span class="step-num">Etapa 15</span><strong>Proposta Final ao Cliente (PB17/PB21)</strong><p>Proposta consolidada exibida no terminal, salva em <code>dados_sistema.json</code> (PB20) e exportada em <code>proposta_cliente.txt</code> e <code>proposta_cliente.html</code>.</p></div>
          </div>
        </section>
        """

    dados_js = _json.dumps(
        {
            "consumo_padrao": round(r["consumo"], 2),
            "potencia_casa_w": round(r["potencia_residencia_w"], 1),
            "pr_padrao": r["pr"],
            "tarifa_padrao": econ["tarifa_brl_kwh"],
            "modulos": ds_completo["modulos"],
            "inversores": ds_completo["inversores"],
            "baterias": ds_completo["baterias"],
            "hsp_lista": list(ds_completo["hsp"].values()),
        },
        ensure_ascii=False,
    )

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <title>Proposta Fotovoltaica & Simulador Sprint 3 - {apelido} | Equipe Lumos FIAP</title>
  <style>
    :root {{
      --bg: #f8fafc;
      --surface: #ffffff;
      --ink: #0f172a;
      --muted: #475569;
      --accent: #0284c7;
      --green: #059669;
      --amber: #d97706;
      --border: #e2e8f0;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 24px;
      font-family: 'Segoe UI', Roboto, Arial, sans-serif;
      background: var(--bg);
      color: var(--ink);
      line-height: 1.5;
    }}
    .container {{ max-width: 1180px; margin: 0 auto; }}
    header {{
      background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 100%);
      color: #fff;
      padding: 28px 32px;
      border-radius: 12px;
      margin-bottom: 20px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 16px;
    }}
    header h1 {{ margin: 0 0 8px 0; font-size: 24px; }}
    header p {{ margin: 4px 0; color: #cbd5e1; font-size: 14px; }}
    .nav-bar {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-bottom: 24px;
      background: var(--surface);
      padding: 12px 16px;
      border-radius: 10px;
      border: 1px solid var(--border);
    }}
    .nav-bar a, .btn-action {{
      text-decoration: none;
      background: #f1f5f9;
      color: #1e3a8a;
      font-weight: 600;
      font-size: 13px;
      padding: 8px 14px;
      border-radius: 8px;
      border: 1px solid #cbd5e1;
      cursor: pointer;
    }}
    .nav-bar a:hover, .btn-action:hover {{ background: #e0f2fe; border-color: #0284c7; }}
    .btn-primary {{ background: #0284c7; color: #fff; border-color: #0284c7; }}
    .btn-primary:hover {{ background: #0369a1; color: #fff; }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }}
    .kpi {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 16px 20px;
    }}
    .kpi .label {{ font-size: 12px; text-transform: uppercase; color: var(--muted); font-weight: 600; }}
    .kpi .value {{ font-size: 22px; font-weight: 700; color: var(--ink); margin-top: 4px; }}
    .kpi .sub {{ font-size: 12px; color: var(--muted); margin-top: 4px; }}
    .card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 24px;
      margin-bottom: 24px;
    }}
    .card h2 {{
      margin-top: 0;
      font-size: 18px;
      border-bottom: 2px solid var(--border);
      padding-bottom: 10px;
      color: #1e3a8a;
    }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 13.5px; }}
    th, td {{ border: 1px solid var(--border); padding: 9px 11px; text-align: left; vertical-align: top; }}
    th {{ background: #f1f5f9; font-weight: 600; }}
    .badge-ok {{ background: #d1fae5; color: #065f46; padding: 3px 8px; border-radius: 6px; font-weight: 600; }}
    .badge-warn {{ background: #fef3c7; color: #92400e; padding: 3px 8px; border-radius: 6px; font-weight: 600; }}
    .callout {{
      background: #f0f9ff;
      border-left: 4px solid var(--accent);
      padding: 16px 20px;
      border-radius: 6px;
      margin-top: 18px;
    }}
    .callout h3 {{ margin: 0 0 8px 0; font-size: 16px; color: #0369a1; }}
    .sim-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 12px;
      margin-bottom: 16px;
    }}
    .sim-field label {{ display: block; font-size: 12px; font-weight: 600; color: var(--muted); margin-bottom: 4px; }}
    .sim-field select, .sim-field input {{
      width: 100%;
      padding: 8px 10px;
      border: 1px solid #cbd5e1;
      border-radius: 6px;
      font-size: 13.5px;
    }}
    .steps-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 14px;
      margin-top: 14px;
    }}
    .step-box {{
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 14px 16px;
      background: #f8fafc;
    }}
    .step-box p {{ margin: 6px 0 0 0; font-size: 13px; color: #334155; }}
    .step-num {{
      display: inline-block;
      background: #1e3a8a;
      color: #fff;
      font-size: 11px;
      font-weight: 700;
      padding: 2px 8px;
      border-radius: 4px;
      margin-right: 8px;
    }}
    footer {{ text-align: center; font-size: 13px; color: var(--muted); padding: 16px 0; }}
    @media print {{ .nav-bar, #secao-simulador {{ display: none; }} body {{ padding: 0; }} }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div>
        <h1>Sistema de Dimensionamento e Orcamento Fotovoltaico ({apelido})</h1>
        <p><strong>Disciplina:</strong> Solucoes em Energias Renovaveis e Sustentaveis (Prof. Alvaro Goncalves) - Sprint 3 Final (PB01 a PB21)</p>
        <p><strong>Equipe Lumos (FIAP):</strong> Pietro Lorande (RM 569125) | Luiz Otavio Brito Freixo (RM 569977) | Maria Eduarda Lemos (RM 574094)</p>
        <p><strong>Localidade Base:</strong> {h['cidade']}/{h['uf']} (HSP {num(h['hsp'])} kWh/m2/dia) | <strong>Emissao:</strong> {r['data']}</p>
      </div>
      <div>
        <button class="btn-action btn-primary" onclick="window.print()">Imprimir / Salvar Proposta PDF</button>
      </div>
    </header>

    <nav class="nav-bar">
      <a href="#secao-proposta">1. Proposta & Orcamento (PB13-PB17)</a>
      <a href="#secao-simulador">2. Simulador Interativo ao Vivo (PB01-PB19)</a>
      <a href="#secao-comparacao">3. Comparacao Sem vs Com Baterias & Secao 9 (PB14)</a>
      <a href="#secao-roteiro">4. Roteiro das 15 Etapas da Sprint Review</a>
      <a href="#secao-datasets">5. Equipamentos da Casa & Datasets CSV (PB05/PB07/PB12)</a>
    </nav>

    <div class="grid">
      <div class="kpi">
        <div class="label">Consumo Mensal / Diario (PB02)</div>
        <div class="value">{num(r['consumo'])} kWh/mes</div>
        <div class="sub">E_dia: {num(r['consumo_diario'], 2)} kWh/dia | Pot. Casa: {num(r['potencia_residencia_kw'], 3)} kW ({num(r['potencia_residencia_w'], 0)} W)</div>
      </div>
      <div class="kpi">
        <div class="label">Potencia FV Instalada (PB04/PB06)</div>
        <div class="value">{num(r['p_inst'], 2)} kWp</div>
        <div class="sub">Necessaria: {num(r['p_fv'], 3)} kWp | HSP: {num(h['hsp'])} | PR: {num(r['pr']*100, 0)}%</div>
      </div>
      <div class="kpi">
        <div class="label">Geracao Estimada (PB08/PB09)</div>
        <div class="value">{num(r['geracao_mes'], 1)} kWh/mes</div>
        <div class="sub">Diaria: {num(r['geracao_dia'], 2)} kWh/dia ({num(comp_g['atendimento_pct'], 1)}% do consumo)</div>
      </div>
      <div class="kpi">
        <div class="label">Investimento & Payback Simples (PB13/PB16)</div>
        <div class="value">{brl(orc['c_total'])}</div>
        <div class="sub">Economia: {brl(econ['economia_mensal_brl'])}/mes | Payback: {num(pay['payback_simples_anos'])} anos</div>
      </div>
    </div>

    <section class="card" id="secao-simulador">
      <h2>Simulador Interativo para Demonstracao ao Vivo (PB01 a PB19)</h2>
      <p style="margin-top:0; color:var(--muted); font-size:13.5px;">Altere qualquer parametro abaixo (localidade/HSP, consumo, PR, modulo, inversor ou adicione baterias) para recalcular instantaneamente usando os datasets reais do projeto:</p>
      <div class="sim-grid">
        <div class="sim-field">
          <label>Localidade / HSP (PB03)</label>
          <select id="sim-hsp" onchange="recalcularSimulador()"></select>
        </div>
        <div class="sim-field">
          <label>Consumo Mensal E_mes (kWh/mes) (PB02)</label>
          <input type="number" id="sim-consumo" value="{r['consumo']:.2f}" min="10" step="10" oninput="recalcularSimulador()">
        </div>
        <div class="sim-field">
          <label>Meta de Atendimento (%) (PB04)</label>
          <input type="number" id="sim-pct" value="{r['percentual']:.0f}" min="1" max="100" step="5" oninput="recalcularSimulador()">
        </div>
        <div class="sim-field">
          <label>Performance Ratio PR (%) (PB03)</label>
          <input type="number" id="sim-pr" value="{r['pr']*100:.0f}" min="50" max="95" step="1" oninput="recalcularSimulador()">
        </div>
        <div class="sim-field">
          <label>Modulo Fotovoltaico (PB05/PB06)</label>
          <select id="sim-mod" onchange="recalcularSimulador()">
            <option value="AUTO">Selecao Otima Automatica (Menor Custo Compativel)</option>
          </select>
        </div>
        <div class="sim-field">
          <label>Armazenamento em Baterias (PB10)</label>
          <select id="sim-bat-ativo" onchange="recalcularSimulador()">
            <option value="0">Sem Baterias (On-Grid Convencional)</option>
            <option value="1">Com Baterias (Hibrido + Backup)</option>
          </select>
        </div>
        <div class="sim-field">
          <label>Autonomia de Baterias (horas) (PB11)</label>
          <input type="number" id="sim-autonomia" value="12" min="1" max="72" step="1" oninput="recalcularSimulador()">
        </div>
        <div class="sim-field">
          <label>Tarifa de Energia (R$/kWh) (PB15)</label>
          <input type="number" id="sim-tarifa" value="{econ['tarifa_brl_kwh']:.2f}" min="0.20" max="5.00" step="0.05" oninput="recalcularSimulador()">
        </div>
      </div>
      <div id="sim-resultado" class="callout" style="margin-top:12px;"></div>
    </section>

    <section class="card" id="secao-proposta">
      <h2>1. Especificacao Tecnica do Sistema Dimensionado (PB03 a PB12)</h2>
      <table>
        <tbody>
          <tr><th style="width:28%">Residencia e Demanda (PB01 / PB02)</th><td><strong>{apelido}</strong> | Consumo Mensal (E_mes): <strong>{num(r['consumo'])} kWh/mes</strong> | Consumo Diario (E_dia = E_mes / 30): <strong>{num(r['consumo_diario'], 2)} kWh/dia</strong> | Potencia Instalada da Casa: <strong>{num(r['potencia_residencia_w'], 0)} W ({num(r['potencia_residencia_kw'], 3)} kW)</strong></td></tr>
          <tr><th>Recurso Solar (HSP e PR - PB03)</th><td><strong>{h['cidade']}/{h['uf']}</strong>: HSP = <strong>{num(h['hsp'])} kWh/m2/dia</strong> ({h['fonte']}) | PR = <strong>{num(r['pr']*100, 0)}%</strong><br><small>{r['justificativa_pr']}</small></td></tr>
          <tr><th>Potencia FV Necessaria (PB04)</th><td><code>P_FV = E_dia / (HSP x PR) = {num(r['consumo_diario'], 3)} / ({num(h['hsp'])} x {num(r['pr'])})</code> = <strong>{num(r['p_fv'], 3)} kWp</strong></td></tr>
          <tr><th>Modulos Fotovoltaicos (PB05 / PB06)</th><td><strong>{cfg['n_modulos']}x [{mod['id']}] {mod['fabricante']} {mod['modelo']}</strong> ({mod['potencia_wp']:.0f} Wp, Eficiencia {num(mod['eficiencia_pct'])}%, Voc {num(mod['voc_v'])} V, Vmp {num(mod['vmp_v'])} V, Imp {num(mod['imp_a'])} A)<br>Dimensionamento: <code>N_mod = teto[({num(r['p_fv'], 3)} x 1000) / {mod['potencia_wp']:.0f}] = {s['n_minimo']}</code> -> Instalado: <strong>{cfg['n_modulos']} modulos</strong> ({cfg['n_strings']} string(s) de {cfg['por_string']} modulos) -> <strong>P_inst = {num(r['p_inst'], 3)} kWp</strong></td></tr>
          <tr><th>Inversor e Compatibilidade (PB07)</th><td><strong>[{inv['id']}] {inv['fabricante']} {inv['modelo']}</strong> (Tipo: {inv['tipo']}, Potencia Nominal: {inv['potencia_nominal_w']:.0f} W, Max FV: {inv['potencia_max_fv_w']:.0f} W, Eficiencia: {num(inv['eficiencia_pct'], 1)}%)<br>Verificacao Eletrica: Voc string (frio +10%) = {num(cfg['voc_string_v'], 1)} V (limite {inv['tensao_max_entrada_v']:.0f} V) | Vmp string = {num(cfg['vmp_string_v'], 1)} V (MPPT {inv['faixa_mppt_min_v']:.0f}-{inv['faixa_mppt_max_v']:.0f} V) | Razao <code>R_DC/AC = P_inst / P_inv = {num(cfg['ratio_dc_ac'])}</code></td></tr>
          <tr><th>Geracao e Atendimento (PB08 / PB09)</th><td>Geracao Diaria: <strong>{num(r['geracao_dia'], 2)} kWh/dia</strong> | Geracao Mensal: <strong>{num(comp_g['geracao_mensal_kwh'])} kWh/mes</strong> (Atendimento: <strong>{num(comp_g['atendimento_pct'], 1)}%</strong> do consumo)<br>Energia Efetivamente Compensada na Fatura: <strong>{num(comp_g['energia_compensada_kwh_mes'])} kWh/mes</strong> | Excedente Injetado na Rede (Creditos GD): <strong>{num(comp_g['energia_excedente_kwh_mes'])} kWh/mes</strong></td></tr>
        </tbody>
      </table>
    </section>

    <section class="card">
      <h2>2. Orcamento Detalhado (PB13) e Indicadores Economicos / Payback Simples (PB15 / PB16)</h2>
      <table>
        <thead>
          <tr><th>Categoria</th><th>Equipamento / Descricao e Fonte Rastreavel</th><th style="text-align:center">Qtd</th><th style="text-align:right">Preco Unitario</th><th style="text-align:right">Subtotal</th></tr>
        </thead>
        <tbody>
          {linhas_orc}
          <tr style="background:#f8fafc"><td colspan="4" style="text-align:right"><strong>CUSTO TOTAL DOS EQUIPAMENTOS (SOMA DOS ITENS DO DATASET: Custo_total = Sigma Custo_item)</strong></td><td style="text-align:right"><strong>{brl(orc['c_equipamentos'])}</strong></td></tr>
          <tr style="background:#e0f2fe"><td colspan="4" style="text-align:right"><strong>INVESTIMENTO TOTAL ESTIMADO DO PROJETO (EQUIPAMENTOS + ESTRUTURA, INSTALACAO E HOMOLOGACAO)</strong></td><td style="text-align:right"><strong>{brl(orc['c_total'])}</strong></td></tr>
        </tbody>
      </table>
      <div class="callout">
        <h3>Estimativa de Economia e Payback Simples (PB15 / PB16)</h3>
        <p><strong>Tarifa de Energia:</strong> {brl(econ['tarifa_brl_kwh'])}/kWh ({econ['fonte_tarifa']}) | <strong>Energia Compensada:</strong> {num(econ['energia_compensada_kwh_mes'])} kWh/mes</p>
        <p><strong>Economia Mensal Estimada:</strong> <code>{num(econ['energia_compensada_kwh_mes'])} x {brl(econ['tarifa_brl_kwh'])}</code> = <strong>{brl(econ['economia_mensal_brl'])}/mes</strong> | <strong>Economia Anual Estimada:</strong> <strong>{brl(econ['economia_anual_brl'])}/ano</strong></p>
        <p><strong>Payback Simples (Investimento Total / Economia Anual):</strong> <span class="badge-ok">{pay['payback_formatado']}</span> &nbsp;|&nbsp; <strong>Payback Simples (Apenas Equipamentos do Dataset):</strong> <span class="badge-ok">{num(pay['payback_apenas_equipamentos_anos'])} anos</span></p>
        <p><small>{pay['aviso_nao_exato']}</small></p>
      </div>
    </section>

    {bloco_comp_html}

    {bloco_15_etapas_html}

    <section class="card" id="secao-datasets">
      <h2>5. Equipamentos Cadastrados na Residencia (PB01/PB02) e Datasets Estruturados (PB05/PB07/PB12)</h2>
      <h3 style="font-size:15px; color:#0f172a; margin-top:12px;">5.1 Cargas Eletricas Cadastradas em "{apelido}" (dados_sistema.json)</h3>
      <table>
        <thead>
          <tr><th>Equipamento</th><th>Categoria</th><th style="text-align:right">Potencia Unit.</th><th style="text-align:center">Qtd</th><th style="text-align:right">Uso Diario</th><th style="text-align:right">Consumo Mensal</th></tr>
        </thead>
        <tbody>
          {linhas_cargas_html}
          <tr style="background:#f1f5f9"><td colspan="2"><strong>TOTAL DA RESIDENCIA (PB02)</strong></td><td style="text-align:right"><strong>{num(r['potencia_residencia_w'], 0)} W ({num(r['potencia_residencia_kw'], 3)} kW)</strong></td><td style="text-align:center"><strong>16</strong></td><td style="text-align:right"><strong>E_dia = {num(r['consumo_diario'], 2)} kWh/dia</strong></td><td style="text-align:right"><strong>E_mes = {num(r['consumo'], 2)} kWh/mes</strong></td></tr>
        </tbody>
      </table>

      <h3 style="font-size:15px; color:#0f172a; margin-top:24px;">5.2 Dataset de Modulos Fotovoltaicos (modulos.csv - PB05)</h3>
      <table>
        <thead>
          <tr><th>ID</th><th>Fabricante</th><th>Modelo</th><th style="text-align:right">Potencia</th><th style="text-align:right">Voc / Vmp</th><th style="text-align:right">Isc / Imp</th><th style="text-align:right">Eficiencia</th><th style="text-align:right">Preco Unit.</th><th>Fonte / Data</th></tr>
        </thead>
        <tbody>{linhas_ds_mod}</tbody>
      </table>

      <h3 style="font-size:15px; color:#0f172a; margin-top:24px;">5.3 Dataset de Inversores (inversores.csv - PB07)</h3>
      <table>
        <thead>
          <tr><th>ID</th><th>Fabricante</th><th>Modelo</th><th>Tipo</th><th style="text-align:right">Pot. Nom / Max FV</th><th style="text-align:right">Faixa MPPT</th><th style="text-align:right">Eficiencia</th><th style="text-align:center">Bateria</th><th style="text-align:right">Preco Unit.</th></tr>
        </thead>
        <tbody>{linhas_ds_inv}</tbody>
      </table>

      <h3 style="font-size:15px; color:#0f172a; margin-top:24px;">5.4 Dataset de Baterias LiFePO4 (baterias.csv - PB12)</h3>
      <table>
        <thead>
          <tr><th>ID</th><th>Fabricante</th><th>Modelo</th><th>Tecnologia</th><th style="text-align:right">Tensao</th><th style="text-align:right">Capacidade</th><th style="text-align:right">DoD / Ciclos</th><th style="text-align:right">Preco Unit.</th><th>Fonte / Data</th></tr>
        </thead>
        <tbody>{linhas_ds_bat}</tbody>
      </table>
    </section>

    <footer>
      Sistema de Dimensionamento Energetico Residencial - Equipe Lumos (FIAP 2026) | Pietro Lorande (RM 569125), Luiz Otavio Brito Freixo (RM 569977), Maria Eduarda Lemos (RM 574094)
    </footer>
  </div>

  <script>
    const DADOS_FV = {dados_js};

    function fmtBRL(v) {{
      return 'R$ ' + Number(v).toLocaleString('pt-BR', {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }});
    }}
    function fmtNum(v, c = 2) {{
      return Number(v).toLocaleString('pt-BR', {{ minimumFractionDigits: c, maximumFractionDigits: c }});
    }}

    function inicializarSimulador() {{
      const selHsp = document.getElementById('sim-hsp');
      DADOS_FV.hsp_lista.forEach((item, idx) => {{
        const opt = document.createElement('option');
        opt.value = idx;
        opt.textContent = `${{item.cidade}}/${{item.uf}} (HSP ${{fmtNum(item.hsp, 1)}} kWh/m2/dia)`;
        if (item.cidade.toLowerCase().includes('paulo') && item.uf === 'SP') opt.selected = true;
        selHsp.appendChild(opt);
      }});

      const selMod = document.getElementById('sim-mod');
      DADOS_FV.modulos.forEach(m => {{
        const opt = document.createElement('option');
        opt.value = m.id;
        opt.textContent = `[${{m.id}}] ${{m.fabricante}} ${{m.modelo}} (${{m.potencia_wp}} Wp - ${{fmtBRL(m.preco_brl)}})`;
        selMod.appendChild(opt);
      }});
      recalcularSimulador();
    }}

    function verificarPar(nMin, mod, inv, comBat) {{
      if (comBat && !inv.compativel_bateria) return null;
      const serieMax = Math.min(
        Math.floor(inv.tensao_max_entrada_v / (mod.voc_v * 1.10)),
        Math.floor(inv.faixa_mppt_max_v / mod.vmp_v)
      );
      const serieMin = Math.ceil(inv.faixa_mppt_min_v / (mod.vmp_v * 0.90));
      const parMax = Math.min(inv.strings_por_mppt, Math.floor(inv.corrente_max_entrada_a / mod.imp_a));
      if (parMax < 1 || serieMax < 1 || serieMin > serieMax) return null;
      const nStrings = Math.ceil(nMin / serieMax);
      if (nStrings > inv.numero_mppt * parMax) return null;
      const porString = Math.max(Math.ceil(nMin / nStrings), serieMin);
      const nFinal = nStrings * porString;
      const pInst = (nFinal * mod.potencia_wp) / 1000.0;
      const ratio = (pInst * 1000.0) / inv.potencia_nominal_w;
      const ratioMin = inv.compativel_bateria ? 0.30 : 0.60;
      if (pInst * 1000.0 > inv.potencia_max_fv_w) return null;
      if (ratio < ratioMin || ratio > 1.35) return null;
      return {{ n_modulos: nFinal, n_strings: nStrings, por_string: porString, p_inst: pInst, ratio: ratio }};
    }}

    function recalcularSimulador() {{
      const hspObj = DADOS_FV.hsp_lista[Number(document.getElementById('sim-hsp').value)] || DADOS_FV.hsp_lista[0];
      const consumoMes = Math.max(1, Number(document.getElementById('sim-consumo').value) || 455.31);
      const pct = Math.min(100, Math.max(1, Number(document.getElementById('sim-pct').value) || 100));
      const pr = Math.min(0.99, Math.max(0.10, (Number(document.getElementById('sim-pr').value) || 78) / 100.0));
      const modId = document.getElementById('sim-mod').value;
      const comBat = document.getElementById('sim-bat-ativo').value === '1';
      const autonomiaH = Math.min(72, Math.max(1, Number(document.getElementById('sim-autonomia').value) || 12));
      const tarifa = Math.max(0.10, Number(document.getElementById('sim-tarifa').value) || 0.92);

      const eDia = consumoMes / 30.0;
      const eDiaMeta = (consumoMes * (pct / 100.0)) / 30.0;
      const pFv = eDiaMeta / (hspObj.hsp * pr);

      const modsCand = modId === 'AUTO' ? DADOS_FV.modulos : DADOS_FV.modulos.filter(m => m.id === modId);
      let melhor = null;
      modsCand.forEach(mod => {{
        const nMin = Math.ceil((pFv * 1000.0) / mod.potencia_wp - 1e-9);
        DADOS_FV.inversores.forEach(inv => {{
          const cfg = verificarPar(nMin, mod, inv, comBat);
          if (cfg) {{
            const custoEq = cfg.n_modulos * mod.preco_brl + inv.preco_brl;
            if (!melhor || custoEq < melhor.custoEq) {{
              melhor = {{ mod, inv, cfg, custoEq }};
            }}
          }}
        }});
      }});

      const box = document.getElementById('sim-resultado');
      if (!melhor) {{
        box.innerHTML = '<strong>Incompatibilidade Tecnica (PB18):</strong> Nenhuma combinacao modulo x inversor atende aos limites eletricos para os parametros informados.';
        return;
      }}

      let infoBatTxt = 'Sem armazenamento (On-Grid convencional, 0 kWh)';
      let custoBat = 0;
      if (comBat) {{
        const eAut = eDia * (autonomiaH / 24.0);
        let melhorBat = null;
        DADOS_FV.baterias.forEach(b => {{
          if (b.tensao_nominal_v >= melhor.inv.tensao_bateria_min_v && b.tensao_nominal_v <= melhor.inv.tensao_bateria_max_v) {{
            const dod = b.dod_pct / 100.0;
            const cBat = eAut / (dod * 0.95);
            const cUtil = b.capacidade_kwh * dod;
            const nBat = Math.ceil((eAut / 0.95) / cUtil - 1e-9);
            const custoB = nBat * b.preco_brl;
            if (!melhorBat || custoB < melhorBat.custoB) {{
              melhorBat = {{ b, nBat, cBat, capNom: nBat * b.capacidade_kwh, capUtil: nBat * cUtil, custoB }};
            }}
          }}
        }});
        if (melhorBat) {{
          custoBat = melhorBat.custoB;
          infoBatTxt = `${{melhorBat.nBat}}x [${{melhorBat.b.id}}] ${{melhorBat.b.fabricante}} ${{melhorBat.b.modelo}} (${{fmtNum(melhorBat.capNom)}} kWh nominais / ${{fmtNum(melhorBat.capUtil)}} kWh uteis para ${{autonomiaH}}h -> ${{fmtBRL(custoBat)}})`;
        }}
      }}

      const cEquip = melhor.custoEq + custoBat;
      const cOutros = cEquip * 0.17 + 500.0 * melhor.cfg.p_inst + 800.0;
      const cTotal = cEquip + cOutros;
      const eGerDia = melhor.cfg.p_inst * hspObj.hsp * pr;
      const eGerMes = eGerDia * 30.0;
      const atendPct = (eGerMes / consumoMes) * 100.0;
      const eComp = Math.min(eGerMes, consumoMes);
      const eExc = Math.max(0, eGerMes - consumoMes);
      const econMes = eComp * tarifa;
      const econAno = econMes * 12.0;
      const paybackTotal = cTotal / econAno;
      const paybackEquip = cEquip / econAno;

      box.innerHTML = `
        <h3>Resultado da Simulacao em Tempo Real (${{hspObj.cidade}}/${{hspObj.uf}} - ${{comBat ? 'Com Baterias Hibrido' : 'Sem Baterias On-Grid'}})</h3>
        <p style="margin:4px 0;"><strong>1. Dimensionamento FV:</strong> E_dia = <strong>${{fmtNum(eDia)}} kWh/dia</strong> | P_FV necessaria = <strong>${{fmtNum(pFv, 3)}} kWp</strong> | Instalada = <strong>${{fmtNum(melhor.cfg.p_inst, 2)}} kWp</strong> (${{melhor.cfg.n_modulos}}x [${{melhor.mod.id}}] ${{melhor.mod.fabricante}} ${{melhor.mod.modelo}} de ${{melhor.mod.potencia_wp}} Wp)</p>
        <p style="margin:4px 0;"><strong>2. Inversor e Geracao:</strong> [${{melhor.inv.id}}] ${{melhor.inv.fabricante}} ${{melhor.inv.modelo}} (${{melhor.inv.potencia_nominal_w}} W, R_DC/AC = ${{fmtNum(melhor.cfg.ratio)}}) | Geracao: <strong>${{fmtNum(eGerDia)}} kWh/dia</strong> (<strong>${{fmtNum(eGerMes, 1)}} kWh/mes</strong> -> <strong>${{fmtNum(atendPct, 1)}}%</strong> do consumo | Compensada: ${{fmtNum(eComp)}} kWh/mes | Excedente: ${{fmtNum(eExc)}} kWh/mes)</p>
        <p style="margin:4px 0;"><strong>3. Armazenamento:</strong> ${{infoBatTxt}}</p>
        <p style="margin:4px 0;"><strong>4. Orcamento e Payback Simples:</strong> Equipamentos (Datasets): <strong>${{fmtBRL(cEquip)}}</strong> | Investimento Total: <strong>${{fmtBRL(cTotal)}}</strong> | Economia: <strong>${{fmtBRL(econMes)}}/mes (${{fmtBRL(econAno)}}/ano)</strong> | <span class="badge-ok">Payback Simples: ${{fmtNum(paybackTotal)}} anos (Total) / ${{fmtNum(paybackEquip)}} anos (So Equipamentos)</span></p>
      `;
    }}

    window.addEventListener('DOMContentLoaded', inicializarSimulador);
  </script>
</body>
</html>
"""
    with open(caminho_arquivo, "w", encoding="utf-8-sig") as f:
        f.write(html)
    return caminho_arquivo


def formatar_incompatibilidades(rejeitados, limite=12):
    """FV-PB08-T05 / PB18 - explica por que cada combinacao foi bloqueada."""
    linhas = [f"Combinacoes bloqueadas: {len(rejeitados)}"]
    linhas += [f"  x {par}: {'; '.join(motivos)}" for par, motivos in rejeitados[:limite]]
    if len(rejeitados) > limite:
        linhas.append(f"  ... e mais {len(rejeitados) - limite}.")
    return "\n".join(linhas)

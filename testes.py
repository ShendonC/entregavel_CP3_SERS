#   ============================================================
#   testes.py - BATERIA DE TESTES AUTOMATIZADOS (CP1 + CP2 + SPRINT 3 FINAL)
#   Disciplina: Solucoes em Energias Renovaveis e Sustentaveis (Prof. Alvaro Goncalves)
#
#   Equipe Lumos - FIAP:
#   - Pietro Lorande | RM 569125
#   - Luiz Otavio Brito Freixo (Luiz Otavio Britto Freixo) | RM 569977
#   - Maria Eduarda Lemos | RM 574094
#
#   Executar:  python testes.py   (ou opcao 4 do menu inicial)
#   Nao pede nada ao usuario e preserva o dados_sistema.json.
#   Cobre as etapas anteriores e todos os itens PB01 a PB21 da Sprint 3.
#   ============================================================

import os
import sys
import tempfile

import fotovoltaico as fv
import sistema_analise_casa as sc


def rodar_testes_calculo():
    """PB01 / PB02 / PB11 / PB12 / PB13 - Consumo mensal, diario, potencia instalada e ranking."""
    sc.dados["equipamentos"]["__t"] = {"nome": "Teste", "categoria": "T", "potencia": 100, "pre_cadastrado": False}
    sc.dados["associacoes"]["__a1"] = {"imovel_id": "__im", "equipamento_id": "__t", "quantidade": 2, "tempo_uso": 5}
    sc.dados["associacoes"]["__a2"] = {"imovel_id": "__im", "equipamento_id": "__t", "quantidade": 1, "tempo_uso": 1}
    try:
        assert sc.calcular_consumo_associacao({"equipamento_id": "__x", "quantidade": 1, "tempo_uso": 1}) == 0.0
        assert abs(sc.calcular_consumo_associacao(sc.dados["associacoes"]["__a1"]) - 30.0) < 1e-9
        assert abs(sc.consumo_total_imovel("__im") - 33.0) < 1e-9
        assert abs(sc.consumo_diario_imovel("__im") - 1.1) < 1e-9
        assert abs(sc.potencia_instalada_imovel("__im") - 300.0) < 1e-9
        assert sc.consumo_total_imovel("__vazio") == 0.0
        ranking = sc.ranking_consumo_imovel("__im")
        assert ranking[0][1] >= ranking[1][1] and sc.ranking_consumo_imovel("__vazio") == []
        print("[OK] Testes de consumo e potencia instalada da residencia (PB01/PB02/PB11/PB12/PB13)")
        return True
    except AssertionError:
        print("[FALHOU] Testes de consumo da etapa anterior")
        return False
    finally:
        for colecao, chave in (("equipamentos", "__t"), ("associacoes", "__a1"), ("associacoes", "__a2")):
            sc.dados[colecao].pop(chave, None)


def rodar_testes_fotovoltaico():
    """Cobre todas as tasks da Sprint 2 (FV-PB01 a FV-PB11) e da Sprint 3 Final (PB01 a PB21)."""
    ds = fv.carregar_datasets_fv()
    sp = fv.obter_hsp("São Paulo", "SP", ds["hsp"])
    mod = {m["id"]: m for m in ds["modulos"]}
    inv = {i["id"]: i for i in ds["inversores"]}

    def da_erro(funcao, *args):
        try:
            funcao(*args)
        except ValueError:
            return True
        return False

    def t_pb01():
        for cidade, uf, hsp in [("São Paulo", "SP", 5.0), ("natal", "rn", 6.0), ("Brasilia", "DF", 5.6)]:
            h = fv.obter_hsp(cidade, uf, ds["hsp"])
            assert h["hsp"] == hsp and h["fonte"]
        assert da_erro(fv.obter_hsp, "Osasco", "SP", ds["hsp"])
        assert da_erro(fv.obter_hsp, "Osasco", "SP", ds["hsp"], 4.9, "")
        assert fv.obter_hsp("Osasco", "SP", ds["hsp"], 4.9, "CRESESB SunData")["hsp"] == 4.9
        assert all(da_erro(fv.validar_hsp, v) for v in (0, -2, 2.5, 9, "abc"))

    def t_pb02():
        assert fv.validar_percentual("80") == 0.8 and fv.validar_percentual("100") == 1.0
        assert all(da_erro(fv.validar_percentual, v) for v in ("0", "-5", "101", "abc", "", None))
        dem = fv.demanda_energetica_residencia(360.0, 8500.0)
        assert abs(dem["consumo_diario_kwh"] - 12.0) < 1e-9
        assert abs(dem["potencia_instalada_kw"] - 8.5) < 1e-9

    def t_pb03():
        for cm, f, hsp in [(350, 1.0, 5.0), (500, 0.8, 6.0), (200, 0.5, 4.6)]:
            e = fv.energia_mensal_desejada(cm, f)
            p1 = fv.potencia_fv_necessaria(e, hsp, 30, 0.78)
            p2 = fv.potencia_fv_por_consumo_diario((cm * f) / 30.0, hsp, 0.78)
            assert abs(p1 - cm * f / (hsp * 30 * 0.78)) < 1e-9
            assert abs(p1 - p2) < 1e-9
        assert da_erro(fv.energia_mensal_desejada, 0, 1) and da_erro(fv.energia_mensal_desejada, 300, 1.5)
        assert da_erro(fv.potencia_fv_necessaria, 300, None, 30, 0.78)
        assert all(da_erro(fv.validar_pr, v) for v in (0, -0.5, 1.05, 150, "abc"))

    def t_pb04():
        assert fv.quantidade_minima_modulos(3.24, 405) == 8 and fv.quantidade_minima_modulos(3.241, 405) == 9
        assert abs(fv.potencia_instalada(8, 405) - 3.24) < 1e-9
        for m in ds["modulos"]:
            n = fv.quantidade_minima_modulos(5.0, m["potencia_wp"])
            assert fv.potencia_instalada(n, m["potencia_wp"]) >= 5.0 > fv.potencia_instalada(n - 1, m["potencia_wp"])

    def t_pb05():
        config, _ = fv.verificar_modulo_inversor(8, mod["FV006"], inv["INV001"], False)
        assert config and config["n_modulos"] == 8
        _, motivos = fv.verificar_modulo_inversor(8, mod["FV004"], inv["INV001"], False)
        assert any(m.startswith("C4") for m in motivos)
        _, motivos = fv.verificar_modulo_inversor(5, mod["FV006"], inv["INV005"], False)
        assert any(m.startswith("C6") for m in motivos)
        r = fv.dimensionar_fv(700, 100, sp, ds)
        assert r["selecao"]["inversor"]["id"] != "INV001"
        assert all(i.get("eficiencia_pct", 0) > 90 for i in ds["inversores"])

    def t_pb06():
        assert fv.consumo_diario(360) == 12 and fv.energia_autonomia(12, 6) == 3
        assert abs(fv.capacidade_bateria_necessaria(3, 0.9, 0.95) - 3 / (0.9 * 0.95)) < 1e-9
        sem = fv.dimensionar_fv(350, 100, sp, ds)["armazenamento"]
        assert not sem["ativo"] and sem["capacidade_instalada_kwh"] == 0 and sem["custo"] == 0
        for horas in (2, 6, 12, 24):
            arm = fv.dimensionar_fv(350, 100, sp, ds, True, horas)["armazenamento"]
            assert arm["capacidade_util_kwh"] * 0.95 + 1e-9 >= arm["energia_autonomia_kwh"]
        assert all(da_erro(fv.validar_autonomia, v) for v in (0, -3, 100))

    def t_pb07():
        assert abs(fv.capacidade_util(5.12, 0.9) - 4.608) < 1e-9
        assert fv.quantidade_baterias(4.608, 4.608) == 1 and fv.quantidade_baterias(4.61, 4.608) == 2
        for e_aut in (1.0, 3.3, 12.0):
            for b in ds["baterias"]:
                dod = b["dod_pct"] / 100
                assert (
                    fv.arredondar_para_cima(fv.capacidade_bateria_necessaria(e_aut, dod, 0.95) / b["capacidade_kwh"])
                    == fv.quantidade_baterias(e_aut / 0.95, fv.capacidade_util(b["capacidade_kwh"], dod))
                )

    def t_pb08():
        assert "C7" in fv.verificar_inversor_bateria(inv["INV002"], ds["baterias"][0])[0]
        assert "C8" in fv.verificar_inversor_bateria(inv["INV006"], dict(ds["baterias"][0], tensao_nominal_v=400))[0]
        assert fv.verificar_inversor_bateria(inv["INV006"], ds["baterias"][0]) == []
        assert fv.dimensionar_fv(350, 100, sp, ds, True, 4)["selecao"]["inversor"]["compativel_bateria"]
        so_ongrid = dict(ds, inversores=[i for i in ds["inversores"] if not i["compativel_bateria"]])
        try:
            fv.dimensionar_fv(350, 100, sp, so_ongrid, True, 4)
            raise AssertionError("on-grid + bateria deveria ser bloqueado")
        except fv.ErroDimensionamento as erro:
            assert "C7" in fv.formatar_incompatibilidades(erro.rejeitados)

    def t_pb09():
        for com in (False, True):
            o = fv.dimensionar_fv(350, 100, sp, ds, com, 12)["orcamento"]
            assert abs(o["c_total"] - o["c_equipamentos"] - o["c_outros"]) < 0.01
            assert abs(o["c_equipamentos"] - sum(i["subtotal"] for i in o["itens"])) < 0.01
            for item in o["itens"]:
                assert abs(item["subtotal"] - item["qtd"] * item["preco_unitario"]) < 0.01
            assert (o["c_baterias"] > 0) == com

    def t_pb10():
        for com in (False, True):
            texto = fv.formatar_proposta(fv.dimensionar_fv(350, 100, sp, ds, com, 8))
            for trecho in (
                "Consumo de referencia",
                "Consumo medio diario",
                "Percentual de atendimento",
                "HSP",
                "Performance Ratio (PR)",
                "Potencia FV calculada",
                "Potencia instalada",
                "Geracao estimada diaria",
                "Geracao estimada mensal",
                "MODULOS",
                "INVERSOR",
                "CUSTO DOS EQUIPAMENTOS",
                "Outros custos",
                "CUSTO TOTAL ESTIMADO",
                "Economia mensal estimada",
                "Economia anual estimada",
                "Payback simples",
                "ORIGEM DOS PRECOS",
            ):
                assert trecho in texto, trecho
            assert ("Capacidade instalada" if com else "Sem armazenamento") in texto

    def t_pb11():
        assert fv.validar_datasets_fv()[0]

    def t_sprint3_geracao_economia_payback():
        """PB08 / PB09 / PB14 / PB15 / PB16 / PB21 - Geracao diaria/mensal, compensacao, economia, payback e cenarios."""
        g_dia = fv.geracao_estimada_diaria(3.30, 5.0, 0.78)
        g_mes = fv.geracao_estimada_mensal(3.30, 5.0, 30, 0.78)
        assert abs(g_dia - 12.87) < 1e-6 and abs(g_mes - 386.10) < 1e-6

        # PB09: quando a geracao supera o consumo, distingue gerada de compensada
        comp_exc = fv.comparar_geracao_consumo(350.0, 386.10)
        assert comp_exc["supera_consumo"] is True
        assert abs(comp_exc["energia_compensada_kwh_mes"] - 350.0) < 1e-6
        assert abs(comp_exc["energia_excedente_kwh_mes"] - 36.10) < 1e-6

        comp_parcial = fv.comparar_geracao_consumo(400.0, 300.0)
        assert comp_parcial["supera_consumo"] is False
        assert abs(comp_parcial["energia_compensada_kwh_mes"] - 300.0) < 1e-6
        assert comp_parcial["energia_excedente_kwh_mes"] == 0.0

        # PB15 e PB16: Economia mensal/anual e Payback simples
        econ = fv.calcular_economia(386.10, 350.0, tarifa_kwh=0.92)
        assert abs(econ["economia_mensal_brl"] - round(350.0 * 0.92, 2)) < 1e-6
        assert abs(econ["economia_anual_brl"] - round(econ["economia_mensal_brl"] * 12, 2)) < 1e-6
        pay = fv.calcular_payback_simples(10000.0, 3864.0, c_equipamentos=7500.0)
        assert abs(pay["payback_simples_anos"] - round(10000.0 / 3864.0, 2)) < 1e-6
        assert "PAYBACK SIMPLES" in pay["aviso_nao_exato"]

        # PB14 e PB21: Comparacao de cenarios e exportacao HTML/TXT
        comp = fv.comparar_cenarios(426.30, 100, sp, ds, autonomia_h=12, tarifa_kwh=0.92, potencia_residencia_w=9963)
        assert comp["com_bateria"]["orcamento"]["c_total"] > comp["sem_bateria"]["orcamento"]["c_total"]
        assert comp["com_bateria"]["payback"]["payback_simples_anos"] > comp["sem_bateria"]["payback"]["payback_simples_anos"]
        texto_comp = fv.formatar_comparacao_cenarios(comp, "Residencia Teste")
        assert "CENARIO 1: SEM BATERIAS" in texto_comp and "CENARIO 2: COM BATERIAS" in texto_comp

        with tempfile.TemporaryDirectory() as tmpdir:
            p_txt = fv.exportar_proposta_txt(comp["sem_bateria"], comp, "Teste", os.path.join(tmpdir, "p.txt"))
            p_html = fv.exportar_proposta_html(comp["sem_bateria"], comp, "Teste", os.path.join(tmpdir, "p.html"))
            assert os.path.isfile(p_txt) and os.path.getsize(p_txt) > 500
            assert os.path.isfile(p_html) and os.path.getsize(p_html) > 1000

    testes = [
        ("PB01/PB03 HSP por localizacao", t_pb01),
        ("PB02 Demanda energetica e percentual", t_pb02),
        ("PB03/PB04 Recurso solar, PR e potencia FV", t_pb03),
        ("PB05/PB06 Dimensionamento de modulos", t_pb04),
        ("PB07 Selecao e eficiencia do inversor", t_pb05),
        ("PB10/PB11 Armazenamento e autonomia", t_pb06),
        ("PB11/PB12 Dimensionamento de baterias", t_pb07),
        ("PB07/PB18 Compatibilidade tecnica (C1-C8)", t_pb08),
        ("PB13 Orcamento automatico (preco unitario e total)", t_pb09),
        ("PB17 Relatorio consolidado completo", t_pb10),
        ("PB05/PB07/PB12 Validacao dos datasets", t_pb11),
        ("PB08/PB09/PB14/PB15/PB16/PB21 Geracao, Economia, Payback e Cenarios", t_sprint3_geracao_economia_payback),
    ]
    aprovados = 0
    for nome, teste in testes:
        try:
            teste()
            aprovados += 1
            print(f"[OK] {nome}")
        except Exception as erro:
            print(f"[FALHOU] {nome} -> {type(erro).__name__}: {erro}")
    print(f"\n{aprovados}/{len(testes)} grupos da Sprint 3 aprovados.")
    return aprovados == len(testes)


def rodar_todos_os_testes():
    print("==== TESTES AUTOMATIZADOS (SPRINT 3 FINAL - EQUIPE LUMOS) ====\n")
    ok = rodar_testes_calculo()
    try:
        ok = rodar_testes_fotovoltaico() and ok
        print("\n" + fv.validar_datasets_fv()[1])
    except FileNotFoundError as erro:
        print(f"ERRO: {erro}")
        ok = False
    return ok


if __name__ == "__main__":
    sys.exit(0 if rodar_todos_os_testes() else 1)

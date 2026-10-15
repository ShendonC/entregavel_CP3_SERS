#   ============================================================
#   SISTEMA DE DIMENSIONAMENTO ENERGETICO RESIDENCIAL (SPRINT 3 - FINAL)
#   Disciplina: Solucoes em Energias Renovaveis e Sustentaveis (Prof. Alvaro Goncalves)
#
#   Equipe Lumos - FIAP:
#   - Pietro Lorande | RM 569125
#   - Luiz Otavio Brito Freixo (Luiz Otavio Britto Freixo) | RM 569977
#   - Maria Eduarda Lemos | RM 574094
#   ============================================================
#
#   O sistema esta dividido em 3 arquivos:
#     sistema_analise_casa.py  -> este: telas, menus, persistencia e Sprint Review
#     fotovoltaico.py          -> calculos, datasets, compatibilidade, comparacao de
#                                 cenarios, orcamento, payback simples e exportacao
#     testes.py                -> bateria de testes automatizados (CP1 + CP2 + CP3)
#
#   Executar interativo:        python sistema_analise_casa.py
#   Demonstracao Sprint Review: python sistema_analise_casa.py --demo
#   Testes automatizados:       python testes.py
#   ============================================================

import os
import sys
import re
import json
import hashlib

import fotovoltaico as fv


PASTA_BASE = os.path.dirname(os.path.abspath(__file__))
ARQUIVO_DADOS = os.path.join(PASTA_BASE, "dados_sistema.json")

# PB17 / PB20 - Persistencia completa do projeto em JSON
dados = {
    "usuarios": {},          # email -> {nome, telefone, senha_hash}
    "imoveis": {},           # id -> {endereco, numero, apelido, tipo, dono_email, localizacao}
    "equipamentos": {},      # id -> {nome, categoria, potencia, pre_cadastrado}
    "associacoes": {},       # id -> {imovel_id, equipamento_id, quantidade, tempo_uso}
    "dimensionamentos": {},  # PB20 -> id -> cenario FV completo salvo (com orcamento, economia e payback)
    "next_ids": {"imovel": 1, "equipamento": 1, "associacao": 1, "dimensionamento": 1},
}
sessao = {"email_logado": None}

TIPOS_IMOVEL = {"1": "Casa", "2": "Apartamento", "3": "Outro"}
UFS = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA",
    "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
}


# ==================================================================
# UTILIDADES, PERSISTENCIA (PB20) E VALIDACAO (PB18)
# ==================================================================

def limpar_terminal():
    os.system("cls" if os.name == "nt" else "clear")


def pausar():
    input("\nPressione ENTER para continuar...")


def concluir(mensagem=None):
    if mensagem:
        print(f"\n{mensagem}")
    pausar()
    limpar_terminal()


def salvar_dados():
    with open(ARQUIVO_DADOS, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)


def carregar_dados():
    if os.path.exists(ARQUIVO_DADOS):
        with open(ARQUIVO_DADOS, "r", encoding="utf-8") as f:
            dados.update(json.load(f))
        dados.setdefault("dimensionamentos", {})
        dados["next_ids"].setdefault("dimensionamento", 1)
        if not dados.get("imoveis"):
            popular_residencia_demonstracao()
            salvar_dados()
    else:
        popular_catalogo_inicial()
        popular_residencia_demonstracao()
        salvar_dados()


def proximo_id(tipo):
    novo = str(dados["next_ids"][tipo])
    dados["next_ids"][tipo] += 1
    return novo


def validar_nao_vazio(texto):
    return texto.strip() != ""


def validar_email_formato(email):
    return re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email) is not None


def validar_numero_positivo(texto):
    try:
        return float(texto.replace(",", ".")) > 0
    except ValueError:
        return False


def validar_inteiro_positivo(texto):
    try:
        return int(texto) > 0
    except ValueError:
        return False


def validar_intervalo_horas(texto):
    try:
        return 0 <= float(texto.replace(",", ".")) <= 24
    except ValueError:
        return False


def ler(mensagem, valido=validar_nao_vazio, erro="ERRO: O campo nao pode ficar vazio!", padrao=""):
    """Pergunta ate receber um valor valido. ENTER mantem o 'padrao', se houver."""
    while True:
        texto = input(mensagem).strip()
        if texto == "" and padrao != "":
            return str(padrao)
        if valido(texto):
            return texto
        print(erro)


def ler_validado(mensagem, funcao, padrao=None):
    """Para validadores que lancam ValueError com a mensagem de erro (PB18)."""
    while True:
        bruto = input(mensagem).strip()
        if bruto == "" and padrao is not None:
            bruto = str(padrao)
        try:
            return funcao(bruto)
        except ValueError as erro:
            print(f"ERRO: {erro}")


def ler_opcao_inteira(minimo, maximo):
    texto = ler(
        f"\nPOR FAVOR DIGITE UMA OPCAO ({minimo}-{maximo})...: ",
        lambda t: t.isdigit() and minimo <= int(t) <= maximo,
        f"ERRO: Escolha um numero entre {minimo} e {maximo}.",
    )
    return int(texto)


def ler_sim_nao(mensagem, padrao=""):
    return (
        ler(
            mensagem,
            lambda t: t.upper() in ("S", "SIM", "N", "NAO", "NÃO"),
            "ERRO: Responda S ou N.",
            padrao=padrao,
        )
        .upper()
        .startswith("S")
    )


def confirmar(mensagem):
    return input(f"\n{mensagem} Digite SIM para confirmar...: ").strip().upper() == "SIM"


def ler_tipo_imovel():
    print("\nTIPO DO IMOVEL: 1. Casa  2. Apartamento  3. Outro")
    return TIPOS_IMOVEL[ler("ESCOLHA UMA OPCAO...: ", lambda t: t in TIPOS_IMOVEL, "ERRO: Escolha 1, 2 ou 3.")]


def ler_localizacao():
    """PB03 - cidade e UF do imovel."""
    cidade = ler("\nCIDADE DO IMOVEL...: ")
    uf = ler("UF (ex.: SP)...: ", lambda t: t.upper() in UFS, "ERRO: Digite uma sigla de UF valida.").upper()
    return {"cidade": cidade, "uf": uf}


def executar_menu(titulo, opcoes):
    """Menu generico: opcoes = [(texto, funcao), ...]. A ultima opcao e sempre Voltar."""
    while True:
        print(f" ==== {titulo} ==== \n")
        for i, (texto, _) in enumerate(opcoes, start=1):
            print(f"{i}. {texto}")
        print(f"{len(opcoes) + 1}. Voltar")
        escolha = ler_opcao_inteira(1, len(opcoes) + 1)
        limpar_terminal()
        if escolha == len(opcoes) + 1:
            return
        opcoes[escolha - 1][1]()


# ==================================================================
# USUARIO, LOGIN E RESIDENCIA PRE-CADASTRADA (PB01)
# ==================================================================

CATALOGO_INICIAL = [
    ("Geladeira", "Cozinha", 133),
    ("Chuveiro eletrico", "Banheiro", 5500),
    ("Televisao", "Sala", 100),
    ("Ar-condicionado", "Quarto", 1200),
    ("Micro-ondas", "Cozinha", 1200),
    ("Ferro de passar", "Lavanderia", 1000),
    ("Maquina de lavar roupa", "Lavanderia", 500),
    ("Computador desktop", "Escritorio", 200),
    ("Notebook", "Escritorio", 65),
    ("Lampada LED", "Geral", 10),
]


def popular_catalogo_inicial():
    """Catalogo base de equipamentos criado na primeira execucao."""
    for nome, categoria, potencia in CATALOGO_INICIAL:
        dados["equipamentos"][proximo_id("equipamento")] = {
            "nome": nome,
            "categoria": categoria,
            "potencia": potencia,
            "pre_cadastrado": True,
        }


def popular_residencia_demonstracao():
    """
    PB01 - Garante uma residencia ja cadastrada com equipamentos e consumo calculado
    para que o usuario possa iniciar o dimensionamento fotovoltaico sem recadastro.
    Conta padrao: demo@lumos.com (senha: 1234).
    """
    if not dados["equipamentos"]:
        popular_catalogo_inicial()

    email_demo = "demo@lumos.com"
    if email_demo not in dados["usuarios"]:
        dados["usuarios"][email_demo] = {
            "nome": "Equipe Lumos (Pietro, Luiz Otavio e Maria Eduarda)",
            "telefone": "11999990000",
            "senha_hash": hashlib.sha256("1234".encode()).hexdigest(),
        }

    if not dados["imoveis"]:
        id_im = proximo_id("imovel")
        dados["imoveis"][id_im] = {
            "endereco": "Av. Paulista",
            "numero": "1106",
            "apelido": "Residencia Familia Silva (SP)",
            "tipo": "Casa",
            "localizacao": {"cidade": "São Paulo", "uf": "SP"},
            "dono_email": email_demo,
        }
        # Cargas residenciais tipicas associadas ao imovel (426,30 kWh/mes e 9.963 W instalados):
        # 1x Geladeira (133W, 24h), 1x Chuveiro (5500W, 0.75h), 2x TV (100W, 4h),
        # 1x Ar-condicionado (1200W, 4h), 1x Micro-ondas (1200W, 0.3h),
        # 1x Maquina de lavar (500W, 1h), 1x Computador (200W, 5h), 8x Lampada LED (10W, 5h)
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
            if eq_id in dados["equipamentos"]:
                dados["associacoes"][proximo_id("associacao")] = {
                    "imovel_id": id_im,
                    "equipamento_id": eq_id,
                    "quantidade": qtd,
                    "tempo_uso": horas,
                }


def cadastro_user():
    print(" ==== CADASTRO DE CONTAS ==== \n")
    nome = ler("POR FAVOR DIGITE SEU NOME...: ")

    while True:
        email = ler("\nPOR FAVOR DIGITE O SEU EMAIL...: ")
        if not validar_email_formato(email):
            print("ERRO: Formato de e-mail invalido (ex: nome@dominio.com)!")
        elif email in dados["usuarios"]:
            print("ERRO: Este email ja esta cadastrado! Por favor, faca login.")
        else:
            break

    telefone = ler(
        "\nPOR FAVOR DIGITE SEU TELEFONE (apenas numeros)...: ",
        str.isdigit,
        "ERRO: Digite apenas numeros no telefone!",
    )
    senha = ler("\nCRIE UMA SENHA PARA SUA CONTA...: ")

    dados["usuarios"][email] = {
        "nome": nome,
        "telefone": telefone,
        "senha_hash": hashlib.sha256(senha.encode()).hexdigest(),
    }
    salvar_dados()
    concluir("==== CADASTRO CONCLUIDO COM SUCESSO ====")


def login():
    print("==== TELA DE LOGIN ====")
    print("Dica Sprint Review: conta pre-cadastrada -> email: demo@lumos.com | senha: 1234")
    email = ler("\nPOR FAVOR DIGITE SEU EMAIL CADASTRADO [demo@lumos.com]...: ", padrao="demo@lumos.com")
    if email not in dados["usuarios"]:
        print("EMAIL NAO CADASTRADO. POR FAVOR, SIGA PARA A PAGINA DE CADASTRO.")
        return False

    usuario = dados["usuarios"][email]
    while True:
        padrao_s = "1234" if email == "demo@lumos.com" else ""
        senha = ler(
            f"\nBEM VINDO DE VOLTA {usuario['nome']} | DIGITE A SENHA...: ",
            padrao=padrao_s,
        )
        if hashlib.sha256(senha.encode()).hexdigest() == usuario["senha_hash"]:
            break
        print("ERRO: Senha incorreta! Tente novamente.")

    sessao["email_logado"] = email
    concluir("==== LOG IN EFETUADO COM SUCESSO ====")
    return True


# ==================================================================
# PRIVACIDADE E SELECAO DE IMOVEL JA CADASTRADO (PB01)
# ==================================================================

def imoveis_do_usuario_logado():
    return {i: im for i, im in dados["imoveis"].items() if im["dono_email"] == sessao["email_logado"]}


def selecionar_imovel_do_usuario():
    """PB01 - Lista residencias ja cadastradas do usuario e recupera seus dados."""
    meus = imoveis_do_usuario_logado()
    if not meus:
        print("\nVOCE AINDA NAO TEM NENHUM IMOVEL CADASTRADO.")
        return None
    print("\n==== SEUS IMOVEIS CADASTRADOS (PB01) ====")
    for i, im in meus.items():
        loc = im.get("localizacao")
        local = f" - {loc['cidade']}/{loc['uf']}" if loc else ""
        cons_m = consumo_total_imovel(i)
        pot_w = potencia_instalada_imovel(i)
        print(
            f"{i}. {im['apelido']} - {im['endereco']}, {im['numero']} ({im['tipo']}){local} | "
            f"Consumo: {cons_m:.2f} kWh/mes ({cons_m/30:.2f} kWh/dia) | Potencia instalada: {pot_w:.0f} W"
        )
    padrao_id = next(iter(meus.keys())) if len(meus) == 1 else ""
    dica = f" [{padrao_id}]" if padrao_id else ""
    return ler(
        f"\nEscolha o imovel pelo numero{dica}...: ",
        lambda t: t in meus,
        "ERRO: Numero invalido ou este imovel nao pertence a voce.",
        padrao=padrao_id,
    )


# ==================================================================
# IMOVEIS (CADASTRO, EDICAO E EXCLUSAO)
# ==================================================================

def cadastro_imovel():
    print("==== CADASTRO DE IMOVEIS ====")
    imovel = {
        "endereco": ler("\nENDERECO DO IMOVEL...: "),
        "numero": ler("\nNUMERO DA RESIDENCIA...: "),
        "apelido": ler("\nAPELIDO PARA A RESIDENCIA...: "),
        "tipo": ler_tipo_imovel(),
        "localizacao": ler_localizacao(),
        "dono_email": sessao["email_logado"],
    }
    dados["imoveis"][proximo_id("imovel")] = imovel
    salvar_dados()
    concluir("==== RESIDENCIA CADASTRADA COM SUCESSO ====")


def modificar_imovel():
    print("==== MODIFICACAO DE IMOVEL ====")
    id_imovel = selecionar_imovel_do_usuario()
    if id_imovel is None:
        return concluir()
    imovel = dados["imoveis"][id_imovel]
    loc = imovel.get("localizacao")
    print(
        f"\nEndereco: {imovel['endereco']} | Numero: {imovel['numero']} | Apelido: {imovel['apelido']}"
        f" | Tipo: {imovel['tipo']} | Local: {loc['cidade'] + '/' + loc['uf'] if loc else '(nao informado)'}"
    )

    print("\n1. ENDERECO  2. NUMERO  3. APELIDO  4. TIPO  5. LOCALIZACAO")
    opcao = ler_opcao_inteira(1, 5)
    if opcao in (1, 2, 3):
        campo = ["endereco", "numero", "apelido"][opcao - 1]
        imovel[campo] = ler(f"\nATUAL: {imovel[campo]}\nNOVO VALOR...: ")
    elif opcao == 4:
        imovel["tipo"] = ler_tipo_imovel()
    else:
        imovel["localizacao"] = ler_localizacao()
    salvar_dados()
    concluir("DADO ATUALIZADO COM SUCESSO...")


def excluir_imovel():
    """Remove tambem associacoes e dimensionamentos do imovel."""
    print("==== EXCLUSAO DE IMOVEL ====")
    id_imovel = selecionar_imovel_do_usuario()
    if id_imovel is None:
        return concluir()
    if not confirmar(
        f"EXCLUIR '{dados['imoveis'][id_imovel]['apelido']}' e os equipamentos e "
        f"dimensionamentos associados a ele?"
    ):
        return concluir("EXCLUSAO CANCELADA.")
    for colecao in ("associacoes", "dimensionamentos"):
        for i in [i for i, reg in dados[colecao].items() if reg["imovel_id"] == id_imovel]:
            del dados[colecao][i]
    del dados["imoveis"][id_imovel]
    salvar_dados()
    concluir("==== IMOVEL EXCLUIDO COM SUCESSO ====")


# ==================================================================
# EQUIPAMENTOS E ASSOCIACOES
# ==================================================================

def listar_equipamentos():
    if not dados["equipamentos"]:
        print("\nNENHUM EQUIPAMENTO CADASTRADO AINDA.")
    for i, eq in dados["equipamentos"].items():
        origem = "(catalogo)" if eq.get("pre_cadastrado") else ""
        print(f"{i}. {eq['nome']} - {eq['categoria']} - {eq['potencia']}W {origem}")


def selecionar_equipamento():
    print("\n==== EQUIPAMENTOS CADASTRADOS ====")
    listar_equipamentos()
    if not dados["equipamentos"]:
        return None
    return ler(
        "\nEscolha o equipamento pelo numero...: ",
        lambda t: t in dados["equipamentos"],
        "ERRO: Numero invalido.",
    )


def cadastro_equipamento():
    print("==== CADASTRO DE EQUIPAMENTO ====\n")
    catalogo = {i: eq for i, eq in dados["equipamentos"].items() if eq.get("pre_cadastrado")}
    for i, eq in catalogo.items():
        print(f"{i}. {eq['nome']} ({eq['categoria']}) - {eq['potencia']}W")
    print("0. Cadastrar um equipamento novo do zero")
    escolha = ler("\nESCOLHA UM NUMERO...: ", lambda t: t == "0" or t in catalogo, "ERRO: Opcao invalida.")
    base = catalogo.get(escolha, {"nome": "", "categoria": "", "potencia": ""})
    dica = " (ENTER mantem o valor entre colchetes)" if escolha != "0" else ""

    novo = {
        "nome": ler(f"\nNOME [{base['nome']}]{dica}...: ", padrao=base["nome"]),
        "categoria": ler(f"\nCATEGORIA [{base['categoria']}]...: ", padrao=base["categoria"]),
        "potencia": float(
            ler(
                f"\nPOTENCIA EM WATTS [{base['potencia']}]...: ",
                validar_numero_positivo,
                "ERRO: Digite um numero maior que zero.",
                padrao=base["potencia"],
            )
        ),
        "pre_cadastrado": False,
    }
    dados["equipamentos"][proximo_id("equipamento")] = novo
    salvar_dados()
    concluir("==== EQUIPAMENTO CADASTRADO COM SUCESSO ====")


def modificar_equipamento():
    print("==== MODIFICACAO DE EQUIPAMENTO ====")
    id_eq = selecionar_equipamento()
    if id_eq is None:
        return concluir()
    eq = dados["equipamentos"][id_eq]
    print(f"\nATUAL: {eq['nome']} - {eq['categoria']} - {eq['potencia']}W")
    print("1. Nome  2. Categoria  3. Potencia")
    opcao = ler_opcao_inteira(1, 3)
    if opcao == 3:
        eq["potencia"] = float(
            ler("\nNOVA POTENCIA (W)...: ", validar_numero_positivo, "ERRO: Digite um numero maior que zero.")
        )
    else:
        eq["nome" if opcao == 1 else "categoria"] = ler("\nNOVO VALOR...: ")
    salvar_dados()
    concluir("EQUIPAMENTO ATUALIZADO COM SUCESSO...")


def excluir_equipamento():
    print("==== EXCLUSAO DE EQUIPAMENTO ====")
    id_eq = selecionar_equipamento()
    if id_eq is None:
        return concluir()
    em_uso = [i for i, a in dados["associacoes"].items() if a["equipamento_id"] == id_eq]
    if em_uso and not confirmar(
        f"AVISO: equipamento associado a {len(em_uso)} imovel(is). Excluir remove essas associacoes."
    ):
        return concluir("EXCLUSAO CANCELADA.")
    for i in em_uso:
        del dados["associacoes"][i]
    del dados["equipamentos"][id_eq]
    salvar_dados()
    concluir("==== EQUIPAMENTO EXCLUIDO COM SUCESSO ====")


def ler_quantidade():
    return int(
        ler(
            "\nQUANTIDADE deste equipamento no imovel...: ",
            validar_inteiro_positivo,
            "ERRO: Digite um numero inteiro maior que zero.",
        )
    )


def ler_tempo_uso():
    return float(
        ler(
            "\nTEMPO DE USO DIARIO em horas (0 a 24)...: ",
            validar_intervalo_horas,
            "ERRO: Digite um valor numerico entre 0 e 24.",
        ).replace(",", ".")
    )


def associar_equipamento():
    print("==== ASSOCIAR EQUIPAMENTO A UM IMOVEL ====")
    id_imovel = selecionar_imovel_do_usuario()
    id_eq = selecionar_equipamento() if id_imovel else None
    if id_eq is None:
        return concluir()
    dados["associacoes"][proximo_id("associacao")] = {
        "imovel_id": id_imovel,
        "equipamento_id": id_eq,
        "quantidade": ler_quantidade(),
        "tempo_uso": ler_tempo_uso(),
    }
    salvar_dados()
    concluir("==== EQUIPAMENTO ASSOCIADO COM SUCESSO ====")


def listar_associacoes_do_imovel(id_imovel):
    return {i: a for i, a in dados["associacoes"].items() if a["imovel_id"] == id_imovel}


def selecionar_associacao():
    id_imovel = selecionar_imovel_do_usuario()
    if id_imovel is None:
        return None
    associacoes = listar_associacoes_do_imovel(id_imovel)
    if not associacoes:
        print("\nNENHUM EQUIPAMENTO ASSOCIADO A ESTE IMOVEL AINDA.")
        return None
    for i, a in associacoes.items():
        print(
            f"{i}. {dados['equipamentos'][a['equipamento_id']]['nome']} - "
            f"qtd: {a['quantidade']} - {a['tempo_uso']}h/dia"
        )
    return ler("\nESCOLHA O NUMERO DA ASSOCIACAO...: ", lambda t: t in associacoes, "ERRO: Numero invalido.")


def editar_associacao():
    print("==== EDITAR ASSOCIACAO ====")
    id_assoc = selecionar_associacao()
    if id_assoc is None:
        return concluir()
    print("\n1. Quantidade  2. Tempo de uso")
    if ler_opcao_inteira(1, 2) == 1:
        dados["associacoes"][id_assoc]["quantidade"] = ler_quantidade()
    else:
        dados["associacoes"][id_assoc]["tempo_uso"] = ler_tempo_uso()
    salvar_dados()
    concluir("ASSOCIACAO ATUALIZADA COM SUCESSO...")


def remover_associacao():
    print("==== REMOVER EQUIPAMENTO DO IMOVEL ====")
    id_assoc = selecionar_associacao()
    if id_assoc is None:
        return concluir()
    if not confirmar("CONFIRMA A REMOCAO?"):
        return concluir("REMOCAO CANCELADA.")
    del dados["associacoes"][id_assoc]
    salvar_dados()
    concluir("==== ASSOCIACAO REMOVIDA COM SUCESSO ====")


# ==================================================================
# CONSUMO, POTENCIA INSTALADA DA RESIDENCIA E RANKING (PB02)
# ==================================================================

def calcular_consumo_associacao(assoc):
    """Potencia (W) * quantidade * horas/dia * 30 / 1000 = kWh/mes. Dado faltando -> 0."""
    eq = dados["equipamentos"].get(assoc.get("equipamento_id"))
    try:
        return eq["potencia"] * assoc["quantidade"] * assoc["tempo_uso"] * 30 / 1000
    except (TypeError, KeyError):
        return 0.0


def consumo_total_imovel(id_imovel):
    """PB02 - Consumo mensal total da residencia em kWh/mes."""
    return sum(calcular_consumo_associacao(a) for a in listar_associacoes_do_imovel(id_imovel).values())


def consumo_diario_imovel(id_imovel):
    """PB02 - Consumo medio diario da residencia: E_dia = E_mes / 30 [kWh/dia]."""
    return consumo_total_imovel(id_imovel) / 30.0


def potencia_instalada_imovel(id_imovel):
    """PB02 - Potencia eletrica instalada total das cargas da residencia em Watts (W)."""
    total_w = 0.0
    for a in listar_associacoes_do_imovel(id_imovel).values():
        eq = dados["equipamentos"].get(a.get("equipamento_id"))
        if eq and isinstance(eq.get("potencia"), (int, float)) and isinstance(a.get("quantidade"), (int, float)):
            total_w += float(eq["potencia"]) * float(a["quantidade"])
    return total_w


def ranking_consumo_imovel(id_imovel):
    """Do maior para o menor consumo mensal."""
    itens = [
        (dados["equipamentos"][a["equipamento_id"]]["nome"], calcular_consumo_associacao(a))
        for a in listar_associacoes_do_imovel(id_imovel).values()
    ]
    return sorted(itens, key=lambda item: item[1], reverse=True)


def exibir_relatorio(tipo):
    """Exibe resumo da demanda energetica (PB02), ranking ou grafico ASCII."""
    id_imovel = selecionar_imovel_do_usuario()
    if id_imovel is None:
        return concluir()
    imovel = dados["imoveis"][id_imovel]
    ranking = ranking_consumo_imovel(id_imovel)
    e_mes = consumo_total_imovel(id_imovel)
    e_dia = consumo_diario_imovel(id_imovel)
    p_inst_w = potencia_instalada_imovel(id_imovel)

    if tipo == "resumo":
        print(f"\n==== RESUMO DA DEMANDA ENERGETICA (PB02) - {imovel['apelido']} ====")
        print(f"Endereco: {imovel['endereco']}, {imovel['numero']} | Tipo: {imovel['tipo']}")
        print(f"Quantidade de tipos de equipamentos: {len(ranking)}")
        print(f"Potencia instalada da residencia: {p_inst_w:.0f} W ({p_inst_w/1000:.3f} kW)")
        print(f"Consumo mensal estimado (E_mes): {e_mes:.2f} kWh/mes")
        print(f"Consumo medio diario (E_dia = E_mes / 30): {e_dia:.2f} kWh/dia\n")
    if not ranking:
        return concluir("ESTE IMOVEL NAO TEM EQUIPAMENTOS ASSOCIADOS.")

    maior = ranking[0][1] or 1
    for posicao, (nome, consumo) in enumerate(ranking, start=1):
        if tipo == "grafico":
            print(f"{nome:<25} {'#' * int(consumo / maior * 40)} {consumo:.2f} kWh/mes")
        elif tipo == "ranking":
            print(f"{posicao}o {nome} - {consumo:.2f} kWh/mes")
        else:
            print(f"  - {nome}: {consumo:.2f} kWh/mes")
    concluir()


# ==================================================================
# TELAS DA PARTE SOLAR - SPRINT 3 COMPLETA (PB01 a PB21)
# ==================================================================

def exibir_catalogo_datasets_fv(ds=None):
    """PB05 / PB07 / PB12 - Exibe os datasets estruturados de modulos, inversores, baterias e HSP."""
    if ds is None:
        ds = fv.carregar_datasets_fv()
    print("\n==== [PB05] DATASET DE MODULOS FOTOVOLTAICOS (modulos.csv) ====")
    for m in ds["modulos"]:
        print(
            f"  [{m['id']}] {m['fabricante']} {m['modelo']} | {m['potencia_wp']:.0f} Wp | "
            f"Voc {m['voc_v']}V | Vmp {m['vmp_v']}V | Imp {m['imp_a']}A | Efic. {m['eficiencia_pct']}% | {fv.brl(m['preco_brl'])}"
        )
    print("\n==== [PB07] DATASET DE INVERSORES (inversores.csv) ====")
    for inv in ds["inversores"]:
        print(
            f"  [{inv['id']}] {inv['fabricante']} {inv['modelo']} ({inv['tipo']}) | Nom: {inv['potencia_nominal_w']:.0f} W | "
            f"Max FV: {inv['potencia_max_fv_w']:.0f} W | MPPT: {inv['faixa_mppt_min_v']:.0f}-{inv['faixa_mppt_max_v']:.0f}V | "
            f"Efic: {inv['eficiencia_pct']}% | Bat: {'SIM' if inv['compativel_bateria'] else 'NAO'} | {fv.brl(inv['preco_brl'])}"
        )
    print("\n==== [PB12] DATASET DE BATERIAS (baterias.csv) ====")
    for b in ds["baterias"]:
        print(
            f"  [{b['id']}] {b['fabricante']} {b['modelo']} ({b['tecnologia']}) | {b['tensao_nominal_v']} V | "
            f"{b['capacidade_ah']:.0f} Ah | {b['capacidade_kwh']} kWh | DoD {b['dod_pct']:.0f}% | {b['ciclos']:.0f} ciclos | {fv.brl(b['preco_brl'])}"
        )


def salvar_dimensionamento_no_banco(id_imovel, r, loc, hsp_info):
    """PB20 - Salva configuracao completa, equipamentos, orcamento, economia e payback."""
    arm, sel, orc, econ, pay = (
        r["armazenamento"],
        r["selecao"],
        r["orcamento"],
        r["economia"],
        r["payback"],
    )
    id_dim = proximo_id("dimensionamento")
    dados["dimensionamentos"][id_dim] = {
        "imovel_id": id_imovel,
        "data": r["data"],
        "consumo_kwh_mes": round(r["consumo"], 2),
        "consumo_kwh_dia": round(r["consumo_diario"], 3),
        "potencia_residencia_w": round(r["potencia_residencia_w"], 1),
        "percentual": r["percentual"],
        "localidade": f"{loc['cidade']}/{loc['uf']}",
        "hsp": hsp_info["hsp"],
        "fonte_hsp": hsp_info["fonte"],
        "pr": r["pr"],
        "potencia_calculada_kwp": round(r["p_fv"], 3),
        "potencia_instalada_kwp": round(r["p_inst"], 3),
        "geracao_dia_kwh": round(r["geracao_dia"], 2),
        "geracao_mes_kwh": round(r["geracao_mes"], 2),
        "atendimento_pct": r["comparacao_geracao"]["atendimento_pct"],
        "energia_compensada_kwh_mes": econ["energia_compensada_kwh_mes"],
        "energia_excedente_kwh_mes": econ["energia_excedente_kwh_mes"],
        "modulo_id": sel["modulo"]["id"],
        "n_modulos": sel["config"]["n_modulos"],
        "inversor_id": sel["inversor"]["id"],
        "bateria_id": arm["bateria"]["id"] if arm["ativo"] else None,
        "n_baterias": arm["n_baterias"],
        "autonomia_h": arm["autonomia_h"],
        "capacidade_instalada_kwh": arm["capacidade_instalada_kwh"],
        "c_equipamentos": orc["c_equipamentos"],
        "c_outros": orc["c_outros"],
        "c_total": orc["c_total"],
        "tarifa_brl_kwh": econ["tarifa_brl_kwh"],
        "economia_mensal_brl": econ["economia_mensal_brl"],
        "economia_anual_brl": econ["economia_anual_brl"],
        "payback_simples_anos": pay["payback_simples_anos"],
    }
    salvar_dados()
    return id_dim


def novo_dimensionamento_fv():
    print("==== DIMENSIONAMENTO FOTOVOLTAICO COMPLETO (SPRINT 3 - PB01 A PB21) ====")
    id_imovel = selecionar_imovel_do_usuario()  # PB01
    if id_imovel is None:
        return concluir()
    imovel = dados["imoveis"][id_imovel]
    try:
        ds = fv.carregar_datasets_fv()
    except FileNotFoundError as erro:
        return concluir(f"ERRO: {erro}")

    # PB02 - Exibe demanda energetica recuperada da residencia
    calculado = consumo_total_imovel(id_imovel)
    pot_casa_w = potencia_instalada_imovel(id_imovel)
    print(f"\n[PB02] Demanda Energetica Recuperada de '{imovel['apelido']}':")
    print(f"  - Potencia instalada da residencia: {fv.num(pot_casa_w, 0)} W ({fv.num(pot_casa_w/1000, 3)} kW)")
    print(f"  - Consumo mensal calculado (E_mes): {fv.num(calculado)} kWh/mes")
    print(f"  - Consumo medio diario (E_dia = E_mes / 30): {fv.num(calculado/30, 3)} kWh/dia")

    # PB03 - Localizacao, HSP e PR
    if not imovel.get("localizacao") or ler_sim_nao(
        f"\nLocalizacao atual: {imovel['localizacao']['cidade']}/{imovel['localizacao']['uf']}. Alterar? (S/N) [N]...: ",
        padrao="N",
    ):
        imovel["localizacao"] = ler_localizacao()
        salvar_dados()
    loc = imovel["localizacao"]
    try:
        hsp_info = fv.obter_hsp(loc["cidade"], loc["uf"], ds["hsp"])
    except ValueError:
        print(f"\nNao ha HSP cadastrado para {loc['cidade']}/{loc['uf']}. Consulte o CRESESB SunData.")
        hsp = ler_validado("HSP do municipio (kWh/m2/dia)...: ", fv.validar_hsp)
        fonte = ler("Origem do valor (ex.: CRESESB SunData - Osasco/SP)...: ")
        hsp_info = fv.obter_hsp(loc["cidade"], loc["uf"], ds["hsp"], hsp, fonte)

    pr_padrao = fv.PARAMETROS_FV["eta_global"]
    print(f"\n[PB03] Recurso Solar: HSP = {fv.num(hsp_info['hsp'])} kWh/m2/dia ({hsp_info['fonte']})")
    print(f"       PR adotado por padrao: {fv.num(pr_padrao*100, 0)}% ({fv.PARAMETROS_FV['justificativa_pr']})")
    pr_escolhido = ler_validado(
        f"Performance Ratio PR (ENTER mantem {pr_padrao})...: ",
        fv.validar_pr,
        padrao=pr_padrao,
    )

    if calculado > 0 and ler_sim_nao(
        "\nUsar o consumo calculado pelos equipamentos do imovel? (S/N) [S]...: ", padrao="S"
    ):
        consumo, origem = calculado, "calculado pelos equipamentos do imovel"
    else:
        consumo = ler_validado("Consumo medio mensal da conta (kWh/mes)...: ", lambda t: fv.positivo("Consumo", t))
        origem = "media da conta de luz"

    percentual = ler_validado(
        "\nPERCENTUAL DO CONSUMO A ATENDER (1 a 100) [100]...: ",
        lambda t: fv.validar_percentual(t) * 100,
        padrao="100",
    )

    # PB05 / PB07 - Opcao de selecao automatica otimizada ou escolha manual nos datasets
    modulo_id, inversor_id, bateria_id = None, None, None
    if ler_sim_nao("\nDeseja escolher manualmente o modulo/inversor nos datasets? (N = selecao otima automatica) [N]...: ", padrao="N"):
        exibir_catalogo_datasets_fv(ds)
        ids_mod = {m["id"] for m in ds["modulos"]}
        ids_inv = {i["id"] for i in ds["inversores"]}
        m_in = ler("ID do modulo (ex.: FV010 ou ENTER para automatico)...: ", lambda t: t == "" or t.upper() in ids_mod, "ERRO: ID de modulo inexistente.", padrao="")
        i_in = ler("ID do inversor (ex.: INV001 ou ENTER para automatico)...: ", lambda t: t == "" or t.upper() in ids_inv, "ERRO: ID de inversor inexistente.", padrao="")
        modulo_id = m_in.upper() if m_in else None
        inversor_id = i_in.upper() if i_in else None

    # PB10 / PB11 / PB12 - Opcao sem ou com baterias
    com_bateria = ler_sim_nao("\nDESEJA INCLUIR BATERIAS NESTA PROPOSTA? (S/N) [N]...: ", padrao="N")
    autonomia = None
    if com_bateria:
        autonomia = ler_validado(
            "AUTONOMIA DESEJADA (horas, ate 72) [12]...: ",
            fv.validar_autonomia,
            padrao="12",
        )
        if modulo_id or inversor_id:
            ids_bat = {b["id"] for b in ds["baterias"]}
            b_in = ler("ID da bateria (ex.: BAT004 ou ENTER para automatica)...: ", lambda t: t == "" or t.upper() in ids_bat, "ERRO: ID de bateria inexistente.", padrao="")
            bateria_id = b_in.upper() if b_in else None

    # PB15 - Tarifa de energia para analise economica e payback
    tarifa_padrao = fv.PARAMETROS_FV["tarifa_padrao_brl_kwh"]
    tarifa_kwh = ler_validado(
        f"\nTARIFA DE ENERGIA DA CONCESSIONARIA em R$/kWh [padrao {tarifa_padrao}]...: ",
        fv.validar_tarifa,
        padrao=tarifa_padrao,
    )

    try:
        r = fv.dimensionar_fv(
            consumo,
            percentual,
            hsp_info,
            ds,
            com_bateria=com_bateria,
            autonomia=autonomia,
            origem=origem,
            tarifa_kwh=tarifa_kwh,
            pr=pr_escolhido,
            potencia_residencia_w=pot_casa_w,
            modulo_id=modulo_id,
            inversor_id=inversor_id,
            bateria_id=bateria_id,
        )
        comp = fv.comparar_cenarios(
            consumo,
            percentual,
            hsp_info,
            ds,
            autonomia_h=autonomia or 12,
            tarifa_kwh=tarifa_kwh,
            pr=pr_escolhido,
            potencia_residencia_w=pot_casa_w,
            origem=origem,
        )
    except fv.ErroDimensionamento as erro:
        return concluir(f"NAO FOI POSSIVEL MONTAR A SOLUCAO: {erro}\n{fv.formatar_incompatibilidades(erro.rejeitados)}")
    except ValueError as erro:
        return concluir(f"ERRO NOS DADOS DE ENTRADA: {erro}")

    limpar_terminal()
    print(fv.formatar_proposta(r, imovel["apelido"]))
    print("\n" + fv.formatar_comparacao_cenarios(comp, imovel["apelido"]))

    if ler_sim_nao("\nVer combinacoes bloqueadas por incompatibilidade tecnica (C1-C8)? (S/N) [N]...: ", padrao="N"):
        print(fv.formatar_incompatibilidades(r["rejeitados"]))

    id_dim = salvar_dimensionamento_no_banco(id_imovel, r, loc, hsp_info)
    arq_txt = fv.exportar_proposta_txt(r, comp, imovel["apelido"])
    arq_html = fv.exportar_proposta_html(
        r, comp, imovel["apelido"], cargas_residencia=obter_cargas_detalhadas_imovel(id_imovel)
    )
    abrir_proposta_no_navegador(arq_html)
    concluir(
        f"DIMENSIONAMENTO #{id_dim} SALVO EM dados_sistema.json!\n"
        f"Proposta consolidada exportada e aberta no navegador (PB21):\n"
        f"  - Relatorio TXT:  {arq_txt}\n"
        f"  - Proposta HTML:  {arq_html}"
    )


def tela_comparar_cenarios_fv():
    """PB14 + Secao 9 - Compara diretamente os cenarios Sem Baterias e Com Baterias."""
    print("==== COMPARACAO DE CENARIOS: SEM BATERIAS vs COM BATERIAS (PB14 / SECAO 9) ====")
    id_imovel = selecionar_imovel_do_usuario()
    if id_imovel is None:
        return concluir()
    imovel = dados["imoveis"][id_imovel]
    ds = fv.carregar_datasets_fv()
    loc = imovel.get("localizacao") or {"cidade": "São Paulo", "uf": "SP"}
    hsp_info = fv.obter_hsp(loc["cidade"], loc["uf"], ds["hsp"])
    consumo = consumo_total_imovel(id_imovel) or 455.31
    pot_casa_w = potencia_instalada_imovel(id_imovel)
    autonomia = ler_validado("Autonomia desejada para o cenario com baterias (horas, ate 72) [12]...: ", fv.validar_autonomia, padrao="12")
    tarifa = ler_validado("Tarifa de energia em R$/kWh [0.92]...: ", fv.validar_tarifa, padrao="0.92")

    comp = fv.comparar_cenarios(
        consumo,
        100,
        hsp_info,
        ds,
        autonomia_h=autonomia,
        tarifa_kwh=tarifa,
        potencia_residencia_w=pot_casa_w,
    )
    limpar_terminal()
    print(fv.formatar_comparacao_cenarios(comp, imovel["apelido"]))
    arq_html = fv.exportar_proposta_html(
        comp["sem_bateria"], comp, imovel["apelido"], cargas_residencia=obter_cargas_detalhadas_imovel(id_imovel)
    )
    abrir_proposta_no_navegador(arq_html)
    concluir(f"Quadro comparativo e analise da Secao 9 atualizados e abertos no navegador: {arq_html}")


def listar_dimensionamentos_fv():
    """PB20 - Recupera os dimensionamentos salvos do imovel."""
    print("==== DIMENSIONAMENTOS SALVOS (PB20) ====")
    id_imovel = selecionar_imovel_do_usuario()
    if id_imovel is None:
        return concluir()
    salvos = {i: d for i, d in dados["dimensionamentos"].items() if d["imovel_id"] == id_imovel}
    if not salvos:
        print("\nNenhum dimensionamento salvo para este imovel.")
    for i, d in salvos.items():
        bat = f"{d['n_baterias']}x {d['bateria_id']} ({d.get('autonomia_h', 0)}h)" if d.get("bateria_id") else "sem baterias"
        econ_m = d.get("economia_mensal_brl", 0.0)
        pay_a = d.get("payback_simples_anos", 0.0)
        print(
            f"\n#{i} {d['data']} | {fv.num(d['consumo_kwh_mes'])} kWh/mes x {fv.num(d['percentual'], 0)}% | "
            f"HSP {fv.num(d['hsp'])} | {fv.num(d['potencia_instalada_kwp'])} kWp ({d['n_modulos']}x {d['modulo_id']}) | "
            f"{d['inversor_id']} | {bat} | Total: {fv.brl(d['c_total'])} | "
            f"Economia: {fv.brl(econ_m)}/mes | Payback simples: {fv.num(pay_a)} anos"
        )
    concluir()


def obter_cargas_detalhadas_imovel(id_imovel):
    """Retorna lista estruturada dos equipamentos associados ao imovel (PB01/PB02)."""
    itens = []
    for a in listar_associacoes_do_imovel(id_imovel).values():
        eq = dados["equipamentos"].get(a.get("equipamento_id"))
        if eq:
            itens.append({
                "nome": eq["nome"],
                "categoria": eq["categoria"],
                "potencia_w": float(eq["potencia"]),
                "qtd": int(a["quantidade"]),
                "horas_dia": float(a["tempo_uso"]),
                "kwh_mes": round(calcular_consumo_associacao(a), 2),
            })
    return sorted(itens, key=lambda x: x["kwh_mes"], reverse=True)


def abrir_proposta_no_navegador(caminho_html):
    """Abre automaticamente a proposta HTML consolidada no navegador padrao."""
    import webbrowser
    try:
        caminho_abs = os.path.abspath(caminho_html)
        webbrowser.open(f"file:///{caminho_abs.replace(os.sep, '/')}")
        return True
    except Exception:
        return False


def tela_validar_datasets():
    try:
        ds = fv.carregar_datasets_fv()
        exibir_catalogo_datasets_fv(ds)
        print("\n" + fv.validar_datasets_fv()[1])
    except FileNotFoundError as erro:
        print(f"ERRO: {erro}")
    concluir()


def executar_demonstracao_sprint_review(pausar_no_final=True, abrir_navegador=False):
    """
    Secao 7 (Sprint Review - 15 etapas obrigatorias) + Secao 9 (Questao Final):
    Executa de ponta a ponta o caso completo usando a residencia ja cadastrada no sistema,
    apresenta os 15 itens da Sprint Review, salva no banco JSON, exporta os relatorios
    e abre automaticamente o navegador quando solicitado.
    """
    carregar_dados()
    ds = fv.carregar_datasets_fv()
    id_imovel = next(iter(dados["imoveis"].keys()))
    imovel = dados["imoveis"][id_imovel]
    loc = imovel["localizacao"]
    hsp_info = fv.obter_hsp(loc["cidade"], loc["uf"], ds["hsp"])
    consumo_mes = consumo_total_imovel(id_imovel)
    consumo_dia = consumo_diario_imovel(id_imovel)
    pot_casa_w = potencia_instalada_imovel(id_imovel)
    cargas_det = obter_cargas_detalhadas_imovel(id_imovel)

    comp = fv.comparar_cenarios(
        consumo_mes,
        100,
        hsp_info,
        ds,
        autonomia_h=12,
        tarifa_kwh=0.92,
        potencia_residencia_w=pot_casa_w,
        origem="calculado pelos equipamentos cadastrados na residencia",
    )
    sem_bat = comp["sem_bateria"]
    com_bat = comp["com_bateria"]

    # Salva os dois cenarios no banco caso ainda nao estejam salvos
    if not dados["dimensionamentos"]:
        salvar_dimensionamento_no_banco(id_imovel, sem_bat, loc, hsp_info)
        salvar_dimensionamento_no_banco(id_imovel, com_bat, loc, hsp_info)

    arq_txt = fv.exportar_proposta_txt(sem_bat, comp, imovel["apelido"])
    arq_html = fv.exportar_proposta_html(
        sem_bat, comp, imovel["apelido"], cargas_residencia=cargas_det
    )

    mod_a, inv_a, cfg_a = sem_bat["selecao"]["modulo"], sem_bat["selecao"]["inversor"], sem_bat["selecao"]["config"]
    inv_b, arm_b = com_bat["selecao"]["inversor"], com_bat["armazenamento"]
    bat_b = arm_b["bateria"]

    print("=" * 88)
    print("  ROTEIRO DE DEMONSTRACAO AO VIVO - SPRINT REVIEW (15 ETAPAS + QUESTAO 9)")
    print("  Equipe Lumos: Pietro Lorande (RM569125) | Luiz Otavio (RM569977) | Maria Eduarda (RM574094)")
    print("=" * 88)
    print(f"  [ETAPA 01] Selecao da Residencia (PB01): #{id_imovel} {imovel['apelido']} ({imovel['endereco']}, {imovel['numero']} - {loc['cidade']}/{loc['uf']})")
    print(f"  [ETAPA 02] Equipamentos e Consumo (PB02): {len(cargas_det)} tipos ({sum(c['qtd'] for c in cargas_det)} un.) | Pot. Casa: {fv.num(pot_casa_w, 0)} W ({fv.num(pot_casa_w/1000, 3)} kW) | E_mes = {fv.num(consumo_mes)} kWh/mes | E_dia = {fv.num(consumo_dia, 2)} kWh/dia")
    for pos, c_it in enumerate(cargas_det, 1):
        print(f"             {pos}. {c_it['nome']} ({c_it['qtd']}x {c_it['potencia_w']:.0f}W, {c_it['horas_dia']}h/dia) -> {fv.num(c_it['kwh_mes'])} kWh/mes")
    print(f"  [ETAPA 03] Dimensionamento FV (PB04): P_FV = E_dia / (HSP * PR) = {fv.num(consumo_dia, 3)} / ({fv.num(hsp_info['hsp'])} * {fv.num(sem_bat['pr'])}) = {fv.num(sem_bat['p_fv'], 3)} kWp")
    print(f"  [ETAPA 04] HSP e PR Utilizados (PB03): HSP = {fv.num(hsp_info['hsp'])} kWh/m2/dia ({hsp_info['fonte']}) | PR = {fv.num(sem_bat['pr']*100, 0)}% (NT EPE DEA-SEE 009/2023)")
    print(f"  [ETAPA 05] Consulta aos Datasets (PB05/PB07/PB12): {len(ds['modulos'])} modulos (modulos.csv), {len(ds['inversores'])} inversores (inversores.csv), {len(ds['baterias'])} baterias (baterias.csv)")
    print(f"  [ETAPA 06] Selecao dos Modulos (PB06): {cfg_a['n_modulos']}x [{mod_a['id']}] {mod_a['fabricante']} {mod_a['modelo']} ({mod_a['potencia_wp']:.0f} Wp) -> P_inst = {fv.num(sem_bat['p_inst'], 3)} kWp")
    print(f"  [ETAPA 07] Inversor e Compatibilidade (PB07): On-Grid [{inv_a['id']}] {inv_a['fabricante']} {inv_a['modelo']} (R_DC/AC = {fv.num(cfg_a['ratio_dc_ac'])}) | Hibrido [{inv_b['id']}] {inv_b['fabricante']} {inv_b['modelo']}")
    print(f"  [ETAPA 08] Geracao Estimada (PB08): E_gerada,dia = {fv.num(sem_bat['geracao_dia'], 2)} kWh/dia | E_gerada,mes = {fv.num(sem_bat['geracao_mes'], 2)} kWh/mes")
    print(f"  [ETAPA 09] Comparacao Geracao x Consumo (PB09): Atendimento = {fv.num(sem_bat['comparacao_geracao']['atendimento_pct'], 2)}% | Compensada = {fv.num(sem_bat['comparacao_geracao']['energia_compensada_kwh_mes'])} kWh/mes | Excedente = {fv.num(sem_bat['comparacao_geracao']['energia_excedente_kwh_mes'])} kWh/mes")
    print(f"  [ETAPA 10] Opcao Sem Baterias (PB10): Sistema On-Grid convencional (0 kWh armazenados, custo de baterias R$ 0,00)")
    print(f"  [ETAPA 11] Opcao Com Baterias e Autonomia (PB11): Autonomia {arm_b['autonomia_h']:.0f}h (E_aut = {fv.num(arm_b['energia_autonomia_kwh'], 2)} kWh, C_bat = {fv.num(arm_b['c_bat_kwh'], 2)} kWh) -> {arm_b['n_baterias']}x [{bat_b['id']}] {bat_b['fabricante']} {bat_b['modelo']} ({fv.num(arm_b['capacidade_instalada_kwh'])} kWh nominais / {fv.num(arm_b['capacidade_util_kwh'])} kWh uteis)")
    print(f"  [ETAPA 12] Orcamento Automatico (PB13): Sem Baterias = {fv.brl(sem_bat['orcamento']['c_equipamentos'])} (equip.) / {fv.brl(sem_bat['orcamento']['c_total'])} (total) | Com Baterias = {fv.brl(com_bat['orcamento']['c_equipamentos'])} (equip.) / {fv.brl(com_bat['orcamento']['c_total'])} (total)")
    print(f"  [ETAPA 13] Comparacao dos Cenarios (PB14): Diferenca de +{fv.brl(comp['diferenca_investimento_total_brl'])} (+{fv.num(comp['acrescimo_percentual'], 1)}%) no sistema com baterias")
    print(f"  [ETAPA 14] Economia e Payback Simples (PB15/PB16): Economia = {fv.brl(sem_bat['economia']['economia_mensal_brl'])}/mes ({fv.brl(sem_bat['economia']['economia_anual_brl'])}/ano) | Payback Total: {fv.num(sem_bat['payback']['payback_simples_anos'])} anos (Sem Bat.) vs {fv.num(com_bat['payback']['payback_simples_anos'])} anos (Com Bat.)")
    print(f"  [ETAPA 15] Proposta Final ao Cliente (PB17/PB21): Exportada em '{ os.path.basename(arq_txt) }' e '{ os.path.basename(arq_html) }'")

    print("\n" + fv.formatar_proposta(sem_bat, f"{imovel['apelido']} [CENARIO 1: SEM BATERIAS]"))
    print("\n" + fv.formatar_proposta(com_bat, f"{imovel['apelido']} [CENARIO 2: COM BATERIAS - 12h AUTONOMIA]"))
    print("\n" + fv.formatar_comparacao_cenarios(comp, imovel["apelido"]))
    print(f"\n[ARQUIVOS EXPORTADOS (PB21)]:\n  - {arq_txt}\n  - {arq_html}")

    if abrir_navegador:
        abrir_proposta_no_navegador(arq_html)

    if pausar_no_final:
        concluir()
    return comp


# ==================================================================
# MENUS INTEGRADOS (PB19)
# ==================================================================

def menu_residencia():
    executar_menu("SISTEMA DE DIMENSIONAMENTO ENERGETICO RESIDENCIAL (SPRINT 3)", [
        ("CADASTRO DE IMOVEL", cadastro_imovel),
        ("MODIFICAR INFORMACOES DO IMOVEL", modificar_imovel),
        ("EXCLUIR IMOVEL", excluir_imovel),
        ("ADICIONAR/GERENCIAR EQUIPAMENTOS DA RESIDENCIA", lambda: executar_menu("EQUIPAMENTOS", [
            ("Cadastrar equipamento", cadastro_equipamento),
            ("Listar equipamentos", lambda: (listar_equipamentos(), concluir())),
            ("Editar equipamento", modificar_equipamento),
            ("Excluir equipamento", excluir_equipamento),
            ("Associar equipamento a um imovel", associar_equipamento),
            ("Editar associacao (quantidade/tempo de uso)", editar_associacao),
            ("Remover associacao", remover_associacao),
        ])),
        ("DEMANDA ENERGETICA E CONSUMO DO IMOVEL (PB02)", lambda: executar_menu("DEMANDA DO IMOVEL", [
            ("Resumo da demanda (E_mes, E_dia e Potencia Instalada)", lambda: exibir_relatorio("resumo")),
            ("Ranking de consumo por equipamento", lambda: exibir_relatorio("ranking")),
            ("Grafico de distribuicao do consumo", lambda: exibir_relatorio("grafico")),
        ])),
        ("ENERGIA SOLAR FOTOVOLTAICA, ORCAMENTO E PAYBACK (PB01 A PB21)", lambda: executar_menu("ENERGIA SOLAR FOTOVOLTAICA - SPRINT 3", [
            ("Novo dimensionamento / proposta consolidada (PB01 a PB21)", novo_dimensionamento_fv),
            ("Comparar cenarios: Sem Baterias vs Com Baterias (PB14 + Questao 9)", tela_comparar_cenarios_fv),
            ("Executar Demonstracao Completa da Sprint Review (15 itens + Abrir HTML)", lambda: executar_demonstracao_sprint_review(True, abrir_navegador=True)),
            ("Ver dimensionamentos salvos de um imovel (PB20)", listar_dimensionamentos_fv),
            ("Consultar e validar datasets de modulos, inversores e baterias (PB05/PB07/PB12)", tela_validar_datasets),
        ])),
    ])


def iniciar_user():
    while True:
        print(" ==== SISTEMA DE DIMENSIONAMENTO ENERGETICO RESIDENCIAL - EQUIPE LUMOS ==== \n")
        print("1. CADASTRO DE CONTA")
        print("2. LOG IN (Conta pronta p/ Sprint Review: demo@lumos.com / senha: 1234)")
        print("3. EXECUTAR DEMONSTRACAO COMPLETA DA SPRINT REVIEW (15 ITENS + ABRIR NAVEGADOR)")
        print("4. RODAR TESTES AUTOMATIZADOS (QA - CP1 + CP2 + CP3)")
        print("5. SAIR DO SISTEMA")
        opcao = ler_opcao_inteira(1, 5)
        limpar_terminal()
        if opcao == 1:
            cadastro_user()
        elif opcao == 2:
            if login():
                menu_residencia()
                sessao["email_logado"] = None
            else:
                concluir()
        elif opcao == 3:
            executar_demonstracao_sprint_review(True, abrir_navegador=True)
        elif opcao == 4:
            import testes
            testes.rodar_todos_os_testes()
            concluir()
        else:
            print("Ate a proxima!")
            break


if __name__ == "__main__":
    carregar_dados()
    if "--demo" in sys.argv:
        abrir = "--abrir-html" in sys.argv
        executar_demonstracao_sprint_review(pausar_no_final=False, abrir_navegador=abrir)
    elif "--apresentacao" in sys.argv:
        import testes
        testes.rodar_todos_os_testes()
        print("\n")
        executar_demonstracao_sprint_review(pausar_no_final=False, abrir_navegador=True)
        print("\n" + "=" * 88)
        print("  NAVEGADOR ABERTO COM A PROPOSTA INTERATIVA (proposta_cliente.html)!")
        print("  SESSAO INICIADA AUTOMATICAMENTE COMO: demo@lumos.com (Residencia Familia Silva - SP)")
        print("=" * 88 + "\n")
        sessao["email_logado"] = "demo@lumos.com"
        menu_residencia()
    else:
        iniciar_user()

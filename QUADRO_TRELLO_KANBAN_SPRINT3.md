# Quadro Trello / Kanban Finalizado — Sprint 3 (Product Backlog PB01 a PB21)

- **Disciplina:** Soluções em Energias Renováveis e Sustentáveis — Prof. Álvaro Alexandre Rezende Gonçalves (FIAP)
- **Turma:** 1CCPZ-2026
- **Equipe Lumos:**
  - **Pietro Lorande** — RM 569125
  - **Luiz Otávio Brito Freixo** — RM 569977
  - **Maria Eduarda Lemos** — RM 574094
- **Status Geral da Sprint 3 Final:** **21 / 21 User Stories Concluídas (`100% DONE`)** · **13 / 13 Baterias de Testes Automatizados Aprovadas (`testes.py`)**

---

## Visão do Quadro Kanban por Sprints (Equivalente ao Quadro Trello Finalizado)

| Coluna 1: Backlog Inicial | Coluna 2: Em Desenvolvimento | Coluna 3: Em Testes / QA | Coluna 4: DONE — Concluído e Validado (21/21) |
|---|---|---|---|
| *(0 itens pendentes)* | *(0 itens em aberto)* | *(0 itens bloqueados — 13/13 suítes aprovadas)* | **Sprint 1 (Base Residencial):** `PB01`, `PB02`<br>**Sprint 2 (Motor Solar FV & C1–C8):** `PB03`, `PB04`, `PB05`, `PB06`, `PB07`, `PB08`, `PB09`<br>**Sprint 3 (Baterias, Orçamento, Payback & Full-Stack Web):** `PB10`, `PB11`, `PB12`, `PB13`, `PB14`, `PB15`, `PB16`, `PB17`, `PB18`, `PB19`, `PB20`, `PB21` |

---

## Detalhamento dos Cartões Concluídos (`PB01` a `PB21`)

| ID | Card / User Story | Sprint | Módulo Responsável no Código | Responsável (Equipe Lumos) | Status Final |
|---|---|---|---|---|---|
| **PB01** | Recuperação automática da residência cadastrada (`#1 Residência Família Silva`) | Sprint 1 | `sistema_analise_casa.py` · `dados_sistema.json` | Pietro / Luiz / Maria | **DONE** |
| **PB02** | Cálculo da demanda energética (`E_mês = 455,31 kWh`, `E_dia = 15,18 kWh/dia`, `P_inst = 9.013 W`) | Sprint 1 | `sistema_analise_casa.py` · `fotovoltaico.py` | Luiz Otávio (RM 569977) | **DONE** |
| **PB03** | Recurso solar (`HSP = 5,00 kWh/m²/dia` CRESESB + `PR = 0,78` NT EPE 009/2023) | Sprint 2 | `fotovoltaico.py` (`obter_hsp`, `validar_pr`) | Maria Eduarda (RM 574094) | **DONE** |
| **PB04** | Cálculo da potência fotovoltaica necessária (`P_FV = E_dia / (HSP * PR) = 3,89 kWp`) | Sprint 2 | `fotovoltaico.py` (`potencia_fv_por_consumo_diario`) | Luiz Otávio (RM 569977) | **DONE** |
| **PB05** | Dataset estruturado de módulos fotovoltaicos (`modulos.csv` — 10 modelos reais) | Sprint 2 | `dados_fv/modulos.csv` · `fotovoltaico.py` | Pietro Lorande (RM 569125) | **DONE** |
| **PB06** | Dimensionamento de módulos (`N_mod = 10× Trina 405 Wp` → `P_inst = 4,05 kWp`) | Sprint 2 | `fotovoltaico.py` (`quantidade_minima_modulos`) | Luiz Otávio (RM 569977) | **DONE** |
| **PB07** | Seleção de inversor compatível e verificação elétrica `C1` a `C8` (`R_DC/AC = 1,35`) | Sprint 2 | `dados_fv/inversores.csv` · `fotovoltaico.py` | Pietro Lorande (RM 569125) | **DONE** |
| **PB08** | Estimativa da geração diária (`15,80 kWh/dia`) e mensal (`473,85 kWh/mês`) | Sprint 2 | `fotovoltaico.py` (`geracao_estimada_mensal`) | Maria Eduarda (RM 574094) | **DONE** |
| **PB09** | Comparação geração × consumo (`104,1%`, separando `455,31 kWh` compensados de `18,54 kWh` excedentes) | Sprint 2 | `fotovoltaico.py` (`comparar_geracao_consumo`) | Luiz Otávio (RM 569977) | **DONE** |
| **PB10** | Opção de configuração Sem Baterias (On-Grid) ou Com Baterias (Híbrido) | Sprint 3 | `fotovoltaico.py` · `app_web.py` | Pietro Lorande (RM 569125) | **DONE** |
| **PB11** | Dimensionamento de baterias (`E_aut = 7,59 kWh`, `C_bat = 8,88 kWh` → `2× Deye 5,12 kWh = 10,24 kWh`) | Sprint 3 | `fotovoltaico.py` (`selecionar_bateria`) | Luiz Otávio (RM 569977) | **DONE** |
| **PB12** | Dataset estruturado de baterias LiFePO4 (`baterias.csv` — 6 modelos reais) | Sprint 3 | `dados_fv/baterias.csv` · `fotovoltaico.py` | Maria Eduarda (RM 574094) | **DONE** |
| **PB13** | Geração automática do orçamento (`R$ 11.590,88` On-Grid vs. `R$ 33.317,78` Híbrido) | Sprint 3 | `fotovoltaico.py` (`calcular_orcamento`) | Pietro Lorande (RM 569125) | **DONE** |
| **PB14** | Comparação lado a lado dos cenários e resposta fundamentada à Questão Final (Seção 9) | Sprint 3 | `fotovoltaico.py` (`comparar_cenarios`) · `app_web.py` | Luiz Otávio (RM 569977) | **DONE** |
| **PB15** | Estimativa de economia mensal (`R$ 418,89/mês`) e anual (`R$ 5.026,68/ano`) | Sprint 3 | `fotovoltaico.py` (`calcular_economia`) | Maria Eduarda (RM 574094) | **DONE** |
| **PB16** | Cálculo do Payback Simples preliminar (`2,31 anos` On-Grid vs. `6,63 anos` Híbrido) | Sprint 3 | `fotovoltaico.py` (`calcular_payback_simples`) | Luiz Otávio (RM 569977) | **DONE** |
| **PB17** | Tela e relatório consolidado da proposta técnica e comercial completa | Sprint 3 | `app_web.py` · `fotovoltaico.py` | Pietro Lorande (RM 569125) | **DONE** |
| **PB18** | Validação de entradas e bloqueio compreensível de incompatibilidades elétricas `C1–C8` | Sprint 3 | `fotovoltaico.py` (`ErroDimensionamento`) · `app_web.py` | Maria Eduarda (RM 574094) | **DONE** |
| **PB19** | Interface gráfica web full-stack integrada em Python puro (`http.server`, zero dependências) | Sprint 3 | `app_web.py` · `RODAR_PROJETO.bat` | Pietro / Luiz | **DONE** |
| **PB20** | Persistência automática de residências, equipamentos e projetos em `dados_sistema.json` | Sprint 3 | `sistema_analise_casa.py` · `dados_sistema.json` | Luiz Otávio (RM 569977) | **DONE** |
| **PB21** | Exportação da proposta comercial final em `.txt`, `.html` e impressão PDF | Sprint 3 | `fotovoltaico.py` · `proposta_cliente.html` / `.txt` | Luiz / Maria | **DONE** |

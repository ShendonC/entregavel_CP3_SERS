# CP3 - Finalizacao Sistema de Orcamento Fotovoltaico (Sprint 3 - Product Backlog Final)
Continuacao dos Checkpoints 1 e 2 - Disciplina: Solucoes em Energias Renovaveis e Sustentaveis (Prof. Alvaro Goncalves)

## INTEGRANTES (Equipe Lumos - FIAP)

- **Pietro Lorande** | RM 569125
- **Luiz Otavio Brito Freixo (Luiz Otavio Britto Freixo)** | RM 569977
- **Maria Eduarda Lemos** | RM 574094

---

## LINKS DO PROJETO E KANBAN (SPRINTS 1, 2 E 3)

- **Entregavel CP1 (GitHub):** https://github.com/pietrolorande01-ELFzen/entregavel_CP1_sustentabilidade/tree/main
- **Kanban / Trello CP1:** https://trello.com/invite/b/6a9b6947fa36b4d757bfadbf/ATTIf06135456fb1670e8f819b23dc4bacdf5FFB6243/sprintsers
- **Entregavel CP2 / Base CP3 (GitHub):** https://github.com/pietrolorande01-ELFzen/entregavel_CP2_SERS
- **Kanban / Trello CP2 & Sprint 3:** https://trello.com/invite/b/6aade675e4a2fddaa89bc71b/ATTI83a4196a19136758446b9c08d9516198BBE75C3E/cp02-sers20

---

# Sistema de Dimensionamento Energetico Residencial - Evolucao Fotovoltaica (Sprint 3 Final)

**Equipe Lumos · FIAP · Ciencia da Computacao / Analise e Desenvolvimento de Sistemas**

Sistema integrado em Python que cadastra usuarios, residencias e equipamentos eletricos, calcula a demanda energetica do imovel (`E_mes`, `E_dia` e potencia instalada em `W`/`kW`) e realiza o **dimensionamento completo de geracao solar fotovoltaica (PB01 a PB21)**: selecao de modulos, inversores e baterias em datasets estruturados, verificacao de compatibilidade tecnica (regras C1 a C8), estimativa de geracao diaria e mensal, comparacao geracao x consumo (distinguindo energia compensada e excedente), orcamento detalhado (com preco unitario, subtotal e total), estimativa de economia mensal/anual, **payback simples**, comparacao lado a lado entre solucao **sem baterias (On-Grid)** e **com baterias (Hibrido)** e exportacao da proposta final em relatorio `.txt` e pagina web `.html`.

---

## 1. Como executar

Requer **Python 3.9 ou superior** (utiliza apenas a biblioteca padrao do Python, sem necessidade de `pip install`).

```bash
# 1. Usar o sistema interativo pelo menu completo (conta pronta: demo@lumos.com / senha: 1234)
python sistema_analise_casa.py

# 2. Executar direto o roteiro completo da Sprint Review (15 itens + Questao 9 + exportacao HTML/TXT)
python sistema_analise_casa.py --demo

# 3. Rodar todos os testes automatizados (CP1 + CP2 + Sprint 3 Final), sem interacao
python testes.py
```

> Os arquivos `.csv` ficam disponiveis tanto na pasta `dados_fv/` quanto na raiz do projeto, garantindo funcionamento imediato em qualquer ambiente.

---

## 2. Estrutura dos arquivos

```
projeto/
├── sistema_analise_casa.py     <- telas, menus, persistencia JSON e roteiro da Sprint Review
├── fotovoltaico.py             <- motor de dimensionamento FV, datasets, comparacao, orcamento e payback
├── testes.py                   <- bateria de testes automatizados (CP1 + CP2 + Sprint 3 PB01-PB21)
├── dados_sistema.json          <- banco persistente com residencia pre-cadastrada e cenarios salvos (PB01/PB20)
├── proposta_cliente.txt        <- relatorio consolidado exportado automaticamente (PB17/PB21)
├── proposta_cliente.html       <- pagina web consolidada da proposta e comparacao de cenarios (PB19/PB21)
└── dados_fv/                   <- datasets estruturados e rastreaveis da parte solar (PB05/PB07/PB12)
    ├── modulos.csv             <- 10 modulos fotovoltaicos reais com precos e fontes
    ├── inversores.csv          <- 8 inversores (on-grid e hibridos) com limites eletricos, MPPT e eficiencia
    ├── baterias.csv            <- 6 baterias LiFePO4 com tensao, Ah, kWh, DoD, ciclos e preco
    └── hsp_localidades.csv     <- irradiacao solar (HSP) por municipio brasileiro (CRESESB/INPE SunData)
```

---

## 3. Rastreabilidade do Product Backlog Final - Sprint 3 (PB01 a PB21)

| Item | User Story / Requisito da Sprint 3 | Onde esta implementado |
|---|---|---|
| **PB01** | Recuperacao da residencia ja cadastrada (sem exigir recadastro) | `sistema_analise_casa.py` (`selecionar_imovel_do_usuario`, `popular_residencia_demonstracao`, `dados_sistema.json`) |
| **PB02** | Recuperacao da demanda energetica (`E_dia = E_mes / 30`, `E_mes` em kWh e potencia instalada em W/kW) | `fotovoltaico.py` (`demanda_energetica_residencia`, `consumo_diario`) e `sistema_analise_casa.py` (`potencia_instalada_imovel`, `exibir_relatorio`) |
| **PB03** | Recurso solar (HSP com fonte + Performance Ratio `PR = 0,78` informado e justificado) | `fotovoltaico.py` (`PARAMETROS_FV`, `obter_hsp`, `validar_hsp`, `validar_pr`) |
| **PB04** | Calculo da potencia fotovoltaica necessaria (`P_FV = E_dia / (HSP * PR)` em kWp) | `fotovoltaico.py` (`potencia_fv_por_consumo_diario`, `potencia_fv_necessaria`) |
| **PB05** | Consulta ao dataset estruturado de modulos fotovoltaicos (`modulos.csv`) | `fotovoltaico.py` (`carregar_dataset("modulos")`) e `sistema_analise_casa.py` (`exibir_catalogo_datasets_fv`) |
| **PB06** | Dimensionamento dos modulos (`N_mod = teto[(P_FV * 1000) / P_mod]` e `P_inst = (N_mod * P_mod) / 1000`) | `fotovoltaico.py` (`quantidade_minima_modulos`, `potencia_instalada`, `verificar_modulo_inversor`) |
| **PB07** | Selecao do inversor compativel (`R_DC/AC = P_FV_instalada / P_inversor`, MPPT, tensao, corrente, eficiencia) | `fotovoltaico.py` (`verificar_modulo_inversor`, `selecionar_modulo_inversor`) e `inversores.csv` |
| **PB08** | Estimativa da geracao fotovoltaica diaria (`E_gerada,dia = P_inst * HSP * PR`) e mensal (`E_gerada,mes = E_gerada,dia * 30`) | `fotovoltaico.py` (`geracao_estimada_diaria`, `geracao_estimada_mensal`) |
| **PB09** | Comparacao geracao x consumo (`Atendimento (%) = (E_gerada,mes / E_consumida,mes) * 100`, distinguindo compensada vs excedente) | `fotovoltaico.py` (`comparar_geracao_consumo`) |
| **PB10** | Opcao de sistema sem baterias (On-Grid) ou com baterias (Hibrido) | `fotovoltaico.py` (`dimensionar_fv`) e `sistema_analise_casa.py` (`novo_dimensionamento_fv`) |
| **PB11** | Dimensionamento das baterias (`C_bat = E_aut / (DoD * eta_bat)` e `N_bat = teto(C_bat / C_unidade)`) | `fotovoltaico.py` (`energia_autonomia`, `capacidade_bateria_necessaria`, `quantidade_baterias`, `selecionar_bateria`) |
| **PB12** | Dataset estruturado e rastreavel de baterias (`baterias.csv`) | `fotovoltaico.py` (`carregar_dataset("baterias")`) e `baterias.csv` |
| **PB13** | Geracao automatica do orcamento (`Custo_item = qtd * preco_unitario` e `Custo_total = Soma(Custo_item)`) | `fotovoltaico.py` (`calcular_orcamento`) |
| **PB14** | Comparacao lado a lado dos cenarios (Sem Baterias vs Com Baterias) | `fotovoltaico.py` (`comparar_cenarios`, `formatar_comparacao_cenarios`) e `sistema_analise_casa.py` (`tela_comparar_cenarios_fv`) |
| **PB15** | Estimativa de economia mensal e anual (`Economia_mensal = E_compensada * tarifa`) | `fotovoltaico.py` (`calcular_economia`) |
| **PB16** | Payback simples (`Payback = Investimento / Economia_anual`, explicitamente indicado como estimativa preliminar) | `fotovoltaico.py` (`calcular_payback_simples`) |
| **PB17** | Tela e relatorio consolidado da proposta completa | `fotovoltaico.py` (`formatar_proposta`) |
| **PB18** | Validacao de dados e tratamento de erros compreensiveis ao usuario | `fotovoltaico.py` (`positivo`, `validar_hsp`, `validar_pr`, `validar_tarifa`, `ErroDimensionamento`) |
| **PB19** | Interface integrada (fluxo completo sem edicao de codigo ou calculos externos) | `sistema_analise_casa.py` (`menu_residencia`, `novo_dimensionamento_fv`, `--demo`) e `proposta_cliente.html` |
| **PB20** | Persistencia completa do projeto em `dados_sistema.json` | `sistema_analise_casa.py` (`salvar_dimensionamento_no_banco`, `listar_dimensionamentos_fv`) |
| **PB21** | Exportacao da proposta para apresentacao ao cliente (`.txt` e `.html`) | `fotovoltaico.py` (`exportar_proposta_txt`, `exportar_proposta_html`) |

---

## 4. Formulas implementadas no motor (`fotovoltaico.py`)

| Formula | Descricao | Funcao em `fotovoltaico.py` |
|---|---|---|
| `E_dia = E_mes / 30` | Consumo medio diario da residencia (kWh/dia) | `consumo_diario` / `demanda_energetica_residencia` |
| `E_FV = Cm * f` | Energia mensal que o sistema deve atender (kWh/mes) | `energia_mensal_desejada` |
| `P_FV = E_dia / (HSP * PR)` | Potencia fotovoltaica necessaria (kWp) | `potencia_fv_por_consumo_diario` / `potencia_fv_necessaria` |
| `N_mod = teto[(P_FV * 1000) / P_mod]` | Quantidade minima de modulos fotovoltaicos | `quantidade_minima_modulos` |
| `P_inst = (N_mod * P_mod) / 1000` | Potencia efetivamente instalada (kWp) | `potencia_instalada` |
| `R_DC/AC = P_FV_instalada / P_inversor` | Razao de carregamento DC/AC do inversor | `verificar_modulo_inversor` |
| `E_gerada,dia = P_inst * HSP * PR` | Geracao fotovoltaica diaria estimada (kWh/dia) | `geracao_estimada_diaria` |
| `E_gerada,mes = E_gerada,dia * 30` | Geracao fotovoltaica mensal estimada (kWh/mes) | `geracao_estimada_mensal` |
| `Atendimento (%) = (E_gerada,mes / E_consumida,mes) * 100` | Percentual de atendimento da demanda mensal | `comparar_geracao_consumo` |
| `E_compensada = min(E_gerada,mes, E_consumida,mes)` | Energia efetivamente compensada na fatura mensal | `comparar_geracao_consumo` |
| `E_aut = E_dia * (A / 24)` | Energia necessaria para `A` horas de autonomia (kWh) | `energia_autonomia` |
| `C_bat = E_aut / (DoD * eta_bat)` | Capacidade nominal de banco de baterias necessaria (kWh) | `capacidade_bateria_necessaria` |
| `N_bat = teto(C_bat / C_unidade)` | Quantidade de baterias necessarias | `quantidade_baterias` |
| `Custo_item = quantidade * preco_unitario` | Subtotal de cada equipamento do orcamento (R$) | `calcular_orcamento` |
| `Custo_total = Soma(Custo_item)` | Somatorio do orcamento de equipamentos e instalacao (R$) | `calcular_orcamento` |
| `Economia_mensal = E_compensada * tarifa` | Economia financeira mensal estimada na conta de luz (R$/mes) | `calcular_economia` |
| `Economia_anual = Economia_mensal * 12` | Economia financeira anual estimada (R$/ano) | `calcular_economia` |
| `Payback = Investimento / Economia_anual` | Tempo de retorno simples do investimento (anos) | `calcular_payback_simples` |

---

## 5. Regras de compatibilidade eletrica (C1 a C8)

| Regra | Verificacao Tecnica | Objetivo |
|---|---|---|
| **C1** | `Voc_string * 1,10 <= tensao_max_entrada_v` | Protege o inversor contra sobretensao de circuito aberto em dias frios |
| **C2** | `Vmp_string <= faixa_mppt_max_v` | Garante que a tensao de operacao da string nao ultrapasse o teto do MPPT |
| **C3** | `Vmp_string * 0,90 >= faixa_mppt_min_v` | Garante que em dias quentes a tensao da string nao caia abaixo da partida do MPPT |
| **C4** | `Imp_string <= corrente_max_entrada_a` | Garante que a corrente dos modulos respeite o limite por entrada MPPT |
| **C5** | `P_instalada * 1000 <= potencia_max_fv_w` | Impede que a potencia total de paineis exceda o limite CC do inversor |
| **C6** | `ratio_min <= R_DC/AC <= 1,35` | Mantem a relacao `P_FV_instalada / P_inversor` na faixa otima de rendimento |
| **C7** | `com_bateria -> compativel_bateria == SIM` | Exige inversor hibrido sempre que o cliente optar por armazenamento |
| **C8** | `tensao_bateria_min_v <= V_bat <= tensao_bateria_max_v` | Garante compatibilidade de barramento CC entre o banco LiFePO4 e o inversor hibrido |

---

## 6. Resposta Fundamentada a Questao Final da Sprint Review (Secao 9)

> **Pergunta (Secao 9 do Enunciado):** *Para a residencia utilizada na demonstracao, qual solucao faz mais sentido: sistema fotovoltaico sem armazenamento ou sistema com baterias? Quais resultados tecnicos e economicos do projeto sustentam a analise?*

### Caso Demonstrado: `Residencia Familia Silva (SP)` - Sao Paulo/SP

1. **Demanda Energetica da Residencia (PB01 / PB02):**
   - **Potencia instalada das cargas da residencia:** `9.963 W` (`9,963 kW`) distribuidos em 8 grupos de equipamentos (chuveiro eletrico, ar-condicionado, geladeira, micro-ondas, maquina de lavar, computador, TVs e iluminacao LED).
   - **Consumo mensal calculado (`E_mes`):** `455,31 kWh/mes`.
   - **Consumo medio diario (`E_dia = E_mes / 30`):** `15,18 kWh/dia`.
   - **Recurso solar local (PB03):** Sao Paulo/SP com `HSP = 5,00 kWh/m2/dia` (fonte: CRESESB/SunData) e Performance Ratio `PR = 0,78 (78%)`.

2. **Quadro Comparativo Obtido pelo Sistema (PB14):**

| Indicador Tecnico / Economico | Cenario 1: Sem Baterias (On-Grid) | Cenario 2: Com Baterias (Hibrido - 12h) |
|---|---|---|
| **Potencia FV Calculada (`P_FV`)** | `3,892 kWp` | `3,892 kWp` |
| **Potencia FV Instalada (`P_inst`)** | `4,050 kWp` | `4,050 kWp` |
| **Modulos Selecionados (`modulos.csv`)** | `10x [FV006] Trina Solar TSM-405DE09 (405 Wp)` (`R$ 590,32/un`) | `10x [FV006] Trina Solar TSM-405DE09 (405 Wp)` (`R$ 590,32/un`) |
| **Inversor Selecionado (`inversores.csv`)** | `[INV001] Growatt MIC 3000TL-X` (On-Grid, `3.000 W`, efic. `97,6%`, `R_DC/AC = 1,35`, `R$ 1.589,00`) | `[INV006] Deye SUN-5K-SG04LP1-EU-SM2` (Hibrido, `5.000 W`, efic. `97,6%`, `R_DC/AC = 0,81`, `R$ 7.859,00`) |
| **Geracao Estimada (Dia / Mes)** | `15,79 kWh/dia` / `473,85 kWh/mes` | `15,79 kWh/dia` / `473,85 kWh/mes` |
| **Atendimento da Demanda (`PB09`)** | `104,1%` (`455,31 kWh/mes` compensados + `18,54 kWh/mes` excedente) | `104,1%` (`455,31 kWh/mes` compensados + `18,54 kWh/mes` excedente) |
| **Banco de Baterias (`baterias.csv`)** | Nao possui (`0 kWh`) | `2x [BAT005] Deye SE-F5 LiFePO4` (`51,2 V`, `100 Ah`, `5,12 kWh`, DoD `90%`, `R$ 6.150,00/un`) |
| **Capacidade Armazenada e Autonomia** | `0 kWh` / `0 h` de autonomia | `10,24 kWh` nominais (`9,22 kWh` uteis) para `12,0 h` de autonomia (`E_aut = 7,59 kWh`, `C_bat = 8,88 kWh`) |
| **Custo dos Equipamentos (`PB13`)** | `R$ 7.492,20` | `R$ 26.062,20` |
| **Outros Custos e Instalacao** | `R$ 4.098,68` | `R$ 7.255,58` |
| **Investimento Total Estimado** | **`R$ 11.590,88`** | **`R$ 33.317,78`** (`+R$ 21.726,90` / `+187,4%`) |
| **Economia Mensal (`R$ 0,92/kWh`)** | `R$ 418,89 / mes` | `R$ 418,89 / mes` |
| **Economia Anual Estimada (`PB15`)** | `R$ 5.026,68 / ano` | `R$ 5.026,68 / ano` |
| **Payback Simples Estimado (`PB16`)** | **`2,31 anos (~2 anos e 4 meses)`** | **`6,63 anos (~6 anos e 8 meses)`** |

3. **Conclusao Tecnica e Economica:**
   - Para a residencia demonstrada, **a solucao que faz mais sentido e o Sistema Fotovoltaico Sem Armazenamento (On-Grid)**.
   - **Sustentacao pelos dados do projeto:** Ambos os sistemas entregam exatamente a mesma geracao fotovoltaica (`473,85 kWh/mes`, cobrindo `100%` dos `455,31 kWh/mes` consumidos pela casa e gerando a mesma economia de `R$ 418,89/mes` ou `R$ 5.026,68/ano`). Contudo, a inclusao de armazenamento para `12 horas` de autonomia (`7,59 kWh`) exige trocar o inversor on-grid (`R$ 1.589,00`) por um inversor hibrido (`R$ 7.859,00`) e adquirir `2 baterias LiFePO4 Deye SE-F5` (`R$ 12.300,00`), elevando o investimento total de **`R$ 11.590,88` para `R$ 33.317,78`** (quase o triplo do valor, `+187,4%`) sem aumentar a economia mensal na fatura.
   - Consequentemente, o **Payback Simples** salta de **`2,31 anos`** (excelente retorno financeiro) para **`6,63 anos`** (`+4,32 anos` adicionais). Assim, em uma area urbana atendida pela rede da concessionaria (Sao Paulo/SP), o sistema On-Grid sem baterias oferece a melhor viabilidade economica, enquanto o sistema Hibrido com baterias so se justificaria caso o cliente tivesse equipamentos medicos vitais, home-office critico ou sofresse blecautes constantes na regiao.

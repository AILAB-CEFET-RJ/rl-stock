# Escrutínio da formulação do paper — 08/10/2026

> Registro **002** · Data de referência: **2026-10-08** · [Índice](README.md)
> Anterior: [Registro 001](001_raw_data_audit.md) · Seguinte: [Registro 003](003_paper_revision_steps_1_3.md)

## Parecer e escopo

A proposta de estudar decisões intradiárias multiativo com observações de livro
é viável como investigação. **A formulação atual ainda não especifica um
backtest economicamente consistente e causal.** Não deve ser transcrita
diretamente para o novo simulador. Os principais impedimentos são relógio de
observação versus execução, contabilidade/restrições, recompensas, normalização
e encerramento dos episódios. Há também problemas no protocolo de avaliação.

Referência: versão anterior de `paper/paper.tex`, preservada em
`paper/archive/paper_pre_revision_2026-10-08.tex`, SHA-256
`4e776eb6f30c63552ef1701d9f20a8b2e50921c25bda915cacac42a9d0aa5078`.
As linhas abaixo se referem a essa versão de referência. O manuscrito ativo
foi posteriormente reescrito nas etapas 1–3; ver `003_paper_revision_steps_1_3.md`.
Não foram reutilizados resultados da dissertação nem executado treinamento.
O código legado foi inspecionado para identificar divergências, sem pressupor
que seja exatamente a versão que gerou as tabelas antigas.

Classificação: **P0** impede interpretar o resultado como lucro de uma estratégia
causal; **P1** compromete a comparação ou a definição científica; **P2** exige
correção documental. Diferencio erros demonstráveis de hipóteses não verificadas.

## Achados sobre dados, relógios e execução

### 1. P0 — O atraso não se torna irrelevante por se tratar de histórico

**Evidência:** linha 399 afirma atraso de aproximadamente 50 minutos e que isso
não afeta os objetivos por o treinamento usar histórico. O responsável pelo
projeto informou **três horas**. Não há horário de mercado do livro nos Parquet;
`File_Date` é da máquina e `Time` está associado aos negócios.

**Problema:** treinamento histórico pode ser perfeitamente válido com dados
originalmente atrasados, desde que se reconstrua uma cronologia coerente. Porém,
não se pode observar um livro atrasado e supor que ele ainda oferece execução
naquele preço no instante de recebimento. Também não se pode corrigir
uniformemente campos cujos relógios e atrasos podem ter semânticas diferentes.

**Correção:** definir três tempos: mercado/fonte, disponibilidade ao agente e
execução. Atraso de publicação e latência da ordem são parâmetros diferentes.
Para simular recebimento real, é necessária uma fonte de execução contemporânea.
Para um replay histórico idealizado, é necessário estabelecer a cronologia de
origem dos snapshots e declarar as hipóteses de execução. Até lá, os produtos
atuais medem cobertura no relógio de recebimento, não rentabilidade negociável.

**Verificação externa:** a [descrição atual do Book Viewer da Cboe](https://www.cboe.com/markets/us/equities/market-statistics/book-viewer)
apresenta dados de cada uma de suas quatro bolsas e os descreve como em tempo
real. Isso **não comprova** o funcionamento da interface em 2025 nem substitui
a informação de três horas fornecida pelo usuário. É uma divergência a esclarecer,
não justificativa para alterar os timestamps automaticamente.

### 2. P0 — O kernel de execução não está especificado

**Evidência:** linhas 97, 306–321 e 729 prometem liquidez, slippage, custos e
restrições, mas não definem transição de caixa/posição, lado do livro, consumo
por nível, execução parcial ou instante de preenchimento. O preço de execução
`p_t` aparece como entrada da quantidade desejada antes de se definir a execução.

**Problema:** o VWAP depende da quantidade e da profundidade. Usá-lo previamente
para determinar essa mesma quantidade cria uma definição circular sem algoritmo.
Um midpoint ou média entre níveis não é um preço garantido de compra/venda.
Snapshots de um minuto não permitem reconstruir fila, cancelamentos e todos os
eventos intraminuto. Reutilizar uma captura em dois minutos não cria liquidez nova.

**Correção:** compra consome asks, venda consome bids; somar preço × quantidade
por nível e aceitar preenchimento parcial. Fixar momento de execução, prioridade
entre ativos, orçamento incluindo taxas, limite de participação e política para
ordens sem contraparte. Separar spread, caminhada no livro, impacto não observado
e latência, evitando cobrar duas vezes o mesmo componente. Uma execução no
snapshot seguinte é uma hipótese de replay, não evidência de preço realmente
disponível entre as capturas. Não reabastecer automaticamente profundidade
consumida usando o mesmo `snapshot_id` em outra linha da grade.

### 3. P1 — Livro de uma bolsa não equivale ao mercado americano consolidado

**Evidência:** linhas 110, 399–401 falam genericamente em livro/liquidez de ações.
Os Parquet não registram bolsa/MIC. O coletor consultado usa URLs por ticker e
não persiste a identificação da bolsa selecionada.

**Problema:** a [Cboe descreve o Viewer por bolsa](https://www.cboe.com/markets/us/equities/market-statistics/book-viewer),
com alternância entre BZX, BYX, EDGX e EDGA. Não há demonstração de que a coleta
seja NBBO, liquidez consolidada ou profundidade integral do mercado. Uma ação
líquida no agregado pode ter pouca profundidade nessa página.

**Correção:** qualificar a fonte como livro exibido da bolsa selecionada, cuja
identidade histórica ainda requer confirmação. Não assumir roteamento para
outras bolsas, prioridade de fila ou acesso a liquidez oculta.

### 4. P1 — Linhas, snapshots e observações por minuto estão confundidos

**Evidência:** linha 926 relata 432.160 observações por empresa. A auditoria
encontrou, no período, **432.160 linhas brutas = 43.216 blocos de dez linhas por
empresa**, antes de validação e alinhamento. A tabela Apple, linhas 433–442,
mostra seis asks e quatro bids, enquanto o estado pede cinco de cada lado.
As amostras ilustrativas são de julho de 2024, fora do período declarado.

**Correção:** contar separadamente linhas, capturas, capturas completas, minutos
alinhados, pregões e episódios elegíveis. Substituir as amostras antigas por
snapshots rastreáveis do novo pipeline. Cada linha bruta combina campos de um
nível e de um negócio por posição na página; isso não vincula aquele negócio
àquele nível nem identifica seu lado agressor. Dez negócios recentes podem se
repetir entre capturas e não representam dez eventos novos a cada minuto.

As porcentagens de 4% ausentes e 7% duplicados, linhas 406–408, precisam ser
recalculadas com denominadores e definições explícitos. Cotações iguais em dois
recebimentos legítimos não são necessariamente duplicatas a remover. O número
de observações válidas e a disponibilidade conjunta variam por ativo e minuto.

## Achados sobre controle, estado e recompensas

### 5. P0 — A projeção inteira não assegura autofinanciamento

**Evidência:** linhas 312–329 definem
`q̃_i = a_i min(V/(N p_i), L_i)` e `q_i = sign(q̃_i) floor(|q̃_i|)`.

**Contraexemplo:** dois ativos, patrimônio 1.000, caixa zero, preços 100 e
liquidez suficiente. Ações `(1,1)` solicitam cinco ações de cada ativo; a compra
gera caixa **−1.000**. Com caixa 1.000, o mesmo lote custa 1.001 se a taxa for
0,1%, também violando o orçamento. Ações negativas podem vender ativos que
não estão na carteira, criando posições short sem autorização explícita.

**Correção:** manter a projeção inteira, que é adequada para reduzir magnitudes,
mas impor conjuntamente `C' >= 0` e `h_i' >= 0` no caso long-only, incluindo
taxas e limites por lado. Especificar se vendas financiam compras no mesmo passo
e como repartir orçamento escasso. O limiar deve produzir ordem zero quando
`|a_i| <= δ`, inclusive na equação. Ações são intenções de quantidade, não pesos
alvo de carteira; o texto deve escolher e manter uma dessas interpretações.

Com capital próximo do preço de uma ação, a discretização também pode eliminar
quase todas as intenções: `V=p`, `N=1`, `|a|<1` e liquidez suficiente dão
`floor(|a|V/p)=0`. Os capitais iniciais das tabelas exigem revisão antes de
combinar controle contínuo com lotes inteiros. Não é necessário abandonar PPO;
o ambiente pode executar ações discretizadas sem ser diferenciável.

### 6. P0 — A recompensa local não representa o lucro da ação

**Evidência:** equação `eq:local-reward`, linhas 657–663:
`r_t = Σ q_t (p_t − p_{t−1})`, com `q_t` explicitamente definido como quantidade
negociada, e não posição mantida.

**Contraexemplos:** comprar uma ação a 110 depois de ela subir de 100 atribui
recompensa +10, embora a compra a 110 e marcação a 110 não gerem lucro. Manter
uma ação durante essa alta produz recompensa zero, pois `q_t=0`. Vender depois
da alta atribui sinal negativo, embora o investidor possa ter lucrado.

**Correção:** usar variação de patrimônio líquido após execução e marcação,
com indexação temporal clara. Se essa expressão for mantida como ablação,
chamá-la de sinal heurístico enviesado, não de lucro local. Não é uma medida
financeira comparável às outras duas recompensas.

### 7. P1 — PnL realizado, patrimônio e desconto têm objetivos diferentes

**Evidência:** linhas 674–694 apresentam variação de PnL realizado e variação
de patrimônio como recompensas alternativas e declaram superioridade empírica.
O objetivo usa `γ<1` nas linhas 275–282.

**Problema:** PnL realizado depende da convenção de custo de aquisição e pode
incentivar realizar ganhos e carregar perdas. Sem liquidação, a perda aberta
pode nunca entrar na recompensa. Já `ΔV` mede riqueza incluindo posições
abertas. A soma não descontada de `ΔV` telescopa; a soma descontada não depende
somente do patrimônio final. Não são objetivos equivalentes por definição.

Para `r_k=V_{k+1}−V_k`, a identidade é:

$$
\sum_{k=0}^{T-1}\gamma^k r_k
=-V_0+(1-\gamma)\sum_{k=1}^{T-1}\gamma^{k-1}V_k
  +\gamma^{T-1}V_T.
$$

**Correção:** escolher recompensa principal, por exemplo `α ΔV/θ`, com `θ`
capital inicial fixo e positivo. Justificar o desconto como preferência temporal
e comparar valores somente na validação. Relatar retorno final separadamente.
Um retorno logarítmico é alternativa, mas muda o critério de agregação e exige
patrimônio positivo; dividir por volatilidade móvel também muda o objetivo.
O código legado usa essa última transformação depois de 20 retornos, sem ser
uma das três recompensas descritas. Isso não é automaticamente o Sharpe nem
uma recompensa diferencial de Sharpe. Se utilizada, precisa de fórmula própria
e histórico suficiente no estado do simulador.
Variação de patrimônio mede desempenho absoluto; não mede automaticamente o
custo de oportunidade de uma alternativa de investimento. Para isso seria
necessário definir rendimento de caixa ou benchmark de referência.

### 8. P0 — Normalização pode revelar o futuro; quantidades têm unidade errada

**Evidência:** linhas 515–518 normalizam preços **e quantidades** em relação ao
preço médio anterior, aplicam min–max sem definir janela de ajuste, e usam
máximos observados dentro do episódio para variáveis de carteira.

**Problema:** o máximo de todo o episódio não está disponível no instante da
decisão. Se fosse apenas máximo acumulado até `t`, isso deveria ser declarado.
Dividir ações por dólares/ação não produz mudança percentual de quantidade.
Min–max ajustado no teste também pode usar informação futura.

**Correção:** preços relativos a uma referência de preço passada ou observável
na decisão; volumes por escala de volumes ajustada no treino ou transformação
causal explicitamente definida. Caixa e valor das posições por `θ`, por exemplo,
ou pesos atuais com denominador bem definido. Congelar estatísticas aprendidas
no treino para validação/teste. Definir a ordem temporal dos dez negócios antes
de calcular retornos e não converter quantidades ou preços ausentes em zero.

### 9. P1 — Uma janela finita não comprova a propriedade de Markov

**Evidência:** linhas 537, 619 e 637 identificam o tensor observado com o estado
MDP e dizem que a interface preserva a estrutura Markoviana.

**Problema:** mercado não observado, relógio, ordens pendentes e regras
dependentes do passado podem influenciar transições sem constar no tensor.
Uma janela de preços não demonstra suficiência estatística. Em horizonte
finito, o tempo restante pode alterar a decisão ótima.

**Correção:** distinguir estado interno do simulador e observação da política.
Descrever uma aproximação por histórico finito em ambiente parcialmente
observável. Incluir caixa, posições, horário e horizonte conhecido; incluir
ordens pendentes se houver latência, custo de aquisição se houver PnL realizado
e pico de patrimônio se houver stop por drawdown. Não preencher a história com
a carteira atual repetida como se essas posições existissem nos passos passados.
Esse enquadramento é consistente com a distinção entre MDP e POMDP em
[Kaelbling, Littman e Cassandra (1998)](https://people.csail.mit.edu/lpk/papers/aij98-pomdp.pdf).

### 10. P0 — O problema declarado como day trading não encerra posições no dia

**Evidência:** linha 117 define encerramento na mesma sessão; linhas 621–628 e
727 terminam por limite de capital ou fim do dataset, sem fechamento diário,
tratamento de lacunas ou liquidação das posições.

**Correção:** definir episódios, warm-up, limite de sessão e valorização terminal.
Uma posição aberta deve sofrer marcação consistente, e liquidação, quando
prevista, precisa pagar spread, taxas e respeitar liquidez. Não conceder
liquidação integral garantida onde o livro não suporta a quantidade.

**Cuidado com o pipeline novo:** `segment_id` identifica continuidade de dados
retrospectivamente. Liquidar no último minuto *antes de uma lacuna inesperada*
ou fornecer o tempo até essa lacuna informa o futuro ao agente. Segmentos não
são automaticamente episódios de uma estratégia executável. Para experimentos
condicionais com janelas completas, usar horizonte fixo anunciado no reset e
declarar a seleção da amostra. Para simular operação contínua, definir o que
ocorre quando a lacuna é efetivamente detectada, sem inventar preços durante ela.
O final de sessão é conhecido; o aparecimento futuro de uma falha não é.

### 11. P1 — O stop está definido como perda de capital inicial, não drawdown

**Evidência:** linhas 624 e 715 usam `V_t < ε θ` e chamam a regra de drawdown.

**Problema:** se `θ` é capital inicial, é um piso de patrimônio. Drawdown é
queda em relação ao pico acumulado `H_t=max_{u<=t} V_u`.

**Correção:** escolher piso inicial ou drawdown verdadeiro. Para perda máxima
`d`, a segunda regra seria `V_t < (1−d)H_t`. Definir tolerância, inclusão de
custos e eventual liquidação. Não confundir a convenção negativa de drawdown
nas tabelas com a fração positiva usada no controle de risco.

## Achados sobre avaliação e relação com a implementação

### 12. P1 — Walk-forward não basta para proteger seleção de modelos

**Evidência:** linhas 758–768 definem treino/teste, sem validação interna.
Linhas 1031–1065 escolhem `γ`; linhas 1107–1132 escolhem o algoritmo com base
nas comparações reportadas.

**Correção:** separar ajuste/seleção do teste externo. Usar validação temporal
interna aos dados de treino ou seleção predefinida antes dos testes. Escolher
também janela, recência, limpeza e custos sem maximizar retorno no teste.
Usar sessões como unidade das divisões, datas efetivas e uma única divisão
global para todos os ativos, inclusive transferência entre ações. Trocar ticker
sem isolar o período não demonstra generalização temporal.

Histórico anterior ao início do teste pode servir de contexto se já conhecido,
mas recompensas/ações de treino não podem atravessar o teste. Não há necessidade
de impor arbitrariamente um embargo de `μ` minutos quando o contexto é todo
passado; se transições/horizontes se sobrepõem ao teste, é preciso removê-los.

A linha 836 começa o teste em 04/07, feriado. A divisão pode começar num feriado
como intervalo civil, mas não se deve tratá-lo como pregão. Percentuais da tabela
precisam ser calculados dos dados finais e dizer se medem linhas, minutos ou dias.
O risco de selecionar estratégias pelo mesmo backtest usado para justificá-las
é discutido por [Bailey et al.](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf).

### 13. P1 — Baselines, capital, horizonte e estatística precisam ser pareados

**Evidência:** linhas 1149–1193 chamam resultados de diários, enquanto o método
descreve blocos de teste; linhas 1298–1313 comparam com índices por período.
O código usa buy-and-hold sem custos, com ações fracionárias, desde a primeira
linha, enquanto o agente espera uma janela de 50 observações e usa inteiros.

**Correção:** baseline principal no mesmo universo, capital, período negociável,
disponibilidade de dados, warm-up, custos e mecanismo de execução. Incluir
caixa e buy-and-hold/igual ponderação intradiário com fechamento compatível.
Índices podem ser referências secundárias com exposição/horizonte diferentes,
não prova isolada de habilidade. Definir qual Nasdaq, preços versus retorno
total, dividendos, ações corporativas, fonte e datas; não comparar média de
retornos de folds com retorno composto de todo o intervalo.

O código `evaluate_significance.py:76–101` remove ausências separadamente e usa
teste independente de Welch ou Mann–Whitney para séries que vêm dos mesmos
períodos. Welch é rotulado como Student. [Mann–Whitney requer amostras independentes](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.mannwhitneyu.html);
o [teste t pareado](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.ttest_rel.html)
é distinto. Trocar simplesmente para um teste pareado também não resolve
autocorrelação, múltiplas comparações e número pequeno de períodos.

Recomendação: diferenças pareadas por sessão fora da amostra, IC por reamostragem
de blocos temporais, efeitos econômicos e ajuste para múltiplas comparações.
Manter separadas incerteza por período de mercado e por semente de treinamento;
várias sementes no mesmo dia não equivalem a vários dias independentes. Um
bootstrap ingênuo das sementes ou de cinco folds não resolve dependência temporal.
Relatar retornos líquidos, curva de patrimônio, drawdown e dispersão entre
sementes; não chamar desvio entre lucros de folds de volatilidade do portfólio.
A relevância de intervalos e variabilidade entre treinamentos é documentada por
[Agarwal et al. (2021)](https://arxiv.org/abs/2108.13264).

### 14. P1 — Ablação não deve modificar o mercado simulado

**Evidência:** linhas 1071–1099 retiram grupos de informações. No código,
`ablation_test.py:146–153,190–194` zera colunas do próprio dataframe de mercado
antes de enviá-lo ao ambiente; preços/quantidades podem servir tanto à política
quanto à execução. A lista `FEATURES` concatena acidentalmente
`Last_10_PricesLast_10_Shares` por falta de vírgula. A opção individual de preço
citada na tabela não consta dessa lista.

**Correção:** dados de mercado, fills, marcação e baseline devem permanecer
idênticos entre ablações. Mascarar somente a construção da observação, retreinar
com orçamento e sementes pareados, e registrar grupos realmente removidos.
A informação de carteira pode revelar preços indiretamente; declarar essa
limitação ao interpretar uma ablação como isolamento de informação.

### 15. P1 — O código disponível não implementa a comparação descrita

**Evidência confirmada por inspeção de AST, sem importar/executar treinamento:**

- `training.py:51–59` seleciona `model_class`, mas `training.py:77` sempre
  instancia `PPO`; `testing.py:48` sempre carrega PPO. Rótulos A2C/SAC/DDPG não
  bastam para comparar algoritmos. Não é possível concluir daqui qual código
  produziu a tabela antiga.
- `rl_model.py:1–9,250–287` usa preço agregado para compra/venda, slippage
  percentual fixo, não impõe profundidade, não aplica `LATENCY_STEPS`, não
  liquida a carteira diariamente e usa recompensa diferente das três descritas.
- `convert_to_dataset.py:128–137` agrega ciclos por um ativo de referência e
  faz médias, sem preservar os cinco níveis por lado e dez negócios do paper.
- A implementação de treino usa `learning_rate=5e-5`, não o `1e-5` da linha 750;
  não há justificativa para tratar todas as configurações como reproduzidas.

**Correção:** reconstruir experimentos com manifesto de algoritmo efetivamente
instanciado, versão, hiperparâmetros, semente, dados e código. Não portar esses
defeitos ao ambiente novo nem usar tabelas antigas para validar sua correção.

### 16. P1/P2 — Afirmações estatísticas e de realismo excedem a evidência

As diferenças 16,0%, 16,1% e 16,3% das linhas 1050–1065, sem incerteza ou
medidas comportamentais, não demonstram influência “significativa”, maior
estabilidade ou reatividade. PPO superior em uma média também não demonstra
que a causa seja clipping. Essas hipóteses requerem dados e desenho específico.

O Mann–Kendall em retornos acumulados, linhas 993–1023, precisa considerar
dependência temporal: ser não paramétrico não elimina autocorrelação. Ver
[Hamed e Rao (1998)](https://doi.org/10.1016/S0022-1694(97)00125-X).
P-valores numéricos iguais a zero devem ser apresentados com limite de precisão,
não como probabilidade exatamente zero. A análise pode ser descritiva sem
transformar essas tendências em evidência da eficácia do agente.

Coletas por minuto são intradiárias, mas não bastam para sustentar uma alegação
de HFT/execução de baixa latência (linhas 168, 399 e 1321). A promessa de
realismo com custos na introdução contrasta com tratá-los como trabalho futuro
na linha 1331. A alegação de “primeira evidência” na linha 97 requer revisão
bibliográfica específica; esta auditoria não confirma prioridade científica.

As alegações de autorização/redistribuição nas linhas 399 e 1337 precisam
corresponder à autorização efetivamente arquivada no projeto. Não foi feita
interpretação jurídica nem inferida ausência de autorização. Um site dinâmico
atual não permite reconstruir automaticamente a mesma amostra histórica de
2025, ao contrário do que a linha 1337 sugere.

## Formulação mínima proposta para orientar a próxima implementação

Esta seção é uma **proposta técnica**, não uma declaração de método já
executado. Primeiro confirmar o tratamento dos relógios e qual regime de
backtest os dados suportam. Até essa confirmação, o simulador pode ser
desenvolvido e validado em dados sintéticos, sem alegações de desempenho real.

1. **Escopo:** replay de snapshots periódicos, long-only, sem alavancagem,
   ações inteiras, caixa compartilhado e agente pequeno sem influência sobre
   a trajetória histórica. Tornar explícita a hipótese de impacto desprezível;
   uma restrição de participação não a comprova.
2. **Cronologia:** observar somente dados disponíveis até a decisão. Declarar
   execução posterior — por exemplo no snapshot seguinte no replay idealizado —
   e separar essa latência do atraso de fonte. Quantidade desejada usa dados
   observados, nunca o preço futuro de execução. O simulador pode usar o próximo
   livro para preencher uma ordem, mas a política não pode observá-lo antes.
3. **Observação:** histórico causal de cinco níveis por lado e dez negócios
   por ativo, idades das capturas/negócios, relógio de sessão, carteira atual e
   horizonte conhecido. Separar histórico de mercado do estado atual da carteira
   em vez de inventar um histórico de posições. Estatísticas ajustadas no treino.
4. **Ação:** conservar intenções incrementais em `[-1,1]^N`, aplicar zona neutra,
   depois converter em ordens viáveis. Executar vendas limitadas às posições;
   repartir o orçamento de compra incluindo taxas por regra determinística
   declarada. Ordem fixa arbitrária de tickers não deve decidir silenciosamente
   quem recebe todo o caixa. A variante de pesos alvo seria outro modelo.
5. **Contabilidade:** se `q_i` é a quantidade efetivamente executada, positiva
   para compra e negativa para venda, e `p̄_i` é o VWAP do lado apropriado:

   $$h_i'=h_i+q_i,\qquad
     C'=C-\sum_i q_i\bar p_i-\mathrm{fees},\qquad
     V'=C'+\sum_i h_i'm_i'.$$

   Impor caixa e posições não negativos. `m_i'` é referência de marcação, não
   fill. Se a execução ocorre no próximo snapshot, com patrimônio anterior
   `V=C+Σh_i m_i`, a identidade de auditoria é:

   $$V'-V=\sum_i h_i(m_i'-m_i)
          +\sum_i q_i(m_i'-\bar p_i)-\mathrm{fees}.$$

   Ela distingue variação das posições existentes de custo de execução; manter
   uma posição recebe sua variação de valor mesmo sem novo negócio. Salvar
   fills por lado/nível, quantidades rejeitadas, caixa e posições por transição.
6. **Recompensa:** principal `r=α(V'−V)/θ`, sem cobrar novamente taxas já
   descontadas de caixa. Incluir custos de liquidação final quando aplicável.
   Recompensas alternativas devem ser tratadas como objetivos distintos.
7. **Episódios:** sessões ou horizontes fixos conhecidos, com warm-up suficiente
   e nenhuma decisão depois do término. Para janela `μ`, pelo menos `μ+1`
   observações são necessárias para observar a janela e executar uma transição
   posterior. Não transformar segmentos retrospectivos de duração variável em
   encerramento antecipadamente conhecido. Liquidar dentro das regras ou
   reportar posição residual; não apagar carteira nem omitir seu risco.
8. **Avaliação:** divisão global por sessões, seleção temporal interna e teste
   externo sem atualização; orçamento e sementes documentados por algoritmo;
   baselines nos mesmos instantes e condições; agregação de retornos por uma
   curva de capital claramente definida. Relatar cobertura e seleção de amostra.

## Critérios para liberar experimentos

Antes de treinar, validar no simulador: caixa/posições nunca negativos; compra
no ask e venda no bid; fills limitados à profundidade; custos cobrados uma vez;
ausência de lucro em ida e volta com preços constantes e custos positivos;
ganho/perda de uma posição mantida; separação observação/execução; nenhuma
informação futura na normalização; regras terminais sem venda retrospectiva
antes de lacunas; ablação alterando só observações; e instância correta de cada
algoritmo. Os contraexemplos numéricos dos achados 5 e 6 foram conferidos com
Python, e os achados de seleção de algoritmo/lista de ablação por AST.

**Sequência recomendada:** corrigir a especificação econômica e temporal;
implementar o núcleo contábil e execução com testes sintéticos; integrar
observações e episódios; só então conectar treinamento e refazer comparações.
As tabelas, a discussão e as conclusões antigas devem ser substituídas pelas
novas evidências, sem usá-las como alvo a reproduzir.

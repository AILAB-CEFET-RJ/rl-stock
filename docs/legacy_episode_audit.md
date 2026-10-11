# Auditoria da duração dos episódios no pipeline legado

Inspeção em 08/10/2026 do código presente no workspace. Não foram lidos CSVs
processados da dissertação, executados treinamentos ou reaproveitados resultados.

**Conclusão: o caminho legado inspecionado não impõe episódios por hora nem
por pregão. O episódio percorre o DataFrame inteiro de cada partição recebida,
sem liquidação obrigatória no fechamento ou no fim do episódio.**

Os blocos de 60 transições da proposta v1 foram introduzidos na nossa revisão,
não demonstrados como escolha de Fernando. Eles já foram substituídos pelo
[protocolo v2 por pregão](protocol_day_trading_revision.md).

## Caminho dos dados

| Etapa | Código | Efeito na duração |
|---|---|---|
| Entrada principal | [main.py](../rl_boleta/main.py#L36) | Lê um CSV agregado, remove faltantes e aplica `TimeSeriesSplit` com cinco divisões por índices de linhas |
| Partições | [main.py](../rl_boleta/main.py#L49) | Escreve cada partição inteira em `temp_train.csv` / `temp_test.csv`; não agrupa por hora ou sessão |
| Preparação | [data_treatment.py](../rl_boleta/data_treatment.py#L55) | Ordena cada partição por `File Date`, remove faltantes e apaga `File Date` e `Day` antes de entregar o DataFrame ao ambiente |
| Treino | [training.py](../rl_boleta/training.py#L63) | Instancia um ambiente com o DataFrame completo da partição; `len(df)*50` é orçamento de aprendizagem, não duração de episódio |
| Reset | [rl_model.py](../rl_boleta/rl_model.py#L207) | Restaura capital, zera posições e inicia o índice em 50, após a janela de observação |
| Passo e término | [rl_model.py](../rl_boleta/rl_model.py#L249) | Avança uma linha; termina quando o índice atinge `len(df)-1`, sem consulta a hora, data ou calendário |
| Avaliação | [testing.py](../rl_boleta/testing.py#L77) | Para no primeiro `done` e usa o patrimônio marcado informado, sem venda terminal obrigatória |

O caminho de ablação também não define sessões: usa um corte 80%/20% por
posição de linha ([ablation_test.py](../rl_boleta/ablation_test.py#L167)) e entrega
as partições às mesmas funções de treino/teste.

A conversão multiativo define ciclos pela recorrência de um ativo de referência
e calcula um timestamp médio do ciclo; não faz agregação horária nem gera
pregões como episódios ([convert_to_dataset.py](../rl_boleta/convert_to_dataset.py#L126)).
Além disso, `main.py` faz a divisão antes da ordenação explícita realizada em
`process_data`: a ordem cronológica global depende da ordem já existente no CSV.
Ordenar posteriormente cada partição não garante fronteiras globais corretas.

## Contagens que não representam duração

- `OBSERVATION_WINDOW=50`: cinquenta linhas de contexto; não cinquenta minutos
  de negociação nem tamanho do episódio.
- `timesteps=len(df)*50`: orçamento total solicitado ao algoritmo.
- `n_steps=2048`: parâmetro de coleta de rollout do PPO; o critério de término
  do ambiente continua sendo o final do DataFrame.
- `Time_Hour`, `Time_Minute`, `Time_Second`: entradas da observação, não regras
  de término ou encerramento de posições.

Com L linhas após `process_data` e L >= 52, o código inicia em 50, processa os
índices 50 até L−2 e executa L−51 passos. A última linha, L−1, não é usada como
preço de execução nesse percurso. Não se pode converter essa contagem em horas
sem verificar os timestamps e lacunas do arquivo; uma linha não é garantia de
um minuto consecutivo.

## Evidência sintética complementar

Foram extraídos por AST os métodos `reset`, `step` e `_take_action`, sem alterar
seus corpos, e executados contra um DataFrame sintético. O construtor foi
bypassado; a geração de observações e o objeto que informa sua forma foram
substituídos por stubs. Não se importou Gym, o treinador ou o script principal.
Isso verifica o controle de estado desses métodos, não a execução integral do
pipeline legado.

O caso tem 56 linhas com preços constantes de US$ 100 e duas datas artificiais.
A janela tem 50 linhas. Uma única intenção de compra é seguida de holds:

| Linha processada | Data sintética | Posição após o passo | done |
|---:|---|---:|---|
| 50 | 03/03/2025 | 4 ações | falso |
| 51 | 04/03/2025 | 4 ações | falso |
| 52 | 04/03/2025 | 4 ações | falso |
| 53 | 04/03/2025 | 4 ações | falso |
| 54 | 04/03/2025 | 4 ações | verdadeiro |

As datas sintéticas são rótulos de conferência, ignorados pelos métodos assim
como não há consulta a data no ambiente de produção. A posição sobrevive à
mudança de data e permanece no término. O saldo terminal é US$ 9.599,3998,
com quatro ações e patrimônio marcado de US$ 9.999,3998. Chamar `reset()` devolve
a carteira ao capital inicial de US$ 10.000 e zero ações, sem executar uma venda
ou registrar custos de saída. Isso é uma reinicialização de simulação, não uma
liquidação econômica.

Artefatos locais em `results/legacy_episode_audit_2026-10-08/`:
`probe.py`, `probe_result.json` e `source_hashes.json`. O hash do módulo legado
está preservado no resultado. Esses artefatos não são experimentos financeiros
nem dependem dos dados históricos.

## Implicações e limites

Se uma partição contiver vários dias, o ambiente pode manter posições entre
esses dias e tratar saltos temporais como passos consecutivos. Não há regra
que impeça isso. Logo, o código inspecionado **não impõe as restrições do estudo
de day trading**, mesmo que uma política particular eventualmente venda antes
do fechamento por decisão própria.

O resultado terminal é marcado com ações possivelmente abertas. Ele não
representa necessariamente caixa após liquidação. A baseline legada usa ainda
outros instantes de entrada/avaliação e não cobra custos; essa comparação não
resolve a ausência de fechamento econômico do agente.

Não é possível concluir, a partir desta inspeção, que a dissertação ou as tabelas
antigas foram geradas exatamente por esta versão. Não inspecionamos seus dados
processados ou checkpoints, conforme o escopo acordado. A duração em calendário
dos episódios efetivamente executados e as motivações do autor permanecem
indeterminadas. O achado verificável é o comportamento do código disponível.

A nova formulação por pregão deve continuar independente desses resultados:
calendário explícito, carteira única por sessão, saída pré-fechamento sujeita a
liquidez, resíduos reportados e truncamento sem transações fictícias.

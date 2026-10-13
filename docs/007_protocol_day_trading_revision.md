# Revisão do protocolo: um episódio por pregão

> Registro **007** · Data de referência: **2026-10-08** · [Índice](README.md)
> Anterior: [Registro 006](006_economic_kernel.md) · Seguinte: [Registro 008](008_legacy_episode_audit.md)

Revisão de 08/10/2026, após discussão sobre a consistência com day trading.
A [versão 2 em JSON](../configs/experimental_protocol_v2.json) e o
[manuscrito ativo](../paper/paper.tex) substituem a proposta principal de blocos
curtos da versão 1. A versão 1 foi preservada como histórico, não como protocolo
vigente. Nenhum treinamento foi executado.

## Problema corrigido

A proposta anterior encerrava e reiniciava a carteira em blocos de 60 transições.
Isso respeitava a ausência de posições entre dias, mas acrescentava uma
obrigação de saída e um reinício de capital dentro do mesmo pregão. Essas regras
mudavam o problema estudado por conveniência de cobertura dos dados.

O estudo principal passa a ter **um episódio por sessão**, com uma única carteira
compartilhada entre os 18 ativos. Não há zeragem a cada hora, reinício de capital
intradiário ou retomada após lacunas. O capital é resetado apenas entre sessões
nos experimentos de capital fixo, sem alegar retornos compostos.

## Cronograma explícito

Horários em `America/New_York`, na interpretação temporal que ainda precisa ser
justificada para os dados históricos. A grade de calendário permanece com
390 pontos normais e 210 no fechamento antecipado, incluindo a abertura e
excluindo o horário exato de fechamento.

| Evento | Pregão normal | 03/07/2025 |
|---|---|---|
| Abertura; carteira apenas em caixa | 09:30 | 09:30 |
| Primeiro midpoint necessário como referência passada | 09:31 | 09:31 |
| Primeira janela de 20 observações transformadas | 09:32–09:51 | 09:32–09:51 |
| Primeira decisão | 09:51 | 09:51 |
| Primeiro fill possível | 09:52 | 09:52 |
| Última intenção discricionária | 15:57 | 12:57 |
| Último fill ordinário possível | 15:58 | 12:58 |
| Observação reservada à liquidação | 15:59 | 12:59 |
| Fechamento oficial | 16:00 | 13:00 |
| Transições do núcleo após warm-up | 368 | 188 |
| Pontos brutos necessários, de 09:31 à saída | 389 | 209 |

O ponto de abertura 09:30 continua no relatório de cobertura, mas não é exigido
para produzir a primeira janela: as primeiras capturas podem chegar durante o
minuto iniciado às 09:30. No ponto 09:31, só se usam capturas já recebidas desde
a abertura, respeitando a idade máxima. Essa escolha fixa permite formar a
janela sem exigir uma captura exatamente no segundo da abertura. Não se usam
capturas pré-abertura, dados da véspera, zero padding ou valores futuros.

A carteira permanece no capital inicial durante o warm-up e só então passa
a negociar. As conclusões serão sobre negociação após esse warm-up declarado,
não atuação desde o primeiro segundo do pregão. O horário não se desloca
conforme a primeira sequência completa encontrada em cada dia.

A saída usa o último ponto da grade, um minuto antes do fechamento. Não representa
o leilão de encerramento e não garante vender todas as ações: custos, participação
e profundidade continuam limitando os fills. Resíduos permanecem marcados e
identificados como falha da restrição de zeragem.

## Lacunas e denominadores

Todos os 105 pregões previstos permanecem nos denominadores de cobertura:
63 de treino, 20 de validação e 22 de teste. O reajuste final reúne as 83 sessões
de desenvolvimento. Há no máximo um episódio por pregão, substituindo os antigos
tetos de 252/80/86 blocos.

- Sem arquivo ou sem a sequência fixa de warm-up: registrar sessão ausente ou
  não iniciável. Não iniciar mais tarde em um segmento conveniente.
- Após início válido: a primeira falha de observação, expiração ou ausência de
  algum ativo trunca o episódio; cancelar a intenção pendente e preservar a
  última marcação e posições. Não inventar uma venda antes da lacuna.
- Dados posteriores à falha: podem descrever cobertura, mas não reiniciam a
  carteira no mesmo dia.
- Sem observação reservada à saída: truncar; não antecipar retroativamente
  a liquidação para a última cotação disponível.
- Stop econômico: tentar encerrar com as regras usuais, registrando custos e
  resíduos. Isso é um término econômico, distinto de falta de dados.

A avaliação tenta todas as sessões de teste iniciáveis. O resultado financeiro
principal usa um subconjunto **comum e independente da estratégia**, que exige
cobertura de todos os pontos necessários de 09:31 à saída. A disponibilidade
posterior não é fornecida à política. Essa seleção retrospectiva é declarada:
a comparação é condicional à cobertura, não uma estimativa de todos os dias.

Mesmo que um agente acione stop antes de uma lacuna posterior, a classificação
de cobertura da data não muda para favorecê-lo. Em datas com cobertura integral
necessária, stops e falhas de zeragem permanecem nos resultados financeiros.
Truncamentos são reportados separadamente, com duração observada, retorno parcial
marcado e resíduos; não entram como se fossem retornos completos ou liquidados.

## Viabilidade e o que permanece

A referência exige pelo menos 20 sessões avaliáveis de treino, 10 de validação
e 10 de teste. Se falhar, registrar que o acervo não sustenta o estudo principal
proposto. Não substituir pregões por segmentos curtos, aumentar tolerâncias,
reduzir horizonte ou baixar os mínimos silenciosamente. Qualquer mudança de
escopo deve ser justificada e versionada antes da seleção por desempenho.

A contagem real de sessões que passam nessa exigência **ainda não foi calculada**
para o período completo com calendário. Os pilotos de cobertura não demonstram
viabilidade de episódios por pregão. Os relógios, o atraso informado e a bolsa
histórica continuam pendências para interpretar um replay financeiro.

Foram mantidos divisão temporal, universo, capital, regras econômicas, taxas,
participação, janela, idade máxima, buscas, sementes, orçamentos, baselines,
ablações e estresses. A amostragem de treino passa a escolher uniformemente uma
sessão avaliável e reproduzi-la como um único episódio. A seleção usa a média
dos resultados por sessão e semente, sem média entre blocos intradiários.

A limitação inferencial de julho permanece: há arquivos em no máximo 17 das
22 datas previstas; o relatório continua descritivo sob o limiar de 20 sessões
pareadas estabelecido no protocolo. Os orçamentos de transições não implicam
a mesma quantidade de episódios da versão anterior, pois os episódios agora
são mais longos e variam com o fechamento.

Blocos intradiários ficam **adiados para estudo secundário com protocolo próprio**.
Eles não substituem a pergunta principal nem podem ser misturados com retornos
por sessão para compensar falta de dados.

## Alinhamento do código e verificação

`economic_kernel.Config` agora exige `horizon` explicitamente, sem padrão de
60 transições. O [controlador por pregão](009_session_replay.md) calcula agora o
horizonte pelo calendário e pelo fim do warm-up, constrói a janela causal e
registra a cobertura requerida de cada sessão. A [camada de observações e PPO](010_observations_and_training.md)
implementa agora a representação de referência e a integração sintética inicial.
A [integração dos quatro algoritmos](011_four_algorithm_integration.md) foi validada
sinteticamente. A geração do manifesto agregado e o executor histórico ainda
precisam ser integrados.

Foram acrescentados testes sintéticos para um pregão normal de 368 transições,
um pregão curto de 188, ausência de encerramentos intermediários, horizonte
obrigatório e falta da observação terminal sem venda fictícia. Os demais testes
de execução e contabilidade continuam aplicáveis.

A documentação antiga da etapa 5 foi marcada como substituída. O registro do
núcleo e o README apontam para a versão 2. A cópia anterior do manuscrito está
em `paper/archive/paper_pre_day_trading_protocol_2026-10-08.tex`, e o patch em
`paper/archive/paper_day_trading_protocol_revision_2026-10-08.patch`.

Validação concluída: 32 testes do núcleo econômico e 71 testes da suíte completa
passaram. Os horários, horizontes e tetos de episódios do JSON foram conferidos
contra o calendário implementado. O PDF foi recompilado com 28 páginas e
42 referências, sem citações ou referências internas indefinidas. Persistem
os avisos tipográficos menores já registrados, incluindo um excesso vertical
de cerca de 4 pontos. Nenhum dado histórico ou resultado de treino foi alterado.

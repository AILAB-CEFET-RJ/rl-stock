# Controlador de episódios por pregão

`rl_boleta/session_replay.py` aplica o protocolo v2 ao núcleo econômico. Não
depende de Gym, pandas ou de resultados anteriores. Os testes usam livros
sintéticos; nenhum agente foi treinado e nenhuma conclusão de desempenho real
decorre dessa implementação.

## Regras implementadas

- Um episódio por data do calendário verificado de março–julho de 2025. O
  calendário usa Nova York, incluindo horário de verão, feriados e fechamento
  antecipado de 3 de julho. Os quadros são comparados em UTC.
- Cada episódio começa com o capital configurado, sem posições. A mesma carteira
  atravessa as horas do pregão, sem reinicializações intermediárias.
- A primeira decisão ocorre às 09:51, após uma referência às 09:31 e vinte
  quadros de mercado de 09:32 a 09:51. A observação contém esses vinte quadros,
  a referência defasada, a carteira atual e o tempo restante. Cada passo move a
  janela um minuto, sem incluir quadros futuros.
- A intenção discricionária é executada no minuto seguinte. A última intenção
  ocorre às 15:57; sua execução às 15:58. Às 15:59 ocorre apenas a liquidação,
  com profundidade disponível e taxas. Em 3 de julho, esses horários são 12:57,
  12:58 e 12:59. Os horizontes após o aquecimento são 368 e 188 transições.
- Ausência, universo incompleto ou captura com idade superior ao limite durante
  o aquecimento impede o início, sem deslocar a janela. Depois do início, a
  primeira falha trunca o episódio, cancela a intenção pendente e preserva a
  última marcação e as posições. Não há retomada nessa data nem venda retroativa.
- Liquidação sem profundidade suficiente pode deixar resíduos: o resultado
  informa `flat=False`. Esses casos permanecem na avaliação se a cobertura
  exigida for completa.

`SessionResult` separa `startable`, `evaluable`, falhas de cobertura, transições
e carteira final. A cobertura de todos os minutos exigidos é calculada
independentemente da estratégia, inclusive quando o stop econômico ocorre antes
de uma lacuna posterior. Esse indicador retrospectivo não é passado à política.
`financial_return` retorna `None` para datas sem cobertura completa ou truncadas.
Os chamadores devem conservar esses registros nos denominadores de cobertura,
sem converter `None` em retorno zero.

## Interface e limites

```python
from datetime import date
from rl_boleta.session_replay import DailySessionReplay, read_market_csv

controller = DailySessionReplay(("AAPL", "MSFT"))
day = date(2025, 3, 3)
frames = (f for f in read_market_csv("market.csv", controller.tickers)
          if f.session_id == day.isoformat())
result = controller.run(day, frames, lambda observation: (0, 0))
```

O exemplo mantém caixa. O CSV deve vir do preparador revisado; arquivos legados
sem livros e relógios explícitos são rejeitados. Para uma data sem nenhum quadro,
passar `[]` registra `not_startable`. O chamador ainda deve percorrer todas as
datas previstas do split; o controlador não seleciona datas nem aplica os
limiares mínimos de viabilidade do protocolo.

Uma instância aceita uma tentativa por data; outra estratégia ou semente usa
outra instância. Quadros misturados entre datas, duplicados, fora da grade,
capturas anteriores à abertura ou identidades contraditórias geram erro de
integridade. Os dados são verificados antes da chamada à política; carregar o
dia inteiro não permite à política consultar sua cobertura futura.

As observações deste controlador contêm livros brutos. A nova
[camada de codificação e integração PPO](observations_and_training.md) combina
esses livros com os negócios do CSV, normaliza as features e oferece um
adaptador Gymnasium para sessões completas. A [integração dos quatro algoritmos](four_algorithm_integration.md)
foi validada sinteticamente; o executor de experimentos históricos permanece
pendente. A leitura do CSV não certifica sua
proveniência ou `training_ready`; os manifestos e as pendências dos relógios
históricos continuam obrigatórios antes dos experimentos reais.

O construtor de `MultiAssetReinforcementLearningEnv` agora falha explicitamente:
os scripts antigos não podem produzir novos experimentos em partições de linhas.
A auditoria e os hashes em `legacy_episode_audit.md` descrevem a versão anterior
a esse bloqueio. Seu código remanescente serve apenas como referência histórica.

## Validação

```sh
python -m unittest discover -s tests -p test_session_replay.py -v
```

Quinze testes verificam calendário, causalidade da janela, persistência da
carteira entre horas, custos da saída, lacunas e resíduos, cobertura independente
do stop, reinício apenas em nova data, contrato CSV e bloqueio do construtor
legado, incluindo a passagem do CSV produzido pelo preparador ao replay diário.
Na trajetória constante de exemplo, comprar nove ações a US$ 101 e
vender a US$ 99, pagando 1 bp em cada lado, transforma US$ 1.000 em US$ 981,82.

Validação em 08/10/2026: os 15 testes do controlador passaram com Python 3.12.4;
a suíte completa passou com 86 testes no Python 3.11.13 do ambiente `ailab`.

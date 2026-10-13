# Revisão do objetivo e da admissibilidade para day trading

> Registro **028** · Data de referência: **2026-10-12** · [Índice](README.md)
> Anterior: [Registro 027](027_validation_selection.md) · Seguinte: [Registro 029](029_exit_capacity_audit.md)

Revisão de 12/10/2026, após o diagnóstico curto de validação e antes da
seleção com orçamento completo. Julho permanece protegido de avaliação de
estratégias. Esta é uma emenda metodológica declarada, não um protocolo
registrado antes de qualquer inspeção da validação. Os artefatos anteriores
continuam preservados sob suas especificações originais.

## Problema encontrado

A recompensa atual é a variação do patrimônio marcado, líquida das taxas.
Com gamma=1, sua soma telescopa até o patrimônio terminal marcado. Quando
restam ações, esse objetivo inclui seu valor estimado sem exigir que a venda
ocorra. Portanto, o objetivo de aprendizagem não impõe encerramento em caixa.

O núcleo permite vendas voluntárias ao longo da sessão e apresenta tempo
restante ao agente. Entretanto, a saída automática programada só tenta vender
no ponto final (15:59, ou 12:59 no pregão reduzido). Isso permite inclusive
comprar no penúltimo ponto de execução, deixando apenas uma tentativa automática
para sair. O stop já repete tentativas enquanto há posições; o encerramento
programado ainda não possui uma fase equivalente de redução de inventário.

As falhas observadas são de execução do encerramento, não de transferência
jurídica de títulos/dinheiro após uma negociação já executada. Essa segunda
acepção de liquidação é tratada na seção sobre conta e settlement.

A possibilidade de não conseguir vender rapidamente também existe em mercados
reais, conforme a [FINRA, regra 2270](https://www.finra.org/rules-guidance/rulebooks/finra-rules/2270).
Isso justifica representar a falha; não autoriza garantir uma venda artificial
nem concluir que nossas lacunas de coleta sejam interrupções reais do mercado.

## Objetivo revisado e regra de admissibilidade

A proposta é maximizar retorno líquido realizado, sujeito a inventário zero
até o encerramento programado, dentro da execução modelada. Não basta preferir
um modelo com menos resíduos se ele ainda viola essa restrição.

Para a seleção, um candidato deve cumprir o encerramento em todas as datas
comuns de validação, em todas as três sementes. Exigir inventário inteiro zero
é uma consequência do objetivo escolhido; não se escolhe uma tolerância de
falhas com base no retorno dos candidatos. Esta é uma decisão experimental,
não um requisito da FINRA para seleção de modelos.

O código separa duas condições:

- `eligible`: ajuste e métricas completos, com todas as sementes/datas.
- `day_trading_admissibility.admissible`: todos os outcomes terminam em caixa,
  com inventário zero, status econômico concluído e retorno realizado finito
  consistente com o retorno marcado.

Um stop encerrado em caixa pode passar, mesmo com prejuízo. Uma posição residual
não passa, mesmo com lucro marcado. A seleção completa filtra candidatos,
nunca sessões: conserva os resultados e motivos de falha de todos os candidatos.
Entre os admissíveis, o score marcado coincide com o realizado; os desempates
anteriores continuam. Se nenhum passar, o algoritmo/cenário fica sem escolha e
não recebe reajuste final ou buscas extras para obter sucesso.

A regra comprova cumprimento apenas na amostra de validação observada. Não
certifica probabilidade de falha zero fora dela. No reajuste e teste, conservar
as dez sementes e todas as datas; nenhuma falha permite escolher outra semente,
retreinar após ver julho ou reportar apenas dias bem-sucedidos. Resíduos no teste
impedem interpretar a média marcada daquele método como retorno realizado de
uma estratégia que cumpriu day trading em todos os dias. Reportar cumprimento,
patrimônio marcado e resíduos com seus denominadores completos.

Baselines passam pela mesma avaliação. Caixa é controle de cumprimento trivial,
não evidência de vantagem econômica. Se o benchmark ativo tiver resíduos, a
diferença marcada permanece diagnóstica; não vira comparação primária de ganhos
realizados, nem se restringe a interseção dos dias em que ambos venderam tudo.

## Preparação da saída e aprendizagem: trabalho necessário

A [auditoria de capacidade no treino](029_exit_capacity_audit.md) foi concluída.
Propõe 54 pontos de execução para a fase de saída, derivados do maior mínimo
finito do estresse concentrado observado. A [fase foi implementada com ativação explícita](030_wind_down_implementation.md)
e não garante capacidade futura; entradas já dentro dela permanecem em caixa,
conservando as datas comuns. A recompensa e o regime de conta continuam pendentes.

Adicionar uma fase comum de encerramento antes do ponto final: bloquear novas
compras e tentar vender o saldo em observações sucessivas, mantendo participação,
profundidade, taxas, frescor dos livros e consumo de cada snapshot. Ausência de
livro continua impedindo execução. Um snapshot reutilizado não fornece nova
capacidade. Não usar a liquidez futura para definir retrospectivamente o início.

A duração e eventuais limites causais de inventário devem ser especificados com
uma auditoria de capacidade nas datas de treino. Não fixamos arbitrariamente
cinco, quinze ou trinta minutos nem prometemos que qualquer janela garantirá
saída. A auditoria deve relacionar inventário inteiro, capacidade observada,
capital de referência e oportunidades restantes; as recomendações são
condicionais ao replay de uma única fonte. O horário deve acompanhar o fechamento
normal ou reduzido e o início tardio deve deixar oportunidades efetivas de saída.

A fase automática será igual para agentes e baselines e fará parte de treino e
avaliação. Uma política que só funciona graças a ela deve ser descrita como agente
com controlador de encerramento. Não se altera o fim da sessão nem se retoma
uma posição no pregão seguinte para obter artificialmente um fechamento.

A restrição também precisa aparecer no treinamento. O filtro de validação não
corrige por si só a recompensa atual. Precisamos implementar uma formulação
com restrição terminal ou um substituto de aprendizagem explicitamente
justificado e validado. Uma eventual penalidade de inventário é custo do
objetivo de aprendizagem, separado de taxas e retorno financeiro; seu peso
não deve ser ajustado para melhorar retornos de julho. Não tratar o valor inteiro
da posição residual como perda financeira realizada, nem apagá-la do balanço.

## Até onde o realismo é sustentado

| Situação | Tratamento atual ou revisão necessária |
| --- | --- |
| Caixa compartilhado, posições inteiras, sem posições vendidas nem alavancagem de exposição | Implementados; não certificam o regime da conta na corretora. |
| Spread, cinco níveis, participação, taxas e execução posterior à intenção | Implementados como regras de replay. |
| Venda parcial, observação indisponível, stop e resíduos | Implementados; manter motivos e inventário. |
| Preparar saída em vários instantes | Pendente; mesma regra para todos os métodos. |
| Impacto de nossas ordens e reação de outros participantes | Não identificáveis no histórico; replay exógeno é limitação. |
| Fila, caminhos de preços entre capturas e leilão de fechamento | Não reconstruídos; não presumir execução nesses eventos. |
| Interrupção real de negociação | Não inferir a partir de falha de coleta. |
| Buying power, recursos liquidados, restrições da conta e custos de financiamento | Regime ainda precisa ser declarado e verificado. |

A implementação credita imediatamente o resultado de vendas ao caixa reutilizável.
Isso não estabelece que seja uma conta cash real. No período de 2025, o ciclo
padrão norte-americano para a maioria dessas transações era T+1, segundo a
[SEC](https://www.sec.gov/newsroom/press-releases/2024-62). A SEC também distingue
restrições de pagamento em [contas cash](https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins/updated-9).
Não confundir não alavancar a exposição do agente com ter modelado essas regras.
Uma alternativa precisa declarar buying power intradiário e suas hipóteses;
outra exige separar recursos liquidados dos valores de vendas pendentes.
Essa escolha e os custos correspondentes precedem a nova especificação executável.

## Implementação e verificações desta revisão

O seletor ganhou a avaliação de admissibilidade e aplica o filtro no modo
completo. O modo diagnóstico continua permitindo ranking marcado e jamais
libera reajuste final. Planos completos recusam protocolos sem a revisão
`frozen_and_verified`; o rascunho atual e os protocolos copiados nos artefatos
antigos ainda não cumprem essa condição. Mudar apenas esse status não constitui
verificação: as regras e sua integração precisam estar implementadas, testadas
e representadas nos novos manifestos.

Não se reescrevem protocolos, normalizadores ou rankings históricos. A avaliação
nova dos relatórios existentes fica em um artefato próprio, sem treinamento
ou acesso a julho. Nenhum dos quatro candidatos PPO diagnósticos cumpre a
restrição; isso descreve 384 passos de treino, não o potencial dos algoritmos
com o orçamento de pesquisa.

O artefato é `results/v3_day_trading_admission_review_2026-10-12/assessment.json`.
Os hashes de todos os JSONs do diagnóstico original foram verificados. As
métricas anteriores dos quatro candidatos foram reproduzidas exatamente;
somente a avaliação de cumprimento foi acrescentada no novo arquivo. Das
28 trajetórias de baselines (14 por cenário), apenas caixa, em ambos os
cenários, cumpriu todas as datas. Isso também evidencia que a revisão da
saída deve atingir os controles ativos, não só os agentes.

A regressão passou com 224 testes, sem falhas ou testes pulados. Os testes
novos verificam que lucro com resíduos não supera um candidato admissível,
que nenhuma data é retirada, que um stop encerrado em caixa pode cumprir a
restrição e que flags inconsistentes não certificam encerramento.

Próximo passo: auditoria de capacidade de saída e especificação causal da fase
de encerramento, seguida de revisão de recompensa e regime de conta, testes
sintéticos e novo diagnóstico integrado. Depois congelar os manifestos e
planejar os recursos dos treinamentos completos. Atualizar o paper para a
especificação efetivamente implementada, preservando o v2 como histórico.

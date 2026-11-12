# Plano para melhorar as escolhas de build

Análise de 7 de novembro de 2026. Run confirmada pelo usuário: Normal 47, Shifting Sands VII, iniciada às 12:36:57 e encerrada em derrota às 12:40:55, horário de São Paulo. Registro local: `7eca379685894f18968110fc65930607`.

O objetivo é aumentar a chance de avançar e vencer com o equipamento disponível. A decisão deve comparar o que cada opção acrescenta ao conjunto: dano efetivo, quantidade de ativações, proteção, controle e caminhos futuros viáveis. O foco elemental continua útil, mas deve funcionar como preferência fundamentada no equipamento, com exceções justificáveis.

Este documento registra a análise original. Em 12/11/2026, os ajustes de campanha desktop foram implementados e receberam testes de regressão. Não foram executadas novas partidas para medir ganho de desempenho.

Implementado: recomposição e nova leitura direcionada de HP; cura substancial na fogueira abaixo de 60%; pressão de sobrevivência por perdas de HP e revive; comparação marginal e frequências conhecidas; fatos numéricos 0.631 com escopo explícito; previsão de desbloqueios por famílias distintas; reroll de opções de ganho muito baixo; reserva para ofertas úteis e liberação sob risco; diário local de alternativas e confirmações, ligado ao histórico por ID e versão da política. As estimativas continuam parciais e não representam DPS total nem probabilidade de vitória. O efeito real, a calibração por duração de batalha, a experimentação entre políticas e a implementação Android exigem validação posterior nas respectivas superfícies.

Validação da implementação em 12/11: **1.216 testes aprovados**, incluindo os casos novos de HP fragmentado, cura da fogueira da fase 47, limite de crítico, ganho incremental sem dupla contagem, abertura de uma cadeia, lojas e retenção dos registros. `git diff --check` sem erros. As mudanças são carregadas pelo iniciador `bin/roguebot.cmd`; o executável empacotado em `dist` não foi recompilado nesta etapa.

## Evidência desta run

Configuração registrada: `custom`, natureza mágica, fogo em primeiro lugar, estratégia `balanced` e suporte a cada cinco escolhas de dano. Equipamento: Lancelot 2★, Ember Staff épico, DragonPlate lendária, Blazing Band épico, Ring of Thorns épico, Voodoo Doll épico e Angel's Grace épico; pets Pyrehorn, Castlepod e Emberin. A árvore está marcada como incompleta. O jogo informado é 0.631; as regras locais são 0.630.

| Momento | Observação confirmada | Interpretação e limite |
| --- | --- | --- |
| 12:36:58 | Escolheu Fire Weapon Lv.2. | Fonte de fogo coerente com Ember Staff. |
| 12:37:18–22 | Rejeitou Sneaky Poison, Live Wire e Poison Strike, fez reroll e pegou Wizard Lv.2. | Manter o foco faz sentido; Wizard tem benefício mágico e custo físico que precisam ser avaliados sobre todas as fontes. Não há registro das outras cartas após o reroll. |
| 12:37:35–12:38:14 | Pegou taxa de crítico, dano crítico e o upgrade de dano crítico. | São escolhas potencialmente úteis. O log não permite afirmar que superaram as alternativas: ele não guarda todas as ofertas. |
| 12:37:50 | Primeira loja: 221 moedas; dois rerolls, um gratuito e um de 10; saiu com 211 e reserva de 285. | A reserva limita compras secundárias. Compras classificadas como principais podem usar a reserva; portanto, ela não bloqueou necessariamente uma habilidade central. Falta o estoque completo para avaliar a visita. |
| 12:38:18 | Primeira fogueira: HP registrado em 100%; escolheu Train. | Decisão coerente com a vida cheia. |
| 12:38:21 | Melhorou Fire Weapon para Lv.2+. | Upgrade útil. O diagnóstico anuncia oito desbloqueios ao contabilizar a segunda escolha de fogo, embora seja a mesma família; a regra real de contagem precisa ser confirmada. |
| 12:39:14 | Usou uma oferta de revive durante a luta. | Sinal concreto de dificuldade. Deve influenciar as decisões seguintes, sem pressupor regras de consumo ou reset ainda não observadas. |
| 12:39:30–12:40:13 | Pegou Resurrection e Combo Mastery; comprou Critical Mastery por 190 moedas. | Combo também pode aumentar ativações de arma. Critical Mastery envolve uma penalidade e merece avaliação contextual. Não há evidência de que alguma dessas escolhas tenha sido necessariamente errada. |
| 12:40:18–26 | Comprou DEF três vezes por 19; deixou a loja com 508 moedas. | Dinheiro restante, sozinho, não comprova erro. É necessário conhecer o estoque, o risco e o valor de outro reroll. |
| 12:40:31 | Segunda fogueira: a captura mostra **2,5m / 4,3m**, aproximadamente **58% de HP**; o JSON registra `hp: null`; escolheu Train, embora Rest oferecesse 45% de HP. | Falha de leitura reproduzida. A cura poderia levar a vida aproximadamente ao máximo. Mesmo com leitura correta, a regra atual só prioriza cura até 25%; as duas partes precisam mudar. |
| 12:40:34–55 | Melhorou taxa de crítico e perdeu na luta seguinte. | A sequência torna a segunda fogueira o caso mais forte para revisão de sobrevivência. Não prova que a cura garantiria vitória. |

Evidência original: `debug/events/event_20261107_124031_927581.png`, consultada em 07/11; o diretório de debug tem retenção limitada e a captura original já foi rotacionada. O [trecho de OCR preservado para regressão](../tests/fixtures/run47_rest.json) contém a vida dividida em `2,5m1` e `4,3m`. A implementação anterior de `health_fraction()` exigia a razão completa em um único bloco e retornava desconhecido. A primeira fogueira tinha leitura correta; não deve mudar automaticamente para Rest.

## O que aproveitar dos guias

Foram consultadas as abas Gear Builds, Skills, Combat Effects, Gear e Heroes da [planilha de theorycraft](https://docs.google.com/spreadsheets/d/1IjL88o5VqXyhSlihm_PkeTHqcwh1OSGcK_MOgIO6eb8/edit?gid=1734831678#gid=1734831678), além dos guias atuais de [habilidades](https://rogue.desoware.com/guide/skills), [desbloqueios e exclusões](https://rogue.desoware.com/guide/skill-links) e [fórmula de dano](https://rogue.desoware.com/guide/damage-formula). As páginas dinâmicas do site foram abertas no navegador; os guias de habilidades e desbloqueios indicam revisão para 0.631.

| Informação | Aplicação ao planejamento |
| --- | --- |
| Gear Builds organiza as builds em torno da arma e destaca crítico para fogo, combo para raio, duração de combate para ultimate e sobrevivência inicial para shuriken. | Usar como modelos de sinergia adaptados à conta. O próprio autor apresenta a tabela como theorycraft; equipamento ideal não deve virar exigência para jogar. |
| A planilha trata bônus de categorias como aditivos; o guia atual descreve multiplicação das fontes de bônus por tag e separa pools aditivos. | Registrar esse conflito. Preferir os dados atuais com evidência da versão e validar contra valores observados; não misturar as duas fórmulas. |
| A planilha diz que DoTs ignoram DEF; o guia atual distingue ticks do jogador e ticks aplicados pelos inimigos. | Modelar a direção do dano. No guia atual, os ticks do jogador ainda enfrentam a defesa do alvo; os inimigos podem atravessar a DEF/DR do jogador. |
| Fire Weapon Lv.2 e Lv.2+ têm probabilidades diferentes; o guia também identifica encadeamentos envolvendo Fireball e Flame Strike. | Avaliar quantas ativações extras cada escolha produz. Abrir uma cadeia pode valer mais que elevar um bônus existente. |
| As oportunidades futuras dependem de elemento, pré-requisitos, árvore, pets e exclusões; há relações incompletas entre versões das cartas. | Separar disponibilidade prevista de compatibilidade real. Uma carta efetivamente oferecida é evidência de disponibilidade, e ainda precisa passar pela avaliação de efeitos e custos. |

## Limites concretos da implementação

| Local | Comportamento atual | Consequência |
| --- | --- | --- |
| `roguebot/build.py`: `_line_score()` e `_score()` | O estágio da família e a preferência elemental aparecem antes da utilidade na tupla de ordenação. | Uma preferência estrutural pode decidir antes do ganho estimado. |
| `roguebot/build.py`: `take()` e `focus()` | A primeira escolha elemental compatível fixa o foco de `custom`. | O equipamento não estabelece sozinho o plano inicial; uma oferta inicial pode fixar uma direção pouco adequada. |
| `roguebot/build.py`: `choose()` | Faz reroll quando nenhuma carta entra no ranking. | Uma carta aceita, mas de pouco ganho, pode impedir a busca por uma peça central. |
| `roguebot/build_rules.py`: `utility()` | Soma pequenos valores heurísticos, frequentemente 1,0; usa números apenas quando a versão da conta corresponde à referência. | Os valores do log não representam ganho de DPS ou probabilidade de vencer. Nesta conta 0.631, a parte numérica 0.630 não é aplicada. |
| `roguebot/build_rules.py`: `future_unlocks()` | Os desbloqueios aparecem na explicação, sem entrar na escolha. | O bot consegue listar um caminho sem valorizar a carta que o abre. |
| `roguebot/build.py`: `type_picks` | Incrementa a contagem a cada aquisição, incluindo upgrades. | Mistura aquisições e famílias distintas. É preciso validar qual contagem o jogo exige para cada gate. |
| `roguebot/combat_context.py` | Distingue presença de fontes, mas não calcula frequência de ativações; `expected_rounds` não é alimentado pelo fluxo de campanha inspecionado. | Ter 10% ou 70% de um gatilho pode produzir o mesmo sinal de presença. Escalonamento por duração fica sem contexto observado. |
| `roguebot/combat_context.py`: `expected_hit()` | Há uma função de camadas de dano, mas ela não é chamada pelo ranking inspecionado. | A existência da fórmula não significa que as escolhas sejam otimizadas por ela. |
| `roguebot/screens.py`, `event_rules.py` e `shopping.py` | A leitura de vida exige um bloco completo; a cura usa limiar fixo de 25%. | A fogueira da run demonstra um caso em que o bot não avalia adequadamente a recuperação disponível. |
| `roguebot/play.py` e `metrics.py` | Registram principalmente a carta escolhida e o resultado final. | Não há replay completo das alternativas nem medida confiável de onde a tentativa terminou. |

Reprodução isolada, sem jogar: com a configuração da run e Fire Weapon Lv.2 aprendido, uma oferta sintética com Fire Weapon Lv.2+, Flame Strike e Firestarter escolhe o upgrade conhecido. As utilidades internas são 2,5, 2,75 e 2,5, respectivamente; o estágio da família prevalece. **Essa oferta é um experimento sobre a política e não foi observada nesta run.** Também não prova, por si só, que Flame Strike seria a melhor opção naquela situação.

## Política proposta

1. **Começar pelo equipamento e pelo objetivo.** Criar um plano inicial explicável usando arma, efeitos ativos, raridade, herói, árvore conhecida e modo. Para esta conta, começar com uma hipótese de fogo apoiado em ataques de arma e crítico, mantendo recuperação/proteção como necessidade tática. Respeitar uma preferência manual explícita. Não depender da obtenção de outro herói ou item.

2. **Acompanhar o estado que muda a decisão.** Guardar HP atual/máximo, escudo quando legível, confiança e instante da leitura, perdas recentes de vida, duração aproximada das lutas, revives observados, progresso e próximo perigo conhecido. Separar stats permanentes dos efeitos adquiridos na run para evitar dupla contagem. Atualizar versões por família, sem somar novamente o bônus total de um upgrade.

3. **Simular o acréscimo de cada opção ao estado atual.** Aplicar primeiro efeitos e custos confirmados. Comparar dano efetivo por alvo e por duração de luta, frequência dos gatilhos, recuperação, proteção e controle. Evitar que o simples fato de ser uma família conhecida determine o vencedor. Preservar vetos para efeitos que desmontam o motor da build.

4. **Dar valor ao próximo passo alcançável.** Usar um grafo pequeno de pré-requisitos e efeitos para distinguir fonte, multiplicador e peça de encadeamento. Valorizar desbloqueios relevantes quando há tempo e disponibilidade plausível para completá-los. Uma árvore parcialmente lida é informação desconhecida, não prova de ausência. Sem dados das ofertas, não inventar probabilidades para cartas futuras.

5. **Ajustar sobrevivência ao perigo.** A cadência de suporte pode servir como preferência, mas deve ceder diante de risco observado. Comparar Rest e Train pela cura efetiva, pelo próximo combate e pelo valor provável do upgrade. Antes de decidir com HP desconhecido, repetir leitura direcionada; usar estimativa visual validada ou a última observação recente com confiança explícita. Não converter desconhecido em vida cheia.

6. **Comparar escolha, reroll e compra no mesmo contexto.** Manter modelos próprios de custo: uma escolha gratuita obrigatória difere de uma compra opcional. Reroll precisa superar a melhor opção presente e o custo de oportunidade. Reserva de loja deve considerar alvos úteis e risco de morrer antes da próxima visita, além do progresso. Não gastar para zerar o saldo nem guardar para uma oportunidade futura irrealista.

7. **Permitir exceções limitadas ao foco.** Uma habilidade de outro elemento pode ser aceita por proteção, controle ou uma sinergia já ativa, quando seu benefício compensa a aquisição. Isso precisa de fonte, frequência e justificativa; não basta a raridade. Mudança completa de linha exige evidência de ganho suficiente para compensar os investimentos anteriores.

Uma avaliação inicial pode combinar ganho ofensivo, margem de sobrevivência, controle e valor de continuidade, descontando penalidades e custos. Cada termo deve ter unidade ou escala documentada. Sem modelo de combate calibrado, apresentar comparação relativa e confiança, sem chamar o resultado de probabilidade de vitória.

## Ordem de implementação

| Etapa | Entrega | Critério de aceite |
| --- | --- | --- |
| **P0 — estado e auditoria** | Leitura de HP com blocos separados, vírgula decimal e unidades; captura completa de ofertas e estoque; contexto de risco e versão da política em cada decisão. | A segunda fogueira desta run volta a produzir aproximadamente 58% de HP. A primeira continua em 100%. Cada nova escolha pode ser reconstruída com suas alternativas. |
| **P0 — fatos versionados** | Conciliar dados 0.631 por efeito, com fonte, evidência e valores desconhecidos preservados; revisar contagem de famílias versus upgrades. | Fire Weapon 2→2+ tem ganho calculável; o sistema não habilita indiscriminadamente toda a referência 0.630. Desbloqueios previstos não são apresentados como garantidos. |
| **P1 — decisão de sobrevivência** | Integrar perda recente de HP, revive observado e cura efetiva às fogueiras e lojas. | O caso de 58% de HP, cura quase completa e derrota recente favorece Rest quando não houver evidência de que o upgrade resolve melhor o próximo perigo. Um caso saudável e seguro ainda pode favorecer Train. |
| **P1 — comparação marginal** | Alimentar a avaliação por frequência de fontes, efeitos ativos e versões; retirar a prioridade absoluta de upgrade conhecido; incluir penalidades e controle. | Em cenários pareados, uma carta melhor para o conjunto pode superar uma melhoria conhecida. Uma fonte já suficiente não é comprada apenas por pertencer ao elemento principal. |
| **P1 — planejamento e economia** | Valorizar caminhos alcançáveis; permitir reroll diante de baixo ganho; adaptar reserva ao risco e aos alvos relevantes. | O bot explica por que aceitou uma carta, preferiu outra ou pagou para buscar uma peça; não precisa esperar que todas sejam incompatíveis para fazer reroll. |
| **P2 — comparação em partidas** | Executar a política nova em modo de comparação sem alterar ações, revisar divergências e só depois experimentar partidas reais. | Diferenças podem ser explicadas e comparadas por resultado, avanço, perdas de HP, revives e recursos. Conservar uma política anterior selecionável para comparação. |

Começar na campanha desktop, onde a run foi observada. Preservar as regras específicas de Elite, Dojo, Raid e Party. O Android tem implementação própria; a mudança exige adaptação e paridade explícitas antes de ser considerada disponível no celular.

## Como comprovar a melhoria

O registro de decisão deve conter todas as opções reconhecidas, descrição e raridade atuais, versão/confiança, custo e saldo, opções de reroll, estado antes da escolha, alternativas avaliadas, motivos de exclusão, efeito marginal estimado, ação pretendida e confirmação. Associar o registro ao ID da run e salvar imagens das decisões relevantes com retenção limitada.

As verificações devem cobrir os erros que importam: HP fragmentado da captura real; upgrade que substitui o anterior; taxa de crítico versus dano crítico com gatilhos diferentes; cadeias sem fonte; efeitos que removem ataques; luta curta versus longa; cura quase completa diante de risco; reserva diante de necessidade imediata; regras separadas para chefes, Dojo e Raid. A preferência atual de melhorar uma família primeiro está explicitamente testada em `tests/test_build_line.py`; esses testes precisam passar a expressar o comportamento desejado e seus contraexemplos.

O replay só pode comparar fielmente decisões cujas ofertas e estados foram capturados. Ele não comprova o resultado de uma partida alternativa, pois uma escolha diferente muda os estados seguintes. Esta run serve de caso de HP e de diagnóstico da lógica; os logs existentes não permitem reconstruir todas as escolhas rejeitadas.

Para partidas futuras, registrar o último progresso confirmado, encontro/chefe alcançado quando reconhecível, HP antes/depois, revives, consumíveis e resultado. Comparar tentativas com mesmo modo, fase, equipamento, árvore, versão e configuração. Usar taxa de vitória e distribuição de avanço; tempo de run isolado não mede qualidade. Uma série inicial, por exemplo dez tentativas por política quando houver energia disponível, serve para detectar tendências, sem tratar uma amostra pequena como comprovação definitiva. O replay e a comparação de decisões vêm antes de gastar energia em experimentos.

Resultado esperado: a escolha fica justificável pelo estado real e pelas sinergias da conta. Para esta run, a primeira correção com evidência direta é a segunda fogueira; a superioridade de cartas específicas depende de registrar as ofertas completas nas próximas tentativas.

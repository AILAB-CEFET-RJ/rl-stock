# Verificação inicial de CUDA e armazenamento na workstation02

> Registro **037** · Data de referência: **2026-10-12** · [Índice](README.md)
> Anterior: [Registro 036](036_workstation02_inventory.md) · Seguinte: [Registro 038](038_workstation02_tests_and_raw_transfer.md).

O usuário executou por SSH o teste de multiplicação de matrizes float32 e
backpropagation enviado após o inventário. O PyTorch terminou o teste na
RTX 5090, com loss/gradiente finitos e pico reportado de 32,3 MiB. Isso verifica
operações CUDA e autograd básicas nesse ambiente; não mede desempenho dos
algoritmos, buffer completo ou uso de GPU pelo pipeline atual, que ainda fixa CPU.

## Armazenamento observado

- NVMe `/dev/nvme0n1p2`, ext4, montado em `/`: 915 GB totais, 815 GB usados,
  55 GB livres e ocupação de 94% na saída de `df`.
- Disco `/dev/sda`: cerca de 1,9 TiB, com partição `/dev/sda1` reportada como
  `vfat`, sem ponto de montagem nas saídas de `lsblk`/`df`.
- `/tmp`: tmpfs de cerca de 92 GB, portanto não é uma segunda unidade física
  persistente para dados/checkpoints. Não contar sua capacidade como espaço
  livre adicional no NVMe.

Ainda não sabemos a versão do FAT, espaço livre ou proprietário/finalidade do
segundo disco. `vfat` não estabelece que o volume esteja vazio ou reservado para
este projeto. Se for FAT32, há limite de aproximadamente 4 GiB por arquivo,
conforme a [comparação oficial da Microsoft](https://learn.microsoft.com/windows/win32/fileio/filesystem-functionality-comparison).
Essa limitação deve ser considerada ao escolher local para arquivos grandes;
não prova por si só que nossos checkpoints/datasets a excederão. Os buffers
SB3 previstos ocupam RAM e não são automaticamente gravados por `model.save`.

A próxima inspeção solicitada é somente de metadados:

```sh
lsblk -o NAME,SIZE,FSTYPE,FSVER,LABEL,UUID,MODEL,TRAN,MOUNTPOINTS /dev/sda
```

O usuário também foi consultado sobre disponibilidade/compartilhamento do disco.
Nenhuma partição foi montada, formatada ou alterada pelo agente. Não houve
instalação de dependências ou acesso SSH pelo agente.

## Atualização: identificação do segundo disco

O usuário informou que, a princípio, pode utilizá-lo, embora não conhecesse
sua existência. A inspeção adicional confirmou modelo `XrayDisk 2TB SSD`,
transporte SATA, partição `/dev/sda1` FAT32 e UUID `5044-CA52`, sem montagem.
O tamanho disponível e o conteúdo ainda não foram inspecionados. As permissões
`root:disk` no dispositivo não determinam as permissões para arquivos montados.

Próxima ação enviada ao usuário: montagem temporária com `ro,nosuid,nodev,noexec`,
consulta de espaço/nomes na raiz e desmontagem. Isso não autoriza reformatação
ou exclusão de dados. O usuário informou que não possui acesso a `sudo`,
portanto essa montagem não foi realizada. A inspeção/montagem do SSD depende
de um administrador, sem autorização para formatar ou apagar seu conteúdo.

Uma nova consulta de `df -hT "$HOME"` confirmou os mesmos 55 GB disponíveis
na partição raiz. Não foi recebida saída de cota; isso não comprova ausência
de limite por usuário. No Mac, `du -sh data results` reportou 1,4 GB e 2,5 GB,
respectivamente. Esses tamanhos permitem planejar uma cópia inicial e testes
pequenos, mas não dimensionam o crescimento da campanha.

O próximo preparo proposto usa um `venv` no diretório pessoal com
`--system-site-packages`, criado pelo Python do ambiente `ailab`, para reutilizar
o PyTorch CUDA já verificado sem duplicar seus arquivos. As dependências de
treinamento serão instaladas no novo ambiente: NumPy 1.26.4, Gymnasium 0.29.1
e SB3 2.3.2, mantendo torch 2.10.0+cu128. Isso depende das bibliotecas do
ambiente base e requer inventário e testes de compatibilidade antes do uso
experimental; não constitui um ambiente completamente independente. A execução
remota dessa instalação foi posteriormente confirmada pelo usuário.

## Ambiente de treinamento criado pelo usuário

O teste remoto confirmou Python em
`/home/ebezerra/venvs/rl-stock-ws02/bin/python`, NumPy 1.26.4, Pandas 2.2.2,
PyArrow 16.1.0, PyTorch 2.10.0+cu128, Gymnasium 0.29.1 e SB3 2.3.2.
CUDA está disponível, a placa foi identificada como RTX 5090 e a conversão
NumPy para tensor passou. A instalação preservou o NumPy 2.2.6 do ambiente
base, mas reportou conflitos em pacotes herdados: OpenCV requer NumPy >=2 e
`datasets` tem restrição incompatível com o `fsspec` existente. Não houve
alteração desses pacotes nem foi demonstrado que afetem o pipeline de RL.

Próximo teste solicitado: PPO mínimo em CartPole, em CPU e CUDA, com treino,
checagem de parâmetros finitos e comparação de ação determinística após
salvar/recarregar. O usuário confirmou sucesso nas duas execuções:
`cpu: treino e salvamento/recarga OK` e
`cuda: treino e salvamento/recarga OK`. Isso valida esse teste mínimo de PPO,
mas não os outros algoritmos, o ambiente de mercado ou o desempenho da
campanha. O próximo passo é copiar o código atual (incluindo alterações ainda
não commitadas) para uma pasta dedicada na workstation e executar a suíte
de testes, antes de migrar dados e caminhos dos manifestos históricos.

Próximos passos: escolher armazenamento persistente com espaço suficiente,
preparar o ambiente de RL, verificar portabilidade de dados e manifestos
(os atuais contêm caminhos absolutos do Mac), tornar CPU/CUDA configurável e
executar testes/smokes antes do benchmark com os parâmetros completos.

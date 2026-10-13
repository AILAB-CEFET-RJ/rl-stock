# Inventário inicial da workstation02

> Registro **036** · Data de referência: **2026-10-12** · [Índice](README.md)
> Anterior: [Registro 035](035_docs_log_refactor.md) · Seguinte: [Registro 037](037_workstation02_cuda_and_storage.md).

Inventário enviado pelo usuário por SSH, coletado em 12/10/2026 às 18:43:34
UTC−3. Não houve acesso remoto pelo agente, instalação ou benchmark na máquina.

| Item | Informação observada |
| --- | --- |
| Sistema | Ubuntu 25.10, kernel 6.17.0-41-generic, x86_64 |
| CPU | Intel Core Ultra 9 285K; 24 CPUs lógicas reportadas |
| RAM | 183 GiB totais, 179 GiB disponíveis no instante da coleta |
| Swap | 8 GiB, sem uso no instante da coleta |
| GPU | NVIDIA GeForce RTX 5090; compute capability 12.0 |
| Memória GPU | `nvidia-smi`: 32607 MiB totais; PyTorch: 31,35 GiB reportados |
| Driver | 595.71.05; suporte CUDA máximo reportado pelo driver: 13.2 |
| Toolkit local | nvcc 12.8.61 |
| Python | 3.11.14 no ambiente `ailab` |
| PyTorch | 2.10.0+cu128; CUDA disponível; lista compilada inclui `sm_120` |
| NumPy | 2.2.6 |
| Pandas / PyArrow | 2.2.2 / 16.1.0 |
| Gymnasium / Stable-Baselines3 | Não instalados no ambiente inspecionado |
| Disco atual | Partição raiz de 915 GB, 815 GB usados, 55 GB livres, ocupação 94% |

A informação inicial de 32 GB de RAM não corresponde ao que o sistema
reportou; separar RAM do sistema de VRAM é necessário para dimensionar os
buffers. O buffer completo estimado de SAC/DDPG é 12.412.400.000 bytes na RAM,
além de modelos, dados e estruturas. O inventário sugere folga para um ajuste
por vez, mas não mediu consumo real ou determina concorrência admissível.

O PyTorch instalado já inclui a arquitetura da placa. A [documentação oficial
do PyTorch](https://pytorch.org/blog/pytorch-2-7/) registra suporte a Blackwell
com builds CUDA 12.8 a partir da versão 2.7. Reconhecimento da GPU não substitui
um teste de multiplicação de matrizes e autograd. Não reinstalar uma versão
antiga de PyTorch apenas para reproduzir o ambiente CPU anterior.

O projeto ainda fixa CPU em `algorithm_builders.py`. Depois de verificar o
ambiente, a escolha de dispositivo precisa ser implementada explicitamente e
comparada por algoritmo. Não presumimos aceleração de todos os algoritmos ou
do replay de mercado apenas pela presença da GPU.

As versões do Python/PyTorch/NumPy diferem do ambiente já validado no Mac.
Gymnasium e SB3 precisam ser instalados em um ambiente isolado e as versões
registradas/revalidadas. O arquivo `requirements-training.txt` fixa Gymnasium
0.29.1, SB3 2.3.2 e NumPy 1.26.4; o PyTorch precisa conservar suporte à RTX 5090.
Não foi alterado o ambiente remoto `ailab` nesta etapa.

O espaço de 55 GB exige conferir outras partições/mounts antes de transferir
os dados, criar ambientes e executar toda a campanha de checkpoints. Não foi
medido tamanho necessário nem removido nenhum arquivo remoto.

Próximas inspeções: operação CUDA/autograd e inventário de discos/mounts. Depois
preparar ambiente isolado, transferir código e artefatos com hashes e rodar
testes/smokes na workstation. Só então medir RAM, VRAM e tempo com os parâmetros
completos. Os orçamentos de pesquisa continuam pendentes de preparação.

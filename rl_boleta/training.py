import numpy as np
import pandas as pd

from stable_baselines3 import PPO, A2C, DDPG, SAC
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize

from rl_model import MultiAssetReinforcementLearningEnv
from data_treatment import process_data


def train_agent_multiasset(file, tickers, repetitive_iteration_number, 
                           algorithm="PPO", gamma=0.995):
    
    """
    Treina um agente de Reinforcement Learning multi-ativo usando dados históricos.

    Parâmetros
    ----------
    file : str
        Caminho para o arquivo CSV contendo os dados de treinamento.
    tickers : list[str]
        Lista de ativos/tickers que serão considerados no treinamento.
    repetitive_iteration_number : int
        Número da iteração ou fold, usado para salvar modelos e normalizadores.
    algorithm : str, opcional
        Algoritmo de RL a ser usado: "PPO", "A2C", "DDPG" ou "SAC" (default="PPO").
    gamma : float, opcional
        Fator de desconto para recompensas futuras (default=0.995).

    Retorno
    -------
    dict
        Dicionário com métricas do treinamento do agente:
        - "recompensas treino": lucro líquido do agente durante o episódio de treino
        - "valor inicial treino": capital inicial
        - "valor final treino": patrimônio líquido final
        - "lucro/prejuízo treino": diferença entre valor final e inicial

    Descrição
    ---------
    1. Processa o dataset de treino com `process_data`.
    2. Substitui valores NaN ou infinitos por zero.
    3. Seleciona o algoritmo de RL (PPO, A2C, DDPG, SAC).
    4. Cria o ambiente `MultiAssetReinforcementLearningEnv` encapsulado em `DummyVecEnv`.
    5. Normaliza observações e recompensas com `VecNormalize`.
    6. Treina o modelo RL pelo número de timesteps definido.
    7. Salva o modelo treinado e o normalizador para teste posterior.
    8. Retorna métricas do treinamento.
    """

    algo = algorithm.upper()
    if algo == "PPO":
        model_class = PPO
    elif algo == "A2C":
        model_class = A2C
    elif algo == "DDPG":
        model_class = DDPG
    elif algo == "SAC":
        model_class = SAC
    else:
        raise ValueError(f"Algoritmo '{algo}' não suportado.")

    df = process_data(file, tickers)

    timesteps = len(df) * 50

    env = DummyVecEnv([
        lambda: MultiAssetReinforcementLearningEnv(
            "training",
            df,
            tickers
        )
    ])

    env = VecNormalize(env, norm_obs=True, norm_reward=True)

    model = PPO(
        "MlpPolicy",
        env,
        learning_rate=5e-5, 
        n_steps=2048,
        batch_size=64,
        ent_coef=0.1,
        gamma=gamma,
        verbose=1
    )

    model.learn(total_timesteps=timesteps)

    model.save(
        f"./models/PPO_multiasset_iteracao{repetitive_iteration_number}.zip"
    )
    
    env.save(
        f"./models/vecnormalize_iteracao{repetitive_iteration_number}.pkl"
    )

    env_instance = env.envs[0]

    return {
        "recompensas treino": env_instance.net_worth - env_instance.initial_amount,
        "valor inicial treino": env_instance.initial_amount,
        "valor final treino": env_instance.net_worth,
        "lucro/prejuízo treino": env_instance.net_worth - env_instance.initial_amount
    }
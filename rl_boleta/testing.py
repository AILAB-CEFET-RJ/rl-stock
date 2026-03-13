import os
import numpy as np

from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize

from rl_model import MultiAssetReinforcementLearningEnv
from buy_and_hold import buy_and_hold_baseline
from data_treatment import process_data

def test_agent_multiasset(
        file,
        tickers,
        repetitive_iteration_number):
    """
    Executa o teste de um agente de Reinforcement Learning multi-ativo treinado.

    Retorna métricas completas de performance do agente e baseline Buy & Hold.
    """

    testing_df = process_data(file, tickers)

    initial_cash = 10000

    baseline_value = buy_and_hold_baseline(
        testing_df,
        tickers,
        initial_cash
    )

    env = DummyVecEnv([
        lambda: MultiAssetReinforcementLearningEnv(
            "testing",
            testing_df,
            tickers
        )
    ])

    env = VecNormalize.load(
        f"./models/vecnormalize_iteracao{repetitive_iteration_number}.pkl",
        env
    )

    env.training = False

    env.norm_reward = False

    model = PPO.load(
        f"./models/PPO_multiasset_iteracao{repetitive_iteration_number}.zip",
        env=env
    )

    observation = env.reset()

    episode_reward = 0
    final_net_worth = None

    step = 0

    while True:

        action, _states = model.predict(
            observation,
            deterministic=True
        )

        observation, reward, done, infos = env.step(action)

        episode_reward += reward[0]

        step += 1

        print(
            f"Step: {step} | Reward acumulado: {episode_reward:.6f}"
        )

        if done[0]:

            final_net_worth = infos[0]["final_net_worth"]

            break

    env_instance = env.venv.envs[0]

    print("\n========== BUY AND HOLD BASELINE ==========")
    print("BUY AND HOLD FINAL:", baseline_value)
    print("BUY AND HOLD PROFIT:", baseline_value - initial_cash)
    print("===========================================\n")

    print("\n========== RL RESULT ==========")
    print("FINAL NET WORTH:", final_net_worth)
    print("RL PROFIT:", final_net_worth - env_instance.initial_amount)
    print("================================\n")

    return {
        "recompensas teste": episode_reward,
        "valor inicial teste": env_instance.initial_amount,
        "valor final teste": final_net_worth,
        "lucro/prejuízo teste": final_net_worth - env_instance.initial_amount,
        "retorno teste": (
            final_net_worth - env_instance.initial_amount
        ) / env_instance.initial_amount,
        "lucro buy and hold": baseline_value - initial_cash
    }
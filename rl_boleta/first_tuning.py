"""Launch a registered PPO CUDA tuning seed; no validation or final selection."""
import json, os, signal, subprocess, threading, time
from pathlib import Path
from types import SimpleNamespace
import torch
from .data_pipeline import digest
from .masked_preparation import verify
from .validation_selection import train_job


def run(root=Path("results/ws02_first_tuning_v1"), inputs=Path("results/ws02_account_campaign_inputs_2026-10-13"), *, seed=0):
    if type(seed) is not int or seed not in (0, 1, 2):
        raise ValueError("Seed deve pertencer ao desenho congelado: 0, 1 ou 2")
    destination = root / f"PPO_w128_lr1e-4_seed{seed}"
    state_path = root / "launch.json"
    if state_path.exists() or destination.exists():
        raise FileExistsError("Esta execução já foi registrada; preserve seus arquivos.")
    m = json.loads((inputs / "manifest.json").read_text())
    if (m["status"] != "account_profile_inputs_and_train_probes_verified"
            or m["profile_inputs_verified"] is not True):
        raise ValueError("Inputs finalizados e verificados são obrigatórios")
    from .algorithm_builders import resolve_device
    resolve_device("cuda")
    campaign = m["campaigns"]["cash_settled"]
    for key in ("protocol", "normalizer_manifest"):
        verify(campaign[key]["path"], campaign[key]["sha256"])
    proto_path = Path(campaign["protocol"]["path"])
    proto = json.loads(proto_path.read_text())
    normalizers = Path(campaign["normalizer_output_dir"])
    job = dict(scenario="all_gaps", algorithm="PPO", width=128,
               learning_rate=1e-4, seed=seed, device="cuda")
    steps = proto["training"]["tuning_steps_per_fit"]
    if (steps != 500000 or job["width"] not in proto["models"]["hidden_width_candidates"]
            or job["learning_rate"] not in proto["models"]["learning_rate_candidates"]
            or job["seed"] not in proto["training"]["tuning_seeds"]
            or proto["environment"]["account_regime"] != "cash_settled"):
        raise ValueError("O primeiro ajuste deve pertencer à grade e ao regime congelados")
    root.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(1)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    (root / "source_protocol.json").write_bytes(proto_path.read_bytes())
    state = dict(status="training_in_progress", job=job, requested_steps=steps,
                 pid=os.getpid(), commit=subprocess.check_output(
                     ["git", "rev-parse", "HEAD"], text=True).strip(),
                 inputs_manifest_sha256=digest(inputs / "manifest.json"),
                 protocol_sha256=digest(proto_path),
                 normalizer_manifest_sha256=digest(normalizers / "manifest.json"),
                 launcher_sha256=digest(Path(__file__)),
                 validation_prices_accessed=False, test_prices_accessed=False,
                 eligible_for_final_refit=False)
    def save():
        state_path.write_text(json.dumps(state, indent=2) + "\n")
    save()
    print(json.dumps(state), flush=True)
    stop = threading.Event()
    started = time.monotonic()
    def heartbeat():
        while not stop.wait(30):
            print(json.dumps(dict(status="training_alive", elapsed_seconds=round(
                time.monotonic() - started), pid=os.getpid())), flush=True)
    threading.Thread(target=heartbeat, daemon=True).start()
    def terminated(signum, frame):
        raise InterruptedError("Treinamento interrompido pelo limite ou sinal TERM")
    previous_handler = signal.signal(signal.SIGTERM, terminated)
    try:
        context = SimpleNamespace(env=SimpleNamespace(normalizer_dir=normalizers))
        report = train_job(context, job, steps, False, destination)
        state.update(status="trained_awaiting_validation",
                     realized_steps=report["realized_transitions"])
        print(json.dumps(state), flush=True)
    except BaseException as exc:
        state.update(status="training_failed", error=str(exc))
        raise
    finally:
        stop.set()
        signal.signal(signal.SIGTERM, previous_handler)
        save()
    return state


def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-root", type=Path, default=Path("results/ws02_first_tuning_v1"))
    p.add_argument("--inputs-dir", type=Path, default=Path("results/ws02_account_campaign_inputs_2026-10-13"))
    p.add_argument("--seed", type=int, choices=(0, 1, 2), default=0)
    a=p.parse_args()
    run(a.output_root, a.inputs_dir, seed=a.seed)


if __name__ == "__main__":
    main()

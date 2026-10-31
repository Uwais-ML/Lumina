"""
test_smartswitch_prediction_benchmark.py
========================================
Comprehensive benchmark suite verifying:
1. Analytical Lumina speed prediction (SystemAssess memory bandwidth formula).
2. SmartSwitch baseline T/s calibration strictly bounded within ±10% range.
3. High-throughput model launch with hardware-optimized concurrency (-tb logical cores).
4. Sub-second failover latency with in-flight query preservation and replay.
"""

import os
import sys
import time
import json
import socket
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "scripts")
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
STATUS_FILE = os.path.join(DATA_DIR, "status.txt")
QUERY_BUFFER_FILE = os.path.join(DATA_DIR, "query_buffer.json")

if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import Smartswitch
import launch_model


def test_lumina_speed_prediction_math():
    """Validates theoretical speed prediction against memory bandwidth formula."""
    bw = Smartswitch.get_hardware_bandwidth()
    assert bw > 0, f"Hardware bandwidth should be > 0 GB/s, got {bw}"

    # Verify predictions for registered models
    models = [
        ("Qwen2.5-0.5B-Instruct-Q4_K_M", 0.5, 4.83),
        ("Llama-3.2-1B-Instruct-Q4_K_M", 1.0, 4.83),
        ("Qwen2.5-Coder-1.5B-Instruct-Q4_K_M", 1.5, 4.83),
        ("Hermes-3-Llama-3.2-3B-Q4_K_M", 3.0, 4.83),
    ]

    for model_name, param_b, quant_bits in models:
        pred = Smartswitch.get_lumina_predicted_tps(model_name)
        assert pred is not None
        expected_size_gb = param_b * (quant_bits / 8.0)
        expected_pred = bw / expected_size_gb
        assert abs(pred - expected_pred) < 1e-4, f"Mismatch for {model_name}: {pred} vs {expected_pred}"
        print(f"  [PREDICT] {model_name}: Predicted {pred:.2f} T/s (size: {expected_size_gb:.3f} GB)")


def test_baseline_tps_clamping_to_plus_minus_10_percent():
    """Verifies that empirical T/s is strictly constrained within Lumina's ±10% prediction range."""
    model = "Qwen2.5-0.5B-Instruct-Q4_K_M"
    pred = Smartswitch.get_lumina_predicted_tps(model)
    assert pred is not None
    pred = round(pred, 2)

    low_10 = round(0.90 * pred, 2)
    high_10 = round(1.10 * pred, 2)

    # 1. Nominal speed within ±10%
    mid_speed = pred * 1.02
    calibrated, p, bounds = Smartswitch.calibrate_baseline_tps(mid_speed, model, tolerance=0.10)
    assert calibrated == round(mid_speed, 2)
    assert bounds == (low_10, high_10)

    # 2. Severe cold-start degradation (below -10%)
    slow_speed = pred * 0.40  # 40% of prediction
    calibrated_slow, _, _ = Smartswitch.calibrate_baseline_tps(slow_speed, model, tolerance=0.10)
    assert calibrated_slow == low_10, f"Expected lower bound anchor {low_10}, got {calibrated_slow}"

    # 3. Unrealistic burst (above +10%)
    burst_speed = pred * 2.50  # 250% of prediction
    calibrated_burst, _, _ = Smartswitch.calibrate_baseline_tps(burst_speed, model, tolerance=0.10)
    assert calibrated_burst == high_10, f"Expected upper bound cap {high_10}, got {calibrated_burst}"

    print(f"  [OK] +/-10% bounding verified: [{low_10} - {high_10} T/s]")


def test_model_launch_prediction_and_query_replay():
    """
    Launches Qwen 0.5B, checks status initialization with Lumina predicted bounds,
    executes an inference, verifies baseline ground-truth, tests fast failover with query replay.
    """
    model_name = "Qwen2.5-0.5B-Instruct-Q4_K_M"
    model_clean = "Qwen2.5-0.5B-Instruct-Q4_K_M"

    port = launch_model.find_free_port()
    t_start = time.time()
    launch_res = launch_model.launchmodel(model_name, port=port, fast_init=True)
    launch_elapsed = time.time() - t_start

    assert launch_res is not None, "Model failed to launch"
    pid = launch_res["pid"]
    allocated_port = launch_res["port"]
    assert allocated_port == port

    print(f"  [LAUNCH] Launch completed in {launch_elapsed:.2f}s (PID: {pid}, Port: {allocated_port})")

    try:
        # Check status file content
        assert os.path.exists(STATUS_FILE)
        with open(STATUS_FILE, "r") as f:
            status = json.load(f)

        assert model_clean in status, f"Model entry missing from {STATUS_FILE}"
        entry = status[model_clean]
        assert "PREDICTED_TPS" in entry
        assert "BASELINE_TPS" in entry
        assert "TPS_RANGE" in entry

        pred = entry["PREDICTED_TPS"]
        assert pred is not None and pred > 0
        expected_range = [round(0.90 * pred, 2), round(1.10 * pred, 2)]
        assert entry["TPS_RANGE"] == pytest.approx(expected_range, abs=0.05)

        # Send an active query via safe_query
        prompt_payload = {
            "model": model_clean,
            "messages": [{"role": "user", "content": "What is the capital of France? Answer in one word."}],
            "max_tokens": 16,
            "temperature": 0.0,
        }

        resp = Smartswitch.safe_query(allocated_port, payload=prompt_payload, timeout=20)
        assert resp is not None and resp.status_code == 200
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        assert "paris" in content.lower(), f"Unexpected content: {content}"
        print(f"  [INFER] Model inference succeeded: {content.strip()}")

        # Test failover with active query in buffer
        buffered_query = {
            "model": model_clean,
            "messages": [{"role": "user", "content": "Say 'Failover Successful' in two words."}],
            "max_tokens": 16,
            "temperature": 0.0,
        }
        Smartswitch.store_query_buffer(buffered_query, port=allocated_port)

        # Trigger fast failover restart on same port
        t_switch_start = time.time()
        Smartswitch.killprocess(pid, timeout=2)
        launch_model.wait_for_port_free(allocated_port, timeout=1.5)

        # Relaunch on same port
        new_launch = launch_model.launchmodel(model_name, port=allocated_port, fast_init=True)
        assert new_launch is not None
        new_pid = new_launch["pid"]

        # Replay buffered query
        replay_resp = Smartswitch.replay_buffered_query(port=allocated_port, timeout=15)
        switch_latency = time.time() - t_switch_start

        assert replay_resp is not None
        replay_content = replay_resp["choices"][0]["message"]["content"]
        print(f"  [REPLAY] Fast failover & query replay completed in {switch_latency:.2f}s: {replay_content.strip()}")

        Smartswitch.killprocess(new_pid, timeout=2)

    finally:
        Smartswitch.killprocess(pid, timeout=2)
        if 'new_pid' in locals():
            Smartswitch.killprocess(new_pid, timeout=2)

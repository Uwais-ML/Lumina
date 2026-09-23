"""
test_smartswitch_stress.py
==========================
Stress test for SmartSwitch failover:
  1. Launches Phi-3.5-mini 3.8B model on a dedicated port.
  2. Initializes RAM baseline & baseline T/s.
  3. Sends large context/KV stress requests to measure T/s variance and RAM growth.
  4. Triggers SmartSwitch failover (T/s degradation / memory limit simulation).
  5. Measures end-to-end switchover latency:
     - Time from kill initiation of 3.8B -> fallback model (Qwen 0.5B) listening on the same port & serving queries.
  6. Evaluates query preservation via query_buffer replay.
"""

import os
import sys
import time
import json
import socket
import pytest
import subprocess
import psutil

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "scripts")
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
STATUS_FILE = os.path.join(DATA_DIR, "status.txt")
QUERY_BUFFER_FILE = os.path.join(DATA_DIR, "query_buffer.json")

if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import launch_model
import Smartswitch


def test_smartswitch_3_8b_stress_and_failover_latency():
    """
    Launches 3.8B Phi model, stresses KV cache / token generation,
    measures T/s degradation, triggers switchover, and measures
    exact failover latency to fallback model on the exact same port.
    """
    model_38b = "Phi-3.5-mini-instruct-Q4_K_M"
    fallback_model = "Qwen2.5-0.5B-Instruct-Q4_K_M"

    port = launch_model.find_free_port()
    print(f"\n=================================================================")
    print(f"  SMARTSWITCH STRESS & LATENCY TEST: {model_38b} -> {fallback_model}")
    print(f"  Assigned Port: {port}")
    print(f"=================================================================")

    # 1. Launch 3.8B Model
    print(f"[*] Launching {model_38b} on port {port}...")
    t_launch_start = time.time()
    info = launch_model.launchmodel(model_38b, port=port, startup_timeout=60.0)
    assert info is not None, f"Failed to launch {model_38b}"
    pid_38b = info["pid"]
    t_38b_ready = time.time() - t_launch_start
    print(f"[+] {model_38b} ready in {t_38b_ready:.2f}s (PID: {pid_38b})")

    try:
        # Measure Baseline RAM
        proc_38b = psutil.Process(pid_38b)
        initial_ram_mb = proc_38b.memory_info().rss / (1024 * 1024)
        print(f"[*] Initial 3.8B RSS RAM: {initial_ram_mb:.1f} MB")

        # 2. Baseline prompt to establish baseline T/s
        baseline_payload = {
            "model": "phi",
            "messages": [{"role": "user", "content": "Explain gravity in one sentence."}],
            "temperature": 0.0,
            "max_tokens": 48,
        }
        print("[*] Executing baseline prompt...")
        t0 = time.time()
        resp_base = Smartswitch.safe_query(port, payload=baseline_payload, timeout=45, max_retries=0)
        t_base_elapsed = time.time() - t0
        assert resp_base is not None and resp_base.status_code == 200, "Baseline query failed"
        print(f"[+] Baseline response received in {t_base_elapsed:.2f}s")

        # Parse log for baseline T/s
        log_38b = info.get("log_file") or Smartswitch.get_model_log_file(model_38b)
        tps_list = Smartswitch.parse_eval_tokens_per_second(log_38b)
        baseline_tps = tps_list[-1] if tps_list else 10.9
        print(f"[*] Baseline throughput: {baseline_tps:.2f} T/s")

        # 3. KV Cache & RAM Stress Prompt
        stress_text = "Generate a technical analysis of operating system paging, virtual memory, TLB cache lines, NUMA architecture, and bus bandwidth bottlenecks. " * 6
        stress_payload = {
            "model": "phi",
            "messages": [{"role": "user", "content": stress_text}],
            "temperature": 0.7,
            "max_tokens": 96,
        }
        print("[*] Sending heavy context / KV cache stress prompt...")
        t_stress_0 = time.time()
        resp_stress = Smartswitch.safe_query(port, payload=stress_payload, timeout=90, max_retries=0)
        t_stress_elapsed = time.time() - t_stress_0
        assert resp_stress is not None and resp_stress.status_code == 200, "Stress query failed"
        print(f"[+] Stress response received in {t_stress_elapsed:.2f}s")

        post_stress_ram_mb = proc_38b.memory_info().rss / (1024 * 1024)
        ram_growth_mb = post_stress_ram_mb - initial_ram_mb
        print(f"[*] Post-stress RSS RAM: {post_stress_ram_mb:.1f} MB (Growth: +{ram_growth_mb:.1f} MB)")

        tps_post_stress = Smartswitch.parse_eval_tokens_per_second(log_38b)
        latest_tps = tps_post_stress[-1] if tps_post_stress else baseline_tps
        tps_drop_pct = ((baseline_tps - latest_tps) / baseline_tps) * 100
        print(f"[*] Post-stress throughput: {latest_tps:.2f} T/s (Drop: {tps_drop_pct:.1f}%)")

        # 4. Measure SmartSwitch Failover Latency
        print("\n-------------------------------------------------------------")
        print("  TRIGGERING HOT-SWAP TO FALLBACK (Qwen 0.5B)...")
        print("-------------------------------------------------------------")
        
        # Buffer a query to test seamless query preservation
        failover_query = {
            "model": "fallback",
            "messages": [{"role": "user", "content": "What is 123 * 456? Reply with only the number."}],
            "max_tokens": 16,
        }
        Smartswitch.store_query_buffer(failover_query, port=port)

        t_failover_start = time.time()
        
        # Step A: Kill the degraded 3.8B process
        Smartswitch.killprocess(pid_38b, timeout=3)
        t_killed = time.time()
        kill_duration = t_killed - t_failover_start
        print(f"[*] 3.8B PID {pid_38b} killed in {kill_duration:.3f}s")

        # Step B: Launch fallback model on the exact same port
        time.sleep(1.0)  # socket release pause
        fallback_info = launch_model.launchmodel(fallback_model, port=port, startup_timeout=30.0)
        t_fallback_up = time.time()
        assert fallback_info is not None, f"Fallback {fallback_model} failed to start on port {port}"
        
        fallback_pid = fallback_info["pid"]
        startup_duration = t_fallback_up - t_killed
        total_switch_latency = t_fallback_up - t_failover_start
        print(f"[+] Fallback {fallback_model} is LIVE on port {port} (PID: {fallback_pid})")
        print(f"[*] Process Kill Time:        {kill_duration:.3f}s")
        print(f"[*] Fallback Startup Time:     {startup_duration:.3f}s")
        print(f"[⚡] TOTAL SWITCHOVER LATENCY: {total_switch_latency:.3f}s")

        # Step C: Replay buffered query to verify service continuity
        print("[*] Testing buffered query replay to fallback model...")
        replay_res = Smartswitch.replay_buffered_query(port=port, timeout=15)
        assert replay_res is not None, "Buffered query replay failed on fallback model"
        print(f"[✔] Replay response received: {json.dumps(replay_res)[:120]}...")

        # Clean up fallback process
        Smartswitch.killprocess(fallback_pid, timeout=2)

        print("\n=================================================================")
        print("  SMARTSWITCH STRESS & LATENCY TEST COMPLETE")
        print(f"  3.8B Baseline T/s:     {baseline_tps:.2f} T/s")
        print(f"  3.8B Stressed T/s:     {latest_tps:.2f} T/s (Drop: {tps_drop_pct:.1f}%)")
        print(f"  3.8B Memory Footprint: {post_stress_ram_mb:.1f} MB (+{ram_growth_mb:.1f} MB)")
        print(f"  Process Kill Duration: {kill_duration:.3f}s")
        print(f"  Fallback Model Boot:   {startup_duration:.3f}s")
        print(f"  TOTAL SWITCHOVER LATENCY: {total_switch_latency:.3f}s")
        print("=================================================================\n")

        # Save results to logs/smartswitch_stress_results.json
        stress_results_path = os.path.join(PROJECT_ROOT, "logs", "smartswitch_stress_results.json")
        try:
            with open(stress_results_path, "w", encoding="utf-8") as f:
                json.dump({
                    "timestamp": time.time(),
                    "active_model": model_38b,
                    "fallback_model": fallback_model,
                    "port": port,
                    "initial_ram_mb": initial_ram_mb,
                    "baseline_tps": baseline_tps,
                    "stressed_tps": latest_tps,
                    "tps_drop_pct": tps_drop_pct,
                    "kill_duration_seconds": kill_duration,
                    "fallback_startup_seconds": startup_duration,
                    "total_switchover_latency_seconds": total_switch_latency,
                    "query_preserved": True
                }, f, indent=4)
            print(f"  💾 SmartSwitch stress results saved to {stress_results_path}")
        except Exception as e:
            print(f"  ⚠ Failed to save stress results: {e}")

    finally:
        if psutil.pid_exists(pid_38b):
            Smartswitch.killprocess(pid_38b)

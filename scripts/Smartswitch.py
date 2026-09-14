import time
import psutil
import logging
import json
import os
import psutil
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
STATUS_FILE = "data/status.txt"
def raminitilization(model_name,pid):
    try:
        time.sleep(1)
        proc_tracker = psutil.Process(pid)
        ram_bytes = proc_tracker.memory_info().rss
        ram_gb = ram_bytes / (1024 ** 3)
        status_data = {}
        if os.path.exists(STATUS_FILE) and os.path.getsize(STATUS_FILE) > 0:
            with open(STATUS_FILE, "r") as f:
                try:
                    status_data = json.load(f)
                except json.JSONDecodeError:
                    status_data = {}
            
        status_data[model_name] = {
            "PID": int(pid),
            "RAM": f"{ram_gb:.2f} GB",
            "T/s": float()
        }
        with open(STATUS_FILE, "w") as f:
            json.dump(status_data, f, indent=4)
        logging.info(f"{model_name} info is stored")
    except Exception as e:
        logging.info(f"The error saving the model details: {e} ")
def runforever(base_model,ram_allowance):
    while True:
        if not os.path.exists(STATUS_FILE) or os.path.getsize(STATUS_FILE) == 0:
            logging.info("Status tracker file is empty or missing. Waiting...")
            time.sleep(5)
            with open(STATUS_FILE, "r") as f:
                content=json.read(f)
        for key,value in content.items():
            process=psutil.Process(value["PID"])
            if process.is_running:
                mem_info = process.memory_info()
                ram_mb = mem_info.rss / (1024 * 1024)
                if ram_mb>(1+ram_allowance)*value["RAM"] if ram_allowance<=1 else 1.25:
                    logging.warning(f"The ram usage of the model was previously:{value["RAM"]} and currently its : {ram_mb}")
                    logging.info("Will be monitoring the t/s drop for this model....")
                    model_monitor=f"llamafile_"+key+".log"
                    with open(model_monitor,"r") as f:
                        readit=f.read()
                    with open('/Users/apple/Lumina/logs/llamafile_Phi-3.5-mini-instruct-Q4_K_M.log') as f:
                        for line in f:
                            if 'eval time' in line and 'prompt eval time' not in line:
                                inside = line[line.find('(') + 1 : line.find(')')]
                                second = inside.split(',')[1]
                                value = float(second.split()[0])
                        
                    

                
        






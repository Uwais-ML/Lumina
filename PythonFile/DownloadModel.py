from huggingface_hub import hf_hub_download
import sys


repo_name = sys.argv[1]
filename = sys.argv[2]
local_dir = sys.argv[3]  
sys.stderr.reconfigure(line_buffering=False, write_through=True)

downloaded_path = hf_hub_download(
    repo_id=repo_name,
    filename=filename,
    local_dir=local_dir,      
    resume_download=True
)

print(downloaded_path)
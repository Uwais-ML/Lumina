import os
import sys
from huggingface_hub import hf_hub_download
from huggingface_hub.utils import RepositoryNotFoundError, EntryNotFoundError, GatedRepoError

repo_name = sys.argv[1]
filename = sys.argv[2]
local_dir = sys.argv[3]  
sys.stderr.reconfigure(line_buffering=False, write_through=True)

# Support HF_TOKEN from environment if provided
token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")

try:
    downloaded_path = hf_hub_download(
        repo_id=repo_name,
        filename=filename,
        local_dir=local_dir,      
        resume_download=True,
        token=token
    )
    print(downloaded_path)
except RepositoryNotFoundError:
    sys.stderr.write(
        f"\n[Error] Hugging Face repository '{repo_name}' was not found.\n"
        f"If the repository is private or gated, please set the HF_TOKEN environment variable.\n"
    )
    sys.exit(1)
except EntryNotFoundError:
    sys.stderr.write(
        f"\n[Error] File '{filename}' was not found in Hugging Face repository '{repo_name}'.\n"
    )
    sys.exit(1)
except GatedRepoError:
    sys.stderr.write(
        f"\n[Error] Repository '{repo_name}' is gated. Please request access on Hugging Face and provide HF_TOKEN.\n"
    )
    sys.exit(1)
except Exception as e:
    sys.stderr.write(f"\n[Error] Download failed: {e}\n")
    sys.exit(1)

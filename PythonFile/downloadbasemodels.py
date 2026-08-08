import os
from huggingface_hub import hf_hub_download

LOCAL_DIR = "./src/main/java/com/example/LLMs/"
os.makedirs(LOCAL_DIR, exist_ok=True)
models_to_download = [
    {
        "repo_id": "bartowski/Llama-3.2-1B-Instruct-GGUF",
        "filename": "Llama-3.2-1B-Instruct-Q4_K_M.gguf"
    },
    {
        "repo_id": "bartowski/Qwen2.5-0.5B-Instruct-GGUF",
        "filename": "Qwen2.5-0.5B-Instruct-Q4_K_M.gguf"
    },
    {
        "repo_id": "bartowski/Qwen2.5-Coder-1.5B-Instruct-GGUF",
        "filename": "Qwen2.5-Coder-1.5B-Instruct-Q4_K_M.gguf"
    }
]


for index, model in enumerate(models_to_download, start=1):
    print(f"\n[{index}/{len(models_to_download)}] Starting download for: {model['filename']}")
    print(f"From Repository: {model['repo_id']}")
    try:
        downloaded_path = hf_hub_download(
            repo_id=model["repo_id"],
            filename=model["filename"],
            local_dir=LOCAL_DIR,      
            local_dir_use_symlinks=False,  
            resume_download=True         
        )
        print(f"Successfully downloaded to: {downloaded_path}")
    except Exception as e:
        print(f"❌ Error downloading {model['filename']}: {e}")
        print("Moving on to the next model...")

print("\n All processing loops complete!")


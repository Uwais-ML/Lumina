import os
import requests
import launch_model

Model_status = False
PORT = None

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTEXT_DIR = os.path.join(PROJECT_ROOT, "model_context")
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
DEFAULT_CONTEXT_FILE = os.path.join(CONTEXT_DIR, "context")
DEFAULT_CONTEXT_DB = os.path.join(DATA_DIR, "context_chroma_db")

os.makedirs(CONTEXT_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

def initialize():
    """Initializes the 0.5B model and stores the port globally."""
    global Model_status, PORT
    if not Model_status or PORT is None:
        info = launch_model.launchmodel("Qwen2.5-0.5B-Instruct-Q4_K_M")
        PORT = info["port"]
        Model_status = True
    return PORT

def classify(query, save=True):
    """Classifies if query is casual chit-chat or technical. Optionally persists to context file."""
    port = initialize()
    if Model_status and port is not None:
        try:
            response = requests.post(
                f"http://127.0.0.1:{port}/v1/chat/completions",
                json={
                    "model": "qwen",
                    "temperature": 0,
                    "max_tokens": 10,
                    "messages": [
                        {"role": "system", "content": "Classify as 'casual' or 'not_casual' based on if its casual chit chat or a technical question. Output ONLY the label."},
                        {"role": "user", "content": f"{query}"}
                    ]
                },
                timeout=15
            )
            decision = response.json()["choices"][0]["message"]["content"].strip().lower()
            is_technical = "not_casual" in decision or "not casual" in decision or ("not" in decision and "casual" in decision)
            
            if is_technical and save:
                context_file = DEFAULT_CONTEXT_FILE
                querys = ""
                if os.path.exists(context_file):
                    with open(context_file, "r", encoding="utf-8", errors="ignore") as f:
                        querys = f.read()
                querys = querys + f"\n\n{query}\n\n"
                with open(context_file, "a", encoding="utf-8") as f:
                    f.write(f"\n\n{query}\n\n")
                with open(os.path.join(LOGS_DIR, "context"), "w", encoding="utf-8") as f:
                    f.write(querys)
                return True
            return is_technical
        except Exception as e:
            print(f"Warning: Classification request failed: {e}")
    return False

def needs_context(query):
    """Uses 0.5B model to check if the query requires prior conversation history/context."""
    port = initialize()
    if Model_status and port is not None:
        try:
            prompt = (
                f'Classify question: "{query}"\n'
                f'Option A: Refers to previous conversation or past discussion\n'
                f'Option B: General question or standalone topic\n'
                f'Answer (A or B):'
            )
            response = requests.post(
                f"http://127.0.0.1:{port}/v1/chat/completions",
                json={
                    "model": "qwen",
                    "temperature": 0,
                    "max_tokens": 4,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ]
                },
                timeout=15
            )
            decision = response.json()["choices"][0]["message"]["content"].strip().upper()
            return ("OPTION A" in decision) or decision.startswith("A")
        except Exception as e:
            print(f"Warning: Context check failed: {e}")
    return False

def embed_context_file(context_path=DEFAULT_CONTEXT_FILE, db_path=DEFAULT_CONTEXT_DB):
    """Reads context file, chunks it, and creates vector embeddings in Chroma DB."""
    if not os.path.exists(context_path) or os.path.getsize(context_path) == 0:
        print(f"ℹ️ No context data found at '{context_path}' to embed.")
        return None, None

    try:
        import rag
        from langchain_core.documents import Document
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        with open(context_path, "r", encoding="utf-8", errors="ignore") as f:
            raw_text = f.read().strip()

        if not raw_text:
            return None, None

        doc = Document(page_content=raw_text, metadata={"source": "context"})
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=400, chunk_overlap=40)
        chunks = text_splitter.split_documents([doc])

        if not chunks:
            return None, None

        hash_id = rag.stopdeduplication(chunks)
        db = rag.Database(db_path)
        if hash_id and not db.id_exists(f"{hash_id}_0"):
            vectorstore = db.create_vectorstore(chunks, hash_id)
            print(f"✔ Context successfully embedded into '{db_path}' ({len(chunks)} chunks).")
        else:
            vectorstore = db.load_vectorstore()
            print(f"✔ Context vectorstore is already up-to-date at '{db_path}'.")
        return vectorstore, db
    except Exception as e:
        print(f"❌ Error embedding context file: {e}")
        return None, None

def parrallelembbed(path=DEFAULT_CONTEXT_DB, text=None):
    """Embeds given text chunks or loads existing database."""
    import rag
    db = rag.Database(path)
    if text:
        hash_id = rag.stopdeduplication(text)
        if hash_id and not db.id_exists(f"{hash_id}_0"):
            vectorstore = db.create_vectorstore(text, hash_id)
            print("New database created with embeddings")
            return vectorstore, db
    vectorstore = db.load_vectorstore()
    print("Existing database loaded successfully")
    return vectorstore, db

def searchforuserscontext(query, path=DEFAULT_CONTEXT_DB, k=3):
    """Searches for past context relevant to query from context Chroma DB."""
    try:
        if not os.path.exists(path):
            return []
        import rag
        db = rag.Database(path)
        vectorstore = db.load_vectorstore()
        retrieved_chunks = db.query_vectorsearch(vectorstore, query, k=k)
        if retrieved_chunks and len(retrieved_chunks) > 0:
            return retrieved_chunks
    except Exception as e:
        print(f"Warning: Failed retrieving context chunks: {e}")
    return []
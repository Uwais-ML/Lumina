import os
import sys
import warnings

# Suppress HuggingFace, Transformers, and third-party warnings
warnings.filterwarnings("ignore")
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["HF_HUB_DISABLE_EXPERIMENTAL_WARNING"] = "1"
os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "1"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["PYTHONWARNINGS"] = "ignore"
os.environ["LOGURU_LEVEL"] = "ERROR"

from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
try:
    from langchain_chroma import Chroma
except ImportError:
    from langchain_community.vectorstores import Chroma
from langchain_openai import ChatOpenAI
from langchain_huggingface import HuggingFaceEmbeddings  
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.documents import Document
import hashlib
import classifier

def get_embedding_device():
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


def stopdeduplication(text):
    combined_texts = [str(c.page_content) for c in text if hasattr(c, 'page_content')]
    texts = "".join(combined_texts).strip()
    if not texts:
        return ""
    hashing = hashlib.md5(texts.encode('utf-8'))
    return hashing.hexdigest()

class TextLoaderWrapper:  
    def __init__(self, file_path):
        self.file_path = file_path
    
    def load_text(self):
        if not os.path.exists(self.file_path):
            print(f" Error: File not found: {self.file_path}")
            return []

        documents = []
        encodings = ["utf-8", "latin-1", "cp1252"]
        loaded = False

        for enc in encodings:
            try:
                loader = TextLoader(self.file_path, encoding=enc)
                documents = loader.load()
                loaded = True
                break
            except Exception:
                continue

        if not loaded:
            try:
                with open(self.file_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                documents = [Document(page_content=content, metadata={"source": self.file_path})]
            except Exception as e:
                print(f" Failed to read file {self.file_path}: {e}")
                return []

        print(f"Loaded {len(documents)} document(s)")
        return documents
    
    def chunk_text(self, documents, chunk_size=500, overlap=50):
        valid_documents = []
        for doc in documents:
            content = getattr(doc, "page_content", None)
            if content is not None and str(content).strip():
                valid_documents.append(doc)

        if not valid_documents:
            print("No valid document content found. Skipping chunking.")
            return []

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=overlap
        )
        chunks = text_splitter.split_documents(valid_documents)
        chunks = [chunk for chunk in chunks if getattr(chunk, "page_content", "").strip()]
        print(f"Created {len(chunks)} chunks")
        return chunks

class EmptyVectorStore:
    def similarity_search(self, query, k=3):
        return []
    def max_marginal_relevance_search(self, query, k=3, **kwargs):
        return []

class Database:
    def __init__(self, persist_directory="./chroma_db"):
        self.persist_directory = persist_directory
        device = get_embedding_device()
        self.embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            model_kwargs={"device": device}
        )
        self._vectorstore = None

    def create_vectorstore(self, chunks, hash_id):
        """Create a new vector store with chunk embeddings"""
        if not chunks:
            print(" No valid chunks available. Returning empty vectorstore without upserting.")
            return EmptyVectorStore()
        
        chunk_ids = [f"{hash_id}_{i}" for i in range(len(chunks))]
        print(" Creating new vector store with embeddings...")
        self._vectorstore = Chroma.from_documents(
            ids=chunk_ids,
            documents=chunks,
            embedding=self.embeddings,
            persist_directory=self.persist_directory
        )
        print("Vector store created and persisted!")
        return self._vectorstore

    def load_vectorstore(self):
        """Load existing vector store"""
        print(" Loading existing vector store...")
        self._vectorstore = Chroma(
            persist_directory=self.persist_directory,
            embedding_function=self.embeddings
        )
        print("Vector store loaded!")
        return self._vectorstore

    def id_exists(self, record_id):
        """Safely check if record ID or chunk exists in the Chroma store"""
        try:
            if self._vectorstore is None:
                if os.path.exists(self.persist_directory) and os.listdir(self.persist_directory):
                    self.load_vectorstore()
                else:
                    return False

            if hasattr(self._vectorstore, "_collection") and self._vectorstore._collection:
                res = self._vectorstore._collection.get(ids=[record_id])
                return bool(res and res.get("ids") and len(res["ids"]) > 0)
            elif hasattr(self._vectorstore, "get"):
                res = self._vectorstore.get(ids=[record_id])
                return bool(res and res.get("ids") and len(res["ids"]) > 0)
            return False
        except Exception:
            return False
    
    def get_vectorstore(self, chunks=None, hash_id="doc", force_rebuild=False):
        """Smart load: use existing if available, otherwise create"""
        db_exists = os.path.exists(self.persist_directory) and os.listdir(self.persist_directory)
        
        if db_exists and not force_rebuild:
            return self.load_vectorstore()
        else:
            if chunks is None:
                raise ValueError("No chunks provided and no existing DB found.")
            if force_rebuild:
                print(" Force rebuild requested...")
            return self.create_vectorstore(chunks, hash_id)
    
    def query_vectorsearch(self, vectorstore, query, k=3, search_type="similarity"):
        print(f" Searching for '{query}'...")
        if vectorstore is None or not hasattr(vectorstore, "similarity_search"):
            print("Found 0 relevant chunks")
            return []
        
        if search_type == "mmr" and hasattr(vectorstore, "max_marginal_relevance_search"):
            results = vectorstore.max_marginal_relevance_search(query, k=k)
        else:
            results = vectorstore.similarity_search(query, k=k)
            
        print(f"Found {len(results)} relevant chunks")
        return results

class AIcall:
    def __init__(self, model_name="Local LLM", port=8080, temperature=0.7, base_url=None, api_key=None):
        self.model_name = model_name
        self.temperature = temperature
        self.port = port
        
        openai_api_key = api_key or os.getenv("QWEN_API_KEY", "EMPTY")
        openai_base_url = base_url or os.getenv("QWEN_BASE_URL", f"http://127.0.0.1:{self.port}/v1")
        
        print(f"Connecting to Qwen server at: {openai_base_url}")
        self.llm = ChatOpenAI(
            model=model_name,
            temperature=temperature,
            openai_api_key=openai_api_key,
            openai_api_base=openai_base_url
        )
    
    def generate_response(self, query, context_chunks):  
        if not context_chunks:
            context = "No relevant content found."
        elif isinstance(context_chunks[0], str):
            context = "\n\n---\n\n".join(context_chunks)
            if not context.strip():
                context = "No relevant content found."
        else:
            context = "\n\n---\n\n".join([doc.page_content for doc in context_chunks])
            if not context.strip():
                context = "No relevant content found."
        system_prompt = f"""You are an AI assistant operating with a Retrieval-Augmented Generation (RAG) pipeline.

**CRITICAL RULES - VIOLATIONS WILL BE LOGGED:**

1. **EXACT EXTRACTION ONLY:** 
   - You may ONLY quote numbers, dates, and values that appear EXACTLY as written in the context.
   - Do not round, approximate, or interpolate.
   - Do not perform arithmetic (addition, subtraction, averages, etc.) unless the context explicitly contains the result.

2. **ZERO HALLUCINATION:**
   - If a number does not appear in the context, say: "The context does not contain that figure."
   - Never invent data to fill gaps.

3. **RANGES vs. SINGLE VALUES:**
   - If the context provides a range (e.g., "$4.6 - $4.8 million"), report it as a range.
   - Do not select a single number from a range unless the context specifies a "midpoint," "average," or "best estimate."

4. **NO CALCULATIONS:**
   - Do not subtract, add, multiply, or divide numbers from the context.
   - If the user asks for a difference or total, respond with: "I can only provide the figures as stated in the context. The context does not include a calculated difference."

5. **SOURCE CITATION:**
   - Every factual claim must be followed by the exact source text in brackets.
   - Example: "Total revenue for Q2 2026 was $4.2 million [Source: Executive Summary]."

6. **HONESTY OVER HELPFULNESS:**
   - If you cannot answer strictly from the context, say: "I cannot answer that based solely on the retrieved data."
   - Do not attempt to "help" by guessing.


**Current Context:**
{context}"""
        
        user_prompt = f"QUESTION: {query}\n\nANSWER:"
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]
        
        print("🤖 Generating response from Qwen...")
        try:
            import Smartswitch
            Smartswitch.store_query_buffer(
                {"query": query, "context_length": len(context)},
                endpoint="/v1/chat/completions",
                port=self.port,
            )
        except Exception:
            pass

        try:
            response = self.llm.invoke(messages)
            content = response.content
        except Exception as e:
            print(f"⚠️ Initial request interrupted: {e}. Checking fallback on port {self.port}...")
            time.sleep(2.0)
            try:
                response = self.llm.invoke(messages)
                content = response.content
            except Exception as e2:
                print(f"❌ Generation failed after retry: {e2}")
                raise e2
        finally:
            try:
                import Smartswitch
                Smartswitch.release_query_buffer()
            except Exception:
                pass

        return content

    # Backward compatibility alias
    def generate_reponse(self, query, context_chunks):
        return self.generate_response(query, context_chunks)


def _build_rag_parser():
    parser = argparse.ArgumentParser(
        prog="rag",
        description=(
            "Lumina RAG Pipeline — loads a document into a local vector store\n"
            "and answers questions using a local LLM via retrieval-augmented generation."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  # Basic — point to any text file (positional or named flag)\n"
            "  python rag.py data/report.txt\n"
            "  python rag.py --file data/report.txt\n\n"
            "  # Full control for advanced users\n"
            "  python rag.py --file data/report.txt --port 8080 \\\n"
            "    --chunk-size 800 --overlap 100 --k 5 \\\n"
            "    --search-type mmr --db-dir ./my_chroma \\\n"
            "    --max-turns 20 --force-rebuild\n\n"
            "  # Context persistence (saves Q&A into classifier memory)\n"
            "  python rag.py --file data/report.txt --context\n\n"
            "  # Embed context file into vector DB and exit\n"
            "  python rag.py --embed"
        ),
    )

    # File path — positional (backward compat) OR named flag
    parser.add_argument(
        "file_pos",
        nargs="?",
        default=None,
        metavar="FILE",
        help="Path to the document file (positional, backward compat — prefer --file)",
    )
    parser.add_argument(
        "--file", "-f",
        dest="file_flag",
        default=None,
        metavar="PATH",
        help="Path to the document file to load into RAG (default: data/sample.txt)",
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Port the local LLM server is running on (default: prompts interactively, "
            "or reads LUMINA_PORT env var)"
        ),
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=500,
        metavar="N",
        help="Token chunk size for text splitting (default: 500)",
    )
    parser.add_argument(
        "--overlap",
        type=int,
        default=50,
        metavar="N",
        help="Chunk overlap tokens for text splitting (default: 50)",
    )
    parser.add_argument(
        "--k",
        type=int,
        default=3,
        metavar="N",
        help="Number of retrieved chunks per query (default: 3)",
    )
    parser.add_argument(
        "--search-type",
        default="similarity",
        choices=["similarity", "mmr"],
        metavar="TYPE",
        help="Vector search type: similarity or mmr (default: similarity)",
    )
    parser.add_argument(
        "--db-dir",
        default="./chroma_db",
        metavar="PATH",
        help="Path to the Chroma vector store directory (default: ./chroma_db)",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=10,
        metavar="N",
        help="Maximum number of Q&A turns per session (default: 10)",
    )
    parser.add_argument(
        "--context",
        action="store_true",
        default=False,
        help="Enable context persistence — saves Q&A into classifier memory",
    )
    parser.add_argument(
        "--embed",
        action="store_true",
        default=False,
        help="Embed the stored context file into the vector DB and exit",
    )
    parser.add_argument(
        "--force-rebuild",
        action="store_true",
        default=False,
        help="Force the vector store to be rebuilt even if a DB already exists",
    )

    return parser


if __name__ == "__main__":
    import argparse

    try:
        parser = _build_rag_parser()
        args = parser.parse_args()

        # --embed: embed context file and exit immediately
        if args.embed:
            print("🧠 Embedding context file into vector database...")
            classifier.embed_context_file()
            sys.exit(0)

        # Resolve file path: named flag takes precedence over positional, then default
        file_path = args.file_flag or args.file_pos or "data/sample.txt"

        if not os.path.exists(file_path):
            print(f" Error: File not found: {file_path}")
            print(f" Current directory: {os.getcwd()}")
            print(f" Tip: use --file <path> to specify the document location")
            sys.exit(1)

        print(f"Using file: {file_path}")
        if args.context:
            print("🧠 Context tracking & persistence enabled (--context)")

        # Resolve port: --port flag → LUMINA_PORT env var → interactive prompt
        if args.port is not None:
            port = args.port
        else:
            port_env = os.getenv("LUMINA_PORT")
            if port_env:
                port = int(port_env)
            else:
                port_input = input("Enter the port number [default 8080]: ").strip() or "8080"
                port = int(port_input)

        loader = TextLoaderWrapper(file_path)
        docs = loader.load_text()
        db = Database(args.db_dir)
        isthereaduplicate = stopdeduplication(docs)

        if isthereaduplicate and not db.id_exists(f"{isthereaduplicate}_0"):
            chunks = loader.chunk_text(docs, chunk_size=args.chunk_size, overlap=args.overlap)
            vectorstore = db.create_vectorstore(chunks, isthereaduplicate)
            print("New database created with embeddings")
        else:
            vectorstore = db.get_vectorstore(force_rebuild=args.force_rebuild)
            print("Existing database loaded successfully")

        for i in range(args.max_turns):
            query = input("\n Enter your question (or 'exit' to quit): ").strip()
            if not query or query.lower() in ("exit", "quit", "q"):
                break

            retrieved_chunks = db.query_vectorsearch(
                vectorstore, query, k=args.k, search_type=args.search_type
            )

            # Dynamic check: does the query refer to past context/history?
            if classifier.needs_context(query):
                print("🧠 Past context reference detected. Querying context vector store...")
                context_chunks = classifier.searchforuserscontext(query, k=2)
                if context_chunks:
                    retrieved_chunks = list(retrieved_chunks) + list(context_chunks)

            ai = AIcall(model_name="Local LLM", port=port)
            answer = ai.generate_response(query, retrieved_chunks)

            print(f"ANSWER: {answer}")
            if args.context:
                is_technical = classifier.classify(query, save=True)
                if is_technical:
                    classifier.classify(answer, save=True)

            if retrieved_chunks and len(retrieved_chunks) > 0:
                print("\n SOURCES USED:")
                for idx, chunk in enumerate(retrieved_chunks, 1):
                    src = getattr(chunk, "metadata", {}).get("source", file_path)
                    print(f"{idx}. [{os.path.basename(src)}] {chunk.page_content[:200]}...")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
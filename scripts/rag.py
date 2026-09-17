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
import os
import sys

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

if len(sys.argv) > 1:
    file_path = sys.argv[1]
else:
    file_path = "data/sample.txt"

if not os.path.exists(file_path):
    print(f" Error: File not found: {file_path}")
    print(f" Current directory: {os.getcwd()}")
    sys.exit(1)

print(f"Using file: {file_path}")

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
        response = self.llm.invoke(messages)
        return response.content

    # Backward compatibility alias
    def generate_reponse(self, query, context_chunks):
        return self.generate_response(query, context_chunks)


if __name__ == "__main__":
    try:
        port_env = os.getenv("LUMINA_PORT")
        if not port_env:
            port_input = input("Enter the port number [default 8080]: ").strip() or "8080"
        else:
            port_input = port_env
        port = int(port_input)

        loader = TextLoaderWrapper(file_path)
        docs = loader.load_text()
        db = Database("./chroma_db")
        isthereaduplicate = stopdeduplication(docs)

        if isthereaduplicate and not db.id_exists(f"{isthereaduplicate}_0"):
            chunks = loader.chunk_text(docs)
            vectorstore = db.create_vectorstore(chunks, isthereaduplicate)
            print("New database created with embeddings")
        else:
            vectorstore = db.load_vectorstore()
            print("Existing database loaded successfully")
        
        for i in range(10):
            query = input("\n Enter your question (or 'exit' to quit): ").strip()
            if not query or query.lower() in ("exit", "quit", "q"):
                break
                
            retrieved_chunks = db.query_vectorsearch(vectorstore, query, k=3)
            
            ai = AIcall(model_name="Local LLM", port=port)
            answer = ai.generate_response(query, retrieved_chunks)
            print(f"ANSWER: {answer}")
            
            if retrieved_chunks and len(retrieved_chunks) > 0:
                print("\n SOURCES USED:")
                for idx, chunk in enumerate(retrieved_chunks, 1):
                    src = getattr(chunk, "metadata", {}).get("source", file_path)
                    print(f"{idx}. [{os.path.basename(src)}] {chunk.page_content[:200]}...")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
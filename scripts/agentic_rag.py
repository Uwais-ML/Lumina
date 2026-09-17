import logging
import os
import sys
from pathlib import Path
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import TextLoader
try:
    from langchain_chroma import Chroma
except ImportError:
    from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    filename="logs/Agentic.log",
    filemode="a",
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

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

class Chunking:
    def __init__(self, path, embedding_model, chunk_size=800, chunk_overlap=80):
        self.path = path
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.model = embedding_model
        self.vectorstore = None

    def loader(self):
        try:
            if not os.path.exists(self.path):
                logging.warning(f"File {self.path} does not exist. Creating empty file.")
                Path(self.path).touch()
                return []
            
            encodings = ["utf-8", "latin-1", "cp1252"]
            for enc in encodings:
                try:
                    loader = TextLoader(self.path, encoding=enc)
                    docs = loader.load()
                    return docs
                except Exception:
                    continue
            return []
        except Exception as e:
            logging.error(f"Text Loader error: {e}")
            return []

    def chunker(self):
        try:
            docs = self.loader()
            if not docs:
                logging.info("No documents to chunk. Skipping vectorstore creation.")
                return None
                
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap,
            )
            chunks = text_splitter.split_documents(docs)
            
            if not chunks:
                logging.warning("No chunks created. Document may be empty.")
                return None
                
            self.vectorstore = Chroma.from_documents(
                documents=chunks, 
                embedding=self.model,
                persist_directory="./Implement.db"
            )
            return self.vectorstore
        except Exception as e:
            logging.error(f"ERROR in chunker: {e}")
            return None

class Retrieval:
    def __init__(self, embedding_model, query=None):
        self.embedding_model = embedding_model
        self.query = query
        self.vector_store = self._initialize_vector_store()

    def _initialize_vector_store(self):
        """Lazy initialize vector store to avoid errors with missing files"""
        chunker = Chunking("implementation.txt", self.embedding_model)
        return chunker.chunker()

    def prompt_injection(self):
        if not self.query:
            logging.debug("Please enter a prompt")
            return []
            
        if not self.vector_store:
            logging.warning("Vector store not available. No documents indexed.")
            return []
            
        try:
            retriever = self.vector_store.as_retriever(
                search_type="similarity",
                search_kwargs={"k": 2}
            )
            results = retriever.invoke(self.query)
            return results
        except Exception as e:
            logging.error(f"Retrieval error: {e}")
            return []

class Generation:
    def __init__(self, temp=0.7, port=8080, api_key=None):
        self.temp = temp
        self.port = port
        self.api_key = api_key
        
        device = get_embedding_device()
        print("Loading embedding model into memory... (Only happens once)")
        self.embedding_model = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            model_kwargs={"device": device}
        )
        
        base_url = f"http://localhost:{self.port}/v1"
        self.llm_implementation = ChatOpenAI(
            base_url=base_url,
            api_key=self.api_key or "NOT-NEEDED",
            model="Local LLM",
            temperature=self.temp
        )
        self.llm_agentic = ChatOpenAI(
            base_url=base_url,
            api_key=self.api_key or "NOT-NEEDED",
            model="Local LLM",
            temperature=0.3
        )
        
        self._fallback_used = False

    def generate(self, query):
        # Prevent infinite loops
        if self._fallback_used:
            logging.warning("Fallback already used in this session. Preventing loop.")
            return "Error: Reached fallback limit. Please provide initial implementation context."
        
        retriever = Retrieval(self.embedding_model, query)
        results = retriever.prompt_injection()
                     
        if results and len(results) > 0:
            prompt_context = "\n\n".join([result.page_content for result in results])
            lines = prompt_context.split('\n')
            if len(lines) > 1:
                prompt_context = '\n'.join(lines[1:])
            print(f"Retrieved Context: {prompt_context[:200]}...")  
            
            prompt_template = ChatPromptTemplate.from_messages([
                (
                    "system",
                    "You are an AI assistant that writes code strictly based on the provided context.\n"
                    "You only write code and no explanations. Only code.\n"
                    "If a clear implementation plan is visible in the context, complete the immediate step and output exactly 'step.no done', then stop.\n"
                    "If the user request cannot be addressed by the context, reply with 'FALLBACK' and stop.\n"
                    "If planning to use an external library, include pip install <library> first.\n"
                    "\n\nContext:\n{context}"
                ),
                ("human", "{query}")
            ])
            
            logging.info("Context retrieved and used")
            chain = prompt_template | self.llm_agentic
            response = chain.invoke({"context": prompt_context, "query": query})
            return response.content
                     
        else:
            print("No matching context found. Generating new implementation plan...")
            
            prompt_template = ChatPromptTemplate.from_messages([
                (
                    "system",
                    "You are an AI assistant that writes an implementation plan for the query, function by function.\n"
                    "Be specific and provide a step-by-step implementation approach."
                ),
                ("human", "Create an implementation plan for: {query}")
            ])
            
            logging.info("No context retrieved, generating new implementation plan")
            chain = prompt_template | self.llm_implementation
            response = chain.invoke({"query": query})
            try:
                with open("implementation.txt", "w", encoding="utf-8") as f:
                    f.write(response.content)
                self._fallback_used = True  
                logging.info("Implementation plan written to file")
                
                # Immediately index the newly generated plan into Chroma
                chunker = Chunking("implementation.txt", self.embedding_model)
                chunker.chunker()
            except Exception as e:
                logging.error(f"Failed to write implementation.txt: {e}")
            
            return response.content


if __name__ == "__main__":
    try:
        port_env = os.getenv("LUMINA_PORT")
        port = int(port_env) if (port_env and port_env.isdigit()) else 53247
        prompt = "create a python todo app with add, list, mark complete, delete, and json storage"
        
        args = sys.argv[1:]
        non_flag_args = []
        for arg in args:
            if arg.isdigit():
                port = int(arg)
            else:
                non_flag_args.append(arg)
                
        if non_flag_args:
            prompt = " ".join(non_flag_args)
            
        generates = Generation(0.7, port, "Noneatall")
        print(f"\n[Lumina Agentic] Running generator on port {port}...")
        print(f"[Lumina Agentic] Task: {prompt}")
        result = generates.generate(prompt)
        print(f"\n[Lumina Agentic] Result:\n{result}")
    except Exception as e:
        logging.error(f"Main execution error: {e}")
        print(f"Error occurred: {e}")
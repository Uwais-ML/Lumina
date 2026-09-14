import logging
import os
from pathlib import Path
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import TextLoader
from langchain_chroma import Chroma
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
            
            loader = TextLoader(self.path)
            docs = loader.load()
            return docs
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
    def __init__(self, temp, port, api_key):
        self.temp = temp
        self.port = port
        self.api_key = api_key
        
        print("Loading embedding model into memory... (Only happens once)")
        self.embedding_model = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )
        
        self.llm_implementation = ChatOpenAI(
            base_url=f"http://localhost:{self.port}/v1",
            api_key=self.api_key or "NOT-NEEDED",
            model="Local LLM",
            temperature=self.temp
        )
        self.llm_agentic = ChatOpenAI(
            base_url=f"http://localhost:{self.port}/v1",
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
            prompt_context = '\n'.join(prompt_context.split('\n')[1:])
            print(f"Retrieved Context: {prompt_context}...")  
            
            prompt_template = ChatPromptTemplate.from_messages([
                (
                    "system",
                    "You are an AI assistant that writes code strictly based on the provided context.\n"
                    "You only write code and no explabations. only code.\n"
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
                with open("implementation.txt", "w") as f:
                    f.write(response.content)
                self._fallback_used = True  
                logging.info("Implementation plan written to file")
            except Exception as e:
                logging.error(f"Failed to write implementation.txt: {e}")
            
            return response.content


if __name__ == "__main__":
    try:
        generates = Generation(0.8, 49494, "Noneatall")
        print("\nRunning generator...")
        result = generates.generate("write me a code that takes a list of sting and a alphabet and returns the list of numbers the words appeared in the list")
        print(f"\nResult:\n{result}")
    except Exception as e:
        logging.error(f"Main execution error: {e}")
        print(f"Error occurred: {e}")
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma 
from langchain_openai import ChatOpenAI
from langchain_huggingface import HuggingFaceEmbeddings  
from langchain_core.messages import HumanMessage, SystemMessage
import os
import sys
if len(sys.argv) > 1:
    file_path = sys.argv[1]
else:
    file_path = "data/sample.txt"

if not os.path.exists(file_path):
    print(f" Error: File not found: {file_path}")
    print(f" Current directory: {os.getcwd()}")
    sys.exit(1)

print(f"Using file: {file_path}")

class TextLoaderWrapper:  
    def __init__(self, file_path):
        self.file_path = file_path
    
    def load_text(self):
        loader = TextLoader(self.file_path)
        documents = loader.load()
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

class Database:
    def __init__(self, persist_directory):
        self.persist_directory = persist_directory
        self.embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )
    
    def create_vectorstore(self, chunks):
        """Create a new vector store (only called if DB doesn't exist)"""
        if not chunks:
            print(" No valid chunks available. Returning empty vectorstore without upserting.")
            return EmptyVectorStore()

        print(" Creating new vector store with embeddings...")
        vectorstore = Chroma.from_documents(
            chunks,
            self.embeddings,
            persist_directory=self.persist_directory
        )
        print("Vector store created and persisted!")
        return vectorstore
    
    def load_vectorstore(self):
        """Load existing vector store (no embedding)"""
        print(" Loading existing vector store...")
        vectorstore = Chroma(
            persist_directory=self.persist_directory,
            embedding_function=self.embeddings
        )
        print("Vector store loaded!")
        return vectorstore
    
    def get_vectorstore(self, chunks=None, force_rebuild=False):
        """Smart load: use existing if available, otherwise create"""
        import os
        
        db_exists = os.path.exists(self.persist_directory) and os.listdir(self.persist_directory)
        
        if db_exists and not force_rebuild:
            return self.load_vectorstore()
        else:
            if chunks is None:
                raise ValueError("No chunks provided and no existing DB found.")
            if force_rebuild:
                print(" Force rebuild requested...")
            return self.create_vectorstore(chunks)
    
    def query_vectorsearch(self, vectorstore, query, k=3):
        print(f" Searching for '{query}'...")
        if hasattr(vectorstore, "similarity_search"):
            results = vectorstore.similarity_search(query, k=k)
        else:
            results = []
        print(f"Found {len(results)} relevant chunks")
        return results


class EmptyVectorStore:
    def similarity_search(self, query, k=3):
        return []

class AIcall:
    def __init__(self, model_name, temperature=0.7, base_url=None, api_key=None):
        self.model_name = model_name
        self.temperature = temperature
        
        
        openai_api_key = api_key or os.getenv("QWEN_API_KEY", "EMPTY")
        openai_base_url = base_url or os.getenv("QWEN_BASE_URL", "http://127.0.0.1:49494")
        
        print(f"Connecting to Qwen server at: {openai_base_url}")
        self.llm = ChatOpenAI(
            model=model_name,
            temperature=temperature,
            openai_api_key=openai_api_key,
            openai_api_base=openai_base_url
        )
    
    def generate_reponse(self, query, context_chunks):  
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


if __name__ == "__main__":
    try:
        loader = TextLoaderWrapper(file_path)
        docs = loader.load_text()
        chunks = loader.chunk_text(docs)
        
        db = Database("./chroma_db")
        
        vectorstore = db.create_vectorstore(chunks)
        print("New database created with embeddings")
        
        for i in range(10):
            query = input("\n Enter your question: ")
            
            retrieved_chunks = db.query_vectorsearch(vectorstore, query, k=3)
            
            ai = AIcall(
                model_name="qwen2.5-7b-instruct"
            )
            answer = ai.generate_reponse(query, retrieved_chunks)
            
            print(f"ANSWER: {answer}")
            print("\n SOURCES USED:")
            for i, chunk in enumerate(retrieved_chunks, 1):
                print(f"{i}. {chunk.page_content[:200]}...")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
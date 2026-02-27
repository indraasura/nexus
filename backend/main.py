from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os
import pandas as pd
from pptx import Presentation
from dotenv import load_dotenv
import io
from pathlib import Path

# --- CORPORATE NETWORK & SSL BYPASS ---
import ssl
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context

os.environ["CURL_CA_BUNDLE"] = ""
os.environ["REQUESTS_CA_BUNDLE"] = ""
os.environ["SSL_CERT_FILE"] = ""

# --- LANGCHAIN & AI IMPORTS ---
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.documents import Document
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser

from dotenv import load_dotenv, find_dotenv
import os

# Automatically hunt down the .env file anywhere in the project
load_dotenv(find_dotenv())

# --- STARTUP SANITY CHECK ---
print("\n" + "="*30)
print("🔍 ENVIRONMENT CHECK")
print(f"Google Key Loaded: {'✅ YES' if os.getenv('GOOGLE_API_KEY') else '❌ NO'}")
print(f"OpenAI Key Loaded: {'✅ YES' if os.getenv('OPENAI_API_KEY') else '❌ NO'}")
print("="*30 + "\n")

app = FastAPI()

# CORS CONFIGURATION: Allows local HTML files (origin 'null') to communicate with the server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory storage for vector databases
active_databases = {}

# --- DOCUMENT PARSING UTILITIES ---
def read_excel(file_bytes):
    # Requires 'openpyxl' and 'tabulate'
    df = pd.read_excel(io.BytesIO(file_bytes))
    return df.to_markdown()

def read_csv(file_bytes):
    df = pd.read_csv(io.BytesIO(file_bytes))
    return df.to_markdown()

def read_ppt(file_bytes):
    prs = Presentation(io.BytesIO(file_bytes))
    text_runs = []
    for slide in prs.slides:
        for shape in slide.shapes:
            if hasattr(shape, "text"):
                text_runs.append(shape.text)
    return "\n".join(text_runs)

# --- API ENDPOINTS ---

@app.post("/upload")
async def upload_files(files: list[UploadFile] = File(...), model: str = Form(...)):
    documents = []
    
    try:
        for file in files:
            contents = await file.read()
            ext = file.filename.split('.')[-1].lower()
            raw_text = ""
            
            if ext in ['xlsx', 'xls']:
                raw_text = read_excel(contents)
            elif ext == 'csv':
                raw_text = read_csv(contents)
            elif ext in ['pptx', 'ppt']:
                raw_text = read_ppt(contents)
            else:
                raw_text = contents.decode('utf-8', errors='ignore')
                
            if raw_text:
                documents.append(Document(page_content=raw_text, metadata={"source": file.filename}))
                
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File parsing error: {str(e)}")
            
    if not documents:
        raise HTTPException(status_code=400, detail="No readable text found.")

    try:
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=10000, chunk_overlap=1000)
        chunks = text_splitter.split_documents(documents)
        
        # Explicitly fetch keys to bypass auto-detection issues
        google_key = os.getenv("GOOGLE_API_KEY")
        openai_key = os.getenv("OPENAI_API_KEY")

        if "gemini" in model.lower():
            embeddings = GoogleGenerativeAIEmbeddings(
                model="gemini-embedding-001", 
                google_api_key=google_key,
                transport="rest"
            )
            db_key = "gemini"
        else:
            embeddings = OpenAIEmbeddings(
                model="text-embedding-3-small",
                openai_api_key=openai_key
            )
            db_key = "openai"
            
        vector_store = FAISS.from_documents(chunks, embeddings)
        active_databases[db_key] = vector_store
        
        return {"status": "success", "message": f"Data synced to {db_key.upper()}."}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI Processing Error: {str(e)}")

def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)

@app.post("/chat")
async def chat(message: str = Form(...), model: str = Form(...)):
    db_key = "gemini" if "gemini" in model.lower() else "openai"
    
    if db_key not in active_databases:
        raise HTTPException(status_code=400, detail=f"Database not synced for {db_key.upper()}.")
        
    vector_store = active_databases[db_key]
    google_key = os.getenv("GOOGLE_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")
    
    try:
        if "gemini" in db_key:
            llm = ChatGoogleGenerativeAI(
                model="gemini-2.5-flash", 
                google_api_key=google_key,
                temperature=0, 
                transport="rest"
            )
        else:
            llm = ChatOpenAI(
                model="gpt-4o", 
                openai_api_key=openai_key,
                temperature=0
            )
            
        system_prompt = (
            "You are a meticulous enterprise data assistant. Use the provided context to answer the user's question. "
            "CRITICAL INSTRUCTIONS:\n"
            "1. TABLES: When asked to list, group, or show all items, output a COMPLETE and exhaustive Markdown table. Do not summarize.\n"
            "2. CHARTS: If the user asks for a chart or graph, output a valid JSON object wrapped EXACTLY in a ```chart ... ``` code block. "
            "The JSON must be a valid Chart.js configuration object (type, data, options). "
            "Keep design modern and minimal.\n"
            "If you don't know the answer based on the context, say you don't know.\n\n"
            "Context: {context}"
        )
        
        prompt_template = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "{input}"),
        ])
        
        retriever = vector_store.as_retriever(search_kwargs={"k": 50})
        rag_chain = (
            {"context": retriever | format_docs, "input": RunnablePassthrough()}
            | prompt_template
            | llm
            | StrOutputParser()
        )
        
        answer = rag_chain.invoke(message)
        return {"answer": answer}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat generation error: {str(e)}")
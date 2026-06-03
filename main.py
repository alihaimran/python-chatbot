from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import psycopg2
import psycopg2.extras
import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", 5432),
        database=os.getenv("DB_NAME", "chatbot_db"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD"),
    )

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id SERIAL PRIMARY KEY,
            session_id VARCHAR(100) UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id SERIAL PRIMARY KEY,
            session_id VARCHAR(100) NOT NULL,
            role VARCHAR(20) NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    conn.commit()
    cur.close()
    conn.close()
    print("Database ready!")

@app.on_event("startup")
async def startup():
    init_db()

class ChatRequest(BaseModel):
    session_id: str
    message: str

class ChatResponse(BaseModel):
    reply: str

def save_message(session_id, role, content):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("INSERT INTO sessions (session_id) VALUES (%s) ON CONFLICT DO NOTHING", (session_id,))
        cur.execute("INSERT INTO messages (session_id, role, content) VALUES (%s, %s, %s)", (session_id, role, content))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

def get_history(session_id):
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT role, content FROM messages WHERE session_id = %s ORDER BY created_at ASC LIMIT 20", (session_id,))
        messages = [dict(row) for row in cur.fetchall()]
        cur.close()
        conn.close()
        return messages
    except:
        return []

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    history = get_history(req.session_id)
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    messages = history + [{"role": "user", "content": req.message}]
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages
    )
    reply = response.choices[0].message.content
    save_message(req.session_id, "user", req.message)
    save_message(req.session_id, "assistant", reply)
    return ChatResponse(reply=reply)

@app.get("/history/{session_id}")
async def get_chat_history(session_id: str):
    return get_history(session_id)
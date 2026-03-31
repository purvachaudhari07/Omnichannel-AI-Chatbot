import os
import warnings
from dotenv import load_dotenv
from groq import Groq
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

# 1. SETUP & SECURITY
load_dotenv()
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
warnings.filterwarnings("ignore")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
client_groq = Groq(api_key=GROQ_API_KEY)

# Path setup
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'database')

# Initialize DB and AI Model
client_qdrant = QdrantClient(path=DB_PATH)
embed_model = SentenceTransformer('all-MiniLM-L6-v2')
COLLECTION_NAME = "iac_collection"

def ask_chatbot(user_query):
    # --- STEP A: GREETINGS ---
    greetings = ['hi', 'hello', 'hii', 'hey', 'hy', 'hola']
    if user_query.lower().strip() in greetings:
        return "Hello! How can I assist you with IAC today?"

    closings = ['ok', 'done', 'thanks', 'thank you', 'understood', 'cool', 'got it', 'fine']
    if user_query.lower().strip() in closings:
        return "Thank you for reaching out! Do let me know if you have any other questions regarding IAC."

    # --- STEP B: RETRIEVAL ---
    query_vector = embed_model.encode(user_query).tolist()
    search_result = client_qdrant.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        limit=1 
    ).points

    context = ""
    if search_result:
        context = search_result[0].payload.get('answer', "")

    # --- STEP C: THE "TRUTH" GENERATION ---
    system_rules = """
    You are a professional IAC Assistant.
    1. PRIMARY SOURCE: Always check 'PROVIDED_DATA' first for the answer.
    2. REASONING: If user asks "Why", provide a logical, professional reason.
    3. HELPFUL INTRO: Use natural language. 
    4. NO DATA LIMIT: If link/contact is missing, refer to dashboard.
    5. SCOPE: Stay focused on IAC.
    6. Numbers: Give answers as they are in PROVIDED_DATA.
    7. NO REPETITION: Don't start with "Yes" unless it's a Yes/No question.
    8. DIRECT DATA: For "How to choose," use PROVIDED_DATA exactly.
    9. REASONING: Only extra reasoning if they ask "Why?".
    10. NO METADATA: Strictly no labels like "Category:".
    11. PROFESSIONAL TONE: Be direct, helpful, and concise.
    """

    user_prompt = f"USER_QUESTION: {user_query}\n\nPROVIDED_DATA: {context}"

    try:
        completion = client_groq.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": system_rules},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.0
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        return f"Bot Error: {e}"

# This block allows you to still test in terminal if you want
if __name__ == "__main__":
    while True:
        user_input = input("You: ")
        if user_input.lower() in ['exit', 'quit']: break
        print(f"Bot: {ask_chatbot(user_input)}")
import os
import json
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

load_dotenv()
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- AUTO-DETECT JSON PATH ---
possible_paths = [
    os.path.join(BASE_DIR, 'conversion', 'iac_data.json'),
    os.path.join(BASE_DIR, 'data', 'iac_data.json'),
    os.path.join(BASE_DIR, 'iac_data.json')
]

JSON_PATH = None
for path in possible_paths:
    if os.path.exists(path):
        JSON_PATH = path
        break

if not JSON_PATH:
    print("❌ Error: iac_data.json not found! Please ensure you ran convert.py.")
    exit()

print(f"✅ Found data at: {JSON_PATH}")

# --- DATABASE SETUP ---
DB_PATH = os.path.join(BASE_DIR, 'database')
client = QdrantClient(path=DB_PATH)
model = SentenceTransformer('all-MiniLM-L6-v2')
COLLECTION_NAME = "iac_collection"

def upload_data():
    if client.collection_exists(COLLECTION_NAME):
        client.delete_collection(COLLECTION_NAME)

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=384, distance=Distance.COSINE),
    )

    with open(JSON_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print(f"Uploading {len(data)} items to Qdrant...")
    points = []
    for idx, item in enumerate(data):
        text_to_embed = f"{item['question']} {item['answer']}"
        vector = model.encode(text_to_embed).tolist()
        points.append(PointStruct(id=idx, vector=vector, payload=item))

    client.upsert(collection_name=COLLECTION_NAME, points=points)
    print(f"✅ Database updated successfully!")

if __name__ == "__main__":
    upload_data()
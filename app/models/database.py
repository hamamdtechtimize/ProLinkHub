from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

MONGODB_URL = os.getenv("MONGODB_URL")
DB_NAME = os.getenv("MONGODB_DB_NAME")

# Async MongoDB client
async_client = AsyncIOMotorClient(MONGODB_URL)
async_db = async_client[DB_NAME]

# Collections
consultations = async_db["consultations"]
users_collection = async_db["users"]
quiz_questions = async_db["quiz_questions"]
chatbot_questions = async_db["chatbot_questions"]

# Create indexes
async def create_indexes():
    await consultations.create_index("session_id", unique=True)
    await users_collection.create_index("email", unique=True)
    await quiz_questions.create_index("order", unique=True)
    await chatbot_questions.create_index("question_text")
    await chatbot_questions.create_index("created_at")

# Database connection dependency
async def get_db():
    try:
        yield async_db
    finally:
        pass  # Connection is handled by motor

# Initialize database
async def init_db():
    await create_indexes()

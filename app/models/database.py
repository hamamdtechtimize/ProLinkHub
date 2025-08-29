from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

MONGODB_URL = os.getenv("MONGODB_URL")
DB_NAME = os.getenv("MONGODB_DB_NAME")

# Lazy-loaded MongoDB client and database
async_client = None
async_db = None

# Collections (will be initialized when needed)
consultations = None
users_collection = None
quiz_questions = None
chatbot_questions = None
hvac_categories = None

# Initialize database connection
async def init_connection():
    global async_client, async_db, consultations, users_collection, quiz_questions, chatbot_questions, hvac_categories
    
    if async_client is None:
        async_client = AsyncIOMotorClient(MONGODB_URL)
        async_db = async_client[DB_NAME]
        
        # Initialize collections
        consultations = async_db["consultations"]
        users_collection = async_db["users"]
        quiz_questions = async_db["quiz_questions"]
        chatbot_questions = async_db["chatbot_questions"]
        hvac_categories = async_db["hvac_categories"]

# Create indexes
async def create_indexes():
    await init_connection()
    await consultations.create_index("session_id", unique=True)
    await users_collection.create_index("email", unique=True)
    await quiz_questions.create_index("order", unique=True)
    await chatbot_questions.create_index("question_text")
    await chatbot_questions.create_index("created_at")

# Database connection dependency
async def get_db():
    await init_connection()
    try:
        yield async_db
    finally:
        pass  # Connection is handled by motor

# Get collections safely
async def get_consultations():
    await init_connection()
    return consultations

async def get_users():
    await init_connection()
    return users_collection

async def get_quiz_questions():
    await init_connection()
    return quiz_questions

async def get_chatbot_questions():
    await init_connection()
    return chatbot_questions

async def get_hvac_categories():
    await init_connection()
    return hvac_categories

# Initialize database
async def init_db():
    await create_indexes()

from fastapi import APIRouter, Depends, HTTPException
from typing import List
from ..models import models, database
from motor.motor_asyncio import AsyncIOMotorDatabase

router = APIRouter()

@router.get("/questions", response_model=List[models.QuizQuestion])
async def get_quiz_questions(db: AsyncIOMotorDatabase = Depends(database.get_db)):
    """Get all quiz questions ordered by their order field"""
    cursor = db.quiz_questions.find({}).sort("order", 1)
    questions = await cursor.to_list(length=1000)
    # Convert MongoDB _id to string
    for q in questions:
        if "_id" in q:
            q["_id"] = str(q["_id"])
    return [models.QuizQuestion(**q) for q in questions]

@router.post("/questions/seed")
async def seed_quiz_questions(db: AsyncIOMotorDatabase = Depends(database.get_db)):
    """Seed the quiz questions collection with initial data"""
    # Check if questions already exist
    existing_count = await db.quiz_questions.count_documents({})
    if existing_count > 0:
        return {"message": f"Questions already exist ({existing_count} questions found). Skipping seed operation."}
    
    # Define the initial questions
    quiz_questions = [
        # Stage 1: The Basics ("Let's Get Started")
        {
            "question_text": "What is your full name?",
            "input_type": "text",
            "is_required": True,
            "order": 1
        },
        {
            "question_text": "What is the address of the property for this project?",
            "input_type": "text",
            "is_required": True,
            "order": 2
        },
        {
            "question_text": "What's the best email to send your report to?",
            "input_type": "email",
            "is_required": True,
            "order": 3
        },
        {
            "question_text": "And what is a good mobile number in case we get disconnected during a future call?",
            "input_type": "tel",
            "is_required": True,
            "order": 4
        },
        
        # Stage 2: Your Home's Profile ("The Lay of the Land")
        {
            "question_text": "About how old is your main HVAC system?",
            "input_type": "radio",
            "options": ["0-5 Years", "6-10 Years", "11-15 Years", "15+ Years"],
            "is_required": True,
            "order": 5
        },
        {
            "question_text": "What's the approximate square footage of the area this system heats and cools?",
            "input_type": "radio",
            "options": ["Under 1,500 sq ft", "1,500 - 2,200 sq ft", "2,200 - 3,000 sq ft", "Over 3,000 sq ft"],
            "is_required": True,
            "order": 6
        },
        {
            "question_text": "How many separate systems control your home's temperature?",
            "input_type": "radio",
            "options": ["1", "2", "3", "4"],
            "is_required": True,
            "order": 7
        },
        {
            "question_text": "What kind of system do you currently have?",
            "input_type": "radio",
            "options": [
                "Furnace/Air Conditioner",
                "Heat Pump/Air handler",
                "Mini Split",
                "Package unit",
            ],
            "is_required": True,
            "order": 8
        },
        {
            "question_text": "Anyone have any underlying health conditions like seasonal allergies etc?",
            "input_type": "text",
            "is_required": False,
            "order": 9
        },
        
        # Stage 3: Your Comfort Challenges ("The Pain Diagnosis")
        {
            "question_text": "What's the #1 frustration you're hoping to solve with a new system? (Check all that apply)",
            "input_type": "checkbox",
            "options": [
                "High Energy Bills",
                "Uneven Temperatures (Hot & cold spots)",
                "Poor Air Quality (Allergies, dust, stuffiness)",
                "System is Too Loud",
                "It's Unreliable / Broken Down",
                "It's Just Old & I'm Planning Ahead"
            ],
            "is_required": True,
            "order": 10
        },
        
        # Stage 4: Your Project Goals ("The Solution Blueprint")
        {
            "question_text": "When it comes to a new system, which of these sounds most like you?",
            "input_type": "radio",
            "options": [
                "Budget-Focused",
                "Efficiency & Value", 
                "Ultimate Comfort"
            ],
            "is_required": True,
            "order": 11
        }
    ]
    
    # Insert the questions
    result = await db.quiz_questions.insert_many(quiz_questions)
    return {"message": f"Successfully seeded {len(result.inserted_ids)} questions"}

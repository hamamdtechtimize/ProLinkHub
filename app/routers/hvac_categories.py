from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase
from ..models import database
from bson import ObjectId

router = APIRouter()

def serialize_mongo_doc(doc):
    """Convert MongoDB document to JSON-serializable format"""
    if isinstance(doc, dict):
        return {
            key: str(value) if isinstance(value, ObjectId)
            else serialize_mongo_doc(value) if isinstance(value, (dict, list))
            else value
            for key, value in doc.items()
        }
    elif isinstance(doc, list):
        return [serialize_mongo_doc(item) for item in doc]
    return doc

@router.get("/hvac-categories")
async def get_hvac_image_categories(db: AsyncIOMotorDatabase = Depends(database.get_db)):
    """Get all HVAC image categories and their requirements from database"""
    try:
        # First try to get categories from database
        categories = await db.hvac_categories.find().to_list(1000)
        
        if categories:
            # Return categories from database (serialized)
            return [serialize_mongo_doc(cat) for cat in categories]
        else:
            return []
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get HVAC categories: {str(e)}")

@router.post("/hvac-categories/seed")
async def seed_hvac_categories(db: AsyncIOMotorDatabase = Depends(database.get_db)):
    """Seed or update HVAC image categories in the database"""
    
    hvac_categories = [
        {
            "category": "outdoor_unit",
            "display_name": "The Outdoor Unit (AC or Heat Pump)",
            "discount_amount": 150.0,
            "description": "These photos tell us the age, size, efficiency, and condition of your system.",
            "why_we_need_this": "This is crucial for us to understand your system's efficiency and overall condition.",
            "warning": "When taking photos of your outdoor unit, be careful of any sharp edges or electrical components. Make sure the area is clear of obstacles.",
            "sub_categories": [
                {
                    "key": "big_picture",
                    "display_name": "Big Picture",
                    "description": "Photo from 10–15 ft showing the whole outdoor unit.",
                    "tip": "Make sure to capture surroundings too.",
                    "image":""
                },
                {
                    "key": "data_plate",
                    "display_name": "Data Plate",
                    "description": "Close photo of model/serial sticker.",
                    "tip": "Wipe it clean if dirty.",
                    "image":""
                }
            ]
        },
        {
            "category": "power_hub",
            "display_name": "The Power Hub (Breaker Panel)",
            "discount_amount": 50.0,
            "description": "Understand your home's electrical capacity for safe installation.",
            "why_we_need_this": "Ensures your home can safely handle modern upgrades.",
            "warning": "Please ensure your hands are completely dry before opening the panel cover. Do not touch any internal wiring.",
            "sub_categories": [
                {
                    "key": "panel_cover",
                    "display_name": "Panel Cover",
                    "description": "Closed breaker panel with brand visible.",
                    "tip": "Stand back 3–4 feet.",
                    "image":""
                },
                {
                    "key": "inside_panel",
                    "display_name": "Inside Panel",
                    "description": "Open panel showing breakers.",
                    "tip": "Use flash for clarity.",
                    "image":""
                }
            ]
        },
        {
            "category": "command_center",
            "display_name": "Command Center (Thermostat)",
            "discount_amount": 25.0,
            "description": "Helps us recommend the best smart thermostat upgrades.",
            "why_we_need_this": "Shows how you control your system.",
            "warning": "Be careful when removing your thermostat cover if needed. Turn off the system before touching any wiring.",
            "sub_categories": [
                {
                    "key": "main_thermostat",
                    "display_name": "Main Thermostat",
                    "description": "Photo of your main thermostat.",
                    "tip": "Capture the display clearly.",
                    "image":""
                }
            ]
        },
        {
            "category": "energy_bill",
            "display_name": "Energy Bill",
            "discount_amount": 500.0,
            "description": "Shows your current usage to estimate savings.",
            "why_we_need_this": "Helps us project efficiency improvements.",
            "warning": "Feel free to black out your personal account number or address if you prefer. We only need to see your usage patterns and rates.",
            "sub_categories": [
                {
                    "key": "recent_bill",
                    "display_name": "Recent Bill",
                    "description": "Photo of your latest energy bill.",
                    "tip": "Ensure account # and kWh usage are visible.",
                    "image":""
                    
                }
            ]
        }
    ]
    
    try:
        # Use upsert to either insert new or update existing
        for category_data in hvac_categories:
            await db.hvac_categories.update_one(
                {"category": category_data["category"]},
                {"$set": category_data},
                upsert=True
            )
        
        return {
            "message": "HVAC categories seeded successfully",
            "total_categories": len(hvac_categories),
            "categories": hvac_categories
        }
        
    except Exception as e:
         raise HTTPException(
             status_code=500,
             detail=f"Failed to seed HVAC categories: {str(e)}"
         )


@router.put("/admin/hvac-categories/{category}")
async def update_hvac_category(
    category: str,
    category_data: Dict[str, Any],
    db: AsyncIOMotorDatabase = Depends(database.get_db)
):
    """Update a specific HVAC category in the database"""
    try:
        # Add the category key to the data if not present
        if "category" not in category_data:
            category_data["category"] = category
        
        result = await db.hvac_categories.update_one(
            {"category": category},
            {"$set": category_data},
            upsert=True
        )
        
        if result.modified_count > 0 or result.upserted_id:
            return {
                "message": f"HVAC category '{category}' updated successfully",
                "category": category,
                "modified_count": result.modified_count,
                "upserted": result.upserted_id is not None
            }
        else:
            raise HTTPException(
                status_code=404,
                detail=f"HVAC category '{category}' not found"
            )
            
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update HVAC category: {str(e)}"
        )

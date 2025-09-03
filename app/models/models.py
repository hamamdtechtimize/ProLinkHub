from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional, List, Dict, Any
from bson import ObjectId
from pydantic_core import core_schema

class PyObjectId(str):
    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler) -> core_schema.CoreSchema:
        return core_schema.json_or_python_schema(
            json_schema=core_schema.str_schema(),
            python_schema=core_schema.union_schema([
                core_schema.is_instance_schema(ObjectId),
                core_schema.chain_schema([
                    core_schema.str_schema(),
                    core_schema.no_info_plain_validator_function(cls.validate)
                ])
            ]),
            serialization=core_schema.plain_serializer_function_schema(
                lambda x: str(x)
            )
        )

    @classmethod
    def validate(cls, value):
        if not ObjectId.is_valid(value):
            raise ValueError("Invalid ObjectId")
        return ObjectId(value)

class MongoBaseModel(BaseModel):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        populate_by_name=True,
        json_encoders={ObjectId: str}
    )
    
    id: Optional[str] = Field(default=None, alias="_id")

    def dict(self, *args, **kwargs):
        if kwargs.get("by_alias", True):
            if hasattr(self, "id") and self.id:
                # Convert ObjectId to string if needed
                if isinstance(self.id, ObjectId):
                    self.id = str(self.id)
        return super().dict(*args, **kwargs)
    
    @classmethod
    def from_mongo(cls, data: dict):
        """Convert MongoDB document to model instance"""
        if data is None:
            return None
        
        # Convert _id ObjectId to string
        if "_id" in data and isinstance(data["_id"], ObjectId):
            data["_id"] = str(data["_id"])
        
        # Create a new dict with only the fields that exist in the model
        model_fields = cls.model_fields.keys()
        filtered_data = {}
        
        for key, value in data.items():
            if key in model_fields or key == "_id":
                filtered_data[key] = value
            
        return cls(**filtered_data)

class QuizQuestion(MongoBaseModel):
    question_text: str
    input_type: str
    options: Optional[List[str]] = None
    is_required: bool = False
    order: int

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "question_text": "What is your full name?",
            "input_type": "text",
            "is_required": True,
            "order": 1
        }
    })

class User(MongoBaseModel):
    email: str
    name: str
    is_admin: bool = False  # This will be set internally, not from user input

from enum import Enum

# HVAC Image Category Enum
class HVACImageCategory(str, Enum):
    OUTDOOR_UNIT = "outdoor_unit"
    POWER_HUB = "power_hub"
    COMMAND_CENTER = "command_center"
    INDOOR_SYSTEM = "indoor_system"
    ENERGY_BILL = "energy_bill"

# HVAC Image Sub-Category Enum
class HVACImageSubCategory(str, Enum):
    # Outdoor Unit sub-categories
    BIG_PICTURE = "big_picture"
    DATA_PLATE = "data_plate"
    
    # Power Hub sub-categories
    PANEL_COVER = "panel_cover"
    INSIDE_PANEL = "inside_panel"
    
    # Command Center sub-categories
    MAIN_THERMOSTAT = "main_thermostat"
    
    # Indoor System sub-categories
    INDOOR_UNIT = "indoor_unit"
    
    # Energy Bill sub-categories
    RECENT_BILL = "recent_bill"







class Consultation(MongoBaseModel):
    session_id: str
    user_id: Optional[str] = None
    quiz_answers: Dict = {}
    created_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = "pending"  # pending, answers_submitted, images_uploaded, estimate_ready, completed
    images: List[Dict[str, Any]] = []
    
    # Discount tracking
    total_discount: float = 0.0
    completed_categories: List[str] = []
    
    # Consultation progress tracking
    quiz_completed: bool = False
    images_completed: bool = False
    estimate_generated: bool = False
    
    def update_progress(self):
        """Update consultation progress based on current state"""
        self.quiz_completed = len(self.quiz_answers) > 0
        
        # Check if all required images are uploaded
        required_categories = ['outdoor_unit', 'power_hub', 'command_center', 'indoor_system', 'energy_bill']
        
        # Simple check for images completion
        self.images_completed = len(self.images) >= 8  # Max 7 images
        
        # Update overall status
        if self.images_completed and self.quiz_completed:
            self.status = "images_uploaded"
        elif self.quiz_completed:
            self.status = "answers_submitted"

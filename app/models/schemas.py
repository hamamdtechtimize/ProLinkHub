from pydantic import BaseModel, EmailStr, ConfigDict, Field
from typing import Optional, Dict, List, Any
from datetime import datetime
from bson import ObjectId
from pydantic_core import CoreSchema, core_schema

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
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda x: str(x)
            )
        )

    @classmethod
    def validate(cls, value):
        if not ObjectId.is_valid(value):
            raise ValueError("Invalid ObjectId")
        return ObjectId(value)

class UserBase(BaseModel):
    email: EmailStr
    name: str

class UserCreate(UserBase):
    password: str

class User(UserBase):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    is_admin: bool = False  # This will be set internally, not from user input
    
    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str})

class QuizQuestion(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    question: str
    question_type: str  # "multiple_choice", "text", "number", etc.
    options: Optional[List[str]] = None
    required: bool = True

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str})

from enum import Enum

# HVAC Image Schemas
class HVACImageCategory(str, Enum):
    OUTDOOR_UNIT = "outdoor_unit"
    POWER_HUB = "power_hub"
    COMMAND_CENTER = "command_center"
    INDOOR_SYSTEM = "indoor_system"
    ENERGY_BILL = "energy_bill"

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





class ConsultationBase(BaseModel):
    quiz_answers: Dict[str, Any] = {}
    status: str = "in_progress"

class ConsultationCreate(ConsultationBase):
    pass

class Consultation(ConsultationBase):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    session_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    images: List[Dict[str, Any]] = []
    quiz_completed: bool = False
    images_completed: bool = False
    estimate_generated: bool = False

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str})



class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class ChatbotQuestionCreate(BaseModel):
    question_text: str
    response_text: Optional[str] = None

class ChatbotQuestion(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    question_text: str
    response_text: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str})

class ChatbotResponse(BaseModel):
    question: ChatbotQuestion
    responses: List[ChatbotQuestion] = []

class AdminLogin(BaseModel):
    email: EmailStr
    password: str

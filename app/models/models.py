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

class ConsultationImage(MongoBaseModel):
    consultation_id: str
    image_type: str
    image_path: str
    analysis_result: Optional[Dict] = None
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)



class Consultation(MongoBaseModel):
    session_id: str
    user_id: Optional[str] = None
    quiz_answers: Dict = {}
    created_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = "pending"  # pending, answers_submitted, estimate_ready, images_uploaded, completed, etc.
    images: List[ConsultationImage] = []

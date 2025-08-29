import os
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
import aiofiles
from PIL import Image
import io

from ..models.models import (
    ConsultationImage, 
    ConsultationImages, 
    Consultation,
    HVACImageCategory,
    HVACImageSubCategory
)
from ..models.schemas import ImageUploadRequest, ImageUploadResponse

class ImageService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.upload_dir = "uploads"
        self.max_file_size = 10 * 1024 * 1024  # 10MB
        self.allowed_mime_types = [
            "image/jpeg",
            "image/jpg", 
            "image/png",
            "image/webp"
        ]
        
        # Ensure upload directory exists
        os.makedirs(self.upload_dir, exist_ok=True)
    
    async def upload_image(
        self, 
        consultation_id: str,
        category: HVACImageCategory,
        sub_category: HVACImageSubCategory,
        file_content: bytes,
        file_name: str,
        mime_type: str,
        user_notes: Optional[str] = None
    ) -> ImageUploadResponse:
        """Upload and store an image for consultation"""
        
        try:
            # Validate file
            if not self._validate_file(file_content, mime_type):
                return ImageUploadResponse(
                    success=False,
                    message="Invalid file type or size"
                )
            
            # Generate unique filename
            file_extension = self._get_file_extension(mime_type)
            unique_filename = f"{uuid.uuid4()}{file_extension}"
            
            # Create category subdirectory
            category_dir = os.path.join(self.upload_dir, consultation_id, category)
            os.makedirs(category_dir, exist_ok=True)
            
            # Save file
            file_path = os.path.join(category_dir, unique_filename)
            async with aiofiles.open(file_path, 'wb') as f:
                await f.write(file_content)
            
            # Create image record
            image_data = {
                "consultation_id": consultation_id,
                "category": category,
                "sub_category": sub_category,
                "image_url": f"/uploads/{consultation_id}/{category}/{unique_filename}",
                "image_path": file_path,
                "file_name": file_name,
                "file_size": len(file_content),
                "mime_type": mime_type,
                "user_notes": user_notes,
                "uploaded_at": datetime.utcnow(),
                "status": "pending",
                "upload_session_id": str(uuid.uuid4())
            }
            
            # Insert into database
            result = await self.db.consultation_images.insert_one(image_data)
            image_id = str(result.inserted_id)
            
            # Update consultation images collection
            await self._update_consultation_images(consultation_id, category, image_id)
            
            # Update consultation progress
            await self._update_consultation_progress(consultation_id)
            
            return ImageUploadResponse(
                success=True,
                image_id=image_id,
                image_url=image_data["image_url"],
                message="Image uploaded successfully",
                upload_session_id=image_data["upload_session_id"]
            )
            
        except Exception as e:
            return ImageUploadResponse(
                success=False,
                message=f"Upload failed: {str(e)}"
            )
    
    async def get_consultation_images(self, consultation_id: str) -> ConsultationImages:
        """Get all images for a consultation"""
        try:
            # Get consultation images
            consultation = await self.db.consultations.find_one({"_id": ObjectId(consultation_id)})
            if not consultation:
                return None
            
            # Get all images for this consultation
            images_cursor = self.db.consultation_images.find({"consultation_id": consultation_id})
            images = await images_cursor.to_list(length=None)
            
            # Organize images by category
            consultation_images = ConsultationImages(consultation_id=consultation_id)
            
            for image in images:
                image_obj = ConsultationImage(**image)
                if image_obj.category == HVACImageCategory.OUTDOOR_UNIT:
                    consultation_images.outdoor_unit_images.append(image_obj)
                elif image_obj.category == HVACImageCategory.POWER_HUB:
                    consultation_images.power_hub_images.append(image_obj)
                elif image_obj.category == HVACImageCategory.COMMAND_CENTER:
                    consultation_images.command_center_images.append(image_obj)
                elif image_obj.category == HVACImageCategory.INDOOR_SYSTEM:
                    consultation_images.indoor_system_images.append(image_obj)
                elif image_obj.category == HVACImageCategory.ENERGY_BILL:
                    consultation_images.energy_bill_images.append(image_obj)
            
            # Update completion status
            consultation_images.update_completion_status()
            
            return consultation_images
            
        except Exception as e:
            print(f"Error getting consultation images: {e}")
            return None
    
    async def get_image_by_id(self, image_id: str) -> Optional[ConsultationImage]:
        """Get a specific image by ID"""
        try:
            image_doc = await self.db.consultation_images.find_one({"_id": ObjectId(image_id)})
            if image_doc:
                return ConsultationImage(**image_doc)
            return None
        except Exception as e:
            print(f"Error getting image: {e}")
            return None
    
    async def delete_image(self, image_id: str) -> bool:
        """Delete an image"""
        try:
            # Get image details
            image = await self.get_image_by_id(image_id)
            if not image:
                return False
            
            # Delete file from disk
            if os.path.exists(image.image_path):
                os.remove(image.image_path)
            
            # Delete from database
            result = await self.db.consultation_images.delete_one({"_id": ObjectId(image_id)})
            
            if result.deleted_count > 0:
                # Update consultation progress
                await self._update_consultation_progress(image.consultation_id)
                return True
            
            return False
            
        except Exception as e:
            print(f"Error deleting image: {e}")
            return False
    
    async def get_consultation_progress(self, consultation_id: str) -> Dict[str, Any]:
        """Get consultation progress and completion status"""
        try:
            consultation_images = await self.get_consultation_images(consultation_id)
            if not consultation_images:
                return {}
            
            consultation_images.update_completion_status()
            
            return {
                "consultation_id": consultation_id,
                "total_images": consultation_images.total_images,
                "total_discount": consultation_images.total_discount,
                "completion_status": consultation_images.completion_status,
                "category_details": {
                    "outdoor_unit": {
                        "images": len(consultation_images.outdoor_unit_images),
                        "required": 2,
                        "completed": consultation_images.completion_status.get("outdoor_unit", False)
                    },
                    "power_hub": {
                        "images": len(consultation_images.power_hub_images),
                        "required": 2,
                        "completed": consultation_images.completion_status.get("power_hub", False)
                    },
                    "command_center": {
                        "images": len(consultation_images.command_center_images),
                        "required": 1,
                        "completed": consultation_images.completion_status.get("command_center", False)
                    },
                    "indoor_system": {
                        "images": len(consultation_images.indoor_system_images),
                        "required": 1,
                        "completed": consultation_images.completion_status.get("indoor_system", False)
                    },
                    "energy_bill": {
                        "images": len(consultation_images.energy_bill_images),
                        "required": 1,
                        "completed": consultation_images.completion_status.get("energy_bill", False)
                    }
                }
            }
            
        except Exception as e:
            print(f"Error getting consultation progress: {e}")
            return {}
    
    def _validate_file(self, file_content: bytes, mime_type: str) -> bool:
        """Validate uploaded file"""
        if len(file_content) > self.max_file_size:
            return False
        
        if mime_type not in self.allowed_mime_types:
            return False
        
        # Try to open as image to validate
        try:
            Image.open(io.BytesIO(file_content))
            return True
        except Exception:
            return False
    
    def _get_file_extension(self, mime_type: str) -> str:
        """Get file extension from MIME type"""
        extension_map = {
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp"
        }
        return extension_map.get(mime_type, ".jpg")
    
    async def _update_consultation_images(self, consultation_id: str, category: str, image_id: str):
        """Update consultation images collection"""
        try:
            # This would update a separate collection that tracks all images per consultation
            # For now, we'll update the main consultation document
            await self.db.consultations.update_one(
                {"_id": ObjectId(consultation_id)},
                {"$push": {f"images.{category}_images": image_id}}
            )
        except Exception as e:
            print(f"Error updating consultation images: {e}")
    
    async def _update_consultation_progress(self, consultation_id: str):
        """Update consultation progress status"""
        try:
            progress = await self.get_consultation_progress(consultation_id)
            
            # Update consultation status
            update_data = {
                "images_completed": all(progress.get("completion_status", {}).values()),
                "status": "images_uploaded" if all(progress.get("completion_status", {}).values()) else "answers_submitted"
            }
            
            await self.db.consultations.update_one(
                {"_id": ObjectId(consultation_id)},
                {"$set": update_data}
            )
            
        except Exception as e:
            print(f"Error updating consultation progress: {e}")
    
    def get_hvac_image_categories(self) -> List[Dict[str, Any]]:
        """Get information about all HVAC image categories"""
        return [
            {
                "category": "outdoor_unit",
                "display_name": "The Outdoor Unit (AC or Heat Pump)",
                "discount_amount": 150.0,
                "description": "These photos tell us the age, size, efficiency, and condition of your system.",
                "why_we_need_this": "This is crucial for us to understand your system's efficiency and overall condition.",
                "sub_categories": [
                    {
                        "key": "big_picture",
                        "display_name": "Big Picture",
                        "description": "Photo from 10–15 ft showing the whole outdoor unit.",
                        "tip": "Make sure to capture surroundings too."
                    },
                    {
                        "key": "data_plate",
                        "display_name": "Data Plate",
                        "description": "Close photo of model/serial sticker.",
                        "tip": "Wipe it clean if dirty."
                    }
                ]
            },
            {
                "category": "power_hub",
                "display_name": "The Power Hub (Breaker Panel)",
                "discount_amount": 50.0,
                "description": "Understand your home's electrical capacity for safe installation.",
                "why_we_need_this": "Ensures your home can safely handle modern upgrades.",
                "sub_categories": [
                    {
                        "key": "panel_cover",
                        "display_name": "Panel Cover",
                        "description": "Closed breaker panel with brand visible.",
                        "tip": "Stand back 3–4 feet."
                    },
                    {
                        "key": "inside_panel",
                        "display_name": "Inside Panel",
                        "description": "Open panel showing breakers.",
                        "tip": "Use flash for clarity."
                    }
                ]
            },
            {
                "category": "command_center",
                "display_name": "Command Center (Thermostat)",
                "discount_amount": 25.0,
                "description": "Helps us recommend the best smart thermostat upgrades.",
                "why_we_need_this": "Shows how you control your system.",
                "sub_categories": [
                    {
                        "key": "main_thermostat",
                        "display_name": "Main Thermostat",
                        "description": "Photo of your main thermostat.",
                        "tip": "Capture the display clearly."
                    }
                ]
            },
            {
                "category": "indoor_system",
                "display_name": "Indoor System",
                "discount_amount": 500.0,
                "description": "Helps us understand your air handler/furnace.",
                "why_we_need_this": "Tells us about indoor air movement and heating/cooling compatibility.",
                "sub_categories": [
                    {
                        "key": "indoor_unit",
                        "display_name": "Indoor Unit",
                        "description": "Photo of air handler/furnace.",
                        "tip": "Include labels if visible."
                    }
                ]
            },
            {
                "category": "energy_bill",
                "display_name": "Energy Bill",
                "discount_amount": 200.0,
                "description": "Shows your current usage to estimate savings.",
                "why_we_need_this": "Helps us project efficiency improvements.",
                "sub_categories": [
                    {
                        "key": "recent_bill",
                        "display_name": "Recent Bill",
                        "description": "Photo of your latest energy bill.",
                        "tip": "Ensure account # and kWh usage are visible."
                    }
                ]
            }
        ]

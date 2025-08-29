from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from typing import List, Dict, Any, Optional
import uuid
from ..models import models, database

from app.services.consultation_analyzer import ConsultationAnalyzer
from app.services.s3_service import S3Service
from app.services.pricing_service import PricingService
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId

router = APIRouter()
analyzer = ConsultationAnalyzer()
s3_service = S3Service()
pricing_service = PricingService()



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

@router.post("/session")
async def create_session(db: AsyncIOMotorDatabase = Depends(database.get_db)):
    """Create a new consultation session"""
    session_id = str(uuid.uuid4())
    consultation = {
        "session_id": session_id,
        "status": "pending",
        "quiz_answers": {},
        "created_at": datetime.utcnow()
    }
    
    result = await db.consultations.insert_one(consultation)
    created_consultation = await db.consultations.find_one({"_id": result.inserted_id})
    return {"session_id": session_id, "consultation": serialize_mongo_doc(created_consultation)}

@router.post("/consultation/{session_id}/submit-answers")
async def submit_consultation_answers(
    session_id: str,
    answers: Dict,
    db: AsyncIOMotorDatabase = Depends(database.get_db)
):
    """Submit answers to consultation questions
    
    Flow: submit_answers -> generate_estimate -> upload_images
    Status progression: pending -> answers_submitted -> estimate_ready -> images_uploaded
    """
    
    # First, verify if the session exists
    consultation = await db.consultations.find_one({"session_id": session_id})
    if not consultation:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Get all questions to validate the answers
    quiz_questions_collection = await database.get_quiz_questions()
    questions = await quiz_questions_collection.find().to_list(1000)
    questions_dict = {str(q["_id"]): q for q in questions}
    
    # Validate required questions
    for question in questions:
        if question["is_required"] and str(question["_id"]) not in answers:
            raise HTTPException(
                status_code=400, 
                detail=f"Missing required answer for question: {question['question_text']}"
            )
    
    # Prepare the formatted answers with question details
    formatted_answers = {}
    
    # Validate answer types and format answers
    for question_id, answer in answers.items():
        if question_id not in questions_dict:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid question ID: {question_id}"
            )
            
        question = questions_dict[question_id]
        
        # Type validation
        if question["input_type"] == "number":
            try:
                float(answer)
            except (ValueError, TypeError):
                raise HTTPException(
                    status_code=400,
                    detail=f"Answer for '{question['question_text']}' must be a number"
                )
                
        elif question["input_type"] in ["checkbox"] and question.get("options"):
            if not isinstance(answer, list):
                raise HTTPException(
                    status_code=400,
                    detail=f"Answer for '{question['question_text']}' must be a list of options"
                )
                
        elif question["input_type"] == "radio" and question.get("options"):
            if not isinstance(answer, str) or answer not in question["options"]:
                raise HTTPException(
                    status_code=400,
                    detail=f"Answer for '{question['question_text']}' must be one of the provided options"
                )
                
        # Store both question details and answer
        formatted_answers[question_id] = {
            "question_text": question["question_text"],
            "input_type": question["input_type"],
            "order": question["order"],
            "answer": answer
        }
        
        # Validate checkbox and radio options
        if question["input_type"] == "checkbox" and question.get("options"):
            invalid_options = [opt for opt in answer if opt not in question["options"]]
            if invalid_options:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid options for '{question['question_text']}': {invalid_options}"
                )
    
    # Update the consultation with formatted answers
    update_result = await db.consultations.update_one(
        {"session_id": session_id},
        {
            "$set": {
                "quiz_answers": formatted_answers,
                "status": "answers_submitted"
            }
        }
    )
    
    if update_result.modified_count == 0:
        raise HTTPException(status_code=400, detail="Failed to update consultation")
    
    # Return updated consultation
    updated_consultation = await db.consultations.find_one({"session_id": session_id})
    return {
        "message": "Answers submitted successfully",
        "consultation": serialize_mongo_doc(updated_consultation)
    }

@router.post("/consultation/{session_id}/images")
async def upload_hvac_image(
    session_id: str,
    category: str = Form(...),
    sub_category: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncIOMotorDatabase = Depends(database.get_db)
):
    """Upload HVAC system image with category and sub-category
    
    Images can be uploaded after answers are submitted or after estimate is generated.
    This allows for the flow: submit_answers -> generate_estimate -> upload_images
    
    Categories: outdoor_unit, power_hub, command_center, indoor_system, energy_bill
    Sub-categories: big_picture, data_plate, panel_cover, inside_panel, main_thermostat, indoor_unit, recent_bill
    """
    # First check if consultation exists and has answers submitted
    consultation = await db.consultations.find_one({"session_id": session_id})
    if not consultation:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if consultation["status"] not in ["answers_submitted", "estimate_ready", "images_uploaded"]:
        raise HTTPException(
            status_code=400, 
            detail="Please submit consultation answers before uploading images"
        )
    
    # Validate category and sub_category
    valid_categories = ["outdoor_unit", "power_hub", "command_center", "indoor_system", "energy_bill"]
    valid_sub_categories = ["big_picture", "data_plate", "panel_cover", "inside_panel", "main_thermostat", "indoor_unit", "recent_bill"]
    
    if category not in valid_categories:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category. Valid categories are: {', '.join(valid_categories)}"
        )
    
    if sub_category not in valid_sub_categories:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid sub_category. Valid sub_categories are: {', '.join(valid_sub_categories)}"
        )
    
    # Check file type
    if not file.content_type.startswith('image/'):
        raise HTTPException(
            status_code=400,
            detail="Only image files are allowed"
        )
    
    # Count existing images in consultation document (max 7 images)
    existing_images = consultation.get("images", [])
    if len(existing_images) >= 7:
        raise HTTPException(
            status_code=400,
            detail="Maximum 7 images allowed per consultation"
        )
    
    # Check if this category/sub-category combination already exists
    for img in existing_images:
        if img.get("category") == category and img.get("sub_category") == sub_category:
            raise HTTPException(
                status_code=400,
                detail=f"Image for {category} - {sub_category} already exists. You can only upload one image per sub-category."
            )
    
    # Initialize S3 service
    s3_service = S3Service()
    
    try:
        # Upload file to S3 with category-based naming
        image_number = len(existing_images) + 1
        s3_key = f"{str(consultation['_id'])}/hvac_images/{category}/{sub_category}_{image_number}"
        
        s3_url = await s3_service.upload_file(
            file.file,
            str(consultation["_id"]),
            s3_key
        )
        
        # Create categorized image object
        image = {
            "image_number": image_number,
            "image_url": s3_url,
            "original_filename": file.filename,
            "category": category,
            "sub_category": sub_category,
            "created_at": datetime.utcnow(),
            "s3_key": s3_key
        }
        
        # Update consultation status and add image directly to consultation document
        # If estimate is already ready, keep that status, otherwise set to images_uploaded
        new_status = "images_uploaded" if consultation["status"] != "estimate_ready" else "estimate_ready"
        
        await db.consultations.update_one(
            {"_id": consultation["_id"]},
            {
                "$set": {"status": new_status},
                "$push": {"images": image}
            }
        )
        
        # Calculate completed categories and total discount
        # Only apply discount when BOTH images of a category are uploaded
        category_image_counts = {}
        for img in existing_images + [image]:
            cat = img.get("category")
            category_image_counts[cat] = category_image_counts.get(cat, 0) + 1
        
        # Get HVAC categories to check which ones are fully completed
        hvac_categories_collection = await database.get_hvac_categories()
        hvac_categories = await hvac_categories_collection.find().to_list(1000)
        
        # Find categories that have both images uploaded
        fully_completed_categories = []
        new_total_discount = 0
        
        for cat in hvac_categories:
            category_key = cat.get("category")
            required_images = len(cat.get("sub_categories", []))
            uploaded_images = category_image_counts.get(category_key, 0)
            
            if uploaded_images >= required_images:
                fully_completed_categories.append(category_key)
                new_total_discount += cat.get("discount_amount", 0)
        
        # Update consultation with new discount and completed categories
        await db.consultations.update_one(
            {"_id": consultation["_id"]},
            {
                "$set": {
                    "total_discount": new_total_discount,
                    "completed_categories": fully_completed_categories
                }
            }
        )
        
        return {
            "message": "HVAC image uploaded successfully",
            "image_url": s3_url,
            "image_number": image_number,
            "category": category,
            "sub_category": sub_category,
            "total_images": len(existing_images) + 1,
            "completed_categories": fully_completed_categories,
            "total_discount": new_total_discount,
            "remaining_images": 7 - (len(existing_images) + 1)
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to upload image: {str(e)}"
        )
    

@router.get("/consultation/{session_id}/details")
async def get_consultation_details(
    session_id: str,
    db: AsyncIOMotorDatabase = Depends(database.get_db)
):
    """Get consultation details including quiz answers, images, and discount status"""
    # Get consultation with quiz answers and images
    consultation = await db.consultations.find_one({"session_id": session_id})
    if not consultation:
        raise HTTPException(status_code=404, detail="Consultation not found")
    
    # Return consultation response with discount info
    consultation_response = serialize_mongo_doc(consultation)
    
    return {
        "consultation": consultation_response,
        "discount_summary": {
            "total_discount": consultation.get("total_discount", 0),
            "completed_categories": consultation.get("completed_categories", []),
            "total_images": len(consultation.get("images", [])),
            "max_images": 7
        }
    }






@router.post("/consultation/{session_id}/analyze-all")
async def analyze_all_consultation_images(
    session_id: str,
    db: AsyncIOMotorDatabase = Depends(database.get_db)
):
    """
    Analyze all images in a consultation using OCR and return combined text.
    Downloads images from S3, applies OCR, and returns both individual and combined results.
    """
    try:
        # First check if consultation exists
        consultation = await db.consultations.find_one({"session_id": session_id})
        if not consultation:
            raise HTTPException(status_code=404, detail="Consultation not found")

        if consultation["status"] not in ["images_uploaded", "estimate_ready", "completed"]:
            raise HTTPException(status_code=400, detail="Consultation must have uploaded images before analysis")

        # Get images from consultation document
        images = consultation.get("images", [])
        if not images:
            raise HTTPException(status_code=404, detail="No images found for this consultation")

        # Extract S3 keys from images
        image_keys = [
            image.get("s3_key", "")  # Get S3 key from image object
            for image in images
            if image.get("s3_key")
        ]

        # Analyze all images
        analysis_results = await analyzer.analyze_consultation_images(
            str(consultation["_id"]),
            image_keys
        )

        # Update consultation with analysis results
        await db.consultations.update_one(
            {"_id": consultation["_id"]},
            {
                "$set": {
                    "image_analysis": analysis_results,
                    "analysis_completed_at": datetime.utcnow()
                }
            }
        )

        return {
            "message": "Analysis completed successfully",
            "consultation_id": str(consultation["_id"]),
            "results": {
                "combined_text": analysis_results["combined_text"],
                "total_images": analysis_results["total_images_analyzed"],
                "individual_results": analysis_results["individual_results"],
                "hvac_info": analysis_results.get("hvac_info", "No HVAC information could be extracted")
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to analyze images: {str(e)}"
        )

def calculate_pricing_estimate(quiz_answers: Dict, hvac_info: Dict = None) -> Dict[str, Any]:
    """Calculate Good-Better-Best pricing estimate based on quiz answers and HVAC analysis"""
    
    # Extract relevant quiz answers
    square_footage_text = None
    system_count_answer = None
    project_goal = None
    location = "Atlanta, GA"  # Hardcoded for MVP as specified
    
    for answer_data in quiz_answers.values():
        question_text = answer_data.get("question_text", "")
        answer = answer_data.get("answer", "")
        
        if "square footage" in question_text.lower():
            square_footage_text = answer
        elif "how many separate systems" in question_text.lower():
            system_count_answer = answer
        elif "which of these sounds most like you" in question_text.lower():
            project_goal = answer
    
    # Extract system count as integer
    system_count = pricing_service.extract_system_count(system_count_answer )
    
    # Generate pricing estimate using new service
    try:
        estimate = pricing_service.calculate_estimate(
            square_footage=square_footage_text or "1,500 - 2,200 sq ft",
            system_count=system_count
        )
        
        return estimate
        
    except Exception as e:
        # Fallback to basic estimate if pricing service fails
        return {
            "estimates": {
                "good": {
                    "label": "Budget-Focused",
                    "minPrice": 9500,
                    "maxPrice": 11500
                },
                "better": {
                    "label": "Efficiency & Value", 
                    "minPrice": 13500,
                    "maxPrice": 15500
                },
                "best": {
                    "label": "Ultimate Comfort",
                    "minPrice": 17000,
                    "maxPrice": 19500
                }
            },
            "tonnage": 3.5,
            "systemCount": 1,
            "error": f"Pricing calculation error: {str(e)}"
        }

@router.post("/consultation/{session_id}/generate-estimate")
async def generate_pricing_estimate(
    session_id: str,
    db: AsyncIOMotorDatabase = Depends(database.get_db)
):
    """Generate pricing estimate based on quiz answers only
    
    This endpoint can be called after submitting answers, before uploading images.
    Images can be uploaded later if additional analysis is needed.
    """
    try:
        # Get consultation data
        consultation = await db.consultations.find_one({"session_id": session_id})
        if not consultation:
            raise HTTPException(status_code=404, detail="Consultation not found")
        
        if not consultation.get("quiz_answers"):
            raise HTTPException(status_code=400, detail="Quiz answers required for pricing estimate")
        
        # Generate pricing estimate based on quiz answers only
        # Images can be uploaded later if needed
        estimate = calculate_pricing_estimate(consultation["quiz_answers"], None)
        
        # Save estimate to consultation
        await db.consultations.update_one(
            {"_id": consultation["_id"]},
            {
                "$set": {
                    "pricing_estimate": estimate,
                    "status": "estimate_ready"
                }
            }
        )
        
        return {
            "message": "Good-Better-Best pricing estimate generated successfully",
            "consultation_id": str(consultation["_id"]),
            "estimate": estimate
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate estimate: {str(e)}"
        )

@router.post("/consultation/{session_id}/update-estimate-with-discount")
async def update_estimate_with_discount(
    session_id: str,
    db: AsyncIOMotorDatabase = Depends(database.get_db)
):
    """Update pricing estimate by applying discount from completed categories
    
    This endpoint takes the existing pricing estimate and subtracts the total discount
    from all three price tiers (good, better, best) based on completed categories.
    
    IMPORTANT: This API can only be called ONCE per session ID.
    """
    try:
        # Get consultation data
        consultation = await db.consultations.find_one({"session_id": session_id})
        if not consultation:
            raise HTTPException(status_code=404, detail="Consultation not found")
        
        # Check if estimate exists
        if not consultation.get("pricing_estimate"):
            raise HTTPException(status_code=400, detail="Pricing estimate not found. Please generate estimate first.")
        
        # Check if discount has already been applied (ONE-TIME ONLY)
        if consultation.get("original_pricing_estimate"):
            raise HTTPException(
                status_code=400, 
                detail="Discount has already been applied to this estimate. This API can only be called once per session."
            )
        
        # Get current discount
        total_discount = consultation.get("total_discount", 0)
        completed_categories = consultation.get("completed_categories", [])
        
        if total_discount == 0:
            return {
                "message": "No discount to apply",
                "consultation_id": str(consultation["_id"]),
                "original_estimate": consultation["pricing_estimate"],
                "discounted_estimate": consultation["pricing_estimate"],
                "total_discount": total_discount,
                "completed_categories": completed_categories
            }
        
        # Get original estimate
        original_estimate = consultation["pricing_estimate"]
        
        # Create discounted estimate by subtracting discount from all tiers
        discounted_estimate = {
            "estimates": {
                "good": {
                    "label": original_estimate["estimates"]["good"]["label"],
                    "minPrice": max(0, original_estimate["estimates"]["good"]["minPrice"] - total_discount),
                    "maxPrice": max(0, original_estimate["estimates"]["good"]["maxPrice"] - total_discount)
                },
                "better": {
                    "label": original_estimate["estimates"]["better"]["label"],
                    "minPrice": max(0, original_estimate["estimates"]["better"]["minPrice"] - total_discount),
                    "maxPrice": max(0, original_estimate["estimates"]["better"]["maxPrice"] - total_discount)
                },
                "best": {
                    "label": original_estimate["estimates"]["best"]["label"],
                    "minPrice": max(0, original_estimate["estimates"]["best"]["minPrice"] - total_discount),
                    "maxPrice": max(0, original_estimate["estimates"]["best"]["maxPrice"] - total_discount)
                }
            },
            "tonnage": original_estimate.get("tonnage", 3.5),
            "systemCount": original_estimate.get("systemCount", 1),
            "discount_applied": total_discount,
            "completed_categories": completed_categories
        }
        
        # Update consultation with discounted estimate
        await db.consultations.update_one(
            {"_id": consultation["_id"]},
            {
                "$set": {
                    "pricing_estimate": discounted_estimate,
                    "original_pricing_estimate": original_estimate  # Store original for reference
                }
            }
        )
        
        return {
            "message": "Pricing estimate updated with discount successfully (ONE-TIME ONLY)",
            "consultation_id": str(consultation["_id"]),
            "discounted_estimate": discounted_estimate,
            "total_discount": total_discount,
            "completed_categories": completed_categories
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update estimate with discount: {str(e)}"
        )
